import os
import re

from llvmlite import ir

from language import FLOAT_TYPES, INTEGER_BITS, UNSIGNED_TYPES, describe_type, is_number_literal, split_type_list
from parser import (
    AssignmentNode, FunctionCallNode, LambdaNode, LibraryCallNode, LiteralNode, MapLiteralNode,
    SetLiteralNode, TupleNode, VariableAccessNode,
)

FORMAT_SPEC = re.compile(r"([<>^])?(\d+)?(?:\.(\d+))?")
INT64_MAX = 2 ** 63 - 1


def tuple_elements(type_name):
    return split_type_list(type_name[6:-1])


class LanguageFeatures:
    def string_constant(self, text):
        return self.visit_LiteralNode(LiteralNode("str", text))[0]

    def concat_strings(self, parts):
        if len(parts) == 1:
            return parts[0]
        array = self.entry_alloca(ir.ArrayType(self.char_pointer_type, len(parts)), "string_parts")
        for idx, part in enumerate(parts):
            self.builder.store(part, self.builder.gep(
                array, [ir.Constant(self.int32_type, 0), ir.Constant(self.int32_type, idx)]))
        fn = self.runtime_function(
            "vamp_str_concat_n", self.char_pointer_type, [self.int32_type, self.char_pointer_type.as_pointer()])
        first = self.builder.gep(array, [ir.Constant(self.int32_type, 0), ir.Constant(self.int32_type, 0)])
        return self.builder.call(fn, [ir.Constant(self.int32_type, len(parts)), first])

    def emit_counted_loop(self, count, body):
        fn = self.builder.function
        index_pointer = self.entry_alloca(self.int64_type, "loop_index")
        self.builder.store(ir.Constant(self.int64_type, 0), index_pointer)
        condition_block = fn.append_basic_block(name="loop_condition")
        body_block = fn.append_basic_block(name="loop_body")
        end_block = fn.append_basic_block(name="loop_end")
        self.builder.branch(condition_block)
        self.builder.position_at_end(condition_block)
        idx = self.builder.load(index_pointer)
        self.builder.cbranch(self.builder.icmp_signed("<", idx, count), body_block, end_block)
        self.builder.position_at_end(body_block)
        body(idx)
        self.builder.store(self.builder.add(self.builder.load(index_pointer), ir.Constant(self.int64_type, 1)),
                           index_pointer)
        self.builder.branch(condition_block)
        self.builder.position_at_end(end_block)

    def emit_map_entries(self, map_value, body):
        fn = self.builder.function
        cursor = self.entry_alloca(self.int32_type, "entry_cursor")
        self.builder.store(ir.Constant(self.int32_type, 0), cursor)
        condition_block = fn.append_basic_block(name="entries_condition")
        body_block = fn.append_basic_block(name="entries_body")
        end_block = fn.append_basic_block(name="entries_end")
        self.builder.branch(condition_block)
        self.builder.position_at_end(condition_block)
        found, _ = self.call_runtime("vamp_map_next", ("str", "i32"), "i32", [map_value, self.builder.load(cursor)])
        self.builder.store(found, cursor)
        self.builder.cbranch(self.builder.icmp_signed(">=", found, ir.Constant(self.int32_type, 0)),
                             body_block, end_block)
        self.builder.position_at_end(body_block)
        body(found)
        self.builder.store(self.builder.add(self.builder.load(cursor), ir.Constant(self.int32_type, 1)), cursor)
        self.builder.branch(condition_block)
        self.builder.position_at_end(end_block)

    def quoted_text(self, value, value_type):
        text = self.cast_value(value, value_type, "str")[0]
        if value_type == "str":
            return self.concat_strings([self.string_constant('"'), text, self.string_constant('"')])
        if value_type == "char":
            return self.concat_strings([self.string_constant("'"), text, self.string_constant("'")])
        return text

    def collection_text(self, value, value_type):
        if value_type.startswith("tuple["):
            parts = [self.string_constant("(")]
            for index, elem_ty in enumerate(tuple_elements(value_type)):
                if index:
                    parts.append(self.string_constant(", "))
                elem = self.wrap_value(self.builder.extract_value(self.as_value(value), index), elem_ty)
                parts.append(self.quoted_text(elem, elem_ty))
            parts.append(self.string_constant(")"))
            return self.concat_strings(parts)

        pieces = self.new_list("str", 4)
        push = self.runtime_function("vamp_list_push_slot", self.char_pointer_type, [self.char_pointer_type])

        def add(text):
            slot = self.builder.call(push, [pieces])
            self.builder.store(text, self.builder.bitcast(slot, self.char_pointer_type.as_pointer()))

        if value_type.startswith("list:"):
            elem_ty = value_type[5:]
            opening, closing = "[", "]"

            def each(index):
                elem = self.load_typed(self.builder.gep(self.list_data(value, elem_ty), [index]),
                                          elem_ty)[0]
                add(self.quoted_text(elem, elem_ty))

            self.emit_counted_loop(self.list_length(value), each)
        else:
            map_type = self.set_map_type(value_type) if value_type.startswith("set:") else value_type
            _, key_ty, elem_ty = map_type.split(":", 2)
            opening, closing = "{", "}"

            def each(entry):
                key = self.map_key_at(value, map_type, entry)
                text = self.quoted_text(key, key_ty)
                if value_type.startswith("map:"):
                    raw = self.call_runtime("vamp_map_value_at", ("str", "i32"), "str", [value, entry])[0]
                    stored = self.load_typed(
                        self.builder.bitcast(raw, self.llvm_type_for(elem_ty).as_pointer()), elem_ty)[0]
                    text = self.concat_strings([text, self.string_constant(": "),
                                                self.quoted_text(stored, elem_ty)])
                add(text)

            self.emit_map_entries(value, each)
        joined = self.call_runtime("vamp_str_join", ("str", "str"), "str", [pieces, self.string_constant(", ")])[0]
        return self.concat_strings([self.string_constant(opening), joined, self.string_constant(closing)])

    def is_collection_type(self, value_type):
        return value_type.startswith(("tuple[", "list:", "map:", "set:"))

    def visit_FormatStringNode(self, node):
        parts = []
        for part in node.parts:
            if isinstance(part, str):
                parts.append(self.string_constant(part))
                continue
            expr, spec = part
            value, val_ty = self.visit(expr)
            parts.append(self.format_value(value, val_ty, spec))
        if not parts:
            return self.string_constant(""), "str"
        return self.concat_strings(parts), "str"

    def format_value(self, value, value_type, spec):
        if value_type == "void":
            raise TypeError("An f-string cannot show the result of a call that returns nothing")
        match = FORMAT_SPEC.fullmatch(spec or "")
        if match is None:
            raise ValueError(
                f"Unknown f-string format '{spec}': use a width (8), an alignment (<, > or ^) "
                "and decimals (.2), for example {price:>8.2}")
        align, width, precision = match.groups()
        numeric = value_type in INTEGER_BITS or value_type in FLOAT_TYPES
        if precision is not None:
            if value_type not in FLOAT_TYPES:
                raise TypeError(f"Decimals (.{precision}) can only be used on float values, not {describe_type(value_type)}")
            double = self.cast_value(value, value_type, "float")[0]
            text = self.call_runtime("vamp_format_float", ("float", "i32"), "str",
                                     [double, ir.Constant(self.int32_type, int(precision))])[0]
        else:
            text = self.cast_value(value, value_type, "str")[0]
        if width is not None:
            alignment = {"<": 0, ">": 1, "^": 2}.get(align, 1 if numeric else 0)
            text = self.call_runtime("vamp_str_pad", ("str", "i32", "i32"), "str",
                                     [text, ir.Constant(self.int32_type, int(width)),
                                      ir.Constant(self.int32_type, alignment)])[0]
        return text

    def visit_ConditionalNode(self, node):
        cond = self.visit_condition(node.condition, "The 'if' inside an expression")
        fn = self.builder.function
        true_block = fn.append_basic_block(name="choose_true")
        false_block = fn.append_basic_block(name="choose_false")
        end_block = fn.append_basic_block(name="choose_end")
        self.builder.cbranch(cond, true_block, false_block)
        order = [(true_block, node.when_true), (false_block, node.when_false)]
        if is_number_literal(node.when_true) and not is_number_literal(node.when_false):
            order.reverse()
        res = []
        result_type = None
        for block, expr in order:
            self.builder.position_at_end(block)
            value, val_ty = (self.visit_as(expr, result_type) if result_type else self.visit(expr))
            if val_ty == "void":
                raise TypeError("Both sides of 'a if condition else b' must be values")
            if result_type is not None and val_ty != result_type:
                raise TypeError(
                    f"Both sides of 'a if condition else b' must have the same type, got "
                    f"{describe_type(result_type)} and {describe_type(val_ty)}")
            result_type = val_ty
            res.append((self.as_value(value), self.builder.block))
            self.builder.branch(end_block)
        self.builder.position_at_end(end_block)
        phi = self.builder.phi(res[0][0].type, name="chosen")
        for value, block in res:
            phi.add_incoming(value, block)
        return self.wrap_value(phi, result_type), result_type

    def visit_SliceNode(self, node):
        value, val_ty = self.visit(node.target)
        bounds = []
        for bound, default in ((node.start, 0), (node.end, INT64_MAX)):
            if bound is None:
                bounds.append(ir.Constant(self.int64_type, default))
                continue
            idx, index_type = self.visit_as(bound, "int")
            if index_type not in INTEGER_BITS:
                raise TypeError(f"Slice positions must be whole numbers, got {describe_type(index_type)}")
            bounds.append(self.cast_value(idx, index_type, "int")[0])
        if val_ty == "str":
            return self.call_runtime("vamp_str_slice", ("str", "c_i64", "c_i64"), "str", [value, *bounds])
        if val_ty.startswith("list:"):
            return self.call_runtime("vamp_list_slice", (val_ty, "c_i64", "c_i64"), val_ty, [value, *bounds])
        raise TypeError(f"Only lists and strings can be sliced, not {describe_type(val_ty)}")

    def build_tuple(self, node, tuple_type=None):
        element_types = tuple_elements(tuple_type) if tuple_type else [None] * len(node.elements)
        if len(element_types) != len(node.elements):
            raise TypeError(f"Expected a tuple of {len(element_types)} values, got {len(node.elements)}")
        vals = []
        for expr, wanted in zip(node.elements, element_types):
            value, val_ty = self.visit_as(expr, wanted) if wanted else self.visit(expr)
            if val_ty == "void":
                raise TypeError("A tuple cannot hold the result of a call that returns nothing")
            if wanted and val_ty != wanted:
                raise TypeError(f"Tuple element should be {describe_type(wanted)}, got {describe_type(val_ty)}")
            vals.append((self.as_value(value), val_ty))
        result_type = "tuple[" + ",".join(val_ty for _, val_ty in vals) + "]"
        aggregate = ir.Constant(self.llvm_type_for(result_type), ir.Undefined)
        for idx, (value, _) in enumerate(vals):
            aggregate = self.builder.insert_value(aggregate, value, idx)
        return aggregate, result_type

    def visit_TupleNode(self, node):
        return self.build_tuple(node)

    def tuple_element(self, value, value_type, index_node):
        if not (isinstance(index_node, LiteralNode) and index_node.literal_type == "int"):
            raise TypeError("A tuple element is read with a fixed number, for example pair[0]")
        element_types = tuple_elements(value_type)
        idx = index_node.value
        if not 0 <= idx < len(element_types):
            raise IndexError(f"This tuple has {len(element_types)} elements, so [{idx}] does not exist")
        elem = self.builder.extract_value(self.as_value(value), idx)
        return self.wrap_value(elem, element_types[idx]), element_types[idx]

    def declare_unpacked(self, node):
        initializer = node.initializers[0]
        names = node.variable_names
        expected = None
        if node.variable_type is not None:
            declared = self.resolve_type(node.variable_type)
            expected = "tuple[" + ",".join([declared] * len(names)) + "]"
        value, val_ty = self.visit_as(initializer, expected) if expected else self.visit(initializer)
        if not val_ty.startswith("tuple["):
            raise TypeError(
                f"{len(names)} names need {len(names)} values: give one value per name, "
                f"or a tuple of {len(names)} values (got {describe_type(val_ty)})")
        element_types = tuple_elements(val_ty)
        if len(element_types) != len(names):
            raise TypeError(f"Cannot unpack a tuple of {len(element_types)} values into {len(names)} names")
        if expected and val_ty != expected:
            raise TypeError(f"Cannot unpack {describe_type(val_ty)} into {describe_type(node.variable_type)} names")
        aggregate = self.as_value(value)
        for idx, (name, elem_ty) in enumerate(zip(names, element_types)):
            elem = self.wrap_value(self.builder.extract_value(aggregate, idx), elem_ty)
            self.declare_variable(name, elem, elem_ty, node.is_constant)

    def set_map_type(self, set_type):
        return f"map:{set_type[4:]}:bool"

    def build_set(self, elements, set_type=None):
        elem_ty = set_type[4:] if set_type else None
        vals = []
        for expr in elements:
            value, val_ty = self.visit_as(expr, elem_ty) if elem_ty else self.visit(expr)
            if elem_ty is None:
                elem_ty = val_ty
            if val_ty != elem_ty:
                raise TypeError(
                    f"Every value in a set must have the same type: {describe_type(elem_ty)} "
                    f"and {describe_type(val_ty)}")
            vals.append(value)
        if elem_ty is None:
            raise TypeError("An empty {} needs a set type, for example: val seen : set[str] = {}")
        if elem_ty not in ("str", "char") and elem_ty not in INTEGER_BITS:
            raise TypeError(f"Sets hold str, char or whole numbers, not {describe_type(elem_ty)}")
        set_type = f"set:{elem_ty}"
        map_type = self.set_map_type(set_type)
        res = self.new_map(map_type)
        for value in vals:
            slot = self.map_slot(res, value, elem_ty, "bool", create=True)
            self.builder.store(ir.Constant(self.bool_type, 1), slot)
        return res, set_type

    def visit_SetLiteralNode(self, node):
        return self.build_set(node.elements)

    SET_METHODS = ("add", "remove", "has", "contains", "length", "is_empty", "clear", "values", "copy",
                   "union", "intersection", "difference", "is_subset")

    def emit_set_method(self, set_value, set_type, node):
        elem_ty = set_type[4:]
        map_type = self.set_map_type(set_type)
        meth = node.method_name
        what = f"set.{meth}"
        if meth == "add":
            value, = self.check_arguments(what, node.arguments, (elem_ty,))
            slot = self.map_slot(set_value, value, elem_ty, "bool", create=True)
            self.builder.store(ir.Constant(self.bool_type, 1), slot)
            return None, "void"
        if meth in ("has", "contains", "remove", "length", "is_empty", "clear"):
            forwarded = type(node)(node.receiver, "has" if meth == "contains" else meth, node.arguments)
            return self.emit_map_method(set_value, map_type, forwarded)
        if meth == "values":
            self.check_arguments(what, node.arguments, ())
            return self.call_runtime("vamp_map_keys", (map_type, "i32"), f"list:{elem_ty}",
                                     [set_value, self.size_of(elem_ty)])
        if meth == "copy":
            self.check_arguments(what, node.arguments, ())
            return self.call_runtime("vamp_map_copy", (map_type,), set_type, [set_value])
        if meth in ("union", "intersection", "difference", "is_subset"):
            other, = self.check_arguments(what, node.arguments, (set_type,))
            ret_ty = "bool" if meth == "is_subset" else set_type
            return self.call_runtime(f"vamp_set_{meth}", (map_type, map_type), ret_ty, [set_value, other])
        from diagnostics import suggest
        close = suggest(meth, self.SET_METHODS)
        msg = f"Sets have no method '{meth}'"
        msg += f" (did you mean '{close}'?)" if close else f"; available: {', '.join(self.SET_METHODS)}"
        raise NameError(msg)

    def expected_literal(self, node, target_type):
        if isinstance(node, TupleNode) and target_type.startswith("tuple["):
            return self.build_tuple(node, target_type)
        if target_type.startswith("fn[") and isinstance(node, VariableAccessNode) \
                and node.variable_name not in self.type_information and node.variable_name in self.function_overloads:
            return self.named_function_value(node.variable_name, target_type)
        if target_type.startswith("set:"):
            if isinstance(node, SetLiteralNode):
                return self.build_set(node.elements, target_type)
            if isinstance(node, MapLiteralNode) and not node.entries:
                return self.build_set([], target_type)
        return None

    BUILDER_METHODS = ("add", "add_line", "text", "length", "clear")

    def emit_builder_method(self, value, node):
        meth = node.method_name
        if meth in ("add", "add_line"):
            if len(node.arguments) > 1 or (meth == "add" and not node.arguments):
                raise TypeError(f"builder.{meth} expects one value")
            if node.arguments:
                part, part_type = self.visit(node.arguments[0])
                if part_type == "void":
                    raise TypeError(f"builder.{meth} cannot add the result of a call that returns nothing")
                text = part if part_type == "str" else self.cast_value(part, part_type, "str")[0]
                self.call_runtime("vamp_builder_add", ("builder", "str"), "void", [value, text])
            if meth == "add_line":
                self.call_runtime("vamp_builder_add", ("builder", "str"), "void", [value, self.string_constant("\n")])
            return None, "void"
        if meth == "text":
            self.check_arguments("builder.text", node.arguments, ())
            return self.call_runtime("vamp_builder_text", ("builder",), "str", [value])
        if meth == "length":
            self.check_arguments("builder.length", node.arguments, ())
            return self.call_runtime("vamp_builder_length", ("builder",), "c_i64", [value])
        if meth == "clear":
            self.check_arguments("builder.clear", node.arguments, ())
            return self.call_runtime("vamp_builder_clear", ("builder",), "void", [value])
        from diagnostics import suggest
        close = suggest(meth, self.BUILDER_METHODS)
        raise NameError(f"A builder has no method '{meth}'" + (f" (did you mean '{close}'?)" if close else
                        f"; available: {', '.join(self.BUILDER_METHODS)}"))

    def emit_assert(self, node):
        if not 1 <= len(node.arguments) <= 2:
            raise TypeError('assert expects a condition, and optionally a message: assert(x > 0, "x must be positive")')
        cond = self.visit_condition(node.arguments[0], "assert")
        line = getattr(node, "line", 0)
        where = f"{os.path.basename(getattr(node, 'filename', None) or 'program')}:{line}"
        fn = self.builder.function
        failed = fn.append_basic_block(name="assert_failed")
        passed = fn.append_basic_block(name="assert_passed")
        self.builder.cbranch(cond, passed, failed)
        self.builder.position_at_end(failed)
        if len(node.arguments) == 2:
            msg, message_type = self.visit(node.arguments[1])
            if message_type != "str":
                raise TypeError("The message of assert must be a str")
            msg = self.concat_strings([self.string_constant(f"assertion failed at {where}: "), msg])
        else:
            msg = self.string_constant(f"assertion failed at {where}")
        self.builder.call(self.runtime_function("vamp_throw", ir.VoidType(), [self.char_pointer_type]), [msg])
        self.builder.unreachable()
        self.builder.position_at_end(passed)
        return None, "void"

    def visit_TestNode(self, node):
        return None, "void"

    def function_signature(self, fn_type):
        inner = fn_type[3:-1]
        depth = 0
        split_at = None
        for pos, ch in enumerate(inner):
            if ch == "[":
                depth += 1
            elif ch == "]":
                depth -= 1
            elif ch == ";" and depth == 0:
                split_at = pos
        parameters_text, ret_ty = inner[:split_at], inner[split_at + 1:]
        params = split_type_list(parameters_text) if parameters_text else []
        return params, ret_ty

    def make_function_type(self, parameters, return_type):
        return "fn[" + ",".join(parameters) + ";" + return_type + "]"

    # closures are {fn ptr, captures...}, called as fn(env, args...).
    # nothing captured -> static closure, no alloc
    def closure_function_type(self, fn_type):
        params, ret_ty = self.function_signature(fn_type)
        return ir.FunctionType(
            self.llvm_type_for(ret_ty),
            [self.char_pointer_type, *[self.llvm_type_for(item) for item in params]])

    def call_closure(self, closure, fn_type, values):
        fn = self.builder.function
        empty_block = fn.append_basic_block(name="empty_function_value")
        call_block = fn.append_basic_block(name="call_function_value")
        is_empty = self.builder.icmp_unsigned("==", closure, ir.Constant(self.char_pointer_type, None))
        self.builder.cbranch(is_empty, empty_block, call_block)
        self.builder.position_at_end(empty_block)
        self.builder.call(self.runtime_function("vamp_throw", ir.VoidType(), [self.char_pointer_type]),
                          [self.string_constant("called an empty function value")])
        self.builder.unreachable()
        self.builder.position_at_end(call_block)
        code = self.builder.load(self.builder.bitcast(closure, self.char_pointer_type.as_pointer()))
        target = self.builder.bitcast(code, self.closure_function_type(fn_type).as_pointer())
        _, ret_ty = self.function_signature(fn_type)
        if ret_ty == "void":
            self.builder.call(target, [closure, *values])
            return None, "void"
        res = self.builder.call(target, [closure, *values], name="function_value_result")
        return self.wrap_value(res, ret_ty), ret_ty

    def call_function_value(self, closure, fn_type, argument_nodes, shown):
        params, _ = self.function_signature(fn_type)
        vals = self.check_arguments(shown, argument_nodes, params)
        return self.call_closure(closure, fn_type, vals)

    def static_closure(self, code, name):
        constant = ir.Constant(ir.LiteralStructType([self.char_pointer_type]),
                               [code.bitcast(self.char_pointer_type)])
        var = ir.GlobalVariable(self.module, constant.type, name=name)
        var.initializer = constant
        var.global_constant = True
        var.linkage = "internal"
        return var.bitcast(self.char_pointer_type)

    def named_function_value(self, name, expected=None):
        overloads = self.function_overloads[name]
        if expected is not None:
            params, ret_ty = self.function_signature(expected)
            matches = [item for item in overloads
                       if list(item["signature"]) == params and item["return_type"] == ret_ty]
            if not matches:
                raise TypeError(f"No version of '{name}' has the type {describe_type(expected)}")
            chosen = matches[0]
        elif len(overloads) == 1:
            chosen = overloads[0]
        else:
            raise TypeError(
                f"'{name}' has several versions; give the variable a function type so the right one is chosen, "
                f"for example: val f : func(int) : int = {name}")
        fn_type = self.make_function_type(list(chosen["signature"]), chosen["return_type"])
        if "closure" not in chosen:
            thunk = ir.Function(self.module, self.closure_function_type(fn_type),
                                name=f"vamp_function_value.{chosen['function'].name}")
            thunk.linkage = "internal"
            builder = ir.IRBuilder(thunk.append_basic_block(name="entry"))
            res = builder.call(chosen["function"], list(thunk.args[1:]))
            if chosen["return_type"] == "void":
                builder.ret_void()
            else:
                builder.ret(res)
            chosen["closure"] = self.static_closure(thunk, f"vamp_function_closure.{chosen['function'].name}")
        return chosen["closure"], fn_type

    def visit_VariableAccessNode(self, node):
        name = node.variable_name
        if name not in self.type_information and name in self.function_overloads:
            return self.named_function_value(name)
        return super().visit_VariableAccessNode(node)

    def visit_FunctionCallNode(self, node):
        variable_type = self.type_information.get(node.function_name)
        if node.function_name == "assert" and variable_type is None and "assert" not in self.function_overloads:
            return self.emit_assert(node)
        if node.function_name == "builder" and variable_type is None and node.function_name not in \
                self.function_overloads and node.function_name not in self.class_definitions:
            if node.arguments:
                raise TypeError("builder() takes no values; add text with b.add(...)")
            return self.call_runtime("vamp_builder_new", (), "builder", [])
        if variable_type is not None and variable_type.startswith("fn["):
            closure = self.builder.load(self.variable_pointers[node.function_name])
            return self.call_function_value(closure, variable_type, node.arguments, node.function_name)
        if variable_type is not None and node.function_name not in self.function_overloads \
                and node.function_name not in self.class_definitions:
            raise TypeError(
                f"'{node.function_name}' is a value of type {describe_type(variable_type)}, which cannot be called")
        return super().visit_FunctionCallNode(node)

    def visit_CallValueNode(self, node):
        closure, fn_type = self.visit(node.callee)
        if not fn_type.startswith("fn["):
            raise TypeError(f"A value of type {describe_type(fn_type)} cannot be called")
        return self.call_function_value(closure, fn_type, node.arguments, "this function value")

    def used_names(self, value, names):
        if isinstance(value, VariableAccessNode):
            names.add(value.variable_name)
        if isinstance(value, AssignmentNode):
            names.add(value.variable_name)
        if isinstance(value, FunctionCallNode):
            names.add(value.function_name)
        if hasattr(value, "__dict__") and not isinstance(value, (str, bytes)):
            for child in vars(value).values():
                self.used_names(child, names)
        elif isinstance(value, (list, tuple)):
            for child in value:
                self.used_names(child, names)
        elif isinstance(value, dict):
            for child in value.values():
                self.used_names(child, names)
        return names

    # captures are copied in when the lambda is created (by value, matches the docs)
    def visit_LambdaNode(self, node):
        params = [(name, self.resolve_type(ty_name)) for name, ty_name in node.parameters]
        ret_ty = self.resolve_type(node.return_type)
        fn_type = self.make_function_type([ty_name for _, ty_name in params], ret_ty)
        own_names = {name for name, _ in params}
        captures = []
        for name in sorted(self.used_names(node.body, set()) - own_names):
            ptr = self.variable_pointers.get(name)
            variable_type = self.type_information.get(name)
            if ptr is None or variable_type is None or isinstance(ptr, (ir.GlobalVariable, ir.Function)):
                continue
            if variable_type in ("array", "dictionary"):
                raise TypeError(
                    f"A function value cannot capture the fixed array or dictionary '{name}'; use a list or map")
            captures.append((name, variable_type, ptr))

        self.lambda_count = getattr(self, "lambda_count", 0) + 1
        fn = ir.Function(self.module, self.closure_function_type(fn_type),
                               name=f"vamp_lambda.{self.lambda_count}")
        fn.linkage = "internal"
        environment_type = ir.LiteralStructType(
            [self.char_pointer_type, *[self.llvm_type_for(variable_type) for _, variable_type, _ in captures]])

        if captures:
            size = self.builder.ptrtoint(
                self.builder.gep(ir.Constant(environment_type.as_pointer(), None), [ir.Constant(self.int32_type, 1)]),
                self.int64_type)
            raw = self.allocate_bytes(size, name="closure")
            env = self.builder.bitcast(raw, environment_type.as_pointer())
            self.builder.store(fn.bitcast(self.char_pointer_type), self.builder.gep(
                env, [ir.Constant(self.int32_type, 0), ir.Constant(self.int32_type, 0)]))
            for idx, (name, variable_type, ptr) in enumerate(captures, start=1):
                value = self.load_typed(ptr, variable_type)[0]
                self.builder.store(self.as_value(value), self.builder.gep(
                    env, [ir.Constant(self.int32_type, 0), ir.Constant(self.int32_type, idx)]))
            closure = raw
        else:
            closure = self.static_closure(fn, f"vamp_lambda_closure.{self.lambda_count}")

        outer_pointers = self.variable_pointers
        outer_types = self.type_information
        saved = self.enter_function(fn, ret_ty, self.current_class)
        self.variable_pointers = {name: ptr for name, ptr in outer_pointers.items()
                                  if isinstance(ptr, (ir.GlobalVariable, ir.Function))}
        self.type_information = {name: outer_types[name] for name in self.variable_pointers if name in outer_types}
        if captures:
            env = self.builder.bitcast(fn.args[0], environment_type.as_pointer())
            for idx, (name, variable_type, _) in enumerate(captures, start=1):
                self.bind_variable(name, self.builder.gep(
                    env, [ir.Constant(self.int32_type, 0), ir.Constant(self.int32_type, idx)]),
                    variable_type)
        for idx, (name, ty_name) in enumerate(params, start=1):
            ptr = self.entry_alloca(self.llvm_type_for(ty_name), name)
            self.builder.store(fn.args[idx], ptr)
            self.bind_variable(name, ptr, ty_name)
        self.visit_block(node.body)
        self.leave_function(saved, "A function value")
        return closure, fn_type

    def function_value_argument(self, node, fn_type):
        if isinstance(node, VariableAccessNode) and node.variable_name not in self.type_information \
                and node.variable_name in self.function_overloads:
            return self.named_function_value(node.variable_name, fn_type)
        value, val_ty = self.visit(node)
        if val_ty != fn_type:
            raise TypeError(f"Expected a function of type {describe_type(fn_type)}, got {describe_type(val_ty)}")
        return value, val_ty

    LIST_FUNCTION_METHODS = ("sort_by", "filter", "map", "for_each", "any", "all", "find_index", "reduce")

    def emit_list_method(self, list_value, list_type, node):
        if node.method_name not in self.LIST_FUNCTION_METHODS:
            return super().emit_list_method(list_value, list_type, node)
        elem_ty = list_type[5:]
        meth = node.method_name
        what = f"list.{meth}"

        def element_at(index):
            return self.load_typed(self.builder.gep(self.list_data(list_value, elem_ty), [index]),
                                   elem_ty)[0]

        def function_argument(position, fn_type):
            if len(node.arguments) <= position:
                raise TypeError(f"{what} needs a function of type {describe_type(fn_type)}")
            return self.function_value_argument(node.arguments[position], fn_type)[0]

        if meth == "sort_by":
            if len(node.arguments) != 1:
                raise TypeError("list.sort_by expects one function: func(a : T, b : T) : bool, true when a comes first")
            fn_type = self.make_function_type([elem_ty, elem_ty], "bool")
            closure = function_argument(0, fn_type)
            self.call_runtime("vamp_list_sort_with", (list_type, "str", "str"), "void",
                              [list_value, closure, self.comparison_trampoline(fn_type, elem_ty)])
            return None, "void"

        if meth == "map":
            if len(node.arguments) != 1:
                raise TypeError("list.map expects one function that turns each value into a new one")
            closure, fn_type = self.visit(node.arguments[0])
            params, result_type = self.function_signature(fn_type) if fn_type.startswith("fn[") else ([], None)
            if params != [elem_ty] or result_type in (None, "void"):
                raise TypeError(f"list.map needs func({describe_type(elem_ty)}) : T, got {describe_type(fn_type)}")
            res = self.new_list(result_type, 4)

            def each(index):
                mapped = self.call_closure(closure, fn_type, [self.as_value(element_at(index))])[0]
                self.store_into_slot(self.builder.call(self.runtime_function(
                    "vamp_list_push_slot", self.char_pointer_type, [self.char_pointer_type]), [res]),
                    mapped, result_type)

            self.emit_counted_loop(self.list_length(list_value), each)
            return res, f"list:{result_type}"

        if meth == "reduce":
            if len(node.arguments) != 2:
                raise TypeError("list.reduce expects a function and a starting value: values.reduce(add, 0)")
            start, total_type = self.visit(node.arguments[1])
            fn_type = self.make_function_type([total_type, elem_ty], total_type)
            closure = function_argument(0, fn_type)
            total = self.entry_alloca(self.llvm_type_for(total_type), "reduce_total")
            self.builder.store(self.as_value(start), total)

            def each(index):
                combined = self.call_closure(closure, fn_type, [self.builder.load(total),
                                                                self.as_value(element_at(index))])[0]
                self.builder.store(self.as_value(combined), total)

            self.emit_counted_loop(self.list_length(list_value), each)
            return self.load_typed(total, total_type)

        if meth == "for_each":
            fn_type = self.make_function_type([elem_ty], "void")
            closure = function_argument(0, fn_type)
            self.emit_counted_loop(self.list_length(list_value), lambda index: self.call_closure(
                closure, fn_type, [self.as_value(element_at(index))]))
            return None, "void"

        fn_type = self.make_function_type([elem_ty], "bool")
        closure = function_argument(0, fn_type)
        if len(node.arguments) != 1:
            raise TypeError(f"{what} expects one function")
        if meth == "filter":
            res = self.new_list(elem_ty, 4)

            def each(index):
                value = element_at(index)
                keep = self.call_closure(closure, fn_type, [self.as_value(value)])[0]
                with self.builder.if_then(keep):
                    self.store_into_slot(self.builder.call(self.runtime_function(
                        "vamp_list_push_slot", self.char_pointer_type, [self.char_pointer_type]), [res]),
                        value, elem_ty)

            self.emit_counted_loop(self.list_length(list_value), each)
            return res, list_type

        found = self.entry_alloca(self.int64_type, "found_index")
        self.builder.store(ir.Constant(self.int64_type, -1), found)
        fn = self.builder.function
        loop_check = fn.append_basic_block(name="search_check")
        loop_body = fn.append_basic_block(name="search_body")
        loop_next = fn.append_basic_block(name="search_next")
        loop_hit = fn.append_basic_block(name="search_hit")
        loop_end = fn.append_basic_block(name="search_end")
        index_pointer = self.entry_alloca(self.int64_type, "search_index")
        self.builder.store(ir.Constant(self.int64_type, 0), index_pointer)
        self.builder.branch(loop_check)
        self.builder.position_at_end(loop_check)
        index = self.builder.load(index_pointer)
        self.builder.cbranch(self.builder.icmp_signed("<", index, self.list_length(list_value)), loop_body, loop_end)
        self.builder.position_at_end(loop_body)
        matched = self.call_closure(closure, fn_type, [self.as_value(element_at(index))])[0]
        if meth == "all":
            matched = self.builder.not_(matched)
        self.builder.cbranch(matched, loop_hit, loop_next)
        self.builder.position_at_end(loop_hit)
        self.builder.store(index, found)
        self.builder.branch(loop_end)
        self.builder.position_at_end(loop_next)
        self.builder.store(self.builder.add(index, ir.Constant(self.int64_type, 1)), index_pointer)
        self.builder.branch(loop_check)
        self.builder.position_at_end(loop_end)
        position = self.builder.load(found)
        if meth == "find_index":
            return position, "int"
        hit = self.builder.icmp_signed(">=", position, ir.Constant(self.int64_type, 0))
        return (self.builder.not_(hit) if meth == "all" else hit), "bool"

    def comparison_trampoline(self, fn_type, element_type):
        cache = getattr(self, "comparison_trampolines", None)
        if cache is None:
            cache = self.comparison_trampolines = {}
        if fn_type in cache:
            return cache[fn_type]
        ptr = self.char_pointer_type
        fn = ir.Function(self.module, ir.FunctionType(self.int32_type, [ptr, ptr, ptr]),
                               name=f"vamp_compare_with.{len(cache)}")
        fn.linkage = "internal"
        saved_builder = self.builder
        self.builder = ir.IRBuilder(fn.append_basic_block(name="entry"))
        element_pointer = self.llvm_type_for(element_type).as_pointer()
        left = self.builder.load(self.builder.bitcast(fn.args[1], element_pointer))
        right = self.builder.load(self.builder.bitcast(fn.args[2], element_pointer))
        code = self.builder.load(self.builder.bitcast(fn.args[0], ptr.as_pointer()))
        target = self.builder.bitcast(code, self.closure_function_type(fn_type).as_pointer())
        less = self.builder.call(target, [fn.args[0], left, right])
        self.builder.ret(self.builder.zext(less, self.int32_type))
        self.builder = saved_builder
        cache[fn_type] = fn
        return fn.bitcast(ptr)

    def emit_closure_thread(self, node):
        fn_type = self.make_function_type([], "void")
        target = node.arguments[0]
        if isinstance(target, VariableAccessNode) and target.variable_name not in self.type_information:
            closure = self.function_value_argument(target, fn_type)[0]
        else:
            closure, val_ty = self.visit(target)
            if val_ty != fn_type:
                raise TypeError(
                    "The first argument of thread.Start must be the name of a function or a function value "
                    f"of type func(), got {describe_type(val_ty)}")
        fh = self.call_runtime("vamp_thread_start_closure", ("str",), "int", [closure])
        return fh

    EVENT_METHODS = ("On_Click", "On_Key", "Every", "Run_Events", "Stop_Events")

    def event_state(self):
        state = getattr(self, "events", None)
        if state is None:
            state = self.events = {"click": {}, "key": {}, "timer": [], "dispatch": None, "stop": None,
                                   "should_stop": None}
        return state

    def handler_slot(self, name):
        slot = ir.GlobalVariable(self.module, self.char_pointer_type, name=name)
        slot.initializer = ir.Constant(self.char_pointer_type, None)
        slot.linkage = "internal"
        return slot

    def emit_event_call(self, node):
        state = self.event_state()
        meth = node.method_name
        handler_type = self.make_function_type([], "void")
        if meth == "On_Click":
            self.require_argument_count(node, 3)
            key = self.get_interface_key(node.arguments[0], node.arguments[1])
            self.get_interface_id(node.arguments[0], node.arguments[1], "button")
            slot = state["click"].get(key)
            if slot is None:
                slot = state["click"][key] = self.handler_slot(f"vamp_on_click.{len(state['click'])}")
            self.builder.store(self.function_value_argument(node.arguments[2], handler_type)[0], slot)
            return None, "void"
        if meth == "On_Key":
            self.require_argument_count(node, 2)
            key_node = node.arguments[0]
            if not isinstance(key_node, LiteralNode) or key_node.literal_type != "str":
                raise TypeError('os.On_Key needs the key name as a string literal, for example "SPACE"')
            slot = state["key"].get(key_node.value.upper())
            if slot is None:
                slot = state["key"][key_node.value.upper()] = self.handler_slot(f"vamp_on_key.{len(state['key'])}")
            self.builder.store(self.function_value_argument(node.arguments[1], handler_type)[0], slot)
            return None, "void"
        if meth == "Every":
            self.require_argument_count(node, 2)
            interval, interval_type = self.visit_as(node.arguments[0], "int")
            if interval_type != "int":
                raise TypeError("os.Every needs the interval in milliseconds as an int")
            idx = len(state["timer"])
            slot = self.handler_slot(f"vamp_every.{idx}")
            period = ir.GlobalVariable(self.module, self.int64_type, name=f"vamp_every_period.{idx}")
            due = ir.GlobalVariable(self.module, self.int64_type, name=f"vamp_every_due.{idx}")
            for var in (period, due):
                var.initializer = ir.Constant(self.int64_type, 0)
                var.linkage = "internal"
            state["timer"].append((slot, period, due))
            now = self.call_runtime("vamp_time_millis", (), "c_i64", [])[0]
            self.builder.store(interval, period)
            self.builder.store(self.builder.add(now, interval), due)
            self.builder.store(self.function_value_argument(node.arguments[1], handler_type)[0], slot)
            return None, "void"
        if meth == "Stop_Events":
            self.require_argument_count(node, 0)
            self.builder.store(ir.Constant(self.bool_type, 1), self.event_stop_flag())
            return None, "void"
        self.require_argument_count(node, 0)
        stop = self.event_stop_flag()
        self.builder.store(ir.Constant(self.bool_type, 0), stop)
        fn = self.builder.function
        loop_block = fn.append_basic_block(name="event_loop")
        sleep_block = fn.append_basic_block(name="event_wait")
        end_block = fn.append_basic_block(name="event_loop_end")
        self.builder.branch(loop_block)
        self.builder.position_at_end(loop_block)
        self.builder.call(self.event_function("dispatch", ir.VoidType()), [])
        finished = self.builder.call(self.event_function("should_stop", self.bool_type), [])
        self.builder.cbranch(finished, end_block, sleep_block)
        self.builder.position_at_end(sleep_block)
        sleep = LibraryCallNode("os", "Sleep", [LiteralNode("int", 4)])
        sleep.resolved = True
        self.visit(sleep)
        self.builder.branch(loop_block)
        self.builder.position_at_end(end_block)
        return None, "void"

    def event_stop_flag(self):
        state = self.event_state()
        if state["stop"] is None:
            flag = ir.GlobalVariable(self.module, self.bool_type, name="vamp_events_stop")
            flag.initializer = ir.Constant(self.bool_type, 0)
            flag.linkage = "internal"
            state["stop"] = flag
        return state["stop"]

    def event_function(self, kind, return_type):
        state = self.event_state()
        if state[kind] is None:
            fn = ir.Function(self.module, ir.FunctionType(return_type, []), name=f"vamp_events_{kind}")
            fn.linkage = "internal"
            state[kind] = fn
        return state[kind]

    def finish_program(self):
        super().finish_program()
        state = getattr(self, "events", None)
        if state is None or state["dispatch"] is None:
            return
        handler_type = self.make_function_type([], "void")
        saved = self.enter_function(state["dispatch"], "void")
        null = ir.Constant(self.char_pointer_type, None)

        def call_if_set(slot):
            closure = self.builder.load(slot)
            with self.builder.if_then(self.builder.icmp_unsigned("!=", closure, null)):
                self.call_closure(closure, handler_type, [])

        for (title, name), slot in state["click"].items():
            clicked = LibraryCallNode("os", "Interface_Clicked", [LiteralNode("str", title), LiteralNode("str", name)])
            clicked.resolved = True
            with self.builder.if_then(self.visit(clicked)[0]):
                call_if_set(slot)
        for key, slot in state["key"].items():
            pressed = self.call_runtime("vamp_input_key_pressed", ("str",), "bool", [self.string_constant(key)])[0]
            with self.builder.if_then(pressed):
                call_if_set(slot)
        for slot, period, due in state["timer"]:
            now = self.call_runtime("vamp_time_millis", (), "c_i64", [])[0]
            ready = self.builder.and_(
                self.builder.icmp_unsigned("!=", self.builder.load(slot), null),
                self.builder.icmp_signed(">=", now, self.builder.load(due)))
            with self.builder.if_then(ready):
                self.builder.store(self.builder.add(now, self.builder.load(period)), due)
                call_if_set(slot)
        self.leave_function(saved, "the event loop")

        stop_function = self.event_function("should_stop", self.bool_type)
        builder = ir.IRBuilder(stop_function.append_basic_block(name="entry"))
        stop = builder.load(self.event_stop_flag())
        if self.active_windows_global is not None:
            closed = builder.icmp_signed("<=", builder.load(self.active_windows_global), ir.Constant(self.int32_type, 0))
            stop = builder.or_(stop, closed)
        builder.ret(stop)
