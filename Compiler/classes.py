from llvmlite import ir

from diagnostics import suggest
from language import describe_type, FLOAT_TYPES, INTEGER_BITS
from parser import LiteralNode, VariableAccessNode
from values import ClassInstanceValue

OPERATOR_SYMBOLS = {
    "+": "op_add", "-": "op_sub", "*": "op_mul", "/": "op_div", "%": "op_mod", "==": "op_eq", "!=": "op_ne",
    "<": "op_lt", "<=": "op_le", ">": "op_gt", ">=": "op_ge",
}
NULLABLE_PREFIXES = ("class:", "interface:", "list:", "map:", "set:", "fn[")


# classes are heap objs w/ a vtable ptr, structs are plain values.
# interfaces are fat ptrs: {obj, itable of slot idxs}
class ClassSystem:
    def is_reference_class(self, name):
        defn = self.class_definitions.get(name)
        if defn is not None:
            return not defn["is_struct"]
        node = self.pending_classes.get(name)
        return node is None or not node.is_struct

    def class_object_type(self, name):
        return self.module.context.get_identified_type(f"vamp.{name}")

    def is_nullable(self, type_name):
        if type_name in ("str", "json", "builder"):
            return True
        if type_name.startswith("class:"):
            return self.is_reference_class(type_name[6:])
        return type_name.startswith(NULLABLE_PREFIXES[1:])

    # T? for nullable T (classes, str, lists...) is just T w/ null, anything else is {i1 has, T}
    def optional_llvm_type(self, inner):
        if self.is_nullable(inner):
            return self.llvm_type_for(inner)
        return ir.LiteralStructType([self.bool_type, self.llvm_type_for(inner)])

    def throw_now(self, message):
        self.builder.call(self.runtime_function("vamp_throw", ir.VoidType(), [self.char_pointer_type]),
                          [self.string_constant(message)])
        self.builder.unreachable()

    def check_not_none(self, pointer, message):
        fn = self.builder.function
        bad = fn.append_basic_block(name="none_reference")
        good = fn.append_basic_block(name="reference_ok")
        self.builder.cbranch(self.builder.icmp_unsigned("==", pointer, ir.Constant(pointer.type, None)), bad, good)
        self.builder.position_at_end(bad)
        self.throw_now(message)
        self.builder.position_at_end(good)

    def register_interface_type(self, node):
        if node.interface_name in self.interface_definitions or node.interface_name in self.pending_classes:
            raise SyntaxError(f"'{node.interface_name}' is already declared")
        self.interface_definitions[node.interface_name] = {"node": node, "methods": None}

    def interface_methods(self, name):
        defn = self.interface_definitions[name]
        if defn["methods"] is None:
            meths = []
            seen = set()
            for meth_name, params, ret_ty in defn["node"].methods:
                signature = tuple(self.resolve_type(type_name) for _, type_name in params)
                if (meth_name, signature) in seen:
                    raise SyntaxError(f"Interface '{name}' lists '{meth_name}' twice with the same parameters")
                seen.add((meth_name, signature))
                meths.append({"name": meth_name, "signature": signature,
                                "parameters": [(item, self.resolve_type(kind)) for item, kind in params],
                                "return_type": self.resolve_type(ret_ty), "defaults": {}})
            defn["methods"] = meths
        return defn["methods"]

    def register_class_tree(self, node, parent_name=None):
        qualified_name = f"{parent_name}.{node.class_name}" if parent_name else node.class_name
        if qualified_name in self.class_definitions:
            raise SyntaxError(f"Class '{qualified_name}' is already declared")
        is_struct = getattr(node, "is_struct", False)
        parents = getattr(node, "parents", None) or ([node.parent] if node.parent else [])
        base_name = None
        interfaces = []
        for pos, parent in enumerate(parents):
            if parent in self.interface_definitions:
                interfaces.append(parent)
                continue
            if pos > 0:
                raise TypeError(
                    f"Class '{qualified_name}' can build on one class, then interfaces; '{parent}' is not an interface")
            base_name = parent
        fields = {}
        field_order = []
        llvm_fields = [] if is_struct else [self.char_pointer_type]
        if base_name is not None:
            self.ensure_class_registered(base_name)
            base = self.class_definitions.get(base_name)
            if base is None:
                close = suggest(base_name, list(self.class_definitions) + list(self.pending_classes)
                                + list(self.interface_definitions))
                msg = f"Class '{qualified_name}' inherits from '{base_name}', which is not declared"
                if close:
                    msg += f" (did you mean '{close}'?)"
                raise NameError(msg)
            if base["is_struct"]:
                raise TypeError(f"Class '{qualified_name}' cannot inherit from struct '{base_name}'")
            fields = dict(base["fields"])
            field_order = list(base["field_order"])
            llvm_fields = list(base["field_types"])
            interfaces = [item for item in base["interfaces"] if item not in interfaces] + interfaces
        defn = {
            "fields": fields, "field_order": field_order, "field_types": llvm_fields,
            "nested_classes": {nested.class_name: f"{qualified_name}.{nested.class_name}"
                               for nested in node.nested_classes},
            "methods": node.methods, "parent": base_name, "interfaces": interfaces, "is_struct": is_struct,
            "vtable": None, "slots": {}, "entries": [], "node": node,
        }
        if not is_struct:
            defn["llvm_type"] = self.class_object_type(qualified_name)
            self.class_definitions[qualified_name] = defn
        for field_name, field_ty, is_constant in node.fields:
            if field_name in fields:
                raise SyntaxError(f"Duplicate field '{field_name}' in class '{qualified_name}'")
            field_ty = self.resolve_type(field_ty)
            fields[field_name] = (len(llvm_fields), field_ty, is_constant)
            field_order.append(field_name)
            llvm_fields.append(self.llvm_type_for(field_ty))
        if is_struct:
            defn["llvm_type"] = ir.LiteralStructType(llvm_fields)
            self.class_definitions[qualified_name] = defn
        else:
            defn["llvm_type"].set_body(*llvm_fields)
        for nested_class in node.nested_classes:
            self.register_class_tree(nested_class, qualified_name)

    def method_symbol(self, qualified_name, method_name, count):
        base = OPERATOR_SYMBOLS.get(method_name, method_name)
        symbol = f"{qualified_name.replace('.', '__')}__{base}"
        return symbol if not count else f"{symbol}${count}"

    def declare_class_methods(self, node, parent_name=None):
        qualified_name = f"{parent_name}.{node.class_name}" if parent_name else node.class_name
        defn = self.class_definitions[qualified_name]
        self_type = (self.llvm_type_for(f"class:{qualified_name}") if not defn["is_struct"]
                     else defn["llvm_type"].as_pointer())
        for meth in node.methods:
            versions = self.class_methods.setdefault((qualified_name, meth.function_name), [])
            params = [(name, self.resolve_type(ty_name)) for name, ty_name in meth.parameters]
            signature = tuple(ty_name for _, ty_name in params)
            if any(item["signature"] == signature for item in versions):
                raise SyntaxError(
                    f"Method '{meth.function_name}' is already declared on '{qualified_name}' "
                    "with these parameter types")
            ret_ty = self.resolve_type(meth.return_type)
            if meth.function_name in OPERATOR_SYMBOLS:
                expected = 0 if meth.function_name == "-" and not params else 1
                if len(params) not in ((0, 1) if meth.function_name == "-" else (1,)):
                    raise SyntaxError(f"Operator method '{meth.function_name}' takes {expected} parameter")
                if meth.function_name in ("==", "!=", "<", "<=", ">", ">=") and ret_ty != "bool":
                    raise TypeError(f"Operator method '{meth.function_name}' must return bool")
            fn = ir.Function(
                self.module,
                ir.FunctionType(self.llvm_type_for(ret_ty),
                                [self_type, *[self.llvm_type_for(ty_name) for _, ty_name in params]]),
                name=self.method_symbol(qualified_name, meth.function_name, len(versions)))
            fn.linkage = "internal"
            info = {
                "function": fn, "return_type": ret_ty, "parameters": params,
                "signature": signature, "declaration": meth, "defaults": getattr(meth, "defaults", {}),
                "owner": qualified_name, "name": meth.function_name, "overridden": False,
            }
            versions.append(info)
            meth.information = info
        for nested_class in node.nested_classes:
            self.declare_class_methods(nested_class, qualified_name)

    def class_depth(self, name):
        depth = 0
        while self.class_definitions[name]["parent"] is not None:
            name = self.class_definitions[name]["parent"]
            depth += 1
        return depth

    # only overridden methods go through the vtable, everything else stays a direct call
    def build_vtables(self, names=None):
        names = names if names is not None else list(self.class_definitions)
        for name in sorted(names, key=self.class_depth):
            defn = self.class_definitions[name]
            if defn["is_struct"] or defn["vtable"] is not None:
                continue
            parent = defn["parent"]
            if parent is not None:
                self.build_vtables([parent])
                slots = dict(self.class_definitions[parent]["slots"])
                entries = list(self.class_definitions[parent]["entries"])
            else:
                slots, entries = {}, []
            for (owner, _), versions in self.class_methods.items():
                if owner != name:
                    continue
                for info in versions:
                    key = (info["name"], info["signature"])
                    if key in slots:
                        replaced = entries[slots[key]]
                        if replaced["return_type"] != info["return_type"]:
                            raise TypeError(
                                f"Method '{info['name']}' in '{name}' must return "
                                f"{describe_type(replaced['return_type'])} like the one it replaces in "
                                f"'{replaced['owner']}'")
                        self.mark_overridden(replaced["owner"], key)
                        entries[slots[key]] = info
                    else:
                        slots[key] = len(entries)
                        entries.append(info)
            defn["slots"] = slots
            defn["entries"] = entries
            table = ir.ArrayType(self.char_pointer_type, max(len(entries), 1))
            vtable = ir.GlobalVariable(self.module, table, name=f"vamp_vtable.{name}")
            vtable.initializer = ir.Constant(table, [item["function"].bitcast(self.char_pointer_type)
                                                     for item in entries] or [ir.Constant(self.char_pointer_type, None)])
            vtable.global_constant = True
            vtable.linkage = "internal"
            defn["vtable"] = vtable
            for interface in defn["interfaces"]:
                for meth in self.interface_methods(interface):
                    found = slots.get((meth["name"], meth["signature"]))
                    if found is None or entries[found]["return_type"] != meth["return_type"]:
                        shown = ", ".join(describe_type(item) for item in meth["signature"])
                        res = "" if meth["return_type"] == "void" else f" : {describe_type(meth['return_type'])}"
                        raise TypeError(
                            f"Class '{name}' says it is a '{interface}' but has no method "
                            f"{meth['name']}({shown}){res}")

    def mark_overridden(self, owner, key):
        while owner is not None:
            for info in self.class_methods.get((owner, key[0]), []):
                if info["signature"] == key[1]:
                    info["overridden"] = True
            owner = self.class_definitions[owner]["parent"]

    def emit_class_methods(self, node, parent_name=None):
        qualified_name = f"{parent_name}.{node.class_name}" if parent_name else node.class_name
        defn = self.class_definitions[qualified_name]
        for meth in node.methods:
            info = meth.information
            if id(info) in self.emitted_class_methods:
                continue
            self.emitted_class_methods.add(id(info))
            fn = info["function"]
            self.debug_last_node = meth
            saved = self.enter_function(fn, info["return_type"], qualified_name)
            if defn["is_struct"]:
                self.bind_variable("self", fn.args[0], f"class:{qualified_name}")
            else:
                slot = self.entry_alloca(fn.args[0].type, "self")
                self.builder.store(fn.args[0], slot)
                self.bind_variable("self", slot, f"class:{qualified_name}", is_constant=True)
            for idx, (parameter_name, parameter_type) in enumerate(info["parameters"], start=1):
                ptr = self.entry_alloca(self.llvm_type_for(parameter_type), parameter_name)
                self.builder.store(fn.args[idx], ptr)
                self.bind_variable(parameter_name, ptr, parameter_type)
            self.visit_block(meth.body)
            self.leave_function(saved, f"Method '{qualified_name}.{meth.function_name}'")
        for nested_class in node.nested_classes:
            self.emit_class_methods(nested_class, qualified_name)

    def visit_ClassDeclarationNode(self, node):
        if node.class_name not in self.class_definitions:
            self.register_class_tree(node)
            self.declare_class_methods(node)
            self.build_vtables()
        if node not in self.top_level_classes:
            self.emit_class_methods(node)

    def visit_InterfaceDeclarationNode(self, node):
        if node.interface_name not in self.interface_definitions:
            self.register_interface_type(node)

    def find_methods(self, class_name, method_name):
        found = []
        seen = set()
        while class_name is not None:
            for info in self.class_methods.get((class_name, method_name), []):
                if info["signature"] not in seen:
                    seen.add(info["signature"])
                    found.append(info)
            class_name = self.class_definitions[class_name].get("parent")
        return found

    def method_names(self, class_name):
        names = []
        while class_name is not None:
            names.extend(method for owner, method in self.class_methods if owner == class_name)
            names.extend(self.class_definitions[class_name]["nested_classes"])
            class_name = self.class_definitions[class_name].get("parent")
        return names

    def choose_overload(self, overloads, argument_nodes, shown):
        if len(overloads) == 1:
            return overloads[0], None
        cnt = len(argument_nodes)
        candidates = [item for item in overloads
                      if len(item["parameters"]) - len(item["defaults"]) <= cnt <= len(item["parameters"])]
        if not candidates:
            raise TypeError(f"No version of {shown} takes {cnt} argument{'s' if cnt != 1 else ''}")
        prepared = self.prepare_arguments(argument_nodes)
        scored = []
        for candidate in candidates:
            fits = [self.argument_fits(item, candidate["signature"][pos]) for pos, item in enumerate(prepared)]
            if all(fits):
                scored.append((sum(fits), candidate))
        shown_arguments = ", ".join(describe_type(item[2]) for item in prepared)
        if not scored:
            options = "\n".join(
                f"    ({', '.join(describe_type(item) for item in candidate['signature'])})" for candidate in overloads)
            raise TypeError(f"No version of {shown} accepts ({shown_arguments})\n  versions:\n{options}")
        best = max(score for score, _ in scored)
        winners = [candidate for score, candidate in scored if score == best]
        if len(winners) > 1:
            raise TypeError(f"The call {shown}({shown_arguments}) matches more than one version")
        return winners[0], prepared

    def object_size(self, llvm_type):
        end = self.builder.gep(ir.Constant(llvm_type.as_pointer(), None), [ir.Constant(self.int32_type, 1)])
        return self.builder.ptrtoint(end, self.int64_type)

    def create_class_instance(self, class_name, arguments, instance_name=None, prepared=None):
        defn = self.class_definitions.get(class_name)
        if defn is None:
            raise NameError(f"Class '{class_name}' is not declared")
        field_order = defn["field_order"]
        if len(arguments) != len(field_order):
            raise TypeError(f"Class '{class_name}' expects {len(field_order)} values, got {len(arguments)}")
        vals = []
        for pos, (field_name, arg) in enumerate(zip(field_order, arguments)):
            field_index, want_ty, _ = defn["fields"][field_name]
            if prepared is not None:
                value, val_ty = self.finish_argument(prepared[pos], want_ty)
            else:
                value, val_ty = self.visit_as(arg, want_ty)
            if val_ty != want_ty:
                raise TypeError(
                    f"Field '{field_name}' in class '{class_name}' expects "
                    f"{describe_type(want_ty)}, got {describe_type(val_ty)}")
            vals.append((field_index, field_name, self.as_value(value)))
        if defn["is_struct"]:
            ptr = self.entry_alloca(defn["llvm_type"], instance_name or f"{class_name.lower()}_value")
        else:
            if defn["vtable"] is None:
                self.build_vtables([class_name])
            raw = self.allocate_bytes(self.object_size(defn["llvm_type"]), name=f"{class_name.lower()}_object")
            ptr = self.builder.bitcast(raw, defn["llvm_type"].as_pointer())
            self.builder.store(defn["vtable"].bitcast(self.char_pointer_type), self.builder.gep(
                ptr, [ir.Constant(self.int32_type, 0), ir.Constant(self.int32_type, 0)]))
        for field_index, field_name, value in vals:
            self.builder.store(value, self.builder.gep(
                ptr, [ir.Constant(self.int32_type, 0), ir.Constant(self.int32_type, field_index)],
                name=f"{field_name}_pointer"))
        return ClassInstanceValue(ptr, temporary=True, reference=not defn["is_struct"]), f"class:{class_name}"

    def class_field_pointer(self, instance_pointer, class_name, field_name):
        defn = self.class_definitions[class_name]
        field = defn["fields"].get(field_name)
        if field is None:
            close = suggest(field_name, defn["fields"])
            msg = f"Class '{class_name}' has no field '{field_name}'"
            if close:
                msg += f" (did you mean '{close}'?)"
            raise NameError(msg)
        field_index, field_ty, is_constant = field
        if instance_pointer.type.pointee != defn["llvm_type"]:
            instance_pointer = self.builder.bitcast(instance_pointer, defn["llvm_type"].as_pointer())
        if not defn["is_struct"]:
            self.check_not_none(instance_pointer, f"read the field '{field_name}' of none")
        ptr = self.builder.gep(
            instance_pointer, [ir.Constant(self.int32_type, 0), ir.Constant(self.int32_type, field_index)],
            name=f"{field_name}_pointer")
        return ptr, field_ty, is_constant

    def call_class_method(self, receiver_pointer, class_name, node, shown_receiver, static=False):
        defn = self.class_definitions[class_name]
        nested_class_name = defn["nested_classes"].get(node.method_name)
        if nested_class_name is not None:
            return self.create_class_instance(nested_class_name, node.arguments)
        candidates = self.find_methods(class_name, node.method_name)
        if not candidates:
            close = suggest(node.method_name, self.method_names(class_name))
            msg = f"Class '{class_name}' has no method or nested class '{node.method_name}'"
            if close:
                msg += f" (did you mean '{close}'?)"
            raise NameError(msg)
        chosen, prepared = self.choose_overload(candidates, node.arguments, f"{class_name}.{node.method_name}")
        vals = self.bind_call_arguments(
            f"{class_name}.{node.method_name}", "Method", chosen["parameters"], chosen["defaults"],
            node.arguments, prepared)
        return self.invoke_method(receiver_pointer, class_name, chosen, vals, static)

    def invoke_method(self, receiver_pointer, class_name, information, values, static=False):
        fn = information["function"]
        self_type = fn.function_type.args[0]
        receiver = receiver_pointer if receiver_pointer.type == self_type else self.builder.bitcast(
            receiver_pointer, self_type)
        defn = self.class_definitions[class_name]
        if not defn["is_struct"]:
            self.check_not_none(receiver, f"called {information['name']}() on none")
        target = fn
        if not defn["is_struct"] and not static and information["overridden"]:
            slot = defn["slots"][(information["name"], information["signature"])]
            target = self.virtual_target(receiver, slot, fn.function_type)
        ret_ty = information["return_type"]
        if ret_ty == "void":
            self.builder.call(target, [receiver, *values])
            return None, "void"
        res = self.builder.call(target, [receiver, *values], name=f"{OPERATOR_SYMBOLS.get(information['name'], information['name'])}_result")
        return self.wrap_value(res, ret_ty), ret_ty

    def virtual_target(self, object_pointer, slot, function_type):
        table_pointer = self.builder.bitcast(object_pointer, self.char_pointer_type.as_pointer().as_pointer())
        table = self.builder.load(table_pointer, name="vtable")
        entry = self.builder.load(self.builder.gep(table, [ir.Constant(self.int32_type, slot)]), name="method")
        return self.builder.bitcast(entry, function_type.as_pointer())

    def call_method_with_values(self, value, value_type, method_name, arguments):
        cls_name = value_type[6:]
        argument_types = tuple(item[1] for item in arguments)
        for info in self.find_methods(cls_name, method_name):
            if info["signature"] == argument_types:
                return self.invoke_method(value.pointer, cls_name, info,
                                          [self.as_value(item[0]) for item in arguments])
        return None

    def has_method(self, class_name, method_name, signature=None):
        return any(signature is None or item["signature"] == signature
                   for item in self.find_methods(class_name, method_name))

    def implements(self, class_name, interface_name):
        defn = self.class_definitions.get(class_name)
        return defn is not None and interface_name in defn["interfaces"]

    def interface_table(self, class_name, interface_name):
        key = (class_name, interface_name)
        table = self.interface_tables.get(key)
        if table is None:
            defn = self.class_definitions[class_name]
            if defn["vtable"] is None:
                self.build_vtables([class_name])
            slots = [defn["slots"][(meth["name"], meth["signature"])]
                     for meth in self.interface_methods(interface_name)]
            table_type = ir.ArrayType(self.int32_type, len(slots))
            table = ir.GlobalVariable(self.module, table_type,
                                      name=f"vamp_itable.{class_name}.{interface_name}")
            table.initializer = ir.Constant(table_type, slots)
            table.global_constant = True
            table.linkage = "internal"
            self.interface_tables[key] = table
        return table.bitcast(self.int32_type.as_pointer())

    def interface_llvm_type(self):
        return ir.LiteralStructType([self.char_pointer_type, self.int32_type.as_pointer()])

    def to_interface(self, value, class_name, interface_name):
        ptr = self.as_value(value)
        aggregate = ir.Constant(self.interface_llvm_type(), ir.Undefined)
        aggregate = self.builder.insert_value(aggregate, self.builder.bitcast(ptr, self.char_pointer_type), 0)
        return self.builder.insert_value(aggregate, self.interface_table(class_name, interface_name), 1)

    def call_interface_method(self, value, interface_name, node):
        meths = [item for item in self.interface_methods(interface_name) if item["name"] == node.method_name]
        if not meths:
            close = suggest(node.method_name, [item["name"] for item in self.interface_methods(interface_name)])
            msg = f"Interface '{interface_name}' has no method '{node.method_name}'"
            if close:
                msg += f" (did you mean '{close}'?)"
            raise NameError(msg)
        chosen, prepared = self.choose_overload(meths, node.arguments, f"{interface_name}.{node.method_name}")
        vals = self.bind_call_arguments(f"{interface_name}.{node.method_name}", "Method", chosen["parameters"],
                                          {}, node.arguments, prepared)
        return self.call_interface_values(value, interface_name, chosen, vals)

    def call_interface_values(self, value, interface_name, method, values):
        aggregate = self.as_value(value)
        object_pointer = self.builder.extract_value(aggregate, 0)
        table = self.builder.extract_value(aggregate, 1)
        self.check_not_none(object_pointer, f"called {method['name']}() on none")
        pos = self.interface_methods(interface_name).index(method)
        slot = self.builder.load(self.builder.gep(table, [ir.Constant(self.int32_type, pos)]))
        vtable = self.builder.load(self.builder.bitcast(object_pointer, self.char_pointer_type.as_pointer().as_pointer()))
        entry = self.builder.load(self.builder.gep(vtable, [slot]))
        function_type = ir.FunctionType(
            self.llvm_type_for(method["return_type"]),
            [self.char_pointer_type, *[self.llvm_type_for(item) for item in method["signature"]]])
        target = self.builder.bitcast(entry, function_type.as_pointer())
        if method["return_type"] == "void":
            self.builder.call(target, [object_pointer, *values])
            return None, "void"
        res = self.builder.call(target, [object_pointer, *values])
        return self.wrap_value(res, method["return_type"]), method["return_type"]

    def none_value(self, inner):
        if self.is_nullable(inner):
            return ir.Constant(self.llvm_type_for(inner), None)
        return ir.Constant(self.optional_llvm_type(inner), None)

    def convert_value(self, value, value_type, target_type):
        if value_type == target_type or target_type is None:
            return None
        if target_type.startswith("optional:"):
            inner = target_type[9:]
            if value_type == "none":
                return self.none_value(inner), target_type
            converted = (value, value_type) if value_type == inner else self.convert_value(value, value_type, inner)
            if converted is None:
                return None
            value, _ = converted
            if self.is_nullable(inner):
                return self.as_value(value), target_type
            aggregate = ir.Constant(self.optional_llvm_type(inner), ir.Undefined)
            aggregate = self.builder.insert_value(aggregate, ir.Constant(self.bool_type, 1), 0)
            return self.builder.insert_value(aggregate, self.as_value(value), 1), target_type
        if target_type.startswith("interface:") and value_type.startswith("class:"):
            cls_name, interface_name = value_type[6:], target_type[10:]
            if self.implements(cls_name, interface_name):
                return self.to_interface(value, cls_name, interface_name), target_type
        if target_type.startswith("class:") and value_type.startswith("class:"):
            child, parent = value_type[6:], target_type[6:]
            if self.is_reference_class(child) and self.is_ancestor(parent, child):
                return ClassInstanceValue(self.builder.bitcast(
                    self.as_value(value), self.llvm_type_for(target_type)), reference=True), target_type
        return None

    def is_ancestor(self, ancestor, name):
        while name is not None:
            if name == ancestor:
                return True
            name = self.class_definitions[name]["parent"] if name in self.class_definitions else None
        return False

    def can_convert(self, value_type, target_type):
        if target_type.startswith("optional:"):
            inner = target_type[9:]
            return value_type in ("none", inner) or self.can_convert(value_type, inner)
        if target_type.startswith("interface:") and value_type.startswith("class:"):
            return self.implements(value_type[6:], target_type[10:])
        if target_type.startswith("class:") and value_type.startswith("class:"):
            return self.is_reference_class(value_type[6:]) and value_type != target_type \
                and self.is_ancestor(target_type[6:], value_type[6:])
        return False

    def optional_has_value(self, value, optional_type):
        inner = optional_type[9:]
        raw = self.as_value(value)
        if self.is_nullable(inner):
            ptr = self.builder.extract_value(raw, 0) if inner.startswith("interface:") else raw
            return self.builder.icmp_unsigned("!=", ptr, ir.Constant(ptr.type, None))
        return self.builder.extract_value(raw, 0)

    def optional_payload(self, value, optional_type):
        inner = optional_type[9:]
        raw = self.as_value(value)
        if self.is_nullable(inner):
            return self.wrap_value(raw, inner), inner
        return self.wrap_value(self.builder.extract_value(raw, 1), inner), inner

    def unwrap_optional(self, value, optional_type, message="used value() on none"):
        fn = self.builder.function
        bad = fn.append_basic_block(name="optional_none")
        good = fn.append_basic_block(name="optional_value")
        self.builder.cbranch(self.optional_has_value(value, optional_type), good, bad)
        self.builder.position_at_end(bad)
        self.throw_now(message)
        self.builder.position_at_end(good)
        return self.optional_payload(value, optional_type)

    def emit_optional_method(self, value, optional_type, node):
        inner = optional_type[9:]
        meth = node.method_name
        if meth == "has_value":
            self.check_arguments("has_value", node.arguments, ())
            return self.optional_has_value(value, optional_type), "bool"
        if meth == "value":
            self.check_arguments("value", node.arguments, ())
            return self.unwrap_optional(value, optional_type)
        if meth == "value_or":
            if len(node.arguments) != 1:
                raise TypeError("value_or expects one value to use when this is none")
            fallback, fallback_type = self.visit_as(node.arguments[0], inner)
            if fallback_type != inner:
                raise TypeError(f"value_or needs a {describe_type(inner)}, got {describe_type(fallback_type)}")
            fn = self.builder.function
            some_block = fn.append_basic_block(name="value_or_some")
            end_block = fn.append_basic_block(name="value_or_end")
            start = self.builder.block
            fallback_raw = self.as_value(fallback)
            self.builder.cbranch(self.optional_has_value(value, optional_type), some_block, end_block)
            self.builder.position_at_end(some_block)
            payload = self.as_value(self.optional_payload(value, optional_type)[0])
            some_end = self.builder.block
            self.builder.branch(end_block)
            self.builder.position_at_end(end_block)
            phi = self.builder.phi(fallback_raw.type)
            phi.add_incoming(fallback_raw, start)
            phi.add_incoming(payload, some_end)
            return self.wrap_value(phi, inner), inner
        if self.is_nullable(inner):
            unwrapped, unwrapped_type = self.unwrap_optional(value, optional_type, f"called {meth}() on none")
            return self.call_on_value(unwrapped, unwrapped_type, node)
        raise NameError(f"{describe_type(optional_type)} values have has_value(), value() and value_or(); "
                        f"use value() first to call {meth}()")

    def compare_with_none(self, operator, value, value_type):
        if operator not in ("==", "!="):
            raise TypeError("none can only be compared with == and !=")
        if value_type.startswith("optional:"):
            has = self.optional_has_value(value, value_type)
        elif self.is_nullable(value_type):
            raw = self.as_value(value)
            ptr = self.builder.extract_value(raw, 0) if value_type.startswith("interface:") else raw
            has = self.builder.icmp_unsigned("!=", ptr, ir.Constant(ptr.type, None))
        else:
            raise TypeError(f"A {describe_type(value_type)} is never none; only optional types (T?) can be none")
        return (self.builder.not_(has) if operator == "==" else has), "bool"

    def object_text(self, value, value_type):
        if value_type.startswith("optional:"):
            fn = self.builder.function
            some_block = fn.append_basic_block(name="text_some")
            end_block = fn.append_basic_block(name="text_end")
            start = self.builder.block
            none_text = self.string_constant("none")
            self.builder.cbranch(self.optional_has_value(value, value_type), some_block, end_block)
            self.builder.position_at_end(some_block)
            payload, inner = self.optional_payload(value, value_type)
            text = self.cast_value(payload, inner, "str")[0]
            some_end = self.builder.block
            self.builder.branch(end_block)
            self.builder.position_at_end(end_block)
            phi = self.builder.phi(self.char_pointer_type)
            phi.add_incoming(none_text, start)
            phi.add_incoming(text, some_end)
            return phi
        if value_type.startswith("interface:"):
            interface_name = value_type[10:]
            for meth in self.interface_methods(interface_name):
                if meth["name"] == "to_str" and not meth["signature"] and meth["return_type"] == "str":
                    return self.call_interface_values(value, interface_name, meth, [])[0]
            return self.string_constant(f"<{interface_name}>")
        cls_name = value_type[6:]
        for info in self.find_methods(cls_name, "to_str"):
            if not info["signature"] and info["return_type"] == "str":
                return self.invoke_method(value.pointer, cls_name, info, [])[0]
        defn = self.class_definitions[cls_name]
        if not defn["is_struct"]:
            self.check_not_none(value.pointer, "printed none")
        parts = [self.string_constant(cls_name.split(".")[-1] + "(")]
        for pos, field_name in enumerate(defn["field_order"]):
            ptr, field_ty, _ = self.class_field_pointer(value.pointer, cls_name, field_name)
            field_value = self.load_typed(ptr, field_ty)[0]
            if field_ty.startswith("class:") and self.is_reference_class(field_ty[6:]):
                shown = self.string_constant(f"<{field_ty[6:]}>")
            elif field_ty.startswith(("fn[", "interface:")) or field_ty == "json":
                shown = self.string_constant(f"<{describe_type(field_ty)}>")
            elif field_ty.startswith("optional:class:") and self.is_reference_class(field_ty[15:]):
                has = self.optional_has_value(field_value, field_ty)
                shown = self.builder.select(has, self.string_constant(f"<{field_ty[15:]}>"),
                                            self.string_constant("none"))
            else:
                shown = self.quoted_text(field_value, field_ty)
            if pos:
                parts.append(self.string_constant(", "))
            parts += [self.string_constant(f"{field_name} = "), shown]
        parts.append(self.string_constant(")"))
        return self.concat_strings(parts)

    def emit_iterator_loop(self, value, value_type, node):
        cls_name = value_type[6:]
        candidates = [item for item in self.find_methods(cls_name, "next") if not item["signature"]]
        if not candidates or not candidates[0]["return_type"].startswith("optional:"):
            raise TypeError(
                f"A for loop over a {cls_name} needs a method next() that returns T? (none when finished)")
        info = candidates[0]
        item_ty = info["return_type"][9:]
        fn = self.builder.function
        check_block = fn.append_basic_block(name="iterate_next")
        body_block = fn.append_basic_block(name="iterate_body")
        end_block = fn.append_basic_block(name="iterate_end")
        holder = self.entry_alloca(self.llvm_type_for(value_type), "iterator")
        self.builder.store(self.as_value(value), holder)
        self.builder.branch(check_block)
        self.builder.position_at_end(check_block)
        receiver = self.load_typed(holder, value_type)[0]
        produced, produced_type = self.invoke_method(receiver.pointer, cls_name, info, [])
        self.builder.cbranch(self.optional_has_value(produced, produced_type), body_block, end_block)
        self.builder.position_at_end(body_block)
        item, _ = self.optional_payload(produced, produced_type)
        saved = self.save_scope()
        self.block_depth += 1
        storage = self.entry_alloca(self.llvm_type_for(item_ty), node.item_name)
        self.builder.store(self.as_value(item), storage)
        self.bind_variable(node.item_name, storage, item_ty)
        self.visit_loop_body(node.body, check_block, end_block)
        self.block_depth -= 1
        self.restore_scope(saved)
        if not self.builder.block.is_terminated:
            self.builder.branch(check_block)
        self.builder.position_at_end(end_block)

    def call_on_value(self, value, value_type, node):
        if isinstance(value, ClassInstanceValue) and value_type.startswith("class:"):
            return self.call_class_method(value.pointer, value_type[6:], node, "value")
        if value_type.startswith("interface:"):
            return self.call_interface_method(value, value_type[10:], node)
        if value_type.startswith("optional:"):
            return self.emit_optional_method(value, value_type, node)
        return None

    def visit_MethodCallNode(self, node):
        receiver = node.receiver
        if isinstance(receiver, VariableAccessNode):
            name = receiver.variable_name
            if name == "super" and "super" not in self.type_information:
                parent = self.class_definitions[self.current_class].get("parent") if self.current_class else None
                if parent is None:
                    raise TypeError("'super' can only be used in a method of a class that inherits from another")
                self_value = self.visit(VariableAccessNode("self"))[0]
                return self.call_class_method(self_value.pointer, parent, node, "super", static=True)
            if name not in self.type_information and name in self.enum_definitions:
                raise TypeError(f"Enum '{name}' has no methods; write {name}.Member to use a member")
        value, val_ty = self.visit(receiver)
        handled = self.call_on_value(value, val_ty, node)
        if handled is not None:
            return handled
        return self.visit_value_method(value, val_ty, node, receiver)

    def visit_BinaryOpNode(self, node):
        right = node.right
        if not (isinstance(right, LiteralNode) and right.literal_type in ("int", "float")):
            return super().visit_BinaryOpNode(node)
        lhs, lhs_ty = self.visit(node.left)
        target = lhs_ty
        if lhs_ty.startswith("class:"):
            parameter_types = [item["signature"][0] for item in self.find_methods(lhs_ty[6:], node.operator)
                               if len(item["signature"]) == 1]
            numbers = [item for item in parameter_types if item in INTEGER_BITS or item in FLOAT_TYPES]
            target = right.literal_type if right.literal_type in parameter_types else (numbers[0] if numbers else None)
        rhs, rhs_ty = self.visit_as(right, target) if target else self.visit(right)
        return self.apply_binary(node.operator, lhs, lhs_ty, rhs, rhs_ty)

    def operator_method(self, operator, left_value, left_type, right_value, right_type):
        if not left_type.startswith("class:") or not isinstance(left_value, ClassInstanceValue):
            return None
        cls_name = left_type[6:]
        res = self.call_method_with_values(left_value, left_type, operator, [(right_value, right_type)])
        if res is not None:
            return res
        if operator == "!=":
            equal = self.call_method_with_values(left_value, left_type, "==", [(right_value, right_type)])
            if equal is not None:
                return self.builder.not_(equal[0]), "bool"
        if operator in ("==", "!=") and self.is_reference_class(cls_name) and right_type.startswith("class:"):
            left = self.builder.ptrtoint(self.as_value(left_value), self.int64_type)
            right = self.builder.ptrtoint(self.as_value(right_value), self.int64_type)
            return self.builder.icmp_unsigned(operator, left, right), "bool"
        if self.has_method(cls_name, operator):
            raise TypeError(f"'{cls_name}' has no operator {operator} that takes {describe_type(right_type)}")
        raise TypeError(f"'{cls_name}' has no operator {operator}; add a method: func {operator}(other : ...) : ...")
