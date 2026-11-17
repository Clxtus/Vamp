import os
import re

from diagnostics import make_error
from lexer import tokenize
from parser import (
    ArrayLiteralNode, ClassDeclarationNode, ComparisonNode, ForLoopNode, FunctionCallNode, FunctionDeclarationNode,
    IfNode, LiteralNode, ReturnNode, TupleNode, VariableAccessNode, VariableDeclarationNode, DictionaryAccessNode,
    unescape_string,
)

ENTRY_TYPE = "DataEntry"
BUILT_IN_FIELDS = ("id", "type", "path", "full_path")
NAME_PATTERN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


class DataParser:
    def __init__(self, path):
        self.path = path
        with open(path, "rb") as fh:
            src = fh.read().decode("utf-8")
        self.tokens = tokenize(src, path)
        self.lines = self.tokens.source_lines
        self.position = 0

    def error(self, message, token=None, hint=None):
        token = token or (self.tokens[self.position] if self.position < len(self.tokens) else None)
        line = token.line if token else (len(self.lines) or 1)
        column = token.column if token else 1
        width = len(token.text) if token else 1
        return make_error(SyntaxError, message, self.path, line, column, self.lines, width, hint)

    def peek(self):
        return self.tokens[self.position] if self.position < len(self.tokens) else None

    def take(self, kind=None, text=None, what=None):
        token = self.peek()
        if token is None or (kind and token.kind != kind) or (text and token.text != text):
            shown = f"'{token.text}'" if token else "the end of the file"
            raise self.error(f"Expected {what or text or kind}, got {shown}", token)
        self.position += 1
        return token

    def parse(self):
        entries = []
        seen = {}
        while self.peek() is not None:
            keyword = self.take("IDENTIFIER", what="'object'")
            if keyword.text != "object":
                raise self.error(f"Expected 'object', got '{keyword.text}'", keyword,
                                 'every entry starts with: object "name" : ( ... )')
            name_token = self.take("STRING_LITERAL", what='the object\'s name in quotes, for example "player"')
            name = unescape_string(name_token.text[1:-1])
            if not NAME_PATTERN.fullmatch(name):
                raise self.error(f'"{name}" cannot be an object name', name_token,
                                 "use letters, digits and _, starting with a letter, so code can write data.name")
            if name in seen:
                raise self.error(f'Object "{name}" is declared twice (first on line {seen[name]})', name_token)
            seen[name] = name_token.line
            self.take("COLON", what="':' after the object name")
            self.take("LPAREN", what="'(' to start the object's properties")
            properties = {}
            while self.peek() is not None and self.peek().kind != "RPAREN":
                key_token = self.take("IDENTIFIER", what="a property name")
                if key_token.text in properties:
                    raise self.error(f"Property '{key_token.text}' is given twice", key_token)
                if key_token.text in ("id", "full_path"):
                    raise self.error(f"'{key_token.text}' is filled in by Vamp and cannot be set", key_token)
                self.take("COLON", what=f"':' after '{key_token.text}'")
                properties[key_token.text] = (self.parse_value(), key_token)
                if self.peek() is not None and self.peek().kind == "COMMA":
                    self.take("COMMA")
            self.take("RPAREN", what="')' to close the object")
            entries.append((name, name_token, properties))
        return entries

    def parse_value(self):
        token = self.peek()
        if token is None:
            raise self.error("Expected a value")
        if token.kind == "STRING_LITERAL":
            self.position += 1
            return ("str", unescape_string(token.text[1:-1]))
        if token.kind in ("INT_LITERAL", "FLOAT_LITERAL") or (token.kind == "OPERATOR" and token.text == "-"):
            negative = token.kind == "OPERATOR"
            if negative:
                self.position += 1
                token = self.take(what="a number after '-'")
                if token.kind not in ("INT_LITERAL", "FLOAT_LITERAL"):
                    raise self.error("Expected a number after '-'", token)
            self.position += 0 if negative else 1
            if token.kind == "FLOAT_LITERAL":
                return ("float", -float(token.text) if negative else float(token.text))
            value = int(token.text, 0)
            return ("int", -value if negative else value)
        if token.kind == "BOOL":
            self.position += 1
            return ("bool", token.text == "true")
        if token.kind in ("LPAREN", "LBRACKET"):
            closing = "RPAREN" if token.kind == "LPAREN" else "RBRACKET"
            self.position += 1
            items = []
            while self.peek() is not None and self.peek().kind != closing:
                items.append(self.parse_value())
                if self.peek() is not None and self.peek().kind == "COMMA":
                    self.take("COMMA")
            self.take(closing, what="')'" if closing == "RPAREN" else "']'")
            kinds = {kind for kind, _ in items}
            if not items:
                raise self.error("A list or group of values cannot be empty", token)
            if kinds <= {"int", "float"} and "float" in kinds:
                items = [("float", float(value)) for _, value in items]
                kinds = {"float"}
            if len(kinds) != 1 or next(iter(kinds)) not in ("int", "float", "str", "bool"):
                raise self.error("All values in a list or group must be the same kind: numbers, text or true/false",
                                 token)
            elem = next(iter(kinds))
            if token.kind == "LPAREN":
                if len(items) < 2:
                    raise self.error("A group needs at least two values, for example (1, 2)", token)
                return (f"tuple[{','.join([elem] * len(items))}]", items)
            return (f"list:{elem}", items)
        raise self.error(f"'{token.text}' is not a value", token,
                         'values are text in quotes, numbers, true/false, (x, y, z) groups and [a, b] lists')


def value_node(type_name, value):
    if type_name.startswith(("tuple[", "list:")):
        elems = [value_node(kind, item) for kind, item in value]
        return TupleNode(elems) if type_name.startswith("tuple[") else ArrayLiteralNode(elems)
    return LiteralNode(type_name, value)


def located(node, path, token):
    node.line, node.column, node.filename = token.line, token.column, path
    return node


# every object -> its own const struct, plus DataEntry copies for all()/get().
# asset paths are checked at compile time
def build_data_module(path, module_id, session):
    entries = DataParser(path).parse()
    folder = os.path.dirname(path)
    stmts = []
    constants = {}
    classes = set()
    if not getattr(session, "data_entry_declared", False):
        session.data_entry_declared = True
        stmts.append(ClassDeclarationNode(ENTRY_TYPE, [(field, "str", True) for field in BUILT_IN_FIELDS],
                                               [], [], None, True))
    common = []
    for name, name_token, properties in entries:
        path_value = properties.get("path")
        if path_value is None:
            raise make_error(SyntaxError, f'Object "{name}" has no path', path, name_token.line, name_token.column,
                             None, len(name_token.text), 'add one, for example: path : "models/player.obj"')
        if path_value[0][0] != "str":
            raise make_error(TypeError, f'The path of "{name}" must be text', path, path_value[1].line,
                             path_value[1].column, None)
        written = path_value[0][1]
        relative = written.lstrip("/\\")
        full_path = os.path.normpath(os.path.join(folder, relative))
        if not os.path.exists(full_path):
            raise make_error(ImportError, f'The file for "{name}" does not exist: {written}', path,
                             path_value[1].line, path_value[1].column, None, len(written) + 2,
                             f"looked for {full_path} (paths are relative to the .vpdata file)")
        type_value = properties.get("type")
        if type_value is not None and type_value[0][0] != "str":
            raise make_error(TypeError, f'The type of "{name}" must be text such as ".obj"', path,
                             type_value[1].line, type_value[1].column, None)
        file_type = type_value[0][1] if type_value else os.path.splitext(written)[1]
        fields = [("id", "str", name), ("type", "str", file_type), ("path", "str", relative.replace("\\", "/")),
                  ("full_path", "str", full_path)]
        for key, ((kind, value), _) in properties.items():
            if key not in ("path", "type"):
                fields.append((key, kind, value))
        struct_name = f"{module_id}__{name}".replace(".", "_")
        stmts.append(located(ClassDeclarationNode(
            struct_name, [(field, kind, True) for field, kind, _ in fields], [], [], None, True), path, name_token))
        classes.add(struct_name)
        symbol = f"{module_id}.{name}"
        constants[name] = symbol
        stmts.append(located(VariableDeclarationNode(
            True, symbol, f"named:{struct_name}",
            FunctionCallNode(struct_name, [value_node(kind, value) for _, kind, value in fields])), path, name_token))
        common.append(fields[:4])

    entry_type = f"named:{ENTRY_TYPE}"

    def make_entry(fields):
        return FunctionCallNode(ENTRY_TYPE, [LiteralNode("str", value) for _, _, value in fields])

    fns = {}
    all_name = f"{module_id}.all"
    stmts.append(FunctionDeclarationNode(all_name, [], f"list:{entry_type}", [
        ReturnNode(ArrayLiteralNode([make_entry(fields) for fields in common]), f"list:{entry_type}")], {}))
    fns["all"] = all_name
    names_name = f"{module_id}.names"
    stmts.append(FunctionDeclarationNode(names_name, [], "list:str", [
        ReturnNode(ArrayLiteralNode([LiteralNode("str", fields[0][2]) for fields in common]), "list:str")], {}))
    fns["names"] = names_name
    get_name = f"{module_id}.get"
    stmts.append(FunctionDeclarationNode(get_name, [("id", "str")], f"optional:{entry_type}", [
        ForLoopNode("entry", FunctionCallNode(all_name, []), [
            IfNode([(ComparisonNode(DictionaryAccessNode(VariableAccessNode("entry"), "id"), "==",
                                    VariableAccessNode("id")),
                     [ReturnNode(VariableAccessNode("entry"), f"optional:{entry_type}")])], None)]),
        ReturnNode(LiteralNode("none", None), f"optional:{entry_type}")], {}))
    fns["get"] = get_name
    for stmt in stmts:
        if getattr(stmt, "line", None) is None:
            stmt.line, stmt.column, stmt.filename = 1, 1, path
    return stmts, constants, fns, classes, len(entries)
