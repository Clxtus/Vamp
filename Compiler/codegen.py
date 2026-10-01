from llvmlite import ir
from parser import LiteralNode, ImportLibNode, ImportFileNode, LibCallNode

class LLVMCodeGenerator:
    def __init__(self):
        self.module = ir.Module(name="vamp_module")
        self.builder = None
        self.symbol_table = {}
        self.type_table = {}
        self.imported_libs = set()
        self.str_count = 0  # Global unique string counter

        # LLVM Types
        self.i32_t = ir.IntType(32)
        self.float_t = ir.FloatType()
        self.i1_t = ir.IntType(1)
        self.i8ptr_t = ir.IntType(8).as_pointer()

        # C Runtime Function Declarations
        printf_ty = ir.FunctionType(self.i32_t, [self.i8ptr_t], var_arg=True)
        self.printf = ir.Function(self.module, printf_ty, name="printf")

        snprintf_ty = ir.FunctionType(self.i32_t, [self.i8ptr_t, self.i32_t, self.i8ptr_t], var_arg=True)
        self.snprintf = ir.Function(self.module, snprintf_ty, name="snprintf")

        malloc_ty = ir.FunctionType(self.i8ptr_t, [self.i32_t])
        self.malloc_fn = ir.Function(self.module, malloc_ty, name="malloc")

        strlen_ty = ir.FunctionType(self.i32_t, [self.i8ptr_t])
        self.strlen_fn = ir.Function(self.module, strlen_ty, name="strlen")

        strcpy_ty = ir.FunctionType(self.i8ptr_t, [self.i8ptr_t, self.i8ptr_t])
        self.strcpy_fn = ir.Function(self.module, strcpy_ty, name="strcpy")

        strcat_ty = ir.FunctionType(self.i8ptr_t, [self.i8ptr_t, self.i8ptr_t])
        self.strcat_fn = ir.Function(self.module, strcat_ty, name="strcat")

        atoi_ty = ir.FunctionType(self.i32_t, [self.i8ptr_t])
        self.atoi_fn = ir.Function(self.module, atoi_ty, name="atoi")

        atof_ty = ir.FunctionType(ir.DoubleType(), [self.i8ptr_t])
        self.atof_fn = ir.Function(self.module, atof_ty, name="atof")

        strcmp_ty = ir.FunctionType(self.i32_t, [self.i8ptr_t, self.i8ptr_t])
        self.strcmp_fn = ir.Function(self.module, strcmp_ty, name="strcmp")

        exit_ty = ir.FunctionType(ir.VoidType(), [self.i32_t])
        self.exit_fn = ir.Function(self.module, exit_ty, name="exit")

        free_ty = ir.FunctionType(ir.VoidType(), [self.i8ptr_t])
        self.free_fn = ir.Function(self.module, free_ty, name="free")

        sh_mkdir_ty = ir.FunctionType(self.i32_t, [self.i8ptr_t, self.i8ptr_t, self.i8ptr_t])
        self.sh_mkdir_fn = ir.Function(self.module, sh_mkdir_ty, name="SHCreateDirectoryExA")

    def generate_code(self, ast):
        main_ty = ir.FunctionType(self.i32_t, [])
        main_func = ir.Function(self.module, main_ty, name="main")
        block = main_func.append_basic_block(name="entry")
        self.builder = ir.IRBuilder(block)

        for stmt in ast:
            self.visit(stmt)

        self.builder.ret(ir.Constant(self.i32_t, 0))
        return str(self.module)

    def visit(self, node):
        meth_name = f"visit_{type(node).__name__}"
        visitor = getattr(self, meth_name, self.generic_visit)
        return visitor(node)

    def generic_visit(self, node):
        raise NotImplementedError(f"No visit_{type(node).__name__} method defined.")

    def visit_ImportLibNode(self, node):
        self.imported_libs.add(node.lib_name)

    def visit_ImportFileNode(self, node):
        pass

    def visit_LibCallNode(self, node):
        if node.lib_name == "os" and "os" not in self.imported_libs:
            raise NameError("Library 'os' is not imported. Add 'import os' at top of file.")

        if node.lib_name == "os":
            if node.method == "Make_Directory":
                path_val, path_type = self.visit(node.args[0])
                if path_type != "str":
                    raise TypeError("os.Make_Directory expected string path")
                null_ptr = ir.Constant(self.i8ptr_t, None)
                res = self.builder.call(self.sh_mkdir_fn, [null_ptr, path_val, null_ptr])
                return res, "int"

        elif node.lib_name == "Directory" and node.method == "exists":
            path_val, _ = self.visit(node.args[0])
            null_ptr = ir.Constant(self.i8ptr_t, None)
            res = self.builder.call(self.sh_mkdir_fn, [null_ptr, path_val, null_ptr])
            is_exists = self.builder.icmp_signed("==", res, ir.Constant(self.i32_t, -1))
            return is_exists, "bool"

        raise NotImplementedError(f"Method '{node.lib_name}.{node.method}' is not implemented.")

    def visit_LiteralNode(self, node):
        if node.type == "int":
            return ir.Constant(self.i32_t, node.value), "int"
        elif node.type == "float":
            return ir.Constant(self.float_t, node.value), "float"
        elif node.type == "bool":
            return ir.Constant(self.i1_t, 1 if node.value else 0), "bool"
        elif node.type == "str":
            text = node.value + "\0"
            c_str = ir.Constant(ir.ArrayType(ir.IntType(8), len(text)), bytearray(text.encode("utf-8")))
            self.str_count += 1
            global_str = ir.GlobalVariable(self.module, c_str.type, name=f".str_{self.str_count}")
            global_str.linkage = "internal"
            global_str.initializer = c_str
            return self.builder.bitcast(global_str, self.i8ptr_t), "str"

    def visit_VarAccessNode(self, node):
        ptr = self.symbol_table[node.name]
        var_type = self.type_table[node.name]
        val = self.builder.load(ptr, name=f"{node.name}_val")
        return val, var_type

    def visit_BinaryOpNode(self, node):
        left_val, lhs_ty = self.visit(node.left)
        right_val, rhs_ty = self.visit(node.right)

        # String Concatenation: "Hello " + x
        if lhs_ty == "str" or rhs_ty == "str":
            if lhs_ty != "str":
                left_val, _ = self.visit_CastNode(type("Cast", (), {"expr_node": node.left, "target_type": "str"})())
            if rhs_ty != "str":
                right_val, _ = self.visit_CastNode(type("Cast", (), {"expr_node": node.right, "target_type": "str"})())

            len1 = self.builder.call(self.strlen_fn, [left_val])
            len2 = self.builder.call(self.strlen_fn, [right_val])
            total_len = self.builder.add(self.builder.add(len1, len2), ir.Constant(self.i32_t, 1))

            buf = self.builder.call(self.malloc_fn, [total_len], name="str_cat_buf")
            self.builder.call(self.strcpy_fn, [buf, left_val])
            self.builder.call(self.strcat_fn, [buf, right_val])
            return buf, "str"

        if lhs_ty != rhs_ty:
            raise TypeError(f"Type mismatch: {lhs_ty} {node.op} {rhs_ty}")

        if lhs_ty == "int":
            if node.op == "+": return self.builder.add(left_val, right_val, name="addtmp"), "int"
            elif node.op == "-": return self.builder.sub(left_val, right_val, name="subtmp"), "int"
            elif node.op == "*": return self.builder.mul(left_val, right_val, name="multmp"), "int"
            elif node.op == "/": return self.builder.sdiv(left_val, right_val, name="divtmp"), "int"
        elif lhs_ty == "float":
            if node.op == "+": return self.builder.fadd(left_val, right_val, name="faddtmp"), "float"
            elif node.op == "-": return self.builder.fsub(left_val, right_val, name="fsubtmp"), "float"
            elif node.op == "*": return self.builder.fmul(left_val, right_val, name="fmultmp"), "float"
            elif node.op == "/": return self.builder.fdiv(left_val, right_val, name="fdivtmp"), "float"

        raise SyntaxError(f"Unsupported binary operator '{node.op}' for type '{lhs_ty}'")

    def visit_CastNode(self, node):
        val, val_type = self.visit(node.expr_node)
        target = node.target_type

        # 1. Identity cast (same type)
        if val_type == target:
            return val, target

        # 2. Convert TO int
        if target == "int":
            if val_type == "float":
                return self.builder.fptosi(val, self.i32_t, name="cast_int"), "int"
            elif val_type == "bool":
                return self.builder.zext(val, self.i32_t, name="cast_int"), "int"
            elif val_type == "str":
                return self.builder.call(self.atoi_fn, [val], name="atoi_tmp"), "int"

        # 3. Convert TO float
        elif target == "float":
            if val_type == "int":
                return self.builder.sitofp(val, self.float_t, name="cast_float"), "float"
            elif val_type == "bool":
                i32_val = self.builder.zext(val, self.i32_t, name="bool_i32")
                return self.builder.sitofp(i32_val, self.float_t, name="cast_float"), "float"
            elif val_type == "str":
                f64 = self.builder.call(self.atof_fn, [val], name="atof_tmp")
                return self.builder.fptrunc(f64, self.float_t, name="fptrunc_tmp"), "float"

        # 4. Convert TO bool
        elif target == "bool":
            if val_type == "int":
                return self.builder.icmp_signed("!=", val, ir.Constant(self.i32_t, 0), name="cast_bool"), "bool"
            elif val_type == "float":
                return self.builder.fcmp_ordered("!=", val, ir.Constant(self.float_t, 0.0), name="cast_bool"), "bool"
            elif val_type == "str":
                str_true = self.visit_LiteralNode(LiteralNode("str", "true"))[0]
                str_one = self.visit_LiteralNode(LiteralNode("str", "1"))[0]
                cmp_true = self.builder.call(self.strcmp_fn, [val, str_true])
                cmp_one = self.builder.call(self.strcmp_fn, [val, str_one])
                is_true = self.builder.icmp_signed("==", cmp_true, ir.Constant(self.i32_t, 0))
                is_one = self.builder.icmp_signed("==", cmp_one, ir.Constant(self.i32_t, 0))
                return self.builder.or_(is_true, is_one, name="cast_bool"), "bool"

        # 5. Convert TO str
        elif target == "str":
            buf = self.builder.call(self.malloc_fn, [ir.Constant(self.i32_t, 64)], name="str_buf")
            buf_size = ir.Constant(self.i32_t, 64)
            if val_type == "int":
                fmt = self.visit_LiteralNode(LiteralNode("str", "%d"))[0]
                self.builder.call(self.snprintf, [buf, buf_size, fmt, val])
                return buf, "str"
            elif val_type == "float":
                fmt = self.visit_LiteralNode(LiteralNode("str", "%f"))[0]
                f64 = self.builder.fpext(val, ir.DoubleType())
                self.builder.call(self.snprintf, [buf, buf_size, fmt, f64])
                return buf, "str"
            elif val_type == "bool":
                str_true = self.visit_LiteralNode(LiteralNode("str", "true"))[0]
                str_false = self.visit_LiteralNode(LiteralNode("str", "false"))[0]
                res_str = self.builder.select(val, str_true, str_false)
                return res_str, "str"  # <-- Added missing return statement here!

        raise TypeError(f"Casting from {val_type} to {target} is not supported.")

    def visit_VariableDeclNode(self, node):
        val, val_type = self.visit(node.value_node)
        if val_type != node.var_type:
            raise TypeError(f"Cannot assign {val_type} to variable '{node.name}' of type {node.var_type}")

        if node.var_type == "int": ll_ty = self.i32_t
        elif node.var_type == "float": ll_ty = self.float_t
        elif node.var_type == "bool": ll_ty = self.i1_t
        elif node.var_type == "str": ll_ty = self.i8ptr_t

        ptr = self.builder.alloca(ll_ty, name=node.name)
        self.builder.store(val, ptr)
        self.symbol_table[node.name] = ptr
        self.type_table[node.name] = node.var_type

    def visit_PrintNode(self, node):
        val, val_type = self.visit(node.expr_node)
        end = "\n\0" if node.newline else "\0"
        fmt = f"%s{end}" if val_type == "str" else f"%d{end}" if val_type == "int" else f"%f{end}" if val_type == "float" else f"%s{end}"

        c_str = ir.Constant(ir.ArrayType(ir.IntType(8), len(fmt)), bytearray(fmt.encode("utf-8")))
        self.str_count += 1
        fmt_var = ir.GlobalVariable(self.module, c_str.type, name=f".str_{self.str_count}")
        fmt_var.linkage = "internal"
        fmt_var.initializer = c_str
        fmt_ptr = self.builder.bitcast(fmt_var, self.i8ptr_t)

        if val_type == "float":
            val = self.builder.fpext(val, ir.DoubleType())
        elif val_type == "bool":
            str_true = self.visit_LiteralNode(LiteralNode("str", "true"))[0]
            str_false = self.visit_LiteralNode(LiteralNode("str", "false"))[0]
            val = self.builder.select(val, str_true, str_false)

        self.builder.call(self.printf, [fmt_ptr, val])

    def visit_ExitNode(self, node):
        val, val_type = self.visit(node.code_node)
        if val_type != "int":
            raise TypeError(f"exit() expected int exit code, got {val_type}")
        self.builder.call(self.exit_fn, [val])

    def visit_FreeNode(self, node):
        val, val_type = self.visit(node.ptr_node)
        if val_type != "str":
            raise TypeError(f"free() expected string pointer, got {val_type}")
        self.builder.call(self.free_fn, [val])