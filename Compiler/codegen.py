from llvmlite import ir
from parser import LiteralNode, LibraryImportNode, ImportFileNode, LibraryCallNode

class LLVMCodeGenerator:
    def __init__(self):
        self.module = ir.Module(name="vamp_module")
        self.builder = None
        self.variable_pointers = {}
        self.type_information = {}
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

    def visit_VariableAccessNode(self, node):
        variable_pointer = self.variable_pointers[node.variable_name]
        variable_type = self.type_information[node.variable_name]
        value = self.builder.load(variable_pointer, name=f"{node.variable_name}_value")
        return value, variable_type

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
        if val_ty != node.variable_type:
            raise TypeError(f"Cannot assign {val_ty} to variable '{node.variable_name}' of type {node.variable_type}")

        if node.variable_type == "int": ll_ty = self.int32_type
        elif node.variable_type == "float": ll_ty = self.float_type
        elif node.variable_type == "bool": ll_ty = self.bool_type
        elif node.variable_type == "str": ll_ty = self.char_pointer_type

        variable_pointer = self.builder.alloca(ll_ty, name=node.variable_name)
        self.builder.store(value, variable_pointer)
        self.variable_pointers[node.variable_name] = variable_pointer
        self.type_information[node.variable_name] = node.variable_type

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
        return self.int32_type

    def visit_FunctionDeclarationNode(self, node):
        previous_builder = self.builder
        previous_variable_pointers = self.variable_pointers.copy()
        previous_type_information = self.type_information.copy()

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

        self.builder = previous_builder
        self.variable_pointers = previous_variable_pointers
        self.type_information = previous_type_information
        self.type_information[f"function_{node.function_name}"] = node.return_type

    def visit_ReturnNode(self, node):
        value, val_ty = self.visit(node.expression)
        if node.return_type is not None and val_ty != node.return_type:
            raise TypeError(f"Return annotation expects {node.return_type}, got {val_ty}")
        if value.type != self.builder.function.function_type.return_type:
            raise TypeError(f"Return value of type {val_ty} does not match the function return type")
        self.builder.ret(value)

    def visit_FunctionCallNode(self, node):
        fn = self.module.get_global(node.function_name)
        argument_values = []
        for arg in node.arguments:
            value, _ = self.visit(arg)
            argument_values.append(value)

        ret_ty = self.type_information.get(f"function_{node.function_name}", "int")
        res = self.builder.call(fn, argument_values, name=f"{node.function_name}_result")
        return res, ret_ty