import os

from llvmlite import ir

from language import INTEGER_BITS, UNSIGNED_TYPES


class DebugInfo:
    debug = False

    def enable_debug_info(self, main_path):
        self.debug = True
        self.debug_files = {}
        self.debug_programs = {}
        self.debug_types = {}
        self.debug_declared = set()
        self.debug_last_node = None
        self.debug_main_path = main_path
        self.debug_unit = self.module.add_debug_info("DICompileUnit", {
            "language": ir.DIToken("DW_LANG_C"), "file": self.debug_file(main_path), "producer": "Vamp",
            "isOptimized": False, "runtimeVersion": 0, "emissionKind": ir.DIToken("FullDebug"),
        }, is_distinct=True)
        self.module.add_named_metadata("llvm.dbg.cu", self.debug_unit)
        int32 = ir.IntType(32)
        self.module.add_named_metadata("llvm.module.flags", self.module.add_metadata(
            [int32(2), "Debug Info Version", int32(3)]))
        self.module.add_named_metadata("llvm.module.flags", self.module.add_metadata([int32(2), "CodeView", int32(1)]))
        self.debug_routine = self.module.add_debug_info("DISubroutineType", {"types": self.module.add_metadata([])})
        self.debug_expression = self.module.add_debug_info("DIExpression", {})
        self.debug_declare = ir.Function(
            self.module, ir.FunctionType(ir.VoidType(), [ir.MetaDataType()] * 3), name="llvm.dbg.declare")

    def debug_file(self, path):
        path = os.path.abspath(path or self.debug_main_path)
        found = self.debug_files.get(path)
        if found is None:
            found = self.debug_files[path] = self.module.add_debug_info(
                "DIFile", {"filename": os.path.basename(path), "directory": os.path.dirname(path)})
        return found

    def debug_type(self, type_name):
        if type_name in self.debug_types:
            return self.debug_types[type_name]
        res = None
        if type_name in INTEGER_BITS:
            encoding = "DW_ATE_unsigned" if type_name in UNSIGNED_TYPES else "DW_ATE_signed"
            res = self.module.add_debug_info("DIBasicType", {
                "name": type_name, "size": INTEGER_BITS[type_name], "encoding": ir.DIToken(encoding)})
        elif type_name in ("float", "f32"):
            res = self.module.add_debug_info("DIBasicType", {
                "name": type_name, "size": 64 if type_name == "float" else 32, "encoding": ir.DIToken("DW_ATE_float")})
        elif type_name == "bool":
            res = self.module.add_debug_info("DIBasicType", {
                "name": "bool", "size": 8, "encoding": ir.DIToken("DW_ATE_boolean")})
        elif type_name == "char":
            res = self.module.add_debug_info("DIBasicType", {
                "name": "char", "size": 8, "encoding": ir.DIToken("DW_ATE_unsigned_char")})
        elif type_name == "str":
            res = self.module.add_debug_info("DIDerivedType", {
                "tag": ir.DIToken("DW_TAG_pointer_type"), "baseType": self.debug_type("char"), "size": 64})
        self.debug_types[type_name] = res
        return res

    def debug_subprogram(self, function, node):
        prog = self.debug_programs.get(function.name)
        if prog is None:
            filename = getattr(node, "filename", None) or self.debug_main_path
            line = getattr(node, "line", 1) or 1
            file = self.debug_file(filename)
            prog = self.module.add_debug_info("DISubprogram", {
                "name": function.name, "file": file, "scope": file, "line": line, "type": self.debug_routine,
                "isLocal": function.linkage == "internal", "isDefinition": True, "scopeLine": line,
                "unit": self.debug_unit,
            }, is_distinct=True)
            function.set_metadata("dbg", prog)
            self.debug_programs[function.name] = prog
        return prog

    def debug_locate(self, node):
        prog = self.debug_programs.get(self.builder.function.name)
        if prog is None:
            return
        self.builder.debug_metadata = self.module.add_debug_info("DILocation", {
            "line": getattr(node, "line", 1) or 1, "column": getattr(node, "column", 1) or 1, "scope": prog})

    def visit(self, node):
        if self.debug and getattr(node, "line", None):
            self.debug_last_node = node
            if self.builder.function.name == "main":
                self.debug_subprogram(self.builder.function, node)
            self.debug_locate(node)
        return super().visit(node)

    def enter_function(self, function, return_type, class_name=None):
        saved = super().enter_function(function, return_type, class_name)
        if self.debug:
            self.debug_subprogram(function, self.debug_last_node)
            self.debug_locate(self.debug_last_node)
        return saved

    def emit_function_body(self, information):
        if self.debug:
            self.debug_last_node = information["node"]
        return super().emit_function_body(information)

    def bind_variable(self, name, pointer, type_name, is_constant=False):
        super().bind_variable(name, pointer, type_name, is_constant)
        if not self.debug or not isinstance(pointer, ir.AllocaInstr) or id(pointer) in self.debug_declared:
            return
        prog = self.debug_programs.get(self.builder.function.name)
        debug_type = self.debug_type(type_name)
        if prog is None or debug_type is None or pointer.parent.parent is not self.builder.function:
            return
        self.debug_declared.add(id(pointer))
        node = self.debug_last_node
        var = self.module.add_debug_info("DILocalVariable", {
            "name": name, "scope": prog, "file": self.debug_file(getattr(node, "filename", None)),
            "line": getattr(node, "line", 1) or 1, "type": debug_type})
        self.builder.call(self.debug_declare, [pointer, var, self.debug_expression])
