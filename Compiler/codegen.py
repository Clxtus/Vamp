# Compiler/codegen.py
from llvmlite import ir
from parser import LiteralNode

class LLVMCodeGenerator:
    def __init__(self):
        self.module = ir.Module(name="vamp_module")
        self.builder = None
        self.symbol_table = {}
        self.type_table = {}

        # LLVM Types
        self.i32_t = ir.IntType(32)
        self.float_t = ir.FloatType()
        self.i1_t = ir.IntType(1)
        self.i8ptr_t = ir.IntType(8).as_pointer()

        # Printf Declaration
        printf_ty = ir.FunctionType(self.i32_t, [self.i8ptr_t], var_arg=True)
        self.printf = ir.Function(self.module, printf_ty, name="printf")

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

    def visit_LiteralNode(self, node):
        if node.type == "int":
            return ir.Constant(self.i32_t, node.value), "int"
        elif node.type == "float":
            return ir.Constant(self.float_t, node.value), "float"
        elif node.type == "bool":
            return ir.Constant(self.i1_t, 1 if node.value else 0), "bool"
        elif node.type == "string":
            text = node.value + "\0"
            c_str = ir.Constant(ir.ArrayType(ir.IntType(8), len(text)), bytearray(text.encode("utf-8")))
            global_str = ir.GlobalVariable(self.module, c_str.type, name=f".str_{len(self.symbol_table)}_{id(node)}")
            global_str.linkage = "internal"
            global_str.initializer = c_str
            return self.builder.bitcast(global_str, self.i8ptr_t), "string"

    def visit_VarAccessNode(self, node):
        ptr = self.symbol_table[node.name]
        var_type = self.type_table[node.name]
        val = self.builder.load(ptr, name=f"{node.name}_val")
        return val, var_type

    def visit_BinaryOpNode(self, node):
        left_val, lhs_ty = self.visit(node.left)
        right_val, rhs_ty = self.visit(node.right)

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

    def visit_VariableDeclNode(self, node):
        val, val_type = self.visit(node.value_node)
        if val_type != node.var_type:
            raise TypeError(f"Cannot assign {val_type} to variable '{node.name}' of type {node.var_type}")

        if node.var_type == "int": ll_ty = self.i32_t
        elif node.var_type == "float": ll_ty = self.float_t
        elif node.var_type == "bool": ll_ty = self.i1_t
        elif node.var_type == "string": ll_ty = self.i8ptr_t

        ptr = self.builder.alloca(ll_ty, name=node.name)
        self.builder.store(val, ptr)
        self.symbol_table[node.name] = ptr
        self.type_table[node.name] = node.var_type

    def visit_PrintlnNode(self, node):
        val, val_type = self.visit(node.expr_node)
        fmt = "%s\n\0" if val_type == "string" else "%d\n\0" if val_type == "int" else "%f\n\0" if val_type == "float" else "%s\n\0"
        
        c_str = ir.Constant(ir.ArrayType(ir.IntType(8), len(fmt)), bytearray(fmt.encode("utf-8")))
        fmt_var = ir.GlobalVariable(self.module, c_str.type, name=f".fmt_{id(node)}")
        fmt_var.linkage = "internal"
        fmt_var.initializer = c_str
        fmt_ptr = self.builder.bitcast(fmt_var, self.i8ptr_t)

        if val_type == "float":
            val = self.builder.fpext(val, ir.DoubleType())
        elif val_type == "bool":
            str_true = self.visit_LiteralNode(LiteralNode("string", "true"))[0]
            str_false = self.visit_LiteralNode(LiteralNode("string", "false"))[0]
            val = self.builder.select(val, str_true, str_false)

        self.builder.call(self.printf, [fmt_ptr, val])