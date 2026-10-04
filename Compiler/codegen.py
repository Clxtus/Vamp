from llvmlite import ir
from parser import ArrayAccessNode, ArrayLiteralNode, ClassDeclarationNode, ClassInstanceDeclarationNode, ComparisonNode, DictionaryAccessNode, DictionaryLiteralNode, ForLoopNode, IfNode, LiteralNode, LibraryImportNode, ImportFileNode, LibraryCallNode, MethodCallNode, VariableAccessNode

class ArrayLiteralValue:
    def __init__(self, elements, element_type):
        self.elements = elements
        self.element_type = element_type

class ArrayReferenceValue:
    def __init__(self, pointer, element_type, length):
        self.pointer = pointer
        self.element_type = element_type
        self.length = length

class DictionaryLiteralValue:
    def __init__(self, entries):
        self.entries = entries

class ClassInstanceValue:
    def __init__(self, pointer):
        self.pointer = pointer

class LLVMCodeGenerator:
    def __init__(self):
        self.module = ir.Module(name="vamp_module")
        self.builder = None
        self.variable_pointers = {}
        self.type_information = {}
        self.array_information = {}
        self.dictionary_information = {}
        self.class_definitions = {}
        self.class_methods = {}
        self.emitted_class_methods = set()
        self.imported_libraries = set()
        self.string_literal_count = 0

        self.int32_type = ir.IntType(32)
        self.float_type = ir.FloatType()
        self.bool_type = ir.IntType(1)
        self.char_pointer_type = ir.IntType(8).as_pointer()

        printf_type = ir.FunctionType(self.int32_type, [self.char_pointer_type], var_arg=True)
        self.printf_function = ir.Function(self.module, printf_type, name="printf")

        snprintf_type = ir.FunctionType(self.int32_type, [self.char_pointer_type, self.int32_type, self.char_pointer_type], var_arg=True)
        self.snprintf_function = ir.Function(self.module, snprintf_type, name="snprintf")

        malloc_type = ir.FunctionType(self.char_pointer_type, [self.int32_type])
        self.malloc_function = ir.Function(self.module, malloc_type, name="malloc")

        strlen_type = ir.FunctionType(self.int32_type, [self.char_pointer_type])
        self.strlen_function = ir.Function(self.module, strlen_type, name="strlen")

        strcpy_type = ir.FunctionType(self.char_pointer_type, [self.char_pointer_type, self.char_pointer_type])
        self.strcpy_function = ir.Function(self.module, strcpy_type, name="strcpy")

        strcat_type = ir.FunctionType(self.char_pointer_type, [self.char_pointer_type, self.char_pointer_type])
        self.strcat_function = ir.Function(self.module, strcat_type, name="strcat")

        atoi_type = ir.FunctionType(self.int32_type, [self.char_pointer_type])
        self.atoi_function = ir.Function(self.module, atoi_type, name="atoi")

        atof_type = ir.FunctionType(ir.DoubleType(), [self.char_pointer_type])
        self.atof_function = ir.Function(self.module, atof_type, name="atof")

        strcmp_type = ir.FunctionType(self.int32_type, [self.char_pointer_type, self.char_pointer_type])
        self.strcmp_function = ir.Function(self.module, strcmp_type, name="strcmp")

        exit_type = ir.FunctionType(ir.VoidType(), [self.int32_type])
        self.exit_function = ir.Function(self.module, exit_type, name="exit")

        free_type = ir.FunctionType(ir.VoidType(), [self.char_pointer_type])
        self.free_function = ir.Function(self.module, free_type, name="free")

        create_directory_type = ir.FunctionType(self.int32_type, [self.char_pointer_type, self.char_pointer_type, self.char_pointer_type])
        self.create_directory_function = ir.Function(self.module, create_directory_type, name="SHCreateDirectoryExA")

    def generate_code(self, program):
        class_declarations = [
            stmt for stmt in program
            if isinstance(stmt, ClassDeclarationNode)
        ]
        for decl in class_declarations:
            self.register_class_tree(decl)
        for decl in class_declarations:
            self.declare_class_methods(decl)

        main_type = ir.FunctionType(self.int32_type, [])
        main_function = ir.Function(self.module, main_type, name="main")
        entry_block = main_function.append_basic_block(name="entry")
        self.builder = ir.IRBuilder(entry_block)

        for stmt in program:
            self.visit(stmt)

        self.builder.ret(ir.Constant(self.int32_type, 0))
        return str(self.module)

    def visit(self, node):
        visitor_name = f"visit_{type(node).__name__}"
        visitor = getattr(self, visitor_name, self.visit_unhandled_node)
        return visitor(node)

    def visit_unhandled_node(self, node):
        raise NotImplementedError(f"No visit_{type(node).__name__} method defined.")

    def visit_LibraryImportNode(self, node):
        self.imported_libraries.add(node.library_name)

    def visit_ImportFileNode(self, node):
        pass

    def visit_ClassDeclarationNode(self, node):
        self.emit_class_methods(node)

    def visit_ClassInstanceDeclarationNode(self, node):
        instance_value, instance_type = self.visit(node.initializer)
        if not isinstance(instance_value, ClassInstanceValue):
            raise TypeError(f"'{node.instance_name}' must be initialized with a class instance")
        self.variable_pointers[node.instance_name] = instance_value.pointer
        self.type_information[node.instance_name] = instance_type
        self.array_information.pop(node.instance_name, None)
        self.dictionary_information.pop(node.instance_name, None)

    def register_class_tree(self, node, parent_name=None):
        qualified_name = f"{parent_name}.{node.class_name}" if parent_name else node.class_name
        if qualified_name in self.class_definitions:
            raise SyntaxError(f"Class '{qualified_name}' is already declared")

        fields = {}
        llvm_field_types = []
        for field_index, (field_name, field_ty, is_constant) in enumerate(node.fields):
            if field_name in fields:
                raise SyntaxError(f"Duplicate field '{field_name}' in class '{qualified_name}'")
            fields[field_name] = (field_index, field_ty, is_constant)
            llvm_field_types.append(self.llvm_type_for(field_ty))

        nested_classes = {
            nested.class_name: f"{qualified_name}.{nested.class_name}"
            for nested in node.nested_classes
        }
        self.class_definitions[qualified_name] = {
            "fields": fields,
            "field_order": [field_name for field_name, _, _ in node.fields],
            "llvm_type": ir.LiteralStructType(llvm_field_types),
            "nested_classes": nested_classes,
            "methods": node.methods,
        }

        for nested_class in node.nested_classes:
            self.register_class_tree(nested_class, qualified_name)

    def declare_class_methods(self, node, parent_name=None):
        qualified_name = f"{parent_name}.{node.class_name}" if parent_name else node.class_name
        for meth in node.methods:
            method_key = (qualified_name, meth.function_name)
            if method_key in self.class_methods:
                raise SyntaxError(
                    f"Method '{meth.function_name}' is already declared on '{qualified_name}'"
                )

            parameter_types = [self.llvm_type_for(parameter_type) for _, parameter_type in meth.parameters]
            function_type = ir.FunctionType(
                self.llvm_type_for(meth.return_type),
                [self.class_definitions[qualified_name]["llvm_type"].as_pointer(), *parameter_types],
            )
            function_name = f"{qualified_name.replace('.', '__')}__{meth.function_name}"
            fn = ir.Function(self.module, function_type, name=function_name)
            self.class_methods[method_key] = {
                "function": fn,
                "return_type": meth.return_type,
                "parameters": meth.parameters,
                "declaration": meth,
            }

        for nested_class in node.nested_classes:
            self.declare_class_methods(nested_class, qualified_name)

    def emit_class_methods(self, node, parent_name=None):
        qualified_name = f"{parent_name}.{node.class_name}" if parent_name else node.class_name
        for meth in node.methods:
            method_key = (qualified_name, meth.function_name)
            if method_key in self.emitted_class_methods:
                continue
            self.emitted_class_methods.add(method_key)
            method_information = self.class_methods[method_key]
            previous_builder = self.builder
            previous_variable_pointers = self.variable_pointers.copy()
            previous_type_information = self.type_information.copy()
            previous_array_information = self.array_information.copy()
            previous_dictionary_information = self.dictionary_information.copy()

            fn = method_information["function"]
            entry_block = fn.append_basic_block(name="entry")
            self.builder = ir.IRBuilder(entry_block)
            self.variable_pointers["self"] = fn.args[0]
            self.type_information["self"] = f"class:{qualified_name}"

            for argument_index, (parameter_name, parameter_type) in enumerate(meth.parameters, start=1):
                parameter_pointer = self.builder.alloca(self.llvm_type_for(parameter_type), name=parameter_name)
                self.builder.store(fn.args[argument_index], parameter_pointer)
                self.variable_pointers[parameter_name] = parameter_pointer
                self.type_information[parameter_name] = parameter_type

            for stmt in meth.body:
                self.visit(stmt)

            if not self.builder.block.is_terminated:
                if isinstance(fn.function_type.return_type, ir.VoidType):
                    raise SyntaxError(
                        f"Method '{qualified_name}.{meth.function_name}' must end with 'return : void'"
                    )
                raise SyntaxError(
                    f"Method '{qualified_name}.{meth.function_name}' must return a value"
                )

            self.builder = previous_builder
            self.variable_pointers = previous_variable_pointers
            self.type_information = previous_type_information
            self.array_information = previous_array_information
            self.dictionary_information = previous_dictionary_information

        for nested_class in node.nested_classes:
            self.emit_class_methods(nested_class, qualified_name)

    def visit_LibraryCallNode(self, node):
        if node.library_name == "os" and "os" not in self.imported_libraries:
            raise NameError("Library 'os' is not imported. Add 'import os' at top of file.")

        if node.library_name == "os":
            if node.method_name == "Make_Directory":
                path_value, path_type = self.visit(node.arguments[0])
                if path_type != "str":
                    raise TypeError("os.Make_Directory expected string path")
                null_pointer = ir.Constant(self.char_pointer_type, None)
                res = self.builder.call(self.create_directory_function, [null_pointer, path_value, null_pointer])
                return res, "int"

        elif node.library_name == "Directory" and node.method_name == "exists":
            path_value, _ = self.visit(node.arguments[0])
            null_pointer = ir.Constant(self.char_pointer_type, None)
            res = self.builder.call(self.create_directory_function, [null_pointer, path_value, null_pointer])
            exists = self.builder.icmp_signed("==", res, ir.Constant(self.int32_type, -1))
            return exists, "bool"

        raise NotImplementedError(f"Method '{node.library_name}.{node.method_name}' is not implemented.")

    def visit_LiteralNode(self, node):
        if node.literal_type == "int":
            return ir.Constant(self.int32_type, node.value), "int"
        elif node.literal_type == "float":
            return ir.Constant(self.float_type, node.value), "float"
        elif node.literal_type == "bool":
            return ir.Constant(self.bool_type, 1 if node.value else 0), "bool"
        elif node.literal_type == "str":
            string_content = node.value + "\0"
            string_constant = ir.Constant(ir.ArrayType(ir.IntType(8), len(string_content)), bytearray(string_content.encode("utf-8")))
            self.string_literal_count += 1
            string_global = ir.GlobalVariable(self.module, string_constant.type, name=f".str_{self.string_literal_count}")
            string_global.linkage = "internal"
            string_global.initializer = string_constant
            return self.builder.bitcast(string_global, self.char_pointer_type), "str"

    def visit_ArrayLiteralNode(self, node):
        if not node.elements:
            raise TypeError("Arrays must contain at least one element so their type can be inferred")

        elems = []
        elem_ty = None
        for expr in node.elements:
            value, val_ty = self.visit(expr)
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
            value, val_ty = self.visit(expr)
            if val_ty != decl_ty:
                raise TypeError(f"Dictionary field '{key}' expects {decl_ty}, got {val_ty}")
            entries.append((key, decl_ty, value))

        return DictionaryLiteralValue(entries), "dictionary"

    def visit_VariableAccessNode(self, node):
        variable_type = self.type_information[node.variable_name]
        if variable_type in ("array", "dictionary") or variable_type.startswith("class:"):
            raise TypeError(f"Use an index or field to read '{node.variable_name}'")
        variable_pointer = self.variable_pointers[node.variable_name]
        value = self.builder.load(variable_pointer, name=f"{node.variable_name}_value")
        return value, variable_type

    def visit_ArrayAccessNode(self, node):
        if not isinstance(node.array, VariableAccessNode):
            raise TypeError("Array access requires an array variable")
        array_name = node.array.variable_name
        array_info = self.array_information[array_name]
        idx, index_type = self.visit(node.index)
        if index_type != "int":
            raise TypeError("Array indexes must be int")
        element_pointer = self.builder.gep(
            self.variable_pointers[array_name],
            [ir.Constant(self.int32_type, 0), idx],
            name=f"{array_name}_element_pointer",
        )
        return self.builder.load(element_pointer, name=f"{array_name}_element"), array_info["element_type"]

    def visit_DictionaryAccessNode(self, node):
        if not isinstance(node.dictionary, VariableAccessNode):
            raise TypeError("Field access requires a variable")
        var_name = node.dictionary.variable_name
        variable_type = self.type_information.get(var_name)
        if variable_type == "dictionary":
            field_information = self.dictionary_information[var_name].get(node.key)
            if field_information is None:
                raise NameError(f"Dictionary has no field '{node.key}'")
            field_index, field_ty = field_information
            aggregate_pointer = self.variable_pointers[var_name]
        elif variable_type and variable_type.startswith("class:"):
            cls_name = variable_type.removeprefix("class:")
            class_definition = self.class_definitions[cls_name]
            field_information = class_definition["fields"].get(node.key)
            if field_information is None:
                raise NameError(f"Class '{cls_name}' has no field '{node.key}'")
            field_index, field_ty, _ = field_information
            aggregate_pointer = self.variable_pointers[var_name]
        else:
            raise TypeError(f"'{var_name}' does not have readable fields")

        field_pointer = self.builder.gep(
            aggregate_pointer,
            [ir.Constant(self.int32_type, 0), ir.Constant(self.int32_type, field_index)],
            name=f"{var_name}_{node.key}_pointer",
        )
        return self.builder.load(field_pointer, name=f"{var_name}_{node.key}"), field_ty

    def visit_MethodCallNode(self, node):
        if not isinstance(node.receiver, VariableAccessNode):
            raise TypeError("Class method calls need an instance variable as the receiver")

        receiver_name = node.receiver.variable_name
        receiver_type = self.type_information.get(receiver_name)
        if not receiver_type or not receiver_type.startswith("class:"):
            raise TypeError(f"'{receiver_name}' is not a class instance")

        cls_name = receiver_type.removeprefix("class:")
        class_definition = self.class_definitions[cls_name]
        nested_class_name = class_definition["nested_classes"].get(node.method_name)
        if nested_class_name is not None:
            return self.create_class_instance(nested_class_name, node.arguments)

        method_information = self.class_methods.get((cls_name, node.method_name))
        if method_information is None:
            raise NameError(f"Class '{cls_name}' has no method or nested class '{node.method_name}'")

        params = method_information["parameters"]
        if len(node.arguments) != len(params):
            raise TypeError(
                f"Method '{cls_name}.{node.method_name}' expects {len(params)} "
                f"arguments, got {len(node.arguments)}"
            )

        argument_values = [self.variable_pointers[receiver_name]]
        for arg, (parameter_name, parameter_type) in zip(node.arguments, params):
            value, val_ty = self.visit(arg)
            if val_ty != parameter_type:
                raise TypeError(
                    f"Method argument '{parameter_name}' expects {parameter_type}, got {val_ty}"
                )
            argument_values.append(value)

        res = self.builder.call(
            method_information["function"],
            argument_values,
            name=f"{receiver_name}_{node.method_name}_result",
        )
        return res, method_information["return_type"]

    def visit_ForLoopNode(self, node):
        if isinstance(node.iterable, DictionaryAccessNode) and node.iterable.key == "values":
            if not isinstance(node.iterable.dictionary, VariableAccessNode):
                raise TypeError("Dictionary value loops require a dictionary variable")
            dictionary_name = node.iterable.dictionary.variable_name
            fields = self.dictionary_information.get(dictionary_name)
            if fields is None:
                raise TypeError(f"'{dictionary_name}' is not a dictionary")
            self.emit_dictionary_value_loop(dictionary_name, node.item_name, node.body)
            return

        if isinstance(node.iterable, VariableAccessNode):
            collection_name = node.iterable.variable_name
            collection_type = self.type_information.get(collection_name)
            if collection_type == "array":
                array_info = self.array_information[collection_name]
                self.emit_array_loop(
                    self.variable_pointers[collection_name],
                    array_info["element_type"],
                    array_info["length"],
                    node.item_name,
                    node.body,
                )
                return
            if collection_type == "dictionary":
                field_names = list(self.dictionary_information[collection_name])
                self.emit_dictionary_key_loop(field_names, node.item_name, node.body)
                return

        iterable_value, iterable_type = self.visit(node.iterable)
        if isinstance(iterable_value, ArrayLiteralValue):
            array_pointer = self.materialize_array(iterable_value, f"{node.item_name}_array")
            self.emit_array_loop(
                array_pointer,
                iterable_value.element_type,
                len(iterable_value.elements),
                node.item_name,
                node.body,
            )
            return
        if isinstance(iterable_value, DictionaryLiteralValue):
            field_names = [field_name for field_name, _, _ in iterable_value.entries]
            self.emit_dictionary_key_loop(field_names, node.item_name, node.body)
            return
        raise TypeError(f"For loops cannot iterate over values of type '{iterable_type}'")

    def emit_dictionary_value_loop(self, dictionary_name, item_name, body):
        dictionary_pointer = self.variable_pointers[dictionary_name]
        saved_variable_pointers = self.variable_pointers.copy()
        saved_type_information = self.type_information.copy()
        saved_array_information = self.array_information.copy()
        saved_dictionary_information = self.dictionary_information.copy()

        for field_name, (field_index, field_ty) in self.dictionary_information[dictionary_name].items():
            field_pointer = self.builder.gep(
                dictionary_pointer,
                [ir.Constant(self.int32_type, 0), ir.Constant(self.int32_type, field_index)],
                name=f"{dictionary_name}_{field_name}_value_pointer",
            )
            self.variable_pointers[item_name] = field_pointer
            self.type_information[item_name] = field_ty
            self.array_information.pop(item_name, None)
            self.dictionary_information.pop(item_name, None)

            for stmt in body:
                self.visit(stmt)
            if self.builder.block.is_terminated:
                break

            self.variable_pointers = saved_variable_pointers.copy()
            self.type_information = saved_type_information.copy()
            self.array_information = saved_array_information.copy()
            self.dictionary_information = saved_dictionary_information.copy()

        self.variable_pointers = saved_variable_pointers
        self.type_information = saved_type_information
        self.array_information = saved_array_information
        self.dictionary_information = saved_dictionary_information

    def materialize_array(self, array_value, array_name):
        array_type = ir.ArrayType(self.llvm_type_for(array_value.element_type), len(array_value.elements))
        array_pointer = self.builder.alloca(array_type, name=array_name)
        for idx, elem in enumerate(array_value.elements):
            element_pointer = self.builder.gep(
                array_pointer,
                [ir.Constant(self.int32_type, 0), ir.Constant(self.int32_type, idx)],
            )
            self.builder.store(elem, element_pointer)
        return array_pointer

    def emit_dictionary_key_loop(self, field_names, item_name, body):
        key_values = [self.visit_LiteralNode(LiteralNode("str", field_name))[0] for field_name in field_names]
        key_array = ArrayLiteralValue(key_values, "str")
        key_pointer = self.materialize_array(key_array, f"{item_name}_keys")
        self.emit_array_loop(key_pointer, "str", len(field_names), item_name, body)

    def emit_array_loop(self, array_pointer, element_type, array_length, item_name, body):

        fn = self.builder.function
        preheader_block = self.builder.block
        condition_block = fn.append_basic_block(name="for_condition")
        body_block = fn.append_basic_block(name="for_body")
        end_block = fn.append_basic_block(name="for_end")
        self.builder.branch(condition_block)

        self.builder.position_at_end(condition_block)
        item_index = self.builder.phi(self.int32_type, name="for_index")
        item_index.add_incoming(ir.Constant(self.int32_type, 0), preheader_block)
        has_next_item = self.builder.icmp_signed(
            "<", item_index, ir.Constant(self.int32_type, array_length), name="for_has_item"
        )
        self.builder.cbranch(has_next_item, body_block, end_block)

        self.builder.position_at_end(body_block)
        item_pointer = self.builder.gep(
            array_pointer,
            [ir.Constant(self.int32_type, 0), item_index],
            name=f"{item_name}_pointer",
        )
        saved_variable_pointers = self.variable_pointers.copy()
        saved_type_information = self.type_information.copy()
        saved_array_information = self.array_information.copy()
        saved_dictionary_information = self.dictionary_information.copy()
        self.variable_pointers[item_name] = item_pointer
        self.type_information[item_name] = element_type
        self.array_information.pop(item_name, None)
        self.dictionary_information.pop(item_name, None)

        for stmt in body:
            self.visit(stmt)

        if not self.builder.block.is_terminated:
            loop_end_block = self.builder.block
            next_item_index = self.builder.add(item_index, ir.Constant(self.int32_type, 1), name="for_next_index")
            self.builder.branch(condition_block)
            item_index.add_incoming(next_item_index, loop_end_block)

        self.variable_pointers = saved_variable_pointers
        self.type_information = saved_type_information
        self.array_information = saved_array_information
        self.dictionary_information = saved_dictionary_information
        self.builder.position_at_end(end_block)

    def visit_BinaryOpNode(self, node):
        lhs, lhs_ty = self.visit(node.left)
        rhs, rhs_ty = self.visit(node.right)

        if lhs_ty == "str" or rhs_ty == "str":
            if lhs_ty != "str":
                lhs, _ = self.visit_CastNode(type("Cast", (), {"expression": node.left, "target_type": "str"})())
            if rhs_ty != "str":
                rhs, _ = self.visit_CastNode(type("Cast", (), {"expression": node.right, "target_type": "str"})())

            left_length = self.builder.call(self.strlen_function, [lhs])
            right_length = self.builder.call(self.strlen_function, [rhs])
            buffer_length = self.builder.add(self.builder.add(left_length, right_length), ir.Constant(self.int32_type, 1))

            buf = self.builder.call(self.malloc_function, [buffer_length], name="string_concat_buffer")
            self.builder.call(self.strcpy_function, [buf, lhs])
            self.builder.call(self.strcat_function, [buf, rhs])
            return buf, "str"

        if lhs_ty != rhs_ty:
            raise TypeError(f"Type mismatch: {lhs_ty} {node.operator} {rhs_ty}")

        if lhs_ty == "int":
            if node.operator == "+": return self.builder.add(lhs, rhs, name="addtmp"), "int"
            elif node.operator == "-": return self.builder.sub(lhs, rhs, name="subtmp"), "int"
            elif node.operator == "*": return self.builder.mul(lhs, rhs, name="multmp"), "int"
            elif node.operator == "/": return self.builder.sdiv(lhs, rhs, name="divtmp"), "int"
        elif lhs_ty == "float":
            if node.operator == "+": return self.builder.fadd(lhs, rhs, name="faddtmp"), "float"
            elif node.operator == "-": return self.builder.fsub(lhs, rhs, name="fsubtmp"), "float"
            elif node.operator == "*": return self.builder.fmul(lhs, rhs, name="fmultmp"), "float"
            elif node.operator == "/": return self.builder.fdiv(lhs, rhs, name="fdivtmp"), "float"

        raise SyntaxError(f"Unsupported binary operator '{node.operator}' for type '{lhs_ty}'")

    def visit_ComparisonNode(self, node):
        lhs, lhs_ty = self.visit(node.left)
        rhs, rhs_ty = self.visit(node.right)

        if lhs_ty != rhs_ty:
            raise TypeError(f"Cannot compare {lhs_ty} with {rhs_ty}")

        if lhs_ty == "float":
            if node.operator == "!=":
                return self.builder.fcmp_unordered(node.operator, lhs, rhs), "bool"
            return self.builder.fcmp_ordered(node.operator, lhs, rhs), "bool"

        if lhs_ty == "str":
            comparison = self.builder.call(self.strcmp_function, [lhs, rhs])
            return self.builder.icmp_signed(node.operator, comparison, ir.Constant(self.int32_type, 0)), "bool"

        if lhs_ty == "bool" and node.operator not in ("==", "!="):
            raise SyntaxError("Boolean values only support == and != comparisons")
        if lhs_ty in ("int", "bool"):
            return self.builder.icmp_signed(node.operator, lhs, rhs), "bool"

        raise SyntaxError(f"Values of type '{lhs_ty}' cannot be compared")

    def visit_IfNode(self, node):
        fn = self.builder.function
        merge_block = fn.append_basic_block(name="if_end")
        visible_variable_pointers = self.variable_pointers.copy()
        visible_type_information = self.type_information.copy()
        visible_array_information = self.array_information.copy()
        visible_dictionary_information = self.dictionary_information.copy()

        for cond, body in node.branches:
            condition_value, condition_type = self.visit(cond)
            if condition_type != "bool":
                raise TypeError(f"if condition must be bool, got {condition_type}")

            body_block = fn.append_basic_block(name="if_body")
            next_branch_block = fn.append_basic_block(name="if_next")
            self.builder.cbranch(condition_value, body_block, next_branch_block)

            self.builder.position_at_end(body_block)
            for stmt in body:
                self.visit(stmt)
            if not self.builder.block.is_terminated:
                self.builder.branch(merge_block)

            self.variable_pointers = visible_variable_pointers.copy()
            self.type_information = visible_type_information.copy()
            self.array_information = visible_array_information.copy()
            self.dictionary_information = visible_dictionary_information.copy()
            self.builder.position_at_end(next_branch_block)

        if node.else_body is not None:
            for stmt in node.else_body:
                self.visit(stmt)
        if not self.builder.block.is_terminated:
            self.builder.branch(merge_block)

        self.variable_pointers = visible_variable_pointers
        self.type_information = visible_type_information
        self.array_information = visible_array_information
        self.dictionary_information = visible_dictionary_information
        self.builder.position_at_end(merge_block)

    def visit_CastNode(self, node):
        value, val_ty = self.visit(node.expression)
        tgt_ty = node.target_type

        if val_ty == tgt_ty:
            return value, tgt_ty

        if tgt_ty == "int":
            if val_ty == "float":
                return self.builder.fptosi(value, self.int32_type, name="cast_int"), "int"
            elif val_ty == "bool":
                return self.builder.zext(value, self.int32_type, name="cast_int"), "int"
            elif val_ty == "str":
                return self.builder.call(self.atoi_function, [value], name="atoi_tmp"), "int"

        elif tgt_ty == "float":
            if val_ty == "int":
                return self.builder.sitofp(value, self.float_type, name="cast_float"), "float"
            elif val_ty == "bool":
                integer_value = self.builder.zext(value, self.int32_type, name="bool_int")
                return self.builder.sitofp(integer_value, self.float_type, name="cast_float"), "float"
            elif val_ty == "str":
                double_value = self.builder.call(self.atof_function, [value], name="atof_tmp")
                return self.builder.fptrunc(double_value, self.float_type, name="fptrunc_tmp"), "float"

        elif tgt_ty == "bool":
            if val_ty == "int":
                return self.builder.icmp_signed("!=", value, ir.Constant(self.int32_type, 0), name="cast_bool"), "bool"
            elif val_ty == "float":
                return self.builder.fcmp_ordered("!=", value, ir.Constant(self.float_type, 0.0), name="cast_bool"), "bool"
            elif val_ty == "str":
                true_string = self.visit_LiteralNode(LiteralNode("str", "true"))[0]
                one_string = self.visit_LiteralNode(LiteralNode("str", "1"))[0]
                true_comparison = self.builder.call(self.strcmp_function, [value, true_string])
                one_comparison = self.builder.call(self.strcmp_function, [value, one_string])
                is_true = self.builder.icmp_signed("==", true_comparison, ir.Constant(self.int32_type, 0))
                is_one = self.builder.icmp_signed("==", one_comparison, ir.Constant(self.int32_type, 0))
                return self.builder.or_(is_true, is_one, name="cast_bool"), "bool"

        elif tgt_ty == "str":
            buf = self.builder.call(self.malloc_function, [ir.Constant(self.int32_type, 64)], name="string_buffer")
            buffer_size = ir.Constant(self.int32_type, 64)
            if val_ty == "int":
                format_string = self.visit_LiteralNode(LiteralNode("str", "%d"))[0]
                self.builder.call(self.snprintf_function, [buf, buffer_size, format_string, value])
                return buf, "str"
            elif val_ty == "float":
                format_string = self.visit_LiteralNode(LiteralNode("str", "%f"))[0]
                double_value = self.builder.fpext(value, ir.DoubleType())
                self.builder.call(self.snprintf_function, [buf, buffer_size, format_string, double_value])
                return buf, "str"
            elif val_ty == "bool":
                true_string = self.visit_LiteralNode(LiteralNode("str", "true"))[0]
                false_string = self.visit_LiteralNode(LiteralNode("str", "false"))[0]
                return self.builder.select(value, true_string, false_string), "str"

        raise TypeError(f"Casting from {val_ty} to {tgt_ty} is not supported.")

    def visit_VariableDeclarationNode(self, node):
        value, val_ty = self.visit(node.initializer)
        if node.variable_type is not None and val_ty != node.variable_type:
            raise TypeError(f"Cannot assign {val_ty} to variable '{node.variable_name}' of type {node.variable_type}")

        if isinstance(value, ClassInstanceValue):
            self.variable_pointers[node.variable_name] = value.pointer
            self.type_information[node.variable_name] = val_ty
            self.array_information.pop(node.variable_name, None)
            self.dictionary_information.pop(node.variable_name, None)
            return

        if isinstance(value, ArrayLiteralValue):
            array_type = ir.ArrayType(self.llvm_type_for(value.element_type), len(value.elements))
            variable_pointer = self.builder.alloca(array_type, name=node.variable_name)
            for idx, elem in enumerate(value.elements):
                element_pointer = self.builder.gep(
                    variable_pointer,
                    [ir.Constant(self.int32_type, 0), ir.Constant(self.int32_type, idx)],
                )
                self.builder.store(elem, element_pointer)
            self.variable_pointers[node.variable_name] = variable_pointer
            self.type_information[node.variable_name] = "array"
            self.array_information[node.variable_name] = {
                "element_type": value.element_type,
                "length": len(value.elements),
            }
            self.dictionary_information.pop(node.variable_name, None)
            return

        if isinstance(value, DictionaryLiteralValue):
            dictionary_type = ir.LiteralStructType([
                self.llvm_type_for(field_ty)
                for _, field_ty, _ in value.entries
            ])
            variable_pointer = self.builder.alloca(dictionary_type, name=node.variable_name)
            fields = {}
            for field_index, (field_name, field_ty, field_value) in enumerate(value.entries):
                field_pointer = self.builder.gep(
                    variable_pointer,
                    [ir.Constant(self.int32_type, 0), ir.Constant(self.int32_type, field_index)],
                )
                self.builder.store(field_value, field_pointer)
                fields[field_name] = (field_index, field_ty)
            self.variable_pointers[node.variable_name] = variable_pointer
            self.type_information[node.variable_name] = "dictionary"
            self.dictionary_information[node.variable_name] = fields
            self.array_information.pop(node.variable_name, None)
            return

        variable_type = node.variable_type or val_ty
        variable_pointer = self.builder.alloca(self.llvm_type_for(variable_type), name=node.variable_name)
        self.builder.store(value, variable_pointer)
        self.variable_pointers[node.variable_name] = variable_pointer
        self.type_information[node.variable_name] = variable_type
        self.array_information.pop(node.variable_name, None)
        self.dictionary_information.pop(node.variable_name, None)

    def visit_PrintNode(self, node):
        value, val_ty = self.visit(node.expression)
        end = "\n\0" if node.newline else "\0"
        format_string = f"%s{end}" if val_ty == "str" else f"%d{end}" if val_ty == "int" else f"%f{end}" if val_ty == "float" else f"%s{end}"

        format_constant = ir.Constant(ir.ArrayType(ir.IntType(8), len(format_string)), bytearray(format_string.encode("utf-8")))
        self.string_literal_count += 1
        format_global = ir.GlobalVariable(self.module, format_constant.type, name=f".str_{self.string_literal_count}")
        format_global.linkage = "internal"
        format_global.initializer = format_constant
        format_pointer = self.builder.bitcast(format_global, self.char_pointer_type)

        if val_ty == "float":
            value = self.builder.fpext(value, ir.DoubleType())
        elif val_ty == "bool":
            true_string = self.visit_LiteralNode(LiteralNode("str", "true"))[0]
            false_string = self.visit_LiteralNode(LiteralNode("str", "false"))[0]
            value = self.builder.select(value, true_string, false_string)

        self.builder.call(self.printf_function, [format_pointer, value])

    def visit_ExitNode(self, node):
        exit_code, exit_code_type = self.visit(node.exit_code)
        if exit_code_type != "int":
            raise TypeError(f"exit() expected int exit code, got {exit_code_type}")
        self.builder.call(self.exit_function, [exit_code])

    def visit_FreeNode(self, node):
        ptr, pointer_type = self.visit(node.pointer_expression)
        if pointer_type != "str":
            raise TypeError(f"free() expected string pointer, got {pointer_type}")
        self.builder.call(self.free_function, [ptr])
        
    def llvm_type_for(self, type_name):
        if type_name == "int": return self.int32_type
        elif type_name == "float": return self.float_type
        elif type_name == "bool": return self.bool_type
        elif type_name == "str": return self.char_pointer_type
        elif type_name == "void": return ir.VoidType()
        elif type_name.startswith("class:"):
            cls_name = type_name.removeprefix("class:")
            return self.class_definitions[cls_name]["llvm_type"]
        return self.int32_type

    def visit_FunctionDeclarationNode(self, node):
        previous_builder = self.builder
        previous_variable_pointers = self.variable_pointers.copy()
        previous_type_information = self.type_information.copy()
        previous_array_information = self.array_information.copy()
        previous_dictionary_information = self.dictionary_information.copy()

        parameter_types = [self.llvm_type_for(parameter_type) for _, parameter_type in node.parameters]
        return_llvm_type = self.llvm_type_for(node.return_type)

        function_type = ir.FunctionType(return_llvm_type, parameter_types)
        fn = ir.Function(self.module, function_type, name=node.function_name)
        fn.attributes.add("noinline")
        
        self.type_information[f"function_{node.function_name}"] = node.return_type

        entry_block = fn.append_basic_block(name="entry")
        self.builder = ir.IRBuilder(entry_block)

        for idx, (parameter_name, parameter_type) in enumerate(node.parameters):
            parameter_llvm_type = self.llvm_type_for(parameter_type)
            parameter_pointer = self.builder.alloca(parameter_llvm_type, name=parameter_name)
            self.builder.store(fn.args[idx], parameter_pointer)
            self.variable_pointers[parameter_name] = parameter_pointer
            self.type_information[parameter_name] = parameter_type

        for stmt in node.body:
            self.visit(stmt)

        if not self.builder.block.is_terminated:
            if isinstance(return_llvm_type, ir.VoidType):
                raise SyntaxError(
                    f"Function '{node.function_name}' must end with 'return : void'"
                )
            raise SyntaxError(f"Function '{node.function_name}' must return a value")

        self.builder = previous_builder
        self.variable_pointers = previous_variable_pointers
        self.type_information = previous_type_information
        self.array_information = previous_array_information
        self.dictionary_information = previous_dictionary_information
        self.type_information[f"function_{node.function_name}"] = node.return_type

    def visit_ReturnNode(self, node):
        function_return_type = self.builder.function.function_type.return_type
        if node.return_type == "void" or node.expression is None:
            if not isinstance(function_return_type, ir.VoidType):
                raise TypeError("A void return can only be used in a void function or method")
            self.builder.ret_void()
            return None, "void"

        value, val_ty = self.visit(node.expression)
        if node.return_type is not None and val_ty != node.return_type:
            raise TypeError(f"Return annotation expects {node.return_type}, got {val_ty}")
        if value.type != function_return_type:
            raise TypeError(f"Return value of type {val_ty} does not match the function return type")
        self.builder.ret(value)

    def visit_FunctionCallNode(self, node):
        if node.function_name in self.class_definitions:
            return self.create_class_instance(node.function_name, node.arguments)

        fn = self.module.get_global(node.function_name)
        argument_values = []
        for arg in node.arguments:
            value, _ = self.visit(arg)
            argument_values.append(value)

        ret_ty = self.type_information.get(f"function_{node.function_name}", "int")
        res = self.builder.call(fn, argument_values, name=f"{node.function_name}_result")
        return res, ret_ty

    def create_class_instance(self, class_name, arguments, instance_name=None):
        class_definition = self.class_definitions.get(class_name)
        if class_definition is None:
            raise NameError(f"Class '{class_name}' is not declared")

        field_order = class_definition["field_order"]
        if len(arguments) != len(field_order):
            raise TypeError(
                f"Class '{class_name}' expects {len(field_order)} values, got {len(arguments)}"
            )

        instance_pointer = self.builder.alloca(
            class_definition["llvm_type"],
            name=instance_name or f"{class_name.lower()}_instance",
        )
        for field_index, (field_name, arg) in enumerate(zip(field_order, arguments)):
            value, val_ty = self.visit(arg)
            _, want_ty, _ = class_definition["fields"][field_name]
            if val_ty != want_ty:
                raise TypeError(
                    f"Field '{field_name}' in class '{class_name}' expects "
                    f"{want_ty}, got {val_ty}"
                )
            field_pointer = self.builder.gep(
                instance_pointer,
                [ir.Constant(self.int32_type, 0), ir.Constant(self.int32_type, field_index)],
                name=f"{field_name}_pointer",
            )
            self.builder.store(value, field_pointer)

        return ClassInstanceValue(instance_pointer), f"class:{class_name}"