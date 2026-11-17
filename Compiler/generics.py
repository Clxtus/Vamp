import copy
import re

from language import describe_type, split_type_list
from parser import ASTNode, LiteralNode, VariableAccessNode


def placeholder_pattern(name):
    return re.compile(r"named:" + re.escape(name) + r"(?![A-Za-z0-9_\[])")


def substitute_types(value, replacements):
    if isinstance(value, str):
        for pat, replacement in replacements:
            value = pat.sub(lambda _: replacement, value)
        return value
    if isinstance(value, LiteralNode):
        return value
    if isinstance(value, ASTNode):
        for key, child in list(vars(value).items()):
            setattr(value, key, substitute_types(child, replacements))
        return value
    if isinstance(value, list):
        return [substitute_types(item, replacements) for item in value]
    if isinstance(value, tuple):
        return tuple(substitute_types(item, replacements) for item in value)
    if isinstance(value, dict):
        return {key: substitute_types(item, replacements) for key, item in value.items()}
    return value


class Generics:
    def init_generics(self):
        if not hasattr(self, "generic_functions"):
            self.generic_functions = {}
            self.generic_classes = {}
            self.generic_function_instances = {}
            self.generic_class_arguments = {}
            self.generic_class_instances = []
            self.generic_classes_in_progress = set()

    def is_generic(self, node):
        return bool(getattr(node, "type_parameters", None))

    def register_generic(self, node):
        self.init_generics()
        if hasattr(node, "class_name"):
            if node.class_name in self.generic_classes or node.class_name in self.pending_classes:
                raise SyntaxError(f"'{node.class_name}' is already declared")
            self.generic_classes[node.class_name] = node
        else:
            if node.function_name in self.generic_functions:
                raise SyntaxError(f"Generic function '{node.function_name}' is already declared")
            self.generic_functions[node.function_name] = node

    def visit_FunctionDeclarationNode(self, node):
        if self.is_generic(node):
            self.init_generics()
            if node.function_name not in self.generic_functions:
                self.register_generic(node)
            return
        return super().visit_FunctionDeclarationNode(node)

    def visit_ClassDeclarationNode(self, node):
        if self.is_generic(node):
            self.init_generics()
            if node.class_name not in self.generic_classes:
                self.register_generic(node)
            return
        return super().visit_ClassDeclarationNode(node)

    def type_pattern(self, type_name, parameters):
        for param in parameters:
            type_name = placeholder_pattern(param).sub("$" + param, type_name)
        return type_name

    def unify(self, pattern, actual, bindings):
        if pattern.startswith("$"):
            name = pattern[1:]
            if name in bindings and bindings[name] != actual:
                raise TypeError(
                    f"Type parameter {name} would be both {describe_type(bindings[name])} and {describe_type(actual)}")
            bindings[name] = actual
            return
        if "$" not in pattern:
            return
        for prefix in ("list:", "set:", "pointer:"):
            if pattern.startswith(prefix) and actual.startswith(prefix):
                return self.unify(pattern[len(prefix):], actual[len(prefix):], bindings)
        if pattern.startswith("optional:"):
            return self.unify(pattern[9:], actual[9:] if actual.startswith("optional:") else actual, bindings)
        if pattern.startswith("map:") and actual.startswith("map:"):
            pattern_key, pattern_value = pattern[4:].split(":", 1)
            actual_key, actual_value = actual[4:].split(":", 1)
            self.unify(pattern_key, actual_key, bindings)
            return self.unify(pattern_value, actual_value, bindings)
        if pattern.startswith("tuple[") and actual.startswith("tuple["):
            for left, right in zip(split_type_list(pattern[6:-1]), split_type_list(actual[6:-1])):
                self.unify(left, right, bindings)
            return
        if pattern.startswith("fn[") and actual.startswith("fn["):
            pattern_parameters, pattern_result = self.function_signature(pattern)
            actual_parameters, actual_result = self.function_signature(actual)
            for left, right in zip(pattern_parameters, actual_parameters):
                self.unify(left, right, bindings)
            return self.unify(pattern_result, actual_result, bindings)
        if pattern.startswith("named:") and "[" in pattern and actual.startswith("class:"):
            inst = self.generic_class_arguments.get(actual[6:])
            base = pattern[6:pattern.index("[")]
            if inst is not None and inst[0] == base:
                for left, right in zip(split_type_list(pattern[pattern.index("[") + 1:-1]), inst[1]):
                    self.unify(left, right, bindings)

    def static_type(self, node):
        if isinstance(node, LiteralNode) and node.literal_type in ("int", "float", "str", "bool", "char"):
            return node.literal_type
        if isinstance(node, VariableAccessNode):
            return self.type_information.get(node.variable_name)
        return None

    def infer_bindings(self, parameters, declared_types, prepared, shown):
        bindings = {}
        for declared, (node, _, actual) in zip(declared_types, prepared):
            if actual == "list literal" and node.elements:
                elem = self.static_type(node.elements[0])
                actual = f"list:{elem}" if elem else None
            if actual in (None, "list literal", "map literal", "none"):
                continue
            self.unify(self.type_pattern(declared, parameters), actual, bindings)
        missing = [name for name in parameters if name not in bindings]
        if missing:
            raise TypeError(
                f"Cannot tell what {', '.join(missing)} should be in {shown}; "
                f"write it out, for example {shown}[int](...)")
        return bindings

    # monomorphize: deepcopy the AST, swap named:T for the real types.
    # one copy per type combo, cached by (name, types)
    def instantiate_function(self, name, bindings):
        node = self.generic_functions[name]
        key = (name, tuple(bindings[item] for item in node.type_parameters))
        info = self.generic_function_instances.get(key)
        if info is not None:
            return info
        inst = copy.deepcopy(node)
        inst.type_parameters = []
        replacements = [(placeholder_pattern(item), bindings[item]) for item in node.type_parameters]
        substitute_types(inst, replacements)
        inst.function_name = f"{name}[{', '.join(describe_type(bindings[item]) for item in node.type_parameters)}]"
        info = self.declare_function(inst)
        self.generic_function_instances[key] = info
        return info

    def call_generic_function(self, name, argument_nodes, explicit=None):
        node = self.generic_functions[name]
        declared_types = [ty_name for _, ty_name in node.parameters]
        if not len(node.parameters) - len(node.defaults) <= len(argument_nodes) <= len(node.parameters):
            raise TypeError(f"Function '{name}' expects {len(node.parameters)} arguments, got {len(argument_nodes)}")
        prepared = self.prepare_arguments(argument_nodes)
        if explicit is not None:
            if len(explicit) != len(node.type_parameters):
                raise TypeError(f"'{name}' has {len(node.type_parameters)} type parameters, got {len(explicit)}")
            bindings = dict(zip(node.type_parameters, [self.resolve_type(item) for item in explicit]))
        else:
            bindings = self.infer_bindings(node.type_parameters, declared_types, prepared, name)
        info = self.instantiate_function(name, bindings)
        vals = self.bind_call_arguments(
            info["name"], "Function", info["parameters"], info["defaults"],
            argument_nodes, prepared)
        if info["return_type"] == "void":
            self.builder.call(info["function"], vals)
            return None, "void"
        res = self.builder.call(info["function"], vals, name="call_result")
        return self.wrap_value(res, info["return_type"]), info["return_type"]

    def instantiate_class(self, base, arguments):
        self.init_generics()
        node = self.generic_classes[base]
        if len(arguments) != len(node.type_parameters):
            raise TypeError(f"'{base}' takes {len(node.type_parameters)} type arguments, got {len(arguments)}")
        name = f"{base}[{', '.join(describe_type(item) for item in arguments)}]"
        if name in self.class_definitions or name in self.generic_classes_in_progress:
            return name
        self.generic_classes_in_progress.add(name)
        try:
            inst = copy.deepcopy(node)
            inst.type_parameters = []
            inst.class_name = name
            substitute_types(inst, [(placeholder_pattern(item), value)
                                        for item, value in zip(node.type_parameters, arguments)])
            self.generic_class_arguments[name] = (base, list(arguments))
            self.pending_classes[name] = inst
            self.register_class_tree(inst)
            self.declare_class_methods(inst)
            self.build_vtables([name])
            self.generic_class_instances.append(inst)
        finally:
            self.generic_classes_in_progress.discard(name)
        return name

    def resolve_type(self, type_name):
        if type_name is not None and type_name.startswith("named:") and "[" in type_name:
            self.init_generics()
            base = type_name[6:type_name.index("[")]
            if base in self.generic_classes:
                args = [self.resolve_type(item) for item in split_type_list(type_name[type_name.index("[") + 1:-1])]
                return "class:" + self.instantiate_class(base, args)
            raise NameError(f"'{base}' is not a generic class or struct")
        return super().resolve_type(type_name)

    def construct_generic(self, base, argument_nodes, explicit=None):
        node = self.generic_classes[base]
        prepared = None
        if explicit is not None:
            args = [self.resolve_type(item) for item in explicit]
        else:
            fields = [ty_name for _, ty_name, _ in node.fields]
            if len(argument_nodes) != len(fields):
                raise TypeError(f"Class '{base}' expects {len(fields)} values, got {len(argument_nodes)}")
            prepared = self.prepare_arguments(argument_nodes)
            bindings = self.infer_bindings(node.type_parameters, fields, prepared, base)
            args = [bindings[item] for item in node.type_parameters]
        return self.create_class_instance(self.instantiate_class(base, args), argument_nodes, prepared=prepared)

    def visit_FunctionCallNode(self, node):
        self.init_generics()
        name = node.function_name
        if name not in self.type_information and name not in self.function_overloads:
            if name in self.generic_functions:
                return self.call_generic_function(name, node.arguments)
            if name in self.generic_classes:
                return self.construct_generic(name, node.arguments)
        return super().visit_FunctionCallNode(node)

    def visit_GenericCallNode(self, node):
        self.init_generics()
        if node.name in self.generic_functions:
            return self.call_generic_function(node.name, node.arguments, node.type_arguments)
        if node.name in self.generic_classes:
            return self.construct_generic(node.name, node.arguments, node.type_arguments)
        raise NameError(f"'{node.name}' is not a generic function or class")
