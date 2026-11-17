from llvmlite import ir

from diagnostics import suggest
from language import FLOAT_TYPES, INTEGER_BITS, describe_type
from libraries import OS_RUNTIME, STANDARD_LIBRARIES
from parser import MethodCallNode, VariableAccessNode


class StandardLibrary:
    def visit_LibraryCallNode(self, node):
        library = node.library_name
        resolved = getattr(node, "resolved", False)
        if not resolved and library in self.type_information and library in self.variable_pointers:
            return self.visit_MethodCallNode(
                MethodCallNode(VariableAccessNode(library), node.method_name, node.arguments))
        if library in STANDARD_LIBRARIES:
            if not resolved and library not in self.imported_libraries:
                raise NameError(f"Library '{library}' is not imported. Add 'import {library}' at top of file.")
            return self.emit_standard_library_call(node)
        if library == "os" and node.method_name in self.EVENT_METHODS:
            if not resolved and "os" not in self.imported_libraries:
                raise NameError("Library 'os' is not imported. Add 'import os' at top of file.")
            return self.emit_event_call(node)
        if library == "os" and node.method_name in OS_RUNTIME:
            if not resolved and "os" not in self.imported_libraries:
                raise NameError("Library 'os' is not imported. Add 'import os' at top of file.")
            return self.emit_standard_library_call(node, OS_RUNTIME)
        if library not in ("os", "Directory") and not resolved:
            return self.visit_MethodCallNode(
                MethodCallNode(VariableAccessNode(library), node.method_name, node.arguments))
        prev = self.narrow_os_values
        self.narrow_os_values = True
        try:
            res = super().visit_LibraryCallNode(node)
        finally:
            self.narrow_os_values = prev
        if isinstance(res, tuple) and len(res) == 2 and res[1] == "int":
            return self.fit_integer(res[0], self.int64_type), "int"
        return res

    def emit_standard_library_call(self, node, methods=None):
        library = node.library_name
        methods = methods or STANDARD_LIBRARIES[library]
        specification = methods.get(node.method_name)
        shown = f"{library}.{node.method_name}"
        if specification is None:
            close = suggest(node.method_name, methods)
            msg = f"Library '{library}' has no method named '{node.method_name}'"
            if close:
                msg += f" (did you mean '{close}'?)"
            raise NameError(msg)
        symbol, parameter_types, ret_ty = specification[:3]
        leading = specification[3] if len(specification) > 3 else ()
        if library == "thread" and node.method_name == "Start":
            return self.emit_thread_start(node)
        if len(node.arguments) != len(parameter_types):
            raise TypeError(
                f"{shown} expects {len(parameter_types)} argument{'s' if len(parameter_types) != 1 else ''}, "
                f"got {len(node.arguments)}"
            )

        vals = [ir.Constant(self.int32_type, constant) for constant in leading]
        c_parameters = ["int"] * len(leading)
        number_types = []
        for pos, (arg, parameter_type) in enumerate(zip(node.arguments, parameter_types), start=1):
            if parameter_type == "number":
                value, val_ty = self.visit(arg)
                if val_ty not in INTEGER_BITS and val_ty not in FLOAT_TYPES:
                    raise TypeError(
                        f"Argument {pos} of {shown} must be a number, got {describe_type(val_ty)}")
                number_types.append(val_ty)
                value, _ = self.cast_value(value, val_ty, "float")
                vals.append(value)
                c_parameters.append("float")
                continue
            vamp_type = "int" if parameter_type == "c_i64" else parameter_type
            value, val_ty = self.visit_as(arg, vamp_type)
            if val_ty != vamp_type:
                raise TypeError(
                    f"Argument {pos} of {shown} must be {describe_type(vamp_type)}, "
                    f"got {describe_type(val_ty)}"
                )
            vals.append(self.as_value(value))
            c_parameters.append(parameter_type)

        if ret_ty in ("number", "number_same"):
            res, _ = self.call_runtime(symbol, c_parameters, "float", vals)
            same_integer = (
                ret_ty == "number_same" and number_types
                and number_types[0] in INTEGER_BITS and len(set(number_types)) == 1
            )
            if same_integer:
                return self.cast_value(res, "float", number_types[0])
            if number_types and set(number_types) == {"f32"}:
                return self.cast_value(res, "float", "f32")
            return res, "float"
        return self.call_runtime(symbol, c_parameters, ret_ty, vals)

    def emit_thread_start(self, node):
        if not 1 <= len(node.arguments) <= 2:
            raise TypeError("thread.Start expects a function name, and optionally one int to pass to it")
        target = node.arguments[0]
        named = isinstance(target, VariableAccessNode) and target.variable_name not in self.type_information \
            and target.variable_name in self.function_overloads
        if not named and len(node.arguments) == 1:
            return self.emit_closure_thread(node)
        if not named:
            raise TypeError(
                "The first argument of thread.Start must be the name of a function, for example thread.Start(worker)")
        name = target.variable_name
        wanted = ("int",) if len(node.arguments) == 2 else ()
        chosen = None
        for candidate in self.function_overloads[name]:
            if candidate["signature"] == wanted:
                chosen = candidate
        if chosen is None:
            expected = "one int parameter" if wanted else "no parameters"
            raise TypeError(f"thread.Start needs a version of '{name}' with {expected}")
        int32 = self.int32_type
        if wanted:
            arg, argument_type = self.visit_as(node.arguments[1], "int")
            if argument_type != "int":
                raise TypeError(f"The value passed to the thread must be int, got {describe_type(argument_type)}")
            arg = self.fit_integer(arg, int32)
        else:
            arg = ir.Constant(int32, 0)

        entry = chosen.get("thread_entry")
        if entry is None:
            entry = ir.Function(
                self.module, ir.FunctionType(ir.VoidType(), [int32]),
                name=f"vamp_thread_entry.{chosen['function'].name}")
            entry.linkage = "internal"
            builder = ir.IRBuilder(entry.append_basic_block(name="entry"))
            builder.call(chosen["function"], [builder.sext(entry.args[0], self.int64_type)] if wanted else [])
            builder.ret_void()
            chosen["thread_entry"] = entry
        start = self.runtime_function("vamp_thread_start", int32, [self.char_pointer_type, int32])
        fh = self.builder.call(start, [self.builder.bitcast(entry, self.char_pointer_type), arg])
        return self.builder.sext(fh, self.int64_type), "int"
