from llvmlite import ir

from diagnostics import suggest
from parser import (
    ArrayAccessNode, ArrayLiteralNode, ClassDeclarationNode, DictionaryAccessNode,
    EnumDeclarationNode, FunctionCallNode, FunctionDeclarationNode, InterfaceDeclarationNode, LiteralNode,
    MapLiteralNode,
    VariableAccessNode,
)
from values import ArrayLiteralValue, ClassInstanceValue, DictionaryLiteralValue, PointerValue

INTEGER_BITS = {"i8": 8, "i16": 16, "i32": 32, "int": 64, "u8": 8, "u16": 16, "u32": 32, "u64": 64}
UNSIGNED_TYPES = {"u8", "u16", "u32", "u64", "char"}
FLOAT_TYPES = ("float", "f32")
INTEGER_RANGES = {
    name: ((0, 2 ** bits - 1) if name in UNSIGNED_TYPES else (-(2 ** (bits - 1)), 2 ** (bits - 1) - 1))
    for name, bits in INTEGER_BITS.items()
}
SORT_KINDS = {"i8": 0, "i16": 1, "i32": 2, "int": 3, "u8": 4, "u16": 5, "u32": 6, "u64": 7,
              "f32": 8, "float": 9, "str": 10, "char": 4}

STRING_METHODS = {
    "length": ("vamp_str_length", (), "int"),
    "upper": ("vamp_str_upper", (), "str"),
    "lower": ("vamp_str_lower", (), "str"),
    "trim": ("vamp_str_trim", (), "str"),
    "reverse": ("vamp_str_reverse", (), "str"),
    "contains": ("vamp_str_contains", ("str",), "bool"),
    "starts_with": ("vamp_str_starts_with", ("str",), "bool"),
    "ends_with": ("vamp_str_ends_with", ("str",), "bool"),
    "find": ("vamp_str_find", ("str",), "int"),
    "replace": ("vamp_str_replace", ("str", "str"), "str"),
    "split": ("vamp_str_split", ("str",), "list:str"),
    "substring": ("vamp_str_substring", ("int", "int"), "str"),
    "repeat": ("vamp_str_repeat", ("int",), "str"),
    "char_at": ("vamp_str_at", ("int",), "char"),
    "is_number": ("vamp_str_is_number", (), "bool"),
    "chars": ("vamp_str_chars", (), "list:str"),
    "char_count": ("vamp_str_char_count", (), "int"),
    "code_points": ("vamp_str_code_points", (), "list:int"),
}


def split_type_list(text):
    parts = []
    depth = 0
    cur = []
    for ch in text:
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    parts.append("".join(cur))
    return parts


def describe_type(type_name):
    if type_name is None:
        return "unknown"
    if type_name.startswith("list:"):
        return f"list[{describe_type(type_name[5:])}]"
    if type_name.startswith("set:"):
        return f"set[{describe_type(type_name[4:])}]"
    if type_name.startswith("tuple["):
        return "(" + ", ".join(describe_type(item) for item in split_type_list(type_name[6:-1])) + ")"
    if type_name.startswith("fn["):
        inner = type_name[3:-1]
        depth = 0
        for pos, ch in enumerate(inner):
            depth += {"[": 1, "]": -1}.get(ch, 0)
            if ch == ";" and depth == 0:
                params, res = inner[:pos], inner[pos + 1:]
        shown = ", ".join(describe_type(item) for item in split_type_list(params)) if params else ""
        return f"func({shown})" + ("" if res == "void" else f" : {describe_type(res)}")
    if type_name.startswith("map:"):
        _, key_ty, val_ty = type_name.split(":", 2)
        return f"map[{key_ty}, {describe_type(val_ty)}]"
    if type_name.startswith("pointer:"):
        return f"pointer to {describe_type(type_name[8:])}"
    if type_name.startswith("optional:"):
        return describe_type(type_name[9:]) + "?"
    if type_name == "none":
        return "none"
    for prefix in ("class:", "enum:", "named:", "interface:"):
        if type_name.startswith(prefix):
            return type_name[len(prefix):]
    return type_name


def is_number_literal(node):
    return isinstance(node, LiteralNode) and node.literal_type in ("int", "float")


class LanguageCore:
    def init_language_state(self):
        self.enum_definitions = {}
        self.interface_definitions = {}
        self.interface_tables = {}
        self.enum_name_functions = {}
        self.function_overloads = {}
        self.declared_function_order = []
        self.pending_classes = {}
        self.classes_being_registered = set()
        self.top_level_classes = []
        self.loop_stack = []
        self.try_depth = 0
        self.block_depth = 0
        self.global_count = 0
        self.user_globals = []
        self.function_allocas = []
        self.function_has_try = False
        self.current_return_type = "int"
        self.current_class = None
        self.runtime_units = set()
        self.runtime_functions = {}
        self.double_type = ir.DoubleType()
        self.int8_type = ir.IntType(8)
        self.list_header_type = ir.LiteralStructType(
            [self.int32_type, self.int32_type, self.int32_type, self.int32_type, self.char_pointer_type]
        )

    def prepare_program(self, program):
        for stmt in program:
            if isinstance(stmt, EnumDeclarationNode):
                self.register_enum(stmt)
            elif isinstance(stmt, InterfaceDeclarationNode):
                self.register_interface_type(stmt)
        self.init_generics()
        for stmt in program:
            if isinstance(stmt, (ClassDeclarationNode, FunctionDeclarationNode)) and self.is_generic(stmt):
                self.register_generic(stmt)
        for stmt in program:
            if isinstance(stmt, ClassDeclarationNode) and not self.is_generic(stmt):
                if stmt.class_name in self.pending_classes or stmt.class_name in self.enum_definitions:
                    raise SyntaxError(f"Class '{stmt.class_name}' is already declared")
                self.pending_classes[stmt.class_name] = stmt
                self.top_level_classes.append(stmt)
        for cls_name in list(self.pending_classes):
            self.ensure_class_registered(cls_name)
        for stmt in self.top_level_classes:
            self.declare_class_methods(stmt)
        self.build_vtables()
        for stmt in program:
            if isinstance(stmt, FunctionDeclarationNode) and not self.is_generic(stmt):
                self.declare_function(stmt)

    def finish_program(self):
        main_builder = self.builder
        main_block = self.builder.block
        main_state = (self.function_allocas, self.function_has_try)
        changed = True
        while changed:
            changed = False
            for info in list(self.declared_function_order):
                if not info["emitted"]:
                    self.emit_function_body(info)
                    changed = True
            for decl in list(self.top_level_classes) + list(self.generic_class_instances):
                emitted = len(self.emitted_class_methods)
                self.emit_class_methods(decl)
                changed = changed or len(self.emitted_class_methods) != emitted
        self.builder = main_builder
        self.function_allocas, self.function_has_try = main_state
        if self.function_has_try:
            self.keep_variables_in_memory()
            entry_block = self.builder.function.entry_basic_block
            keep = self.runtime_function("vamp_keep", ir.VoidType(), [self.char_pointer_type])
            self.builder.position_at_start(entry_block)
            for var in self.user_globals:
                self.builder.call(keep, [self.builder.bitcast(var, self.char_pointer_type)])
        self.builder.position_at_end(main_block)

    # which runtime .c gets linked is picked by symbol prefix.
    # vamp_start is its own tiny unit so hello world doesn't pull in the GC
    RUNTIME_UNIT_PREFIXES = (
        ("vamp_json_", "json"), ("vamp_thread_", "thread"), ("vamp_net_", "net"),
        ("vamp_input_", "media"), ("vamp_audio_", "media"), ("vamp_ui_", "ui"), ("vamp_os_", "system"),
        ("vamp_gc_", "gc"), ("vamp_regex_", "regex"), ("vamp_start", "start"),
    )

    def runtime_function(self, name, return_type, parameter_types):
        fn = self.runtime_functions.get(name)
        if fn is None:
            fn = ir.Function(self.module, ir.FunctionType(return_type, parameter_types), name=name)
            self.runtime_functions[name] = fn
            unit = "core"
            for prefix, prefix_unit in self.RUNTIME_UNIT_PREFIXES:
                if name.startswith(prefix):
                    unit = prefix_unit
            self.runtime_units.update((unit,) if unit == "start" else ("core", "gc", unit))
        return fn

    def c_type_for(self, type_name):
        if type_name in ("bool", "char", "int", "i32"):
            return self.int32_type
        if type_name == "c_i64":
            return self.int64_type
        if type_name in FLOAT_TYPES:
            return self.double_type
        return self.llvm_type_for(type_name)

    def fit_integer(self, value, llvm_type, unsigned=False):
        if value.type.width == llvm_type.width:
            return value
        if value.type.width > llvm_type.width:
            return self.builder.trunc(value, llvm_type)
        if unsigned:
            return self.builder.zext(value, llvm_type)
        return self.builder.sext(value, llvm_type)

    def to_c_value(self, value, c_type):
        if isinstance(c_type, ir.IntType) and isinstance(value.type, ir.IntType):
            return self.fit_integer(value, c_type, unsigned=value.type.width in (1, 8))
        if isinstance(c_type, ir.DoubleType) and isinstance(value.type, ir.FloatType):
            return self.builder.fpext(value, c_type)
        return value

    def call_runtime(self, symbol, parameter_types, return_type, values):
        c_parameters = [self.c_type_for(item) for item in parameter_types]
        fn = self.runtime_function(symbol, self.c_type_for(return_type), c_parameters)
        args = [self.to_c_value(value, c_type) for value, c_type in zip(values, c_parameters)]
        if return_type == "void":
            self.builder.call(fn, args)
            return None, "void"
        res = self.builder.call(fn, args)
        if return_type == "c_i64":
            return res, "int"
        if return_type == "bool":
            res = self.builder.icmp_signed("!=", res, ir.Constant(self.int32_type, 0))
        elif return_type == "char":
            res = self.builder.trunc(res, self.int8_type)
        elif return_type == "int":
            res = self.builder.sext(res, self.int64_type)
        elif return_type == "f32":
            res = self.builder.fptrunc(res, self.float_type)
        return res, return_type

    def check_arguments(self, what, argument_nodes, parameter_types):
        if len(argument_nodes) != len(parameter_types):
            raise TypeError(
                f"{what} expects {len(parameter_types)} argument{'s' if len(parameter_types) != 1 else ''}, "
                f"got {len(argument_nodes)}"
            )
        vals = []
        for pos, (arg, parameter_type) in enumerate(zip(argument_nodes, parameter_types), start=1):
            value, val_ty = self.visit_as(arg, parameter_type)
            if val_ty != parameter_type:
                raise TypeError(
                    f"Argument {pos} of {what} must be {describe_type(parameter_type)}, "
                    f"got {describe_type(val_ty)}"
                )
            vals.append(self.as_value(value))
        return vals

    def resolve_type(self, type_name):
        if type_name is None:
            return None
        if type_name.startswith("list:"):
            return "list:" + self.resolve_type(type_name[5:])
        if type_name.startswith("set:"):
            return "set:" + self.resolve_type(type_name[4:])
        if type_name.startswith("tuple["):
            return "tuple[" + ",".join(self.resolve_type(item) for item in split_type_list(type_name[6:-1])) + "]"
        if type_name.startswith("fn["):
            params, res = self.function_signature(type_name)
            return self.make_function_type([self.resolve_type(item) for item in params], self.resolve_type(res))
        if type_name.startswith("map:"):
            _, key_ty, val_ty = type_name.split(":", 2)
            return f"map:{key_ty}:{self.resolve_type(val_ty)}"
        if type_name.startswith("pointer:"):
            return "pointer:" + self.resolve_type(type_name[8:])
        if type_name.startswith("optional:"):
            inner = self.resolve_type(type_name[9:])
            return inner if inner.startswith("optional:") else "optional:" + inner
        if type_name.startswith("named:"):
            name = type_name[6:]
            if name in self.interface_definitions:
                return f"interface:{name}"
            if name == "builder" and name not in self.pending_classes:
                return "builder"
            if name in self.pending_classes and not self.is_reference_class(name):
                self.ensure_class_registered(name)
            elif name in self.pending_classes:
                return f"class:{name}"
            if name in self.class_definitions:
                return f"class:{name}"
            if name in self.enum_definitions:
                return f"enum:{name}"
            close = suggest(name, list(self.class_definitions) + list(self.enum_definitions) + ["list", "map"])
            msg = f"Unknown type '{name}'"
            if close:
                msg += f" (did you mean '{close}'?)"
            raise NameError(msg)
        return type_name

    def llvm_type_for(self, type_name):
        type_name = self.resolve_type(type_name)
        if type_name in INTEGER_BITS:
            return ir.IntType(INTEGER_BITS[type_name])
        if type_name == "float":
            return self.double_type
        if type_name == "f32":
            return self.float_type
        if type_name == "bool":
            return self.bool_type
        if type_name == "char":
            return self.int8_type
        if type_name in ("str", "json", "builder") or type_name.startswith(("list:", "map:", "set:", "fn[")):
            return self.char_pointer_type
        if type_name.startswith("tuple["):
            return ir.LiteralStructType([self.llvm_type_for(item) for item in split_type_list(type_name[6:-1])])
        if type_name == "void":
            return ir.VoidType()
        if type_name.startswith("enum:"):
            return self.int32_type
        if type_name.startswith("pointer:"):
            return self.llvm_type_for(type_name[8:]).as_pointer()
        if type_name.startswith("class:"):
            name = type_name[6:]
            if self.is_reference_class(name):
                return self.class_object_type(name).as_pointer()
            return self.class_definitions[name]["llvm_type"]
        if type_name.startswith("interface:"):
            return self.interface_llvm_type()
        if type_name.startswith("optional:"):
            return self.optional_llvm_type(type_name[9:])
        raise TypeError(f"Values of type '{describe_type(type_name)}' cannot be stored")

    def size_of(self, type_name):
        ll_ty = self.llvm_type_for(type_name)
        end = self.builder.gep(ir.Constant(ll_ty.as_pointer(), None), [ir.Constant(self.int32_type, 1)])
        return self.builder.ptrtoint(end, self.int32_type)

    def as_value(self, value):
        if isinstance(value, ClassInstanceValue):
            return value.pointer if value.reference else self.builder.load(value.pointer)
        if isinstance(value, PointerValue):
            return value.pointer
        return value

    def wrap_value(self, value, value_type):
        if value_type.startswith("class:") and not isinstance(value, ClassInstanceValue):
            if self.is_reference_class(value_type[6:]):
                return ClassInstanceValue(value, reference=True)
            storage = self.entry_alloca(self.llvm_type_for(value_type), "class_value")
            self.builder.store(value, storage)
            return ClassInstanceValue(storage, temporary=True)
        return value

    def load_typed(self, pointer, value_type):
        if value_type.startswith("class:"):
            if self.is_reference_class(value_type[6:]):
                return ClassInstanceValue(self.builder.load(pointer), reference=True), value_type
            return ClassInstanceValue(pointer), value_type
        return self.builder.load(pointer), value_type

    def integer_constant(self, value, type_name):
        low, high = INTEGER_RANGES[type_name]
        if not low <= value <= high:
            raise ValueError(f"The number {value} does not fit in {type_name} ({low} to {high})")
        return ir.Constant(ir.IntType(INTEGER_BITS[type_name]), value)

    def visit_as(self, node, target_type):
        target_type = self.resolve_type(target_type)
        if target_type is not None:
            if isinstance(node, LiteralNode):
                if node.literal_type == "int" and target_type in INTEGER_BITS:
                    return self.integer_constant(node.value, target_type), target_type
                if node.literal_type == "int" and target_type in FLOAT_TYPES:
                    return ir.Constant(self.llvm_type_for(target_type), float(node.value)), target_type
                if node.literal_type == "float" and target_type == "f32":
                    return ir.Constant(self.float_type, node.value), "f32"
            if isinstance(node, ArrayLiteralNode) and target_type.startswith("list:"):
                return self.build_list_literal(node, target_type)
            expected = self.expected_literal(node, target_type)
            if expected is not None:
                return expected
            if isinstance(node, MapLiteralNode) and target_type.startswith("map:"):
                return self.build_map_literal(node, target_type)
        value, val_ty = self.visit(node)
        if target_type is not None and val_ty != target_type:
            converted = self.convert_value(value, val_ty, target_type)
            if converted is not None:
                return converted
        return value, val_ty

    def default_value(self, type_name):
        type_name = self.resolve_type(type_name)
        if type_name == "str":
            return self.visit_LiteralNode(LiteralNode("str", ""))
        if type_name.startswith("list:"):
            return self.new_list(type_name[5:], 4), type_name
        if type_name.startswith("map:"):
            return self.new_map(type_name), type_name
        if type_name.startswith("set:"):
            return self.build_set([], type_name)
        if type_name.startswith("optional:"):
            return self.none_value(type_name[9:]), type_name
        if type_name.startswith("class:") and self.is_reference_class(type_name[6:]):
            raise TypeError(
                f"A variable of class {describe_type(type_name)} needs an object, or make its type "
                f"{describe_type(type_name)}? so it can start as none")
        if type_name.startswith("class:"):
            storage = self.entry_alloca(self.llvm_type_for(type_name), "default_value")
            self.builder.store(ir.Constant(self.llvm_type_for(type_name), None), storage)
            return ClassInstanceValue(storage, temporary=True), type_name
        if type_name == "void" or type_name.startswith("pointer:") or type_name in ("array", "dictionary"):
            raise TypeError(f"A variable of type {describe_type(type_name)} needs an initial value")
        return ir.Constant(self.llvm_type_for(type_name), None), type_name

    def at_global_scope(self):
        return self.builder.function.name == "main" and self.block_depth == 0

    def entry_alloca(self, llvm_type, name=""):
        with self.builder.goto_entry_block():
            ptr = self.builder.alloca(llvm_type, name=name)
        self.function_allocas.append(ptr)
        return ptr

    def allocate_variable(self, llvm_type, name):
        if self.at_global_scope():
            self.global_count += 1
            var = ir.GlobalVariable(self.module, llvm_type, name=f"vamp_global.{name}.{self.global_count}")
            var.linkage = "internal"
            var.initializer = ir.Constant(llvm_type, None)
            self.user_globals.append(var)
            return var
        return self.entry_alloca(llvm_type, name)

    def keep_variables_in_memory(self):
        keep = self.runtime_function("vamp_keep", ir.VoidType(), [self.char_pointer_type])
        for ptr in self.function_allocas:
            self.builder.position_after(ptr)
            self.builder.call(keep, [self.builder.bitcast(ptr, self.char_pointer_type)])

    def save_scope(self):
        return (
            self.variable_pointers.copy(), self.type_information.copy(), self.array_information.copy(),
            self.dictionary_information.copy(), self.constant_variables.copy(),
        )

    def restore_scope(self, saved):
        self.variable_pointers = saved[0].copy()
        self.type_information = saved[1].copy()
        self.array_information = saved[2].copy()
        self.dictionary_information = saved[3].copy()
        self.constant_variables = saved[4].copy()

    def bind_variable(self, name, pointer, type_name, is_constant=False):
        self.variable_pointers[name] = pointer
        self.type_information[name] = type_name
        self.array_information.pop(name, None)
        self.dictionary_information.pop(name, None)
        if is_constant:
            self.constant_variables.add(name)
        else:
            self.constant_variables.discard(name)

    def require_variable(self, name):
        if name not in self.variable_pointers or name not in self.type_information:
            known = [item for item in self.variable_pointers if not item.startswith("function_")]
            close = suggest(name, known)
            msg = f"Variable '{name}' is not declared"
            if close:
                msg += f" (did you mean '{close}'?)"
            raise NameError(msg)
        return self.type_information[name]

    def declare_variable(self, name, value, value_type, is_constant=False):
        if isinstance(value, ArrayLiteralValue):
            array_type = ir.ArrayType(self.llvm_type_for(value.element_type), len(value.elements))
            ptr = self.allocate_variable(array_type, name)
            for idx, elem in enumerate(value.elements):
                self.builder.store(self.as_value(elem), self.builder.gep(
                    ptr, [ir.Constant(self.int32_type, 0), ir.Constant(self.int32_type, idx)]))
            self.bind_variable(name, ptr, "array", is_constant)
            self.array_information[name] = {"element_type": value.element_type, "length": len(value.elements)}
            return
        if isinstance(value, DictionaryLiteralValue):
            dictionary_type = ir.LiteralStructType(
                [self.llvm_type_for(field_ty) for _, field_ty, _ in value.entries])
            ptr = self.allocate_variable(dictionary_type, name)
            fields = {}
            for field_index, (field_name, field_ty, field_value) in enumerate(value.entries):
                self.builder.store(self.as_value(field_value), self.builder.gep(
                    ptr, [ir.Constant(self.int32_type, 0), ir.Constant(self.int32_type, field_index)]))
                fields[field_name] = (field_index, field_ty)
            self.bind_variable(name, ptr, "dictionary", is_constant)
            self.dictionary_information[name] = fields
            return
        if isinstance(value, ClassInstanceValue) and value.reference:
            ptr = self.allocate_variable(self.llvm_type_for(value_type), name)
            self.builder.store(value.pointer, ptr)
            self.bind_variable(name, ptr, value_type, is_constant)
            return
        if isinstance(value, ClassInstanceValue):
            if value.temporary and not self.at_global_scope():
                ptr = value.pointer
            else:
                ptr = self.allocate_variable(self.llvm_type_for(value_type), name)
                self.builder.store(self.builder.load(value.pointer), ptr)
            self.bind_variable(name, ptr, value_type, is_constant)
            return
        if value_type == "void":
            raise TypeError(f"Cannot store the result of a call that returns nothing in '{name}'")
        ptr = self.allocate_variable(self.llvm_type_for(value_type), name)
        self.builder.store(self.as_value(value), ptr)
        self.bind_variable(name, ptr, value_type, is_constant)

    def visit_VariableDeclarationNode(self, node):
        decl_ty = self.resolve_type(node.variable_type)
        value, val_ty = self.visit_as(node.initializer, decl_ty)
        if decl_ty is not None and val_ty != decl_ty:
            raise TypeError(
                f"Cannot assign {describe_type(val_ty)} to variable '{node.variable_name}' "
                f"of type {describe_type(decl_ty)}"
            )
        self.declare_variable(node.variable_name, value, val_ty, node.is_constant)

    def visit_GroupVariableDeclarationNode(self, node):
        if node.initializers is not None and len(node.initializers) == 1 and len(node.variable_names) > 1:
            return self.declare_unpacked(node)
        if node.variable_type is None:
            raise SyntaxError("Grouped declarations require an explicit type")
        if len(set(node.variable_names)) != len(node.variable_names):
            raise SyntaxError("Grouped declarations cannot contain duplicate variable names")
        if node.initializers is not None and len(node.initializers) != len(node.variable_names):
            raise SyntaxError(
                f"Grouped declaration has {len(node.variable_names)} variables but "
                f"{len(node.initializers)} initializers"
            )
        decl_ty = self.resolve_type(node.variable_type)
        for pos, var_name in enumerate(node.variable_names):
            if node.initializers is None:
                value, val_ty = self.default_value(decl_ty)
            else:
                value, val_ty = self.visit_as(node.initializers[pos], decl_ty)
            if val_ty != decl_ty:
                raise TypeError(
                    f"Cannot assign {describe_type(val_ty)} to variable '{var_name}' "
                    f"of type {describe_type(decl_ty)}"
                )
            self.declare_variable(var_name, value, val_ty, node.is_constant)

    def visit_ClassInstanceDeclarationNode(self, node):
        value, val_ty = self.visit(node.initializer)
        if not isinstance(value, ClassInstanceValue):
            raise TypeError(f"'{node.instance_name}' must be initialized with a class instance")
        self.declare_variable(node.instance_name, value, val_ty)

    def lvalue_pointer(self, node, for_write=True):
        if isinstance(node, VariableAccessNode):
            name = node.variable_name
            variable_type = self.require_variable(name)
            if variable_type in ("array", "dictionary"):
                raise TypeError(f"Use an index or field to change '{name}'")
            return self.variable_pointers[name], variable_type, name in self.constant_variables, f"variable '{name}'"
        if isinstance(node, DictionaryAccessNode):
            base = node.dictionary
            if isinstance(base, VariableAccessNode) and self.type_information.get(base.variable_name) == "dictionary":
                field = self.dictionary_information[base.variable_name].get(node.key)
                if field is None:
                    raise NameError(f"Dictionary has no field '{node.key}'")
                ptr = self.builder.gep(
                    self.variable_pointers[base.variable_name],
                    [ir.Constant(self.int32_type, 0), ir.Constant(self.int32_type, field[0])],
                )
                return ptr, field[1], base.variable_name in self.constant_variables, f"field '{node.key}'"
            base_pointer, base_ty, base_constant, _ = self.lvalue_pointer(base, for_write)
            if base_ty.startswith("optional:class:") and self.is_reference_class(base_ty[15:]):
                base_ty = base_ty[9:]
            if not base_ty.startswith("class:"):
                raise TypeError(f"Values of type {describe_type(base_ty)} do not have fields")
            if self.is_reference_class(base_ty[6:]):
                base_pointer = self.builder.load(base_pointer)
                base_constant = False
            elif base_pointer.type.pointee == self.char_pointer_type or not isinstance(
                    base_pointer.type.pointee, (ir.LiteralStructType, ir.BaseStructType)):
                raise TypeError(f"Values of type {describe_type(base_ty)} do not have fields")
            ptr, field_ty, field_constant = self.class_field_pointer(base_pointer, base_ty[6:], node.key)
            return ptr, field_ty, base_constant or field_constant, f"field '{node.key}'"
        if isinstance(node, ArrayAccessNode):
            ptr, elem_ty, is_constant = self.element_pointer(node, for_write)
            return ptr, elem_ty, is_constant, "an element"
        value, val_ty = self.visit(node)
        if isinstance(value, ClassInstanceValue):
            return value.pointer, val_ty, False, "a value"
        raise TypeError("Only variables, fields and indexed values can be assigned to")

    def element_pointer(self, node, for_write):
        target = node.array
        if isinstance(target, VariableAccessNode):
            name = target.variable_name
            variable_type = self.require_variable(name)
            is_constant = name in self.constant_variables
            if variable_type == "array":
                idx = self.visit_index(node.index)
                info = self.array_information[name]
                ptr = self.builder.gep(
                    self.variable_pointers[name], [ir.Constant(self.int32_type, 0), idx],
                    name=f"{name}_element_pointer",
                )
                return ptr, info["element_type"], is_constant
            if variable_type.startswith("pointer:"):
                idx = self.visit_index(node.index)
                base = self.builder.load(self.variable_pointers[name], name=f"{name}_pointer_value")
                return self.builder.gep(base, [idx], name=f"{name}_element_pointer"), variable_type[8:], False
        value, val_ty = self.visit(target)
        if val_ty.startswith("list:"):
            elem_ty = val_ty[5:]
            return self.list_element_pointer(value, self.visit_index(node.index), elem_ty), elem_ty, False
        if val_ty.startswith("map:"):
            _, key_ty, elem_ty = val_ty.split(":", 2)
            key = self.map_key(node.index, key_ty)
            return self.map_slot(value, key, key_ty, elem_ty, create=for_write), elem_ty, False
        if isinstance(target, VariableAccessNode):
            raise TypeError(f"'{target.variable_name}' is not an array, list, map or pointer")
        raise TypeError(f"Values of type {describe_type(val_ty)} cannot be indexed")

    def visit_index(self, index_node):
        idx, index_type = self.visit(index_node)
        if index_type not in INTEGER_BITS:
            raise TypeError("Indexes must be int")
        if index_type != "int":
            idx, _ = self.cast_value(idx, index_type, "int")
        return idx

    def assign_to(self, target, operator, expression):
        ptr, tgt_ty, is_constant, description = self.lvalue_pointer(target)
        if is_constant:
            if isinstance(target, VariableAccessNode):
                raise TypeError(f"Cannot assign to constant '{target.variable_name}'")
            raise TypeError(f"Cannot assign to {description} because it is constant")
        if operator == "=":
            value, val_ty = self.visit_as(expression, tgt_ty)
        else:
            cur, _ = self.load_typed(ptr, tgt_ty)
            right, rhs_ty = self.visit_as(expression, tgt_ty) if is_number_literal(expression) \
                else self.visit(expression)
            value, val_ty = self.apply_binary(operator[:-1], cur, tgt_ty, right, rhs_ty)
        if val_ty != tgt_ty:
            raise TypeError(
                f"Cannot assign {describe_type(val_ty)} to {description} of type {describe_type(tgt_ty)}"
            )
        self.builder.store(self.as_value(value), ptr)

    def visit_AssignmentNode(self, node):
        if node.variable_name not in self.variable_pointers:
            if node.operator == "=":
                value, val_ty = self.visit(node.expression)
                if isinstance(value, ClassInstanceValue):
                    self.declare_variable(node.variable_name, value, val_ty)
                    return
            self.require_variable(node.variable_name)
        self.assign_to(VariableAccessNode(node.variable_name), node.operator, node.expression)

    def visit_ArrayAssignmentNode(self, node):
        self.assign_to(ArrayAccessNode(node.array, node.index), node.operator, node.expression)

    def visit_TargetAssignmentNode(self, node):
        self.assign_to(node.target, node.operator, node.expression)

    def visit_LiteralNode(self, node):
        if node.literal_type == "none":
            return None, "none"
        if node.literal_type == "int":
            low, high = INTEGER_RANGES["int"]
            if not low <= node.value <= high:
                return self.integer_constant(node.value, "u64"), "u64"
            return ir.Constant(self.int64_type, node.value), "int"
        if node.literal_type == "float":
            return ir.Constant(self.double_type, node.value), "float"
        if node.literal_type == "bool":
            return ir.Constant(self.bool_type, 1 if node.value else 0), "bool"
        if node.literal_type == "char":
            return ir.Constant(self.int8_type, node.value), "char"
        string_content = node.value + "\0"
        encoded = bytearray(string_content.encode("utf-8"))
        string_constant = ir.Constant(ir.ArrayType(ir.IntType(8), len(encoded)), encoded)
        self.string_literal_count += 1
        string_global = ir.GlobalVariable(
            self.module, string_constant.type, name=f".str_{self.string_literal_count}")
        string_global.linkage = "internal"
        string_global.global_constant = True
        string_global.initializer = string_constant
        return self.builder.bitcast(string_global, self.char_pointer_type), "str"

    def visit_ArrayLiteralNode(self, node):
        if not node.elements:
            raise TypeError(
                "An empty [] needs a list type so its element type is known, "
                "for example: val names : list[str] = []"
            )
        elems = []
        elem_ty = None
        for expr in node.elements:
            value, val_ty = self.visit_as(expr, elem_ty) if elem_ty else self.visit(expr)
            if elem_ty is None:
                elem_ty = val_ty
            elif val_ty != elem_ty:
                raise TypeError("Array elements must all have the same type")
            elems.append(value)
        return ArrayLiteralValue(elems, elem_ty), "array"

    def visit_DictionaryLiteralNode(self, node):
        if not node.entries:
            raise TypeError("Dictionaries must contain at least one typed field")
        entries = []
        seen_keys = set()
        for key, decl_ty, expr in node.entries:
            if key in seen_keys:
                raise SyntaxError(f"Duplicate dictionary field '{key}'")
            seen_keys.add(key)
            decl_ty = self.resolve_type(decl_ty)
            value, val_ty = self.visit_as(expr, decl_ty)
            if val_ty != decl_ty:
                raise TypeError(
                    f"Dictionary field '{key}' expects {describe_type(decl_ty)}, got {describe_type(val_ty)}")
            entries.append((key, decl_ty, value))
        return DictionaryLiteralValue(entries), "dictionary"

    def visit_MapLiteralNode(self, node):
        raise TypeError(
            "A { } map literal needs a map type so its key and value types are known, "
            "for example: val ages : map[str, int] = {\"Ada\": 36}"
        )

    def visit_VariableAccessNode(self, node):
        variable_type = self.require_variable(node.variable_name)
        if variable_type in ("array", "dictionary"):
            raise TypeError(f"Use an index or field to read '{node.variable_name}'")
        ptr = self.variable_pointers[node.variable_name]
        if variable_type.startswith("class:"):
            return self.load_typed(ptr, variable_type)
        return self.builder.load(ptr, name=f"{node.variable_name}_value"), variable_type

    def visit_ArrayAccessNode(self, node):
        target = node.array
        is_storage = isinstance(target, VariableAccessNode) and (
            self.type_information.get(target.variable_name) == "array"
            or str(self.type_information.get(target.variable_name)).startswith("pointer:")
        )
        if not is_storage and not isinstance(target, (ArrayLiteralNode, MapLiteralNode)):
            value, val_ty = self.visit(target)
            if val_ty.startswith("tuple["):
                return self.tuple_element(value, val_ty, node.index)
            if val_ty == "str":
                return self.call_runtime("vamp_str_at", ("str", "i32"), "char", [value, self.visit_index(node.index)])
            if val_ty.startswith("list:"):
                elem_ty = val_ty[5:]
                ptr = self.list_element_pointer(value, self.visit_index(node.index), elem_ty)
                return self.load_typed(ptr, elem_ty)
            if val_ty.startswith("map:"):
                _, key_ty, elem_ty = val_ty.split(":", 2)
                key = self.map_key(node.index, key_ty)
                return self.load_typed(self.map_slot(value, key, key_ty, elem_ty, create=False), elem_ty)
            if isinstance(target, VariableAccessNode):
                raise TypeError(f"'{target.variable_name}' is not an array, list, map, string or pointer")
            raise TypeError(f"Values of type {describe_type(val_ty)} cannot be indexed")
        ptr, elem_ty, _ = self.element_pointer(node, for_write=False)
        return self.load_typed(ptr, elem_ty)

    def visit_DictionaryAccessNode(self, node):
        base = node.dictionary
        if isinstance(base, VariableAccessNode):
            name = base.variable_name
            if name not in self.type_information and name in self.enum_definitions:
                members = self.enum_definitions[name]
                if node.key not in members:
                    close = suggest(node.key, members)
                    msg = f"Enum '{name}' has no member '{node.key}'"
                    if close:
                        msg += f" (did you mean '{close}'?)"
                    raise NameError(msg)
                return ir.Constant(self.int32_type, members[node.key]), f"enum:{name}"
            variable_type = self.require_variable(name)
            if variable_type == "dictionary":
                field = self.dictionary_information[name].get(node.key)
                if field is None:
                    raise NameError(f"Dictionary has no field '{node.key}'")
                ptr = self.builder.gep(
                    self.variable_pointers[name],
                    [ir.Constant(self.int32_type, 0), ir.Constant(self.int32_type, field[0])],
                    name=f"{name}_{node.key}_pointer",
                )
                return self.load_typed(ptr, field[1])
            if not variable_type.startswith(("class:", "optional:class:")):
                raise TypeError(f"'{name}' does not have readable fields")
        value, val_ty = self.visit(base)
        if val_ty.startswith("optional:class:"):
            if self.is_reference_class(val_ty[15:]):
                value, val_ty = ClassInstanceValue(self.as_value(value), reference=True), val_ty[9:]
            else:
                value, val_ty = self.unwrap_optional(value, val_ty, f"read field '{node.key}' of none")
        if not isinstance(value, ClassInstanceValue):
            raise TypeError(f"Values of type {describe_type(val_ty)} do not have fields")
        ptr, field_ty, _ = self.class_field_pointer(value.pointer, val_ty[6:], node.key)
        return self.load_typed(ptr, field_ty)

    def visit_operands(self, left_node, right_node):
        left_literal = is_number_literal(left_node)
        right_literal = is_number_literal(right_node)
        if left_literal and right_literal:
            if left_node.literal_type != right_node.literal_type:
                lhs, lhs_ty = self.visit_as(left_node, "float")
                rhs, rhs_ty = self.visit_as(right_node, "float")
                return lhs, lhs_ty, rhs, rhs_ty
        elif left_literal:
            rhs, rhs_ty = self.visit(right_node)
            lhs, lhs_ty = self.visit_as(left_node, rhs_ty)
            return lhs, lhs_ty, rhs, rhs_ty
        lhs, lhs_ty = self.visit(left_node)
        rhs, rhs_ty = self.visit_as(right_node, lhs_ty) if right_literal else self.visit(right_node)
        return lhs, lhs_ty, rhs, rhs_ty

    def visit_BinaryOpNode(self, node):
        lhs, lhs_ty, rhs, rhs_ty = self.visit_operands(node.left, node.right)
        return self.apply_binary(node.operator, lhs, lhs_ty, rhs, rhs_ty)

    def apply_binary(self, operator, left_value, left_type, right_value, right_type):
        if left_type.startswith("class:"):
            return self.operator_method(operator, left_value, left_type, right_value, right_type)
        if operator == "+" and (left_type == "str" or right_type == "str"):
            if left_type != "str":
                left_value, _ = self.cast_value(left_value, left_type, "str")
            if right_type != "str":
                right_value, _ = self.cast_value(right_value, right_type, "str")
            concat = self.runtime_function(
                "vamp_str_concat2", self.char_pointer_type, [self.char_pointer_type, self.char_pointer_type])
            return self.builder.call(concat, [left_value, right_value], name="joined"), "str"

        if left_type != right_type:
            raise TypeError(f"Type mismatch: {describe_type(left_type)} {operator} {describe_type(right_type)}")

        builder = self.builder
        if left_type in INTEGER_BITS:
            unsigned = left_type in UNSIGNED_TYPES
            operations = {
                "+": builder.add, "-": builder.sub, "*": builder.mul,
                "/": builder.udiv if unsigned else builder.sdiv,
                "%": builder.urem if unsigned else builder.srem,
                "&": builder.and_, "|": builder.or_, "^": builder.xor,
                "<<": builder.shl, ">>": builder.lshr if unsigned else builder.ashr,
            }
            if operator in ("/", "%"):
                return self.checked_division(operator, left_value, right_value, unsigned), left_type
            if operator in operations:
                return operations[operator](left_value, right_value), left_type
        elif left_type in FLOAT_TYPES:
            operations = {"+": builder.fadd, "-": builder.fsub, "*": builder.fmul, "/": builder.fdiv,
                          "%": builder.frem}
            if operator in operations:
                return operations[operator](left_value, right_value), left_type
        elif left_type == "bool":
            operations = {"&": builder.and_, "|": builder.or_, "^": builder.xor}
            if operator in operations:
                return operations[operator](left_value, right_value), "bool"
        raise SyntaxError(f"Unsupported binary operator '{operator}' for type '{describe_type(left_type)}'")

    # x / 0 and INT_MIN / -1 both trap on x86, so check first. const divisors skip it
    def checked_division(self, operator, left, right, unsigned):
        builder = self.builder
        kind = right.type
        if isinstance(right, ir.Constant) and right.constant not in (0, -1):
            if operator == "/":
                return builder.udiv(left, right) if unsigned else builder.sdiv(left, right)
            return builder.urem(left, right) if unsigned else builder.srem(left, right)
        fn = builder.function
        bad = fn.append_basic_block(name="divide_by_zero")
        good = fn.append_basic_block(name="divide_ok")
        builder.cbranch(builder.icmp_unsigned("==", right, ir.Constant(kind, 0)), bad, good)
        builder.position_at_end(bad)
        self.throw_now("division by zero" if operator == "/" else "modulo by zero")
        builder.position_at_end(good)
        if unsigned:
            return builder.udiv(left, right) if operator == "/" else builder.urem(left, right)
        minus_one = builder.icmp_signed("==", right, ir.Constant(kind, -1))
        safe = builder.select(minus_one, ir.Constant(kind, 1), right)
        if operator == "/":
            return builder.select(minus_one, builder.sub(ir.Constant(kind, 0), left), builder.sdiv(left, safe))
        return builder.select(minus_one, ir.Constant(kind, 0), builder.srem(left, safe))

    def visit_UnaryOpNode(self, node):
        value, val_ty = self.visit(node.operand)
        if node.operator == "-" and val_ty.startswith("class:"):
            res = self.call_method_with_values(value, val_ty, "-", [])
            if res is None:
                raise TypeError(f"'{val_ty[6:]}' has no unary operator -; add: func -() : {val_ty[6:]}")
            return res
        if node.operator == "-":
            if val_ty in INTEGER_BITS:
                return self.builder.neg(value), val_ty
            if val_ty in FLOAT_TYPES:
                return self.builder.fsub(ir.Constant(value.type, -0.0), value), val_ty
        elif node.operator == "!":
            if val_ty == "bool":
                return self.builder.not_(value), "bool"
            raise TypeError(f"'!' needs a bool, got {describe_type(val_ty)}")
        elif node.operator == "~":
            if val_ty in INTEGER_BITS:
                return self.builder.not_(value), val_ty
        raise TypeError(f"Operator '{node.operator}' cannot be used on {describe_type(val_ty)}")

    def visit_LogicalNode(self, node):
        lhs, lhs_ty = self.visit(node.left)
        if lhs_ty != "bool":
            raise TypeError(f"'{node.operator}' needs bool values, got {describe_type(lhs_ty)}")
        fn = self.builder.function
        right_block = fn.append_basic_block(name="logical_right")
        end_block = fn.append_basic_block(name="logical_end")
        start_block = self.builder.block
        if node.operator == "&&":
            self.builder.cbranch(lhs, right_block, end_block)
        else:
            self.builder.cbranch(lhs, end_block, right_block)
        self.builder.position_at_end(right_block)
        rhs, rhs_ty = self.visit(node.right)
        if rhs_ty != "bool":
            raise TypeError(f"'{node.operator}' needs bool values, got {describe_type(rhs_ty)}")
        right_end = self.builder.block
        self.builder.branch(end_block)
        self.builder.position_at_end(end_block)
        res = self.builder.phi(self.bool_type, name="logical_result")
        res.add_incoming(ir.Constant(self.bool_type, 0 if node.operator == "&&" else 1), start_block)
        res.add_incoming(rhs, right_end)
        return res, "bool"

    def visit_ComparisonNode(self, node):
        lhs, lhs_ty, rhs, rhs_ty = self.visit_operands(node.left, node.right)
        return self.compare_values(node.operator, lhs, lhs_ty, rhs, rhs_ty)

    def compare_values(self, operator, left_value, left_type, right_value, right_type):
        if left_type == "none" and right_type == "none":
            return ir.Constant(self.bool_type, 1 if operator == "==" else 0), "bool"
        if right_type == "none":
            return self.compare_with_none(operator, left_value, left_type)
        if left_type == "none":
            return self.compare_with_none(operator, right_value, right_type)
        if left_type.startswith("class:"):
            return self.operator_method(operator, left_value, left_type, right_value, right_type)
        if left_type.startswith("interface:") and right_type.startswith("interface:") and operator in ("==", "!="):
            left = self.builder.extract_value(self.as_value(left_value), 0)
            right = self.builder.extract_value(self.as_value(right_value), 0)
            return self.builder.icmp_unsigned(operator, left, right), "bool"
        if left_type != right_type:
            raise TypeError(f"Cannot compare {describe_type(left_type)} with {describe_type(right_type)}")
        if left_type in FLOAT_TYPES:
            if operator == "!=":
                return self.builder.fcmp_unordered(operator, left_value, right_value), "bool"
            return self.builder.fcmp_ordered(operator, left_value, right_value), "bool"
        if left_type == "str":
            comparison = self.builder.call(self.strcmp_function, [left_value, right_value])
            return self.builder.icmp_signed(operator, comparison, ir.Constant(self.int32_type, 0)), "bool"
        if left_type == "bool" and operator not in ("==", "!="):
            raise SyntaxError("Boolean values only support == and != comparisons")
        if left_type in UNSIGNED_TYPES:
            return self.builder.icmp_unsigned(operator, left_value, right_value), "bool"
        if left_type in INTEGER_BITS or left_type == "bool" or left_type.startswith("enum:"):
            return self.builder.icmp_signed(operator, left_value, right_value), "bool"
        raise SyntaxError(f"Values of type '{describe_type(left_type)}' cannot be compared")

    def visit_CastNode(self, node):
        tgt_ty = node.target_type
        if is_number_literal(node.expression) and (tgt_ty in INTEGER_BITS or tgt_ty in FLOAT_TYPES):
            if node.expression.literal_type == "int" or tgt_ty in FLOAT_TYPES:
                return self.visit_as(node.expression, tgt_ty)
        value, val_ty = self.visit(node.expression)
        return self.cast_value(value, val_ty, tgt_ty)

    def cast_value(self, value, value_type, target_type):
        if value_type == target_type:
            return value, target_type
        builder = self.builder
        src_ty = value_type
        if src_ty.startswith("enum:") and target_type != "str":
            src_ty = "i32"
            if target_type == "i32":
                return value, "i32"
        if src_ty == "char" and target_type != "str":
            src_ty = "u8"
        source_integer = src_ty in INTEGER_BITS
        source_float = src_ty in FLOAT_TYPES
        target_llvm = self.llvm_type_for(target_type) if target_type != "str" else None
        target_integer = target_type in INTEGER_BITS or target_type == "char"
        target_bits = 8 if target_type == "char" else INTEGER_BITS.get(target_type)

        if target_integer:
            if source_integer:
                source_bits = INTEGER_BITS[src_ty]
                if source_bits == target_bits:
                    return value, target_type
                if source_bits > target_bits:
                    return builder.trunc(value, target_llvm), target_type
                if src_ty in UNSIGNED_TYPES:
                    return builder.zext(value, target_llvm), target_type
                return builder.sext(value, target_llvm), target_type
            if source_float:
                if target_type in UNSIGNED_TYPES:
                    return builder.fptoui(value, target_llvm), target_type
                return builder.fptosi(value, target_llvm, name="cast_int"), target_type
            if src_ty == "bool":
                return builder.zext(value, target_llvm, name="cast_int"), target_type
            if src_ty == "str" and target_type != "char":
                parse = self.runtime_function("vamp_str_to_i64", self.int64_type, [self.char_pointer_type])
                wide = builder.call(parse, [value])
                return (wide if target_bits == 64 else builder.trunc(wide, target_llvm)), target_type
        elif target_type in FLOAT_TYPES:
            if source_integer:
                if src_ty in UNSIGNED_TYPES:
                    return builder.uitofp(value, target_llvm), target_type
                return builder.sitofp(value, target_llvm, name="cast_float"), target_type
            if source_float:
                if target_type == "float":
                    return builder.fpext(value, target_llvm), target_type
                return builder.fptrunc(value, target_llvm), target_type
            if src_ty == "bool":
                return builder.uitofp(value, target_llvm, name="cast_float"), target_type
            if src_ty == "str":
                parse = self.runtime_function("vamp_str_to_f64", ir.DoubleType(), [self.char_pointer_type])
                parsed = builder.call(parse, [value], name="parsed")
                if target_type == "float":
                    return parsed, "float"
                return builder.fptrunc(parsed, self.float_type, name="fptrunc_tmp"), "f32"
        elif target_type == "bool":
            if source_integer:
                return builder.icmp_signed("!=", value, ir.Constant(value.type, 0), name="cast_bool"), "bool"
            if source_float:
                return builder.fcmp_ordered("!=", value, ir.Constant(value.type, 0.0), name="cast_bool"), "bool"
            if src_ty == "str":
                true_string = self.visit_LiteralNode(LiteralNode("str", "true"))[0]
                one_string = self.visit_LiteralNode(LiteralNode("str", "1"))[0]
                zero = ir.Constant(self.int32_type, 0)
                is_true = builder.icmp_signed("==", builder.call(self.strcmp_function, [value, true_string]), zero)
                is_one = builder.icmp_signed("==", builder.call(self.strcmp_function, [value, one_string]), zero)
                return builder.or_(is_true, is_one, name="cast_bool"), "bool"
        elif target_type == "str":
            if isinstance(value, ArrayLiteralValue):
                parts = [self.quoted_text(elem, value.element_type) for elem in value.elements]
                joined = []
                for idx, part in enumerate(parts):
                    joined += [self.string_constant(", "), part] if idx else [part]
                return self.concat_strings([self.string_constant("["), *joined, self.string_constant("]")]), "str"
            if self.is_collection_type(value_type):
                return self.collection_text(value, value_type), "str"
            if value_type.startswith(("class:", "interface:", "optional:")):
                return self.object_text(value, value_type), "str"
            if value_type == "bool":
                true_string = self.visit_LiteralNode(LiteralNode("str", "true"))[0]
                false_string = self.visit_LiteralNode(LiteralNode("str", "false"))[0]
                return builder.select(value, true_string, false_string), "str"
            if value_type.startswith("enum:"):
                return builder.call(self.get_enum_name_function(value_type[5:]), [value]), "str"
            if value_type == "char":
                buf = self.allocate_bytes(ir.Constant(self.int32_type, 2), name="char_string")
                builder.store(value, buf)
                builder.store(ir.Constant(self.int8_type, 0), builder.gep(buf, [ir.Constant(self.int32_type, 1)]))
                return buf, "str"
            if value_type in INTEGER_BITS:
                unsigned = value_type in UNSIGNED_TYPES
                wide = self.fit_integer(value, self.int64_type, unsigned=unsigned)
                symbol = "vamp_str_from_u64" if unsigned else "vamp_str_from_i64"
                return builder.call(self.runtime_function(
                    symbol, self.char_pointer_type, [self.int64_type]), [wide]), "str"
            formatted = self.printf_argument(value, value_type)
            if formatted is not None:
                format_text, arg = formatted
                buffer_size = ir.Constant(self.int32_type, 64)
                buf = self.allocate_bytes(buffer_size, name="string_buffer")
                format_string = self.visit_LiteralNode(LiteralNode("str", format_text))[0]
                builder.call(self.snprintf_function, [buf, buffer_size, format_string, arg])
                return buf, "str"
        raise TypeError(
            f"Casting from {describe_type(value_type)} to {describe_type(target_type)} is not supported.")

    def printf_argument(self, value, value_type):
        if value_type in INTEGER_BITS:
            bits = INTEGER_BITS[value_type]
            if value_type in UNSIGNED_TYPES:
                if bits == 64:
                    return "%llu", value
                return "%u", (value if bits == 32 else self.builder.zext(value, self.int32_type))
            if bits == 64:
                return "%lld", value
            return "%d", (value if bits == 32 else self.builder.sext(value, self.int32_type))
        if value_type == "f32":
            return "%f", self.builder.fpext(value, self.double_type)
        if value_type == "float":
            return "%f", value
        return None

    def visit_block(self, statements):
        for stmt in statements:
            if self.builder.block.is_terminated:
                break
            self.visit(stmt)

    def visit_scoped_block(self, statements):
        saved = self.save_scope()
        self.block_depth += 1
        try:
            self.visit_block(statements)
        finally:
            self.block_depth -= 1
            self.restore_scope(saved)

    def visit_condition(self, condition, what):
        value, val_ty = self.visit(condition)
        if val_ty != "bool":
            raise TypeError(f"{what} condition must be bool, got {describe_type(val_ty)}")
        return value

    def visit_IfNode(self, node):
        fn = self.builder.function
        merge_block = fn.append_basic_block(name="if_end")
        for cond, body in node.branches:
            condition_value = self.visit_condition(cond, "if")
            body_block = fn.append_basic_block(name="if_body")
            next_block = fn.append_basic_block(name="if_next")
            self.builder.cbranch(condition_value, body_block, next_block)
            self.builder.position_at_end(body_block)
            self.visit_scoped_block(body)
            if not self.builder.block.is_terminated:
                self.builder.branch(merge_block)
            self.builder.position_at_end(next_block)
        if node.else_body is not None:
            self.visit_scoped_block(node.else_body)
        if not self.builder.block.is_terminated:
            self.builder.branch(merge_block)
        self.builder.position_at_end(merge_block)

    def visit_loop_body(self, body, continue_block, break_block):
        self.loop_stack.append((continue_block, break_block, self.try_depth))
        try:
            self.visit_block(body)
        finally:
            self.loop_stack.pop()
        if not self.builder.block.is_terminated:
            self.builder.branch(continue_block)

    def visit_WhileLoopNode(self, node):
        fn = self.builder.function
        condition_block = fn.append_basic_block(name="while_condition")
        body_block = fn.append_basic_block(name="while_body")
        end_block = fn.append_basic_block(name="while_end")
        self.builder.branch(condition_block)
        self.builder.position_at_end(condition_block)
        self.builder.cbranch(self.visit_condition(node.condition, "while"), body_block, end_block)
        self.builder.position_at_end(body_block)
        saved = self.save_scope()
        self.block_depth += 1
        self.visit_loop_body(node.body, condition_block, end_block)
        self.block_depth -= 1
        self.restore_scope(saved)
        self.builder.position_at_end(end_block)

    def visit_BreakNode(self, node):
        if not self.loop_stack:
            raise SyntaxError("'break' can only be used inside a loop")
        _, break_block, try_depth = self.loop_stack[-1]
        self.emit_try_pops(self.try_depth - try_depth)
        self.builder.branch(break_block)

    def visit_ContinueNode(self, node):
        if not self.loop_stack:
            raise SyntaxError("'continue' can only be used inside a loop")
        continue_block, _, try_depth = self.loop_stack[-1]
        self.emit_try_pops(self.try_depth - try_depth)
        self.builder.branch(continue_block)

    def emit_index_loop(self, item_name, body, get_length, bind_item):
        fn = self.builder.function
        int64 = self.int64_type
        index_pointer = self.entry_alloca(int64, "for_index")
        self.builder.store(ir.Constant(int64, 0), index_pointer)
        condition_block = fn.append_basic_block(name="for_condition")
        body_block = fn.append_basic_block(name="for_body")
        step_block = fn.append_basic_block(name="for_step")
        end_block = fn.append_basic_block(name="for_end")
        self.builder.branch(condition_block)

        self.builder.position_at_end(condition_block)
        idx = self.builder.load(index_pointer, name="for_index_value")
        self.builder.cbranch(self.builder.icmp_signed("<", idx, get_length()), body_block, end_block)

        self.builder.position_at_end(body_block)
        saved = self.save_scope()
        self.block_depth += 1
        bind_item(idx)
        self.visit_loop_body(body, step_block, end_block)
        self.block_depth -= 1
        self.restore_scope(saved)

        self.builder.position_at_end(step_block)
        self.builder.store(
            self.builder.add(self.builder.load(index_pointer), ir.Constant(int64, 1)), index_pointer)
        self.builder.branch(condition_block)
        self.builder.position_at_end(end_block)

    def bind_copy(self, item_name, element_pointer, element_type):
        storage = self.entry_alloca(self.llvm_type_for(element_type), item_name)
        self.builder.store(self.builder.load(element_pointer), storage)
        self.bind_variable(item_name, storage, element_type)

    def emit_array_loop(self, array_pointer, element_type, array_length, item_name, body):
        def bind_item(index):
            ptr = self.builder.gep(
                array_pointer, [ir.Constant(self.int32_type, 0), index], name=f"{item_name}_pointer")
            self.bind_variable(item_name, ptr, element_type)

        self.emit_index_loop(item_name, body, lambda: ir.Constant(self.int64_type, array_length), bind_item)

    def materialize_array(self, array_value, array_name):
        array_type = ir.ArrayType(self.llvm_type_for(array_value.element_type), len(array_value.elements))
        array_pointer = self.entry_alloca(array_type, array_name)
        for idx, elem in enumerate(array_value.elements):
            self.builder.store(self.as_value(elem), self.builder.gep(
                array_pointer, [ir.Constant(self.int32_type, 0), ir.Constant(self.int32_type, idx)]))
        return array_pointer

    def emit_unrolled_loop(self, item_name, body, items):
        fn = self.builder.function
        end_block = fn.append_basic_block(name="for_end")
        for ptr, item_ty in items:
            next_block = fn.append_basic_block(name="for_next_field")
            saved = self.save_scope()
            self.block_depth += 1
            self.bind_variable(item_name, ptr, item_ty)
            self.visit_loop_body(body, next_block, end_block)
            self.block_depth -= 1
            self.restore_scope(saved)
            self.builder.position_at_end(next_block)
        self.builder.branch(end_block)
        self.builder.position_at_end(end_block)

    def emit_range_loop(self, node):
        args = node.iterable.arguments
        if not 1 <= len(args) <= 3:
            raise TypeError("range expects 1 to 3 arguments: range(stop), range(start, stop) or range(start, stop, step)")
        vals = []
        for arg in args:
            value, val_ty = self.visit_as(arg, "int")
            if val_ty != "int":
                raise TypeError(f"range arguments must be int, got {describe_type(val_ty)}")
            vals.append(value)
        int64 = self.int64_type
        zero = ir.Constant(int64, 0)
        start = vals[0] if len(vals) > 1 else zero
        stop = vals[1] if len(vals) > 1 else vals[0]
        step = vals[2] if len(vals) == 3 else ir.Constant(int64, 1)
        if len(args) == 3 and isinstance(args[2], LiteralNode) and args[2].value == 0:
            raise ValueError("range step cannot be 0")

        fn = self.builder.function
        counter = self.entry_alloca(int64, node.item_name)
        self.builder.store(start, counter)
        condition_block = fn.append_basic_block(name="range_condition")
        body_block = fn.append_basic_block(name="range_body")
        step_block = fn.append_basic_block(name="range_step")
        end_block = fn.append_basic_block(name="range_end")
        self.builder.branch(condition_block)

        self.builder.position_at_end(condition_block)
        cur = self.builder.load(counter)
        ascending = self.builder.icmp_signed("<", cur, stop)
        if len(vals) == 3:
            descending = self.builder.icmp_signed(">", cur, stop)
            in_range = self.builder.select(self.builder.icmp_signed(">", step, zero), ascending, descending)
        else:
            in_range = ascending
        self.builder.cbranch(in_range, body_block, end_block)

        self.builder.position_at_end(body_block)
        saved = self.save_scope()
        self.block_depth += 1
        self.bind_variable(node.item_name, counter, "int")
        self.visit_loop_body(node.body, step_block, end_block)
        self.block_depth -= 1
        self.restore_scope(saved)

        self.builder.position_at_end(step_block)
        self.builder.store(self.builder.add(self.builder.load(counter), step), counter)
        self.builder.branch(condition_block)
        self.builder.position_at_end(end_block)

    def emit_map_loop(self, map_value, map_type, item_name, body):
        _, key_ty, _ = map_type.split(":", 2)
        fn = self.builder.function
        int32 = self.int32_type
        cursor = self.entry_alloca(int32, "map_cursor")
        self.builder.store(ir.Constant(int32, 0), cursor)
        condition_block = fn.append_basic_block(name="map_condition")
        body_block = fn.append_basic_block(name="map_body")
        step_block = fn.append_basic_block(name="map_step")
        end_block = fn.append_basic_block(name="map_end")
        self.builder.branch(condition_block)

        self.builder.position_at_end(condition_block)
        found, _ = self.call_runtime(
            "vamp_map_next", (map_type, "i32"), "i32", [map_value, self.builder.load(cursor)])
        self.builder.store(found, cursor)
        self.builder.cbranch(
            self.builder.icmp_signed(">=", found, ir.Constant(int32, 0)), body_block, end_block)

        self.builder.position_at_end(body_block)
        saved = self.save_scope()
        self.block_depth += 1
        key = self.map_key_at(map_value, map_type, found)
        storage = self.entry_alloca(self.llvm_type_for(key_ty), item_name)
        self.builder.store(key, storage)
        self.bind_variable(item_name, storage, key_ty)
        self.visit_loop_body(body, step_block, end_block)
        self.block_depth -= 1
        self.restore_scope(saved)

        self.builder.position_at_end(step_block)
        self.builder.store(self.builder.add(self.builder.load(cursor), ir.Constant(int32, 1)), cursor)
        self.builder.branch(condition_block)
        self.builder.position_at_end(end_block)

    def visit_ForLoopNode(self, node):
        iterable = node.iterable
        if isinstance(iterable, DictionaryAccessNode) and iterable.key == "values" and isinstance(
                iterable.dictionary, VariableAccessNode) and self.type_information.get(
                iterable.dictionary.variable_name) == "dictionary":
            name = iterable.dictionary.variable_name
            items = []
            for field_name, (field_index, field_ty) in self.dictionary_information[name].items():
                ptr = self.builder.gep(
                    self.variable_pointers[name],
                    [ir.Constant(self.int32_type, 0), ir.Constant(self.int32_type, field_index)],
                    name=f"{name}_{field_name}_value_pointer",
                )
                items.append((ptr, field_ty))
            self.emit_unrolled_loop(node.item_name, node.body, items)
            return

        if isinstance(iterable, FunctionCallNode) and iterable.function_name == "range" \
                and "range" not in self.function_overloads:
            self.emit_range_loop(node)
            return

        if isinstance(iterable, VariableAccessNode):
            collection_type = self.type_information.get(iterable.variable_name)
            if collection_type == "array":
                info = self.array_information[iterable.variable_name]
                self.emit_array_loop(
                    self.variable_pointers[iterable.variable_name], info["element_type"],
                    info["length"], node.item_name, node.body)
                return
            if collection_type == "dictionary":
                self.emit_dictionary_key_loop(
                    list(self.dictionary_information[iterable.variable_name]), node.item_name, node.body)
                return

        value, val_ty = self.visit(iterable)
        if isinstance(value, ArrayLiteralValue):
            ptr = self.materialize_array(value, f"{node.item_name}_array")
            self.emit_array_loop(ptr, value.element_type, len(value.elements), node.item_name, node.body)
            return
        if isinstance(value, DictionaryLiteralValue):
            self.emit_dictionary_key_loop(
                [field_name for field_name, _, _ in value.entries], node.item_name, node.body)
            return
        if val_ty.startswith("list:"):
            elem_ty = val_ty[5:]

            def bind_item(index):
                ptr = self.builder.gep(self.list_data(value, elem_ty), [index])
                self.bind_copy(node.item_name, ptr, elem_ty)

            self.emit_index_loop(node.item_name, node.body, lambda: self.list_length(value), bind_item)
            return
        if val_ty.startswith("map:"):
            self.emit_map_loop(value, val_ty, node.item_name, node.body)
            return
        if val_ty.startswith("set:"):
            self.emit_map_loop(value, self.set_map_type(val_ty), node.item_name, node.body)
            return
        if val_ty.startswith("class:"):
            return self.emit_iterator_loop(value, val_ty, node)
        if val_ty == "str":
            length = self.builder.sext(self.builder.call(self.strlen_function, [value]), self.int64_type)

            def bind_character(index):
                self.bind_copy(node.item_name, self.builder.gep(value, [index]), "char")

            self.emit_index_loop(node.item_name, node.body, lambda: length, bind_character)
            return
        raise TypeError(f"For loops cannot iterate over values of type '{describe_type(val_ty)}'")

    def emit_dictionary_key_loop(self, field_names, item_name, body):
        key_values = [self.visit_LiteralNode(LiteralNode("str", field_name))[0] for field_name in field_names]
        key_pointer = self.materialize_array(ArrayLiteralValue(key_values, "str"), f"{item_name}_keys")
        self.emit_array_loop(key_pointer, "str", len(field_names), item_name, body)

    def visit_MatchNode(self, node):
        subject, subject_type = self.visit(node.subject)
        if isinstance(subject, (ClassInstanceValue, ArrayLiteralValue, DictionaryLiteralValue)):
            raise TypeError(f"match cannot compare values of type {describe_type(subject_type)}")
        fn = self.builder.function
        end_block = fn.append_basic_block(name="match_end")
        for patterns, body in node.cases:
            matched = None
            for pat in patterns:
                pattern_value, pattern_type = self.visit_as(pat, subject_type)
                if pattern_type != subject_type:
                    raise TypeError(
                        f"A match pattern of type {describe_type(pattern_type)} cannot match a value "
                        f"of type {describe_type(subject_type)}"
                    )
                equal, _ = self.compare_values("==", subject, subject_type, pattern_value, pattern_type)
                matched = equal if matched is None else self.builder.or_(matched, equal)
            body_block = fn.append_basic_block(name="match_body")
            next_block = fn.append_basic_block(name="match_next")
            self.builder.cbranch(matched, body_block, next_block)
            self.builder.position_at_end(body_block)
            self.visit_scoped_block(body)
            if not self.builder.block.is_terminated:
                self.builder.branch(end_block)
            self.builder.position_at_end(next_block)
        if node.else_body is not None:
            self.visit_scoped_block(node.else_body)
        if not self.builder.block.is_terminated:
            self.builder.branch(end_block)
        self.builder.position_at_end(end_block)

    def emit_try_pops(self, count):
        if count > 0:
            pop = self.runtime_function("vamp_try_pop", ir.VoidType(), [])
            for _ in range(count):
                self.builder.call(pop, [])

    def visit_TryNode(self, node):
        self.function_has_try = True
        ptr = self.char_pointer_type
        push = self.runtime_function("vamp_try_push", ptr, [])
        set_jump = self.module.globals.get("_setjmp")
        if set_jump is None:
            set_jump = ir.Function(self.module, ir.FunctionType(self.int32_type, [ptr, ptr]), name="_setjmp")
            set_jump.attributes.add("returns_twice")
        fn = self.builder.function
        body_block = fn.append_basic_block(name="try_body")
        catch_block = fn.append_basic_block(name="try_catch")
        end_block = fn.append_basic_block(name="try_end")
        buf = self.builder.call(push, [])
        arrived = self.builder.call(set_jump, [buf, ir.Constant(ptr, None)])
        self.builder.cbranch(
            self.builder.icmp_signed("==", arrived, ir.Constant(self.int32_type, 0)), body_block, catch_block)

        self.builder.position_at_end(body_block)
        self.try_depth += 1
        self.visit_scoped_block(node.body)
        self.try_depth -= 1
        if not self.builder.block.is_terminated:
            self.emit_try_pops(1)
            self.builder.branch(end_block)

        self.builder.position_at_end(catch_block)
        saved = self.save_scope()
        self.block_depth += 1
        if node.error_name is not None:
            msg = self.builder.call(self.runtime_function("vamp_error_message", ptr, []), [])
            storage = self.entry_alloca(ptr, node.error_name)
            self.builder.store(msg, storage)
            self.bind_variable(node.error_name, storage, "str")
        self.visit_block(node.catch_body)
        self.block_depth -= 1
        self.restore_scope(saved)
        if not self.builder.block.is_terminated:
            self.builder.branch(end_block)
        self.builder.position_at_end(end_block)

    def visit_ThrowNode(self, node):
        msg, message_type = self.visit(node.expression)
        if message_type != "str":
            msg, _ = self.cast_value(msg, message_type, "str")
        self.builder.call(self.runtime_function("vamp_throw", ir.VoidType(), [self.char_pointer_type]), [msg])
        self.builder.unreachable()

    def declare_function(self, node):
        params = [(name, self.resolve_type(ty_name)) for name, ty_name in node.parameters]
        ret_ty = self.resolve_type(node.return_type)
        overloads = self.function_overloads.setdefault(node.function_name, [])
        signature = tuple(ty_name for _, ty_name in params)
        shown = ", ".join(describe_type(item) for item in signature)
        for other in overloads:
            if other["signature"] == signature:
                raise SyntaxError(
                    f"Function '{node.function_name}({shown})' is already declared with these parameter types")
        symbol = node.function_name if not overloads else f"{node.function_name}${len(overloads)}"
        fn = ir.Function(
            self.module,
            ir.FunctionType(self.llvm_type_for(ret_ty), [self.llvm_type_for(item) for item in signature]),
            name=symbol,
        )
        fn.linkage = "internal"
        info = {
            "name": node.function_name, "parameters": params, "signature": signature,
            "return_type": ret_ty, "function": fn, "defaults": node.defaults,
            "node": node, "emitted": False,
        }
        overloads.append(info)
        self.declared_function_order.append(info)
        self.function_signatures[node.function_name] = params
        node.overload = info
        return info

    def enter_function(self, function, return_type, class_name=None):
        saved = (
            self.builder, self.save_scope(), self.loop_stack, self.try_depth, self.block_depth,
            self.current_return_type, self.current_class, self.function_allocas, self.function_has_try,
        )
        self.builder = ir.IRBuilder(function.append_basic_block(name="entry"))
        self.loop_stack = []
        self.try_depth = 0
        self.block_depth = 0
        self.current_return_type = return_type
        self.current_class = class_name
        self.function_allocas = []
        self.function_has_try = False
        return saved

    def leave_function(self, saved, shown_name):
        if not self.builder.block.is_terminated:
            if self.current_return_type == "void":
                self.builder.ret_void()
            else:
                raise SyntaxError(f"{shown_name} must return a value")
        if self.function_has_try:
            self.keep_variables_in_memory()
        (self.builder, scope, self.loop_stack, self.try_depth, self.block_depth,
         self.current_return_type, self.current_class, self.function_allocas, self.function_has_try) = saved
        self.restore_scope(scope)

    def emit_function_body(self, information):
        information["emitted"] = True
        node = information["node"]
        fn = information["function"]
        saved = self.enter_function(fn, information["return_type"])
        for idx, (parameter_name, parameter_type) in enumerate(information["parameters"]):
            ptr = self.entry_alloca(self.llvm_type_for(parameter_type), parameter_name)
            self.builder.store(fn.args[idx], ptr)
            self.bind_variable(parameter_name, ptr, parameter_type)
        self.visit_block(node.body)
        self.leave_function(saved, f"Function '{node.function_name}'")

    def visit_FunctionDeclarationNode(self, node):
        if getattr(node, "overload", None) is None:
            self.emit_function_body(self.declare_function(node))

    def visit_ReturnNode(self, node):
        expected = self.current_return_type
        if node.return_type == "void" or node.expression is None:
            if expected != "void":
                raise TypeError("A void return can only be used in a void function or method")
            self.emit_try_pops(self.try_depth)
            self.builder.ret_void()
            return None, "void"
        if expected == "void":
            raise TypeError("This function returns nothing, so 'return' cannot give a value")
        value, val_ty = self.visit_as(node.expression, expected)
        annotation = self.resolve_type(node.return_type)
        if annotation is not None and val_ty != annotation:
            raise TypeError(
                f"Return annotation expects {describe_type(annotation)}, got {describe_type(val_ty)}")
        if val_ty != expected:
            raise TypeError(
                f"Return value of type {describe_type(val_ty)} does not match the function return type "
                f"{describe_type(expected)}"
            )
        res = self.as_value(value)
        self.emit_try_pops(self.try_depth)
        self.builder.ret(res)
        return None, "void"

    def prepare_arguments(self, argument_nodes):
        prepared = []
        for node in argument_nodes:
            if is_number_literal(node) or (isinstance(node, LiteralNode) and node.literal_type == "none"):
                prepared.append((node, None, node.literal_type))
            elif isinstance(node, ArrayLiteralNode):
                prepared.append((node, None, "list literal"))
            elif isinstance(node, MapLiteralNode):
                prepared.append((node, None, "map literal"))
            else:
                value, val_ty = self.visit(node)
                prepared.append((node, value, val_ty))
        return prepared

    def argument_fits(self, prepared, parameter_type):
        _, value, val_ty = prepared
        if val_ty == parameter_type:
            return 2
        if value is None:
            if val_ty == "int" and (parameter_type in INTEGER_BITS or parameter_type in FLOAT_TYPES):
                return 1
            if val_ty == "float" and parameter_type == "f32":
                return 1
            if val_ty == "list literal" and parameter_type.startswith("list:"):
                return 2
            if val_ty == "map literal" and parameter_type.startswith("map:"):
                return 2
            if val_ty == "none" and parameter_type.startswith("optional:"):
                return 1
            return 0
        return 1 if self.can_convert(val_ty, parameter_type) else 0

    def finish_argument(self, prepared, parameter_type):
        node, value, val_ty = prepared
        if value is None:
            return self.visit_as(node, parameter_type)
        if val_ty != parameter_type:
            converted = self.convert_value(value, val_ty, parameter_type)
            if converted is not None:
                return converted
        return value, val_ty

    def bind_call_arguments(self, shown_name, kind, parameters, defaults, argument_nodes, prepared=None):
        required = len(parameters) - len(defaults)
        if not required <= len(argument_nodes) <= len(parameters):
            wanted = str(len(parameters)) if required == len(parameters) else f"{required} to {len(parameters)}"
            plural = "" if wanted == "1" else "s"
            raise TypeError(
                f"{kind} '{shown_name}' expects {wanted} argument{plural}, got {len(argument_nodes)}")
        if prepared is None:
            prepared = self.prepare_arguments(argument_nodes)
        vals = []
        for pos, (parameter_name, parameter_type) in enumerate(parameters):
            if pos < len(prepared):
                value, val_ty = self.finish_argument(prepared[pos], parameter_type)
            else:
                value, val_ty = self.visit_as(defaults[pos], parameter_type)
            if val_ty != parameter_type:
                raise TypeError(
                    f"Argument {pos + 1} ('{parameter_name}') of '{shown_name}' expects "
                    f"{describe_type(parameter_type)}, got {describe_type(val_ty)}"
                )
            vals.append(self.as_value(value))
        return vals

    def visit_FunctionCallNode(self, node):
        name = node.function_name
        if name in self.class_definitions:
            return self.create_class_instance(name, node.arguments)
        overloads = self.function_overloads.get(name)
        if overloads is None:
            if name == "len":
                return self.emit_length_call(node)
            if name == "range":
                raise TypeError("range(...) can only be used as the collection of a for loop")
            declared = [item for item in self.function_overloads if "." not in item]
            close = suggest(name, declared + list(self.class_definitions) + ["len"])
            msg = f"Function '{name}' is not declared"
            if close:
                msg += f" (did you mean '{close}'?)"
            raise NameError(msg)

        prepared = None
        if len(overloads) == 1:
            chosen = overloads[0]
        else:
            cnt = len(node.arguments)
            candidates = [
                item for item in overloads
                if len(item["parameters"]) - len(item["defaults"]) <= cnt <= len(item["parameters"])
            ]
            if not candidates:
                raise TypeError(f"No version of function '{name}' takes {cnt} argument{'s' if cnt != 1 else ''}")
            prepared = self.prepare_arguments(node.arguments)
            scored = []
            for candidate in candidates:
                fits = [self.argument_fits(item, candidate["signature"][pos])
                        for pos, item in enumerate(prepared)]
                if all(fits):
                    scored.append((sum(fits), candidate))
            shown = ", ".join(describe_type(item[2]) for item in prepared)
            if not scored:
                options = "\n".join(
                    f"    {name}({', '.join(describe_type(item) for item in candidate['signature'])})"
                    for candidate in overloads
                )
                raise TypeError(f"No version of function '{name}' accepts ({shown})\n  declared versions:\n{options}")
            best = max(score for score, _ in scored)
            winners = [candidate for score, candidate in scored if score == best]
            if len(winners) > 1:
                raise TypeError(f"The call {name}({shown}) matches more than one version of '{name}'")
            chosen = winners[0]

        vals = self.bind_call_arguments(
            name, "Function", chosen["parameters"], chosen["defaults"], node.arguments, prepared)
        ret_ty = chosen["return_type"]
        if ret_ty == "void":
            self.builder.call(chosen["function"], vals)
            return None, "void"
        res = self.builder.call(chosen["function"], vals, name="call_result")
        return self.wrap_value(res, ret_ty), ret_ty

    def emit_length_call(self, node):
        if len(node.arguments) != 1:
            raise TypeError(f"len expects 1 argument, got {len(node.arguments)}")
        arg = node.arguments[0]
        if isinstance(arg, VariableAccessNode) and self.type_information.get(arg.variable_name) == "array":
            return ir.Constant(self.int64_type, self.array_information[arg.variable_name]["length"]), "int"
        value, val_ty = self.visit(arg)
        if val_ty == "str":
            return self.builder.sext(self.builder.call(self.strlen_function, [value]), self.int64_type), "int"
        if val_ty.startswith("list:"):
            return self.list_length(value), "int"
        if val_ty.startswith(("map:", "set:")):
            return self.call_runtime("vamp_map_length", ("str",), "int", [value])
        if isinstance(value, ArrayLiteralValue):
            return ir.Constant(self.int64_type, len(value.elements)), "int"
        raise TypeError(f"len cannot measure a value of type {describe_type(val_ty)}")

    def register_enum(self, node):
        if node.enum_name in self.enum_definitions or node.enum_name in self.class_definitions:
            raise SyntaxError(f"'{node.enum_name}' is already declared")
        self.enum_definitions[node.enum_name] = dict(node.members)

    def visit_EnumDeclarationNode(self, node):
        if node.enum_name not in self.enum_definitions:
            self.register_enum(node)

    def get_enum_name_function(self, enum_name):
        fn = self.enum_name_functions.get(enum_name)
        if fn is not None:
            return fn
        fn = ir.Function(
            self.module, ir.FunctionType(self.char_pointer_type, [self.int32_type]),
            name=f"vamp_enum_name.{enum_name}")
        fn.linkage = "internal"
        self.enum_name_functions[enum_name] = fn
        saved_builder = self.builder
        self.builder = ir.IRBuilder(fn.append_basic_block(name="entry"))
        unknown_block = fn.append_basic_block(name="unknown")
        switch = self.builder.switch(fn.args[0], unknown_block)
        seen = set()
        for member_name, member_value in self.enum_definitions[enum_name].items():
            if member_value in seen:
                continue
            seen.add(member_value)
            block = fn.append_basic_block(name=f"member_{member_name}")
            switch.add_case(ir.Constant(self.int32_type, member_value), block)
            self.builder.position_at_end(block)
            self.builder.ret(self.visit_LiteralNode(LiteralNode("str", member_name))[0])
        self.builder.position_at_end(unknown_block)
        self.builder.ret(self.visit_LiteralNode(LiteralNode("str", "?"))[0])
        self.builder = saved_builder
        return fn

    def ensure_class_registered(self, class_name):
        if class_name in self.class_definitions:
            return
        node = self.pending_classes.get(class_name)
        if node is None:
            return
        if class_name in self.classes_being_registered:
            raise TypeError(
                f"Class '{class_name}' contains itself (directly, or through its fields or parent class)")
        self.classes_being_registered.add(class_name)
        try:
            self.register_class_tree(node)
        finally:
            self.classes_being_registered.discard(class_name)

    def visit_value_method(self, value, value_type, node, receiver):
        if value_type == "str":
            return self.emit_string_method(value, node)
        if value_type.startswith("list:"):
            return self.emit_list_method(value, value_type, node)
        if value_type.startswith("map:"):
            return self.emit_map_method(value, value_type, node)
        if value_type.startswith("set:"):
            return self.emit_set_method(value, value_type, node)
        if value_type == "builder":
            return self.emit_builder_method(value, node)
        if isinstance(receiver, VariableAccessNode):
            raise TypeError(f"'{receiver.variable_name}' is not a class instance")
        raise TypeError(f"Values of type {describe_type(value_type)} have no methods")

    def emit_string_method(self, value, node):
        meth = STRING_METHODS.get(node.method_name)
        if node.method_name == "join":
            raise TypeError("join is a list method: write parts.join(\", \")")
        if meth is None:
            close = suggest(node.method_name, STRING_METHODS)
            msg = f"Strings have no method '{node.method_name}'"
            msg += f" (did you mean '{close}'?)" if close else f"; available: {', '.join(sorted(STRING_METHODS))}"
            raise NameError(msg)
        symbol, parameter_types, ret_ty = meth
        args = self.check_arguments(f"str.{node.method_name}", node.arguments, parameter_types)
        return self.call_runtime(symbol, ("str", *parameter_types), ret_ty, [value, *args])

    def new_list(self, element_type, capacity):
        size = self.size_of(element_type)
        res, _ = self.call_runtime(
            "vamp_list_new", ("i32", "i32"), "list:" + element_type, [size, ir.Constant(self.int32_type, capacity)])
        return res

    def list_header(self, list_value):
        return self.builder.bitcast(list_value, self.list_header_type.as_pointer())

    def list_length(self, list_value):
        zero = ir.Constant(self.int32_type, 0)
        stored = self.builder.load(self.builder.gep(self.list_header(list_value), [zero, zero]), name="list_length")
        return self.builder.sext(stored, self.int64_type)

    def list_data(self, list_value, element_type):
        raw = self.builder.load(self.builder.gep(
            self.list_header(list_value), [ir.Constant(self.int32_type, 0), ir.Constant(self.int32_type, 4)]))
        return self.builder.bitcast(raw, self.llvm_type_for(element_type).as_pointer())

    def list_element_pointer(self, list_value, index, element_type):
        fn = self.builder.function
        length = self.list_length(list_value)
        in_range = self.builder.icmp_unsigned("<", index, length)
        valid_block = fn.append_basic_block(name="list_index_valid")
        invalid_block = fn.append_basic_block(name="list_index_invalid")
        self.builder.cbranch(in_range, valid_block, invalid_block)
        self.builder.position_at_end(invalid_block)
        self.builder.call(
            self.runtime_function("vamp_list_index_error", ir.VoidType(), [self.int32_type, self.int32_type]),
            [self.fit_integer(index, self.int32_type), self.fit_integer(length, self.int32_type)])
        self.builder.unreachable()
        self.builder.position_at_end(valid_block)
        return self.builder.gep(self.list_data(list_value, element_type), [index], name="list_element_pointer")

    def store_into_slot(self, raw_slot, value, value_type):
        typed = self.builder.bitcast(raw_slot, self.llvm_type_for(value_type).as_pointer())
        self.builder.store(self.as_value(value), typed)

    def build_list_literal(self, node, list_type):
        elem_ty = list_type[5:]
        lst = self.new_list(elem_ty, len(node.elements))
        if node.elements:
            resize = self.runtime_function(
                "vamp_list_resize", self.char_pointer_type, [self.char_pointer_type, self.int32_type])
            data = self.builder.bitcast(
                self.builder.call(resize, [lst, ir.Constant(self.int32_type, len(node.elements))]),
                self.llvm_type_for(elem_ty).as_pointer())
            for idx, elem in enumerate(node.elements):
                value, val_ty = self.visit_as(elem, elem_ty)
                if val_ty != elem_ty:
                    raise TypeError(
                        f"Element {idx + 1} of the list is {describe_type(val_ty)}, "
                        f"but the list holds {describe_type(elem_ty)}"
                    )
                self.builder.store(self.as_value(value), self.builder.gep(data, [ir.Constant(self.int32_type, idx)]))
        return lst, list_type

    def spill(self, value, value_type):
        storage = self.entry_alloca(self.llvm_type_for(value_type), "spilled_value")
        self.builder.store(self.as_value(value), storage)
        return self.builder.bitcast(storage, self.char_pointer_type)

    LIST_METHODS = ("push", "pop", "insert", "remove", "clear", "length", "is_empty", "contains", "index_of",
                    "first", "last", "sort", "reverse", "copy", "join")

    def emit_list_method(self, list_value, list_type, node):
        elem_ty = list_type[5:]
        meth = node.method_name
        what = f"list.{meth}"
        ptr = self.char_pointer_type
        int32 = self.int32_type
        zero = ir.Constant(int32, 0)
        if meth == "push":
            value, = self.check_arguments(what, node.arguments, (elem_ty,))
            header = self.list_header(list_value)
            length_pointer = self.builder.gep(header, [zero, zero])
            length = self.builder.load(length_pointer)
            cap = self.builder.load(self.builder.gep(header, [zero, ir.Constant(int32, 1)]))
            fn = self.builder.function
            fast_block = fn.append_basic_block(name="push_fast")
            slow_block = fn.append_basic_block(name="push_grow")
            done_block = fn.append_basic_block(name="push_done")
            self.builder.cbranch(self.builder.icmp_signed("<", length, cap), fast_block, slow_block)
            self.builder.position_at_end(fast_block)
            self.builder.store(self.as_value(value), self.builder.gep(self.list_data(list_value, elem_ty), [length]))
            self.builder.store(self.builder.add(length, ir.Constant(int32, 1)), length_pointer)
            self.builder.branch(done_block)
            self.builder.position_at_end(slow_block)
            slot = self.builder.call(self.runtime_function("vamp_list_push_slot", ptr, [ptr]), [list_value])
            self.store_into_slot(slot, value, elem_ty)
            self.builder.branch(done_block)
            self.builder.position_at_end(done_block)
            return None, "void"
        if meth == "pop":
            self.check_arguments(what, node.arguments, ())
            slot = self.builder.call(self.runtime_function("vamp_list_pop_slot", ptr, [ptr]), [list_value])
            typed = self.builder.bitcast(slot, self.llvm_type_for(elem_ty).as_pointer())
            return self.wrap_value(self.builder.load(typed), elem_ty), elem_ty
        if meth == "insert":
            idx, value = self.check_arguments(what, node.arguments, ("int", elem_ty))
            slot = self.builder.call(
                self.runtime_function("vamp_list_insert_slot", ptr, [ptr, int32]),
                [list_value, self.fit_integer(idx, int32)])
            self.store_into_slot(slot, value, elem_ty)
            return None, "void"
        if meth == "remove":
            idx, = self.check_arguments(what, node.arguments, ("int",))
            return self.call_runtime("vamp_list_remove", (list_type, "int"), "void", [list_value, idx])
        if meth in ("clear", "reverse"):
            self.check_arguments(what, node.arguments, ())
            return self.call_runtime(f"vamp_list_{meth}", (list_type,), "void", [list_value])
        if meth == "length":
            self.check_arguments(what, node.arguments, ())
            return self.list_length(list_value), "int"
        if meth == "is_empty":
            self.check_arguments(what, node.arguments, ())
            return self.builder.icmp_signed("==", self.list_length(list_value), ir.Constant(self.int64_type, 0)), "bool"
        if meth in ("contains", "index_of"):
            value, = self.check_arguments(what, node.arguments, (elem_ty,))
            if elem_ty.startswith("class:") and not self.is_reference_class(elem_ty[6:]):
                raise TypeError(f"{what} cannot compare struct values")
            if elem_ty == "str":
                found, _ = self.call_runtime(
                    "vamp_list_index_of_str", (list_type, "str"), "int", [list_value, value])
            else:
                found, _ = self.call_runtime(
                    "vamp_list_index_of", (list_type, "str"), "int", [list_value, self.spill(value, elem_ty)])
            if meth == "contains":
                return self.builder.icmp_signed(">=", found, ir.Constant(self.int64_type, 0)), "bool"
            return found, "int"
        if meth in ("first", "last"):
            self.check_arguments(what, node.arguments, ())
            idx = ir.Constant(self.int64_type, 0) if meth == "first" else self.builder.sub(
                self.list_length(list_value), ir.Constant(self.int64_type, 1))
            return self.load_typed(self.list_element_pointer(list_value, idx, elem_ty), elem_ty)
        if meth == "sort":
            self.check_arguments(what, node.arguments, ())
            if elem_ty not in SORT_KINDS:
                raise TypeError(f"list.sort cannot order values of type {describe_type(elem_ty)}")
            return self.call_runtime(
                "vamp_list_sort", (list_type, "i32"), "void",
                [list_value, ir.Constant(int32, SORT_KINDS[elem_ty])])
        if meth == "copy":
            self.check_arguments(what, node.arguments, ())
            return self.call_runtime("vamp_list_copy", (list_type,), list_type, [list_value])
        if meth == "join":
            if elem_ty != "str":
                raise TypeError("list.join needs a list[str]")
            sep, = self.check_arguments(what, node.arguments, ("str",))
            return self.call_runtime("vamp_str_join", (list_type, "str"), "str", [list_value, sep])
        close = suggest(meth, self.LIST_METHODS)
        msg = f"Lists have no method '{meth}'"
        msg += f" (did you mean '{close}'?)" if close else f"; available: {', '.join(self.LIST_METHODS)}"
        raise NameError(msg)

    def new_map(self, map_type):
        _, key_ty, val_ty = map_type.split(":", 2)
        res, _ = self.call_runtime(
            "vamp_map_new", ("i32", "i32"), map_type,
            [ir.Constant(self.int32_type, 1 if key_ty == "str" else 0), self.size_of(val_ty)])
        return res

    def map_key(self, key_node, key_type):
        key, actual_type = self.visit_as(key_node, key_type)
        if actual_type != key_type:
            raise TypeError(f"This map has {key_type} keys, got {describe_type(actual_type)}")
        return key

    def wide_key(self, key, key_type):
        if key_type == "int" or key_type == "u64":
            return key
        if key_type in UNSIGNED_TYPES:
            return self.builder.zext(key, self.int64_type)
        return self.builder.sext(key, self.int64_type)

    def map_slot(self, map_value, key, key_type, value_type, create):
        ptr = self.char_pointer_type
        int32 = self.int32_type
        flag = ir.Constant(int32, 1 if create else 0)
        if key_type == "str":
            raw = self.builder.call(
                self.runtime_function("vamp_map_slot_s", ptr, [ptr, ptr, int32]), [map_value, key, flag])
        else:
            key = self.wide_key(key, key_type)
            raw = self.builder.call(
                self.runtime_function("vamp_map_slot_i", ptr, [ptr, self.int64_type, int32]),
                [map_value, key, flag])
        if not create:
            fn = self.builder.function
            found_block = fn.append_basic_block(name="map_key_found")
            missing_block = fn.append_basic_block(name="map_key_missing")
            self.builder.cbranch(
                self.builder.icmp_unsigned("!=", raw, ir.Constant(ptr, None)), found_block, missing_block)
            self.builder.position_at_end(missing_block)
            if key_type == "str":
                self.builder.call(self.runtime_function("vamp_map_key_error_s", ir.VoidType(), [ptr]), [key])
            else:
                self.builder.call(
                    self.runtime_function("vamp_map_key_error_i", ir.VoidType(), [self.int64_type]), [key])
            self.builder.unreachable()
            self.builder.position_at_end(found_block)
        return self.builder.bitcast(raw, self.llvm_type_for(value_type).as_pointer())

    def map_key_at(self, map_value, map_type, entry_index):
        _, key_ty, _ = map_type.split(":", 2)
        ptr = self.char_pointer_type
        if key_ty == "str":
            return self.builder.call(
                self.runtime_function("vamp_map_key_at_s", ptr, [ptr, self.int32_type]),
                [map_value, entry_index])
        wide = self.builder.call(
            self.runtime_function("vamp_map_key_at_i", self.int64_type, [ptr, self.int32_type]),
            [map_value, entry_index])
        target = self.llvm_type_for(key_ty)
        return wide if target.width == 64 else self.builder.trunc(wide, target)

    def build_map_literal(self, node, map_type):
        _, key_ty, val_ty = map_type.split(":", 2)
        mp = self.new_map(map_type)
        for key_node, value_node in node.entries:
            key = self.map_key(key_node, key_ty)
            value, actual_type = self.visit_as(value_node, val_ty)
            if actual_type != val_ty:
                raise TypeError(
                    f"This map holds {describe_type(val_ty)} values, got {describe_type(actual_type)}")
            self.builder.store(
                self.as_value(value), self.map_slot(mp, key, key_ty, val_ty, create=True))
        return mp, map_type

    MAP_METHODS = ("has", "get", "set", "remove", "length", "is_empty", "clear", "keys", "values")

    def emit_map_method(self, map_value, map_type, node):
        _, key_ty, val_ty = map_type.split(":", 2)
        meth = node.method_name
        what = f"map.{meth}"
        ptr = self.char_pointer_type
        int32 = self.int32_type
        zero = ir.Constant(int32, 0)

        def raw_slot(key):
            if key_ty == "str":
                return self.builder.call(
                    self.runtime_function("vamp_map_slot_s", ptr, [ptr, ptr, int32]),
                    [map_value, key, zero])
            return self.builder.call(
                self.runtime_function("vamp_map_slot_i", ptr, [ptr, self.int64_type, int32]),
                [map_value, self.wide_key(key, key_ty), zero])

        if meth == "has":
            key, = self.check_arguments(what, node.arguments, (key_ty,))
            return self.builder.icmp_unsigned("!=", raw_slot(key), ir.Constant(ptr, None)), "bool"
        if meth == "get":
            key, fallback = self.check_arguments(what, node.arguments, (key_ty, val_ty))
            if val_ty.startswith("class:"):
                raise TypeError("map.get with a default is not available for class values; use map.has and map[key]")
            slot = raw_slot(key)
            fn = self.builder.function
            found_block = fn.append_basic_block(name="map_get_found")
            end_block = fn.append_basic_block(name="map_get_end")
            start_block = self.builder.block
            self.builder.cbranch(
                self.builder.icmp_unsigned("!=", slot, ir.Constant(ptr, None)), found_block, end_block)
            self.builder.position_at_end(found_block)
            stored = self.builder.load(self.builder.bitcast(slot, self.llvm_type_for(val_ty).as_pointer()))
            self.builder.branch(end_block)
            self.builder.position_at_end(end_block)
            res = self.builder.phi(self.llvm_type_for(val_ty))
            res.add_incoming(fallback, start_block)
            res.add_incoming(stored, found_block)
            return res, val_ty
        if meth == "set":
            key, value = self.check_arguments(what, node.arguments, (key_ty, val_ty))
            self.builder.store(value, self.map_slot(map_value, key, key_ty, val_ty, create=True))
            return None, "void"
        if meth == "remove":
            key, = self.check_arguments(what, node.arguments, (key_ty,))
            if key_ty == "str":
                return self.call_runtime("vamp_map_remove_s", (map_type, "str"), "bool", [map_value, key])
            return self.call_runtime(
                "vamp_map_remove_i", (map_type, "c_i64"), "bool", [map_value, self.wide_key(key, key_ty)])
        if meth == "length":
            self.check_arguments(what, node.arguments, ())
            return self.call_runtime("vamp_map_length", (map_type,), "int", [map_value])
        if meth == "is_empty":
            self.check_arguments(what, node.arguments, ())
            length, _ = self.call_runtime("vamp_map_length", (map_type,), "int", [map_value])
            return self.builder.icmp_signed("==", length, ir.Constant(self.int64_type, 0)), "bool"
        if meth == "clear":
            self.check_arguments(what, node.arguments, ())
            return self.call_runtime("vamp_map_clear", (map_type,), "void", [map_value])
        if meth == "keys":
            self.check_arguments(what, node.arguments, ())
            return self.call_runtime(
                "vamp_map_keys", (map_type, "i32"), f"list:{key_ty}", [map_value, self.size_of(key_ty)])
        if meth == "values":
            self.check_arguments(what, node.arguments, ())
            return self.call_runtime("vamp_map_values", (map_type,), f"list:{val_ty}", [map_value])
        close = suggest(meth, self.MAP_METHODS)
        msg = f"Maps have no method '{meth}'"
        msg += f" (did you mean '{close}'?)" if close else f"; available: {', '.join(self.MAP_METHODS)}"
        raise NameError(msg)

    def visit_PrintNode(self, node):
        value, val_ty = self.visit(node.expression)
        end = "\n" if node.newline else ""
        if val_ty == "void":
            raise TypeError("Cannot print the result of a call that returns nothing")
        formatted = self.printf_argument(value, val_ty)
        if formatted is not None:
            format_text, arg = formatted
        elif val_ty == "char":
            format_text, arg = "%c", self.builder.zext(value, self.int32_type)
        elif val_ty == "str":
            format_text, arg = "%s", value
        elif val_ty == "bool" or val_ty.startswith(("enum:", "class:", "interface:", "optional:")) \
                or self.is_collection_type(val_ty):
            format_text, arg = "%s", self.cast_value(value, val_ty, "str")[0]
        else:
            raise TypeError(
                f"Cannot print a value of type {describe_type(val_ty)}; print its fields or elements instead")
        format_pointer = self.visit_LiteralNode(LiteralNode("str", format_text + end))[0]
        self.builder.call(self.printf_function, [format_pointer, arg])

    def visit_ExitNode(self, node):
        exit_code, exit_code_type = self.visit(node.exit_code)
        if exit_code_type != "int":
            raise TypeError(f"exit() expected int exit code, got {describe_type(exit_code_type)}")
        self.builder.call(self.exit_function, [self.fit_integer(exit_code, self.int32_type)])

    def visit_FreeNode(self, node):
        ptr, pointer_type = self.visit(node.pointer_expression)
        if pointer_type.startswith("list:"):
            return self.call_runtime("vamp_list_free", (pointer_type,), "void", [ptr])
        if pointer_type.startswith(("map:", "set:")):
            return self.call_runtime("vamp_map_free", ("str",), "void", [ptr])
        if pointer_type == "json":
            return self.call_runtime("vamp_json_free", ("json",), "void", [ptr])
        if pointer_type.startswith("class:") and self.is_reference_class(pointer_type[6:]):
            self.builder.call(self.free_function, [self.builder.bitcast(ptr.pointer, self.char_pointer_type)])
            return None, "void"
        if pointer_type != "str" and not pointer_type.startswith("pointer:"):
            raise TypeError(f"free() expected an allocated pointer, got {describe_type(pointer_type)}")
        if isinstance(ptr, PointerValue):
            ptr = ptr.pointer
        if ptr.type != self.char_pointer_type:
            ptr = self.builder.bitcast(ptr, self.char_pointer_type, name="free_pointer")
        self.builder.call(self.free_function, [ptr])
        return None, "void"

    def visit_MallocNode(self, node):
        elem_ty = self.resolve_type(node.element_type)
        cnt, count_type = self.visit(node.count)
        if count_type != "int":
            raise TypeError(f"malloc element count must be int, got {describe_type(count_type)}")
        if isinstance(node.count, LiteralNode) and node.count.value <= 0:
            raise ValueError("malloc element count must be greater than zero")
        fn = self.builder.function
        allocation_block = fn.append_basic_block(name="malloc_allocate")
        error_block = fn.append_basic_block(name="malloc_invalid_count")
        self.builder.cbranch(
            self.builder.icmp_signed(">", cnt, ir.Constant(cnt.type, 0), name="malloc_valid_count"),
            allocation_block, error_block)

        self.builder.position_at_end(error_block)
        self.builder.call(self.printf_function, [self.visit_LiteralNode(
            LiteralNode("str", "Error: malloc element count must be greater than zero\n"))[0]])
        self.builder.call(self.exit_function, [ir.Constant(self.int32_type, 1)])
        self.builder.unreachable()

        self.builder.position_at_end(allocation_block)
        byte_count = self.builder.mul(
            self.fit_integer(cnt, self.int64_type), self.builder.zext(self.size_of(elem_ty), self.int64_type),
            name="malloc_byte_count")
        raw_pointer = self.allocate_bytes(byte_count, name="malloc_raw_pointer")
        failed_block = fn.append_basic_block(name="malloc_failed")
        success_block = fn.append_basic_block(name="malloc_success")
        self.builder.cbranch(
            self.builder.icmp_unsigned("==", raw_pointer, ir.Constant(self.char_pointer_type, None)),
            failed_block, success_block)

        self.builder.position_at_end(failed_block)
        self.builder.call(self.printf_function, [self.visit_LiteralNode(
            LiteralNode("str", "Error: malloc could not allocate memory\n"))[0]])
        self.builder.call(self.exit_function, [ir.Constant(self.int32_type, 1)])
        self.builder.unreachable()

        self.builder.position_at_end(success_block)
        typed_pointer = self.builder.bitcast(
            raw_pointer, self.llvm_type_for(elem_ty).as_pointer(), name="malloc_typed_pointer")
        return PointerValue(typed_pointer, elem_ty), f"pointer:{elem_ty}"

