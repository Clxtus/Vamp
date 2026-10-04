from llvmlite import ir
from parser import ArrayAccessNode, ArrayLiteralNode, AssignmentNode, BinaryOpNode, ClassDeclarationNode, ClassInstanceDeclarationNode, ComparisonNode, DictionaryAccessNode, DictionaryLiteralNode, ForLoopNode, IfNode, LiteralNode, LibraryImportNode, ImportFileNode, LibraryCallNode, MethodCallNode, VariableAccessNode, WhileLoopNode

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
        self.constant_variables = set()
        self.array_information = {}
        self.dictionary_information = {}
        self.class_definitions = {}
        self.class_methods = {}
        self.emitted_class_methods = set()
        self.imported_libraries = set()
        self.string_literal_count = 0

        self.int32_type = ir.IntType(32)
        self.int64_type = ir.IntType(64)
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

        file_attributes_type = ir.FunctionType(self.int32_type, [self.char_pointer_type])
        self.get_file_attributes_function = ir.Function(
            self.module,
            file_attributes_type,
            name="GetFileAttributesA",
        )

        find_first_file_type = ir.FunctionType(
            self.char_pointer_type,
            [self.char_pointer_type, self.char_pointer_type],
        )
        self.find_first_file_function = ir.Function(
            self.module,
            find_first_file_type,
            name="FindFirstFileA",
        )

        find_next_file_type = ir.FunctionType(
            self.int32_type,
            [self.char_pointer_type, self.char_pointer_type],
        )
        self.find_next_file_function = ir.Function(
            self.module,
            find_next_file_type,
            name="FindNextFileA",
        )

        find_close_type = ir.FunctionType(self.int32_type, [self.char_pointer_type])
        self.find_close_function = ir.Function(
            self.module,
            find_close_type,
            name="FindClose",
        )

        get_last_error_type = ir.FunctionType(self.int32_type, [])
        self.get_last_error_function = ir.Function(
            self.module,
            get_last_error_type,
            name="GetLastError",
        )

        full_path_type = ir.FunctionType(
            self.int32_type,
            [
                self.char_pointer_type,
                self.int32_type,
                self.char_pointer_type,
                self.char_pointer_type.as_pointer(),
            ],
        )
        self.get_full_path_name_function = ir.Function(
            self.module,
            full_path_type,
            name="GetFullPathNameA",
        )

        self.file_operation_type = ir.LiteralStructType([
            self.char_pointer_type,
            self.int32_type,
            self.char_pointer_type,
            self.char_pointer_type,
            ir.IntType(16),
            self.int32_type,
            self.char_pointer_type,
            self.char_pointer_type,
        ])
        file_operation_function_type = ir.FunctionType(
            self.int32_type,
            [self.file_operation_type.as_pointer()],
        )
        self.file_operation_function = ir.Function(
            self.module,
            file_operation_function_type,
            name="SHFileOperationA",
        )

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

    def visit_AssignmentNode(self, node):
        variable_pointer = self.variable_pointers.get(node.variable_name)
        if node.operator == "=":
            value, val_ty = self.visit(node.expression)
            if variable_pointer is None:
                if not isinstance(value, ClassInstanceValue):
                    raise NameError(f"Variable '{node.variable_name}' is not declared")
                self.variable_pointers[node.variable_name] = value.pointer
                self.type_information[node.variable_name] = val_ty
                self.array_information.pop(node.variable_name, None)
                self.dictionary_information.pop(node.variable_name, None)
                return
        else:
            if variable_pointer is None:
                raise NameError(f"Variable '{node.variable_name}' is not declared")
            value, val_ty = self.visit(
                BinaryOpNode(
                    VariableAccessNode(node.variable_name),
                    node.operator[0],
                    node.expression,
                )
            )

        if node.variable_name in self.constant_variables:
            raise TypeError(f"Cannot assign to constant '{node.variable_name}'")
        want_ty = self.type_information[node.variable_name]
        if want_ty not in ("int", "float", "bool", "str"):
            raise TypeError(f"Assignment to values of type '{want_ty}' is not supported")
        if val_ty != want_ty:
            raise TypeError(
                f"Cannot assign {val_ty} to variable '{node.variable_name}' of type {want_ty}"
            )
        self.builder.store(value, variable_pointer)

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
            previous_constant_variables = self.constant_variables.copy()

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
            self.constant_variables = previous_constant_variables

        for nested_class in node.nested_classes:
            self.emit_class_methods(nested_class, qualified_name)

    def visit_LibraryCallNode(self, node):
        if node.library_name == "os" and "os" not in self.imported_libraries:
            raise NameError("Library 'os' is not imported. Add 'import os' at top of file.")

        if node.library_name == "os":
            if node.method_name == "Make_Directory":
                path_value = self.get_directory_path_argument(node)
                absolute_path, _ = self.emit_absolute_path(path_value)
                null_pointer = ir.Constant(self.char_pointer_type, None)
                res = self.builder.call(
                    self.create_directory_function,
                    [null_pointer, absolute_path, null_pointer],
                )
                self.builder.call(self.free_function, [absolute_path])
                return res, "int"
            if node.method_name == "Get_Directory":
                path_value = self.get_directory_path_argument(node)
                return self.emit_absolute_directory_path(path_value)
            if node.method_name == "List_Directory":
                path_value = self.get_directory_path_argument(node)
                absolute_path, _ = self.emit_absolute_path(path_value)
                res = self.emit_directory_listing(absolute_path)
                self.builder.call(self.free_function, [absolute_path])
                return res
            if node.method_name == "Remove_Directory":
                path_value = self.get_directory_path_argument(node)
                absolute_path, _ = self.emit_absolute_path(path_value)
                res = self.emit_directory_removal(absolute_path)
                self.builder.call(self.free_function, [absolute_path])
                return res
            if node.method_name == "Directory_Exists":
                path_value = self.get_directory_path_argument(node)
                res = self.builder.call(self.get_file_attributes_function, [path_value])
                is_valid_path = self.builder.icmp_signed(
                    "!=",
                    res,
                    ir.Constant(self.int32_type, -1),
                )
                is_directory = self.builder.icmp_unsigned(
                    "!=",
                    self.builder.and_(res, ir.Constant(self.int32_type, 0x10)),
                    ir.Constant(self.int32_type, 0),
                )
                exists = self.builder.and_(is_valid_path, is_directory)
                return exists, "bool"

        raise NotImplementedError(f"Method '{node.library_name}.{node.method_name}' is not implemented.")

    def require_argument_count(self, node, expected_count):
        if len(node.arguments) != expected_count:
            raise TypeError(
                f"{node.library_name}.{node.method_name} expects "
                f"{expected_count} argument(s), got {len(node.arguments)}"
            )

    def get_directory_path_argument(self, node):
        self.require_argument_count(node, 1)
        path_value, path_type = self.visit(node.arguments[0])
        if path_type != "str":
            raise TypeError(
                f"{node.library_name}.{node.method_name} expected string path"
            )
        return path_value

    def emit_absolute_path(self, path_value):
        fn = self.builder.function
        max_windows_path_length = 32768
        path_buffer = self.builder.call(
            self.malloc_function,
            [ir.Constant(self.int32_type, max_windows_path_length)],
            name="absolute_directory_path_buffer",
        )
        null_pointer = ir.Constant(self.char_pointer_type, None)
        null_file_part_pointer = ir.Constant(
            self.char_pointer_type.as_pointer(),
            None,
        )
        empty_path = self.builder.call(
            self.malloc_function,
            [ir.Constant(self.int32_type, 1)],
            name="empty_path_buffer",
        )
        self.builder.store(ir.Constant(ir.IntType(8), 0), empty_path)

        resolved_length = self.builder.call(
            self.get_full_path_name_function,
            [
                path_value,
                ir.Constant(self.int32_type, max_windows_path_length),
                path_buffer,
                null_file_part_pointer,
            ],
            name="absolute_path_length",
        )
        path_resolved = self.builder.icmp_unsigned(
            "!=",
            resolved_length,
            ir.Constant(self.int32_type, 0),
        )
        path_fits_buffer = self.builder.icmp_unsigned(
            "<",
            resolved_length,
            ir.Constant(self.int32_type, max_windows_path_length),
        )
        path_is_resolved = self.builder.and_(path_resolved, path_fits_buffer)
        resolve_error_block = fn.append_basic_block(name="absolute_path_error")
        success_block = fn.append_basic_block(name="absolute_path_success")
        merge_block = fn.append_basic_block(name="absolute_path_end")
        self.builder.cbranch(path_is_resolved, success_block, resolve_error_block)

        self.builder.position_at_end(resolve_error_block)
        resolve_error_format = self.visit_LiteralNode(
            LiteralNode("str", "Error: could not resolve absolute path for '%s'\n")
        )[0]
        self.builder.call(self.printf_function, [resolve_error_format, path_value])
        self.builder.call(self.free_function, [path_buffer])
        self.builder.branch(merge_block)
        resolve_error_predecessor = self.builder.block

        self.builder.position_at_end(success_block)
        self.builder.branch(merge_block)
        success_predecessor = self.builder.block

        self.builder.position_at_end(merge_block)
        res = self.builder.phi(self.char_pointer_type, name="absolute_path")
        res.add_incoming(empty_path, resolve_error_predecessor)
        res.add_incoming(path_buffer, success_predecessor)
        return res, "str"

    def emit_absolute_directory_path(self, path_value):
        fn = self.builder.function
        empty_path = self.builder.call(
            self.malloc_function,
            [ir.Constant(self.int32_type, 1)],
            name="empty_directory_path_buffer",
        )
        self.builder.store(ir.Constant(ir.IntType(8), 0), empty_path)
        attributes = self.builder.call(self.get_file_attributes_function, [path_value])
        invalid_attributes = self.builder.icmp_signed(
            "==",
            attributes,
            ir.Constant(self.int32_type, -1),
        )
        is_directory = self.builder.icmp_unsigned(
            "!=",
            self.builder.and_(attributes, ir.Constant(self.int32_type, 0x10)),
            ir.Constant(self.int32_type, 0),
        )
        invalid_path = self.builder.or_(invalid_attributes, self.builder.not_(is_directory))
        invalid_block = fn.append_basic_block(name="get_directory_invalid")
        resolve_block = fn.append_basic_block(name="get_directory_resolve")
        merge_block = fn.append_basic_block(name="get_directory_end")
        self.builder.cbranch(invalid_path, invalid_block, resolve_block)

        self.builder.position_at_end(invalid_block)
        error_format = self.visit_LiteralNode(
            LiteralNode("str", "Error: directory does not exist: '%s'\n")
        )[0]
        self.builder.call(self.printf_function, [error_format, path_value])
        self.builder.branch(merge_block)
        invalid_predecessor = self.builder.block

        self.builder.position_at_end(resolve_block)
        absolute_path, _ = self.emit_absolute_path(path_value)
        self.builder.branch(merge_block)
        resolve_predecessor = self.builder.block

        self.builder.position_at_end(merge_block)
        res = self.builder.phi(self.char_pointer_type, name="absolute_directory_path")
        res.add_incoming(empty_path, invalid_predecessor)
        res.add_incoming(absolute_path, resolve_predecessor)
        return res, "str"

    def emit_directory_removal(self, path_value):
        null_pointer = ir.Constant(self.char_pointer_type, None)
        path_length = self.builder.call(self.strlen_function, [path_value])
        buffer_size = self.builder.add(path_length, ir.Constant(self.int32_type, 2))
        double_null_path = self.builder.call(
            self.malloc_function,
            [buffer_size],
            name="remove_directory_path_buffer",
        )
        self.builder.call(self.strcpy_function, [double_null_path, path_value])
        second_null_pointer = self.builder.gep(
            double_null_path,
            [
                self.builder.add(
                    path_length,
                    ir.Constant(self.int32_type, 1),
                )
            ],
            name="remove_directory_path_terminator",
        )
        self.builder.store(ir.Constant(ir.IntType(8), 0), second_null_pointer)

        attributes = self.builder.call(self.get_file_attributes_function, [path_value])
        invalid_attributes = self.builder.icmp_signed(
            "==",
            attributes,
            ir.Constant(self.int32_type, -1),
        )
        is_directory = self.builder.icmp_unsigned(
            "!=",
            self.builder.and_(attributes, ir.Constant(self.int32_type, 0x10)),
            ir.Constant(self.int32_type, 0),
        )
        invalid_path = self.builder.or_(invalid_attributes, self.builder.not_(is_directory))

        fn = self.builder.function
        invalid_block = fn.append_basic_block(name="remove_directory_invalid")
        remove_block = fn.append_basic_block(name="remove_directory_operation")
        merge_block = fn.append_basic_block(name="remove_directory_end")
        self.builder.cbranch(invalid_path, invalid_block, remove_block)

        self.builder.position_at_end(invalid_block)
        error_format = self.visit_LiteralNode(
            LiteralNode("str", "Error: not a directory or it does not exist: '%s'\n")
        )[0]
        self.builder.call(self.printf_function, [error_format, path_value])
        self.builder.call(self.free_function, [double_null_path])
        self.builder.branch(merge_block)
        invalid_predecessor = self.builder.block

        self.builder.position_at_end(remove_block)
        file_operation = self.builder.alloca(
            self.file_operation_type,
            name="remove_directory_file_operation",
        )
        delete_operation = ir.Constant(self.int32_type, 3)
        silent_delete_flags = ir.Constant(ir.IntType(16), 0x414)
        fields = [
            null_pointer,
            delete_operation,
            double_null_path,
            null_pointer,
            silent_delete_flags,
            ir.Constant(self.int32_type, 0),
            null_pointer,
            null_pointer,
        ]
        for idx, value in enumerate(fields):
            field_pointer = self.builder.gep(
                file_operation,
                [ir.Constant(self.int32_type, 0), ir.Constant(self.int32_type, idx)],
            )
            self.builder.store(value, field_pointer)

        res = self.builder.call(
            self.file_operation_function,
            [file_operation],
            name="remove_directory_result",
        )
        self.builder.call(self.free_function, [double_null_path])
        operation_succeeded = self.builder.icmp_signed(
            "==",
            res,
            ir.Constant(self.int32_type, 0),
        )
        error_block = fn.append_basic_block(name="remove_directory_error")
        success_block = fn.append_basic_block(name="remove_directory_success")
        self.builder.cbranch(operation_succeeded, success_block, error_block)

        self.builder.position_at_end(error_block)
        error_format = self.visit_LiteralNode(
            LiteralNode("str", "Error: could not remove directory '%s' (code %d)\n")
        )[0]
        self.builder.call(self.printf_function, [error_format, path_value, res])
        self.builder.branch(merge_block)
        error_predecessor = self.builder.block

        self.builder.position_at_end(success_block)
        self.builder.branch(merge_block)
        success_predecessor = self.builder.block

        self.builder.position_at_end(merge_block)
        succeeded = self.builder.phi(self.bool_type, name="remove_directory_succeeded")
        succeeded.add_incoming(ir.Constant(self.bool_type, 0), invalid_predecessor)
        succeeded.add_incoming(ir.Constant(self.bool_type, 0), error_predecessor)
        succeeded.add_incoming(ir.Constant(self.bool_type, 1), success_predecessor)
        return succeeded, "bool"

    def emit_directory_listing(self, path_value):
        fn = self.builder.function
        directory_attribute = ir.Constant(self.int32_type, 0x10)
        # FindFirstFileA writes the Windows WIN32_FIND_DATAA structure here.
        find_data_size = 592
        file_name_offset = 44

        attributes = self.builder.call(self.get_file_attributes_function, [path_value])
        invalid_attributes = self.builder.icmp_signed(
            "==",
            attributes,
            ir.Constant(self.int32_type, -1),
        )
        is_directory = self.builder.icmp_unsigned(
            "!=",
            self.builder.and_(attributes, directory_attribute),
            ir.Constant(self.int32_type, 0),
        )
        invalid_path = self.builder.or_(invalid_attributes, self.builder.not_(is_directory))

        error_block = fn.append_basic_block(name="directory_listing_error")
        search_block = fn.append_basic_block(name="directory_listing_search")
        empty_block = fn.append_basic_block(name="directory_listing_empty")
        empty_success_block = fn.append_basic_block(name="directory_listing_empty_success")
        search_error_block = fn.append_basic_block(name="directory_listing_search_error")
        entry_block = fn.append_basic_block(name="directory_listing_entry")
        next_block = fn.append_basic_block(name="directory_listing_next")
        next_error_check_block = fn.append_basic_block(name="directory_listing_next_error_check")
        iteration_error_block = fn.append_basic_block(name="directory_listing_iteration_error")
        print_block = fn.append_basic_block(name="directory_listing_print")
        skip_block = fn.append_basic_block(name="directory_listing_skip")
        close_block = fn.append_basic_block(name="directory_listing_close")
        merge_block = fn.append_basic_block(name="directory_listing_end")
        self.builder.cbranch(invalid_path, error_block, search_block)

        self.builder.position_at_end(error_block)
        error_format = self.visit_LiteralNode(
            LiteralNode("str", "Error: not a directory or it does not exist: '%s'\n")
        )[0]
        self.builder.call(self.printf_function, [error_format, path_value])
        self.builder.branch(merge_block)
        error_predecessor = self.builder.block

        self.builder.position_at_end(search_block)
        search_path_length = self.builder.call(self.strlen_function, [path_value])
        search_path_size = self.builder.add(
            search_path_length,
            ir.Constant(self.int32_type, 3),
        )
        search_path = self.builder.call(self.malloc_function, [search_path_size])
        self.builder.call(self.strcpy_function, [search_path, path_value])
        wildcard_suffix = self.visit_LiteralNode(LiteralNode("str", "\\*"))[0]
        self.builder.call(self.strcat_function, [search_path, wildcard_suffix])

        find_data_type = ir.ArrayType(ir.IntType(8), find_data_size)
        find_data = self.builder.alloca(find_data_type, name="directory_find_data")
        find_data_pointer = self.builder.bitcast(find_data, self.char_pointer_type)
        find_handle = self.builder.call(
            self.find_first_file_function,
            [search_path, find_data_pointer],
            name="directory_find_handle",
        )
        invalid_handle = ir.Constant(self.int64_type, -1).inttoptr(self.char_pointer_type)
        no_entries = self.builder.icmp_unsigned("==", find_handle, invalid_handle)
        count_pointer = self.builder.alloca(self.int32_type, name="directory_entry_count")
        self.builder.store(ir.Constant(self.int32_type, 0), count_pointer)
        iteration_failed_pointer = self.builder.alloca(
            self.int32_type,
            name="directory_iteration_failed",
        )
        self.builder.store(ir.Constant(self.int32_type, 0), iteration_failed_pointer)
        self.builder.cbranch(no_entries, empty_block, entry_block)

        self.builder.position_at_end(empty_block)
        search_error = self.builder.call(
            self.get_last_error_function,
            [],
            name="directory_listing_search_error_code",
        )
        no_matching_files = self.builder.icmp_unsigned(
            "==",
            search_error,
            ir.Constant(self.int32_type, 2),
        )
        self.builder.cbranch(no_matching_files, empty_success_block, search_error_block)

        self.builder.position_at_end(empty_success_block)
        self.builder.call(self.free_function, [search_path])
        self.builder.branch(merge_block)
        empty_predecessor = self.builder.block

        self.builder.position_at_end(search_error_block)
        search_error_format = self.visit_LiteralNode(
            LiteralNode("str", "Error: could not list directory '%s' (code %d)\n")
        )[0]
        self.builder.call(
            self.printf_function,
            [search_error_format, path_value, search_error],
        )
        self.builder.call(self.free_function, [search_path])
        self.builder.branch(merge_block)
        search_error_predecessor = self.builder.block

        self.builder.position_at_end(entry_block)
        file_name_pointer = self.builder.gep(
            find_data_pointer,
            [ir.Constant(self.int32_type, file_name_offset)],
            name="directory_entry_name",
        )
        current_name = file_name_pointer
        dot_name = self.visit_LiteralNode(LiteralNode("str", "."))[0]
        dot_dot_name = self.visit_LiteralNode(LiteralNode("str", ".."))[0]
        is_dot = self.builder.icmp_signed(
            "==",
            self.builder.call(self.strcmp_function, [current_name, dot_name]),
            ir.Constant(self.int32_type, 0),
        )
        is_dot_dot = self.builder.icmp_signed(
            "==",
            self.builder.call(self.strcmp_function, [current_name, dot_dot_name]),
            ir.Constant(self.int32_type, 0),
        )
        is_navigation_entry = self.builder.or_(is_dot, is_dot_dot)
        self.builder.cbranch(is_navigation_entry, skip_block, print_block)

        self.builder.position_at_end(print_block)
        line_format = self.visit_LiteralNode(LiteralNode("str", "%s\n"))[0]
        self.builder.call(self.printf_function, [line_format, current_name])
        cnt = self.builder.load(count_pointer, name="directory_entry_count_value")
        self.builder.store(
            self.builder.add(cnt, ir.Constant(self.int32_type, 1)),
            count_pointer,
        )
        self.builder.branch(next_block)

        self.builder.position_at_end(skip_block)
        self.builder.branch(next_block)

        self.builder.position_at_end(next_block)
        has_next_entry = self.builder.call(
            self.find_next_file_function,
            [find_handle, find_data_pointer],
            name="directory_has_next_entry",
        )
        has_next_entry = self.builder.icmp_signed(
            "!=",
            has_next_entry,
            ir.Constant(self.int32_type, 0),
        )
        self.builder.cbranch(has_next_entry, entry_block, next_error_check_block)

        self.builder.position_at_end(next_error_check_block)
        iteration_error = self.builder.call(
            self.get_last_error_function,
            [],
            name="directory_listing_iteration_error_code",
        )
        no_more_files = self.builder.icmp_unsigned(
            "==",
            iteration_error,
            ir.Constant(self.int32_type, 18),
        )
        self.builder.cbranch(no_more_files, close_block, iteration_error_block)

        self.builder.position_at_end(iteration_error_block)
        iteration_error_format = self.visit_LiteralNode(
            LiteralNode("str", "Error: could not continue listing directory '%s' (code %d)\n")
        )[0]
        self.builder.call(
            self.printf_function,
            [iteration_error_format, path_value, iteration_error],
        )
        self.builder.store(ir.Constant(self.int32_type, 1), iteration_failed_pointer)
        self.builder.branch(close_block)

        self.builder.position_at_end(close_block)
        self.builder.call(self.find_close_function, [find_handle])
        self.builder.call(self.free_function, [search_path])
        listed_count = self.builder.load(count_pointer, name="listed_directory_entry_count")
        iteration_failed = self.builder.load(
            iteration_failed_pointer,
            name="directory_iteration_failed_value",
        )
        listing_succeeded = self.builder.icmp_unsigned(
            "==",
            iteration_failed,
            ir.Constant(self.int32_type, 0),
        )
        listing_result = self.builder.select(
            listing_succeeded,
            listed_count,
            ir.Constant(self.int32_type, -1),
        )
        self.builder.branch(merge_block)
        close_predecessor = self.builder.block

        self.builder.position_at_end(merge_block)
        res = self.builder.phi(self.int32_type, name="directory_listing_result")
        res.add_incoming(ir.Constant(self.int32_type, -1), error_predecessor)
        res.add_incoming(ir.Constant(self.int32_type, 0), empty_predecessor)
        res.add_incoming(ir.Constant(self.int32_type, -1), search_error_predecessor)
        res.add_incoming(listing_result, close_predecessor)
        return res, "int"

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

    def visit_WhileLoopNode(self, node):
        fn = self.builder.function
        condition_block = fn.append_basic_block(name="while_condition")
        body_block = fn.append_basic_block(name="while_body")
        end_block = fn.append_basic_block(name="while_end")
        self.builder.branch(condition_block)

        self.builder.position_at_end(condition_block)
        condition_value, condition_type = self.visit(node.condition)
        if condition_type != "bool":
            raise TypeError(f"while condition must be bool, got {condition_type}")
        self.builder.cbranch(condition_value, body_block, end_block)

        self.builder.position_at_end(body_block)
        visible_variable_pointers = self.variable_pointers.copy()
        visible_type_information = self.type_information.copy()
        visible_array_information = self.array_information.copy()
        visible_dictionary_information = self.dictionary_information.copy()
        visible_constant_variables = self.constant_variables.copy()
        for stmt in node.body:
            self.visit(stmt)
        if not self.builder.block.is_terminated:
            self.builder.branch(condition_block)

        self.variable_pointers = visible_variable_pointers
        self.type_information = visible_type_information
        self.array_information = visible_array_information
        self.dictionary_information = visible_dictionary_information
        self.constant_variables = visible_constant_variables
        self.builder.position_at_end(end_block)

    def emit_dictionary_value_loop(self, dictionary_name, item_name, body):
        dictionary_pointer = self.variable_pointers[dictionary_name]
        saved_variable_pointers = self.variable_pointers.copy()
        saved_type_information = self.type_information.copy()
        saved_array_information = self.array_information.copy()
        saved_dictionary_information = self.dictionary_information.copy()
        saved_constant_variables = self.constant_variables.copy()

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
            self.constant_variables = saved_constant_variables.copy()

        self.variable_pointers = saved_variable_pointers
        self.type_information = saved_type_information
        self.array_information = saved_array_information
        self.dictionary_information = saved_dictionary_information
        self.constant_variables = saved_constant_variables

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
        saved_constant_variables = self.constant_variables.copy()
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
        self.constant_variables = saved_constant_variables
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
        visible_constant_variables = self.constant_variables.copy()

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
            self.constant_variables = visible_constant_variables.copy()
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
        self.constant_variables = visible_constant_variables
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

        if node.is_constant:
            self.constant_variables.add(node.variable_name)
        else:
            self.constant_variables.discard(node.variable_name)

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
        previous_constant_variables = self.constant_variables.copy()

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
        self.constant_variables = previous_constant_variables
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