import os
import re

from diagnostics import make_error, suggest, describe_choices
from lexer import tokenize
from libraries import BUILTIN_LIBRARIES, NATIVE_EXTENSIONS, SOURCE_EXTENSIONS
import native


class ASTNode:
    pass

class FunctionDeclarationNode(ASTNode):
    def __init__(self, function_name, parameters, return_type, body, defaults=None):
        self.function_name = function_name
        self.parameters = parameters
        self.return_type = return_type
        self.body = body
        self.defaults = defaults or {}

class ReturnNode(ASTNode):
    def __init__(self, expression, return_type=None):
        self.expression = expression
        self.return_type = return_type

class IfNode(ASTNode):
    def __init__(self, branches, else_body):
        self.branches = branches
        self.else_body = else_body

class ForLoopNode(ASTNode):
    def __init__(self, item_name, iterable, body):
        self.item_name = item_name
        self.iterable = iterable
        self.body = body

class WhileLoopNode(ASTNode):
    def __init__(self, condition, body):
        self.condition = condition
        self.body = body

class AssignmentNode(ASTNode):
    def __init__(self, variable_name, operator, expression):
        self.variable_name = variable_name
        self.operator = operator
        self.expression = expression

class ArrayLiteralNode(ASTNode):
    def __init__(self, elements):
        self.elements = elements

class DictionaryLiteralNode(ASTNode):
    def __init__(self, entries):
        self.entries = entries

class WindowSizeNode(ASTNode):
    def __init__(self, width, height):
        self.width = width
        self.height = height

class WindowPointNode(ASTNode):
    def __init__(self, x, y):
        self.x = x
        self.y = y

class WindowConfigNode(ASTNode):
    def __init__(self, properties):
        self.properties = properties

class ArrayAccessNode(ASTNode):
    def __init__(self, array, index):
        self.array = array
        self.index = index

class ArrayAssignmentNode(ASTNode):
    def __init__(self, array, index, operator, expression):
        self.array = array
        self.index = index
        self.operator = operator
        self.expression = expression

class MallocNode(ASTNode):
    def __init__(self, element_type, count):
        self.element_type = element_type
        self.count = count

class DictionaryAccessNode(ASTNode):
    def __init__(self, dictionary, key):
        self.dictionary = dictionary
        self.key = key

class ClassDeclarationNode(ASTNode):
    def __init__(self, class_name, fields, nested_classes=None, methods=None, parent=None, is_struct=False):
        self.class_name = class_name
        self.fields = fields
        self.nested_classes = nested_classes or []
        self.methods = methods or []
        self.parent = parent
        self.is_struct = is_struct

class ClassInstanceDeclarationNode(ASTNode):
    def __init__(self, instance_name, initializer):
        self.instance_name = instance_name
        self.initializer = initializer

class MethodCallNode(ASTNode):
    def __init__(self, receiver, method_name, arguments):
        self.receiver = receiver
        self.method_name = method_name
        self.arguments = arguments

class FunctionCallNode(ASTNode):
    def __init__(self, function_name, arguments):
        self.function_name = function_name
        self.arguments = arguments

class ImportFileNode(ASTNode):
    def __init__(self, alias, filepath):
        self.alias = alias
        self.filepath = filepath

class LibraryImportNode(ASTNode):
    def __init__(self, library_name, alias=None, members=None):
        self.library_name = library_name
        self.alias = alias
        self.members = members or []

class ModuleImportNode(ASTNode):
    def __init__(self, module_id, path, statements):
        self.module_id = module_id
        self.path = path
        self.statements = statements

class NativeImportNode(ASTNode):
    def __init__(self, module):
        self.module = module

class NativeCallNode(ASTNode):
    def __init__(self, module, function_name, arguments):
        self.module = module
        self.function_name = function_name
        self.arguments = arguments

class LibraryCallNode(ASTNode):
    def __init__(self, library_name, method_name, arguments):
        self.library_name = library_name
        self.method_name = method_name
        self.arguments = arguments

class VariableDeclarationNode(ASTNode):
    def __init__(self, is_constant, variable_name, variable_type, initializer):
        self.is_constant = is_constant
        self.variable_name = variable_name
        self.variable_type = variable_type
        self.initializer = initializer

class GroupVariableDeclarationNode(ASTNode):
    def __init__(self, is_constant, variable_names, variable_type, initializers):
        self.is_constant = is_constant
        self.variable_names = variable_names
        self.variable_type = variable_type
        self.initializers = initializers

class PrintNode(ASTNode):
    def __init__(self, expression, newline=True):
        self.expression = expression
        self.newline = newline

class ExitNode(ASTNode):
    def __init__(self, exit_code):
        self.exit_code = exit_code

class FreeNode(ASTNode):
    def __init__(self, pointer_expression):
        self.pointer_expression = pointer_expression

class LiteralNode(ASTNode):
    def __init__(self, literal_type, value):
        self.literal_type = literal_type
        self.value = value

class VariableAccessNode(ASTNode):
    def __init__(self, variable_name):
        self.variable_name = variable_name

class BinaryOpNode(ASTNode):
    def __init__(self, left, operator, right):
        self.left = left
        self.operator = operator
        self.right = right

class ComparisonNode(ASTNode):
    def __init__(self, left, operator, right):
        self.left = left
        self.operator = operator
        self.right = right

class CastNode(ASTNode):
    def __init__(self, target_type, expression):
        self.target_type = target_type
        self.expression = expression

class UnaryOpNode(ASTNode):
    def __init__(self, operator, operand):
        self.operator = operator
        self.operand = operand

class LogicalNode(ASTNode):
    def __init__(self, left, operator, right):
        self.left = left
        self.operator = operator
        self.right = right

class BreakNode(ASTNode):
    pass

class ContinueNode(ASTNode):
    pass

class MatchNode(ASTNode):
    def __init__(self, subject, cases, else_body):
        self.subject = subject
        self.cases = cases
        self.else_body = else_body

class EnumDeclarationNode(ASTNode):
    def __init__(self, enum_name, members):
        self.enum_name = enum_name
        self.members = members

class TargetAssignmentNode(ASTNode):
    def __init__(self, target, operator, expression):
        self.target = target
        self.operator = operator
        self.expression = expression

class MapLiteralNode(ASTNode):
    def __init__(self, entries):
        self.entries = entries

class TryNode(ASTNode):
    def __init__(self, body, error_name, catch_body):
        self.body = body
        self.error_name = error_name
        self.catch_body = catch_body

class ThrowNode(ASTNode):
    def __init__(self, expression):
        self.expression = expression

ASSIGNMENT_OPERATORS = ("=", "+=", "-=", "*=", "/=", "%=", "&=", "|=", "^=", "<<=", ">>=")
MAP_KEY_TYPES = ("str", "char", "int", "i8", "i16", "i32", "u8", "u16", "u32", "u64")
TYPE_ALIASES = {"i64": "int", "double": "float"}
CHAR_ESCAPES = {"n": 10, "t": 9, "r": 13, "0": 0, "\\": 92, "'": 39}


STRING_ESCAPES = {"n": chr(10), "t": chr(9), '"': '"', "\\": "\\"}


def unescape_string(text):
    if "\\" not in text:
        return text
    res = []
    idx = 0
    while idx < len(text):
        ch = text[idx]
        if ch == "\\" and idx + 1 < len(text) and text[idx + 1] in STRING_ESCAPES:
            res.append(STRING_ESCAPES[text[idx + 1]])
            idx += 2
        else:
            res.append(ch)
            idx += 1
    return "".join(res)


def collect_returns(statements):
    found = []
    for stmt in statements or []:
        if isinstance(stmt, ReturnNode):
            found.append(stmt)
        elif isinstance(stmt, IfNode):
            for _, body in stmt.branches:
                found.extend(collect_returns(body))
            found.extend(collect_returns(stmt.else_body))
        elif isinstance(stmt, (ForLoopNode, WhileLoopNode)):
            found.extend(collect_returns(stmt.body))
        elif isinstance(stmt, MatchNode):
            for _, body in stmt.cases:
                found.extend(collect_returns(body))
            found.extend(collect_returns(stmt.else_body))
        elif isinstance(stmt, TryNode):
            found.extend(collect_returns(stmt.body))
            found.extend(collect_returns(stmt.catch_body))
    return found


KIND_NAMES = {
    "LPAREN": "'('", "RPAREN": "')'", "LBRACE": "'{'", "RBRACE": "'}'", "LBRACKET": "'['",
    "RBRACKET": "']'", "COLON": "':'", "COMMA": "','", "SEMICOLON": "';'", "DOT": "'.'",
    "IDENTIFIER": "a name", "TYPE": "a type (int, float, bool, str, ...)", "KEYWORD": "a keyword",
    "INT_LITERAL": "an integer", "FLOAT_LITERAL": "a float", "STRING_LITERAL": "a string",
    "OPERATOR": "an operator", "IMPORT": "'import'", "BOOL": "true or false",
}


class Binding:
    def __init__(self, kind, target, line, column, extra=None):
        self.kind = kind
        self.target = target
        self.line = line
        self.column = column
        self.extra = extra


class ModuleInfo:
    def __init__(self, module_id, path):
        self.module_id = module_id
        self.path = path
        self.functions = {}
        self.classes = set()
        self.statements = []
        self.is_native = False


class ParseSession:
    def __init__(self):
        self.stack = []
        self.modules = {}
        self.module_ids = set()
        self.class_origins = {}


STATEMENT_DESCRIPTIONS = {
    "VariableDeclarationNode": "a val/const declaration",
    "PrintNode": "a print statement",
    "ExitNode": "an exit statement",
    "FreeNode": "a free statement",
    "IfNode": "an if statement",
    "WhileNode": "a while loop",
    "ForNode": "a for loop",
    "AssignmentNode": "an assignment",
    "ArrayAssignmentNode": "an assignment",
    "LibraryCallNode": "a library call",
    "MethodCallNode": "a method call",
    "FunctionCallNode": "a function call",
    "NativeCallNode": "a C/C++ call",
    "ReturnNode": "a return statement",
}


class Parser:
    def __init__(self, tokens, filename=None, source_lines=None, session=None):
        self.tokens = tokens
        self.position = 0
        self.filename = filename or getattr(tokens, "filename", None)
        self.source_lines = source_lines or getattr(tokens, "source_lines", None)
        self.base_dir = os.path.dirname(os.path.abspath(self.filename)) if self.filename else os.getcwd()
        self.session = session or ParseSession()
        self.bindings = {}
        self.declared_functions = {}

    def error(self, message, token=None, hint=None, kind=SyntaxError):
        if token is None:
            token = self.peek()
            if token is None and self.tokens:
                token = self.tokens[-1]
        line = column = 0
        width = 1
        if token is not None:
            line, column, width = token.line, token.column, max(len(token.text), 1)
        return make_error(kind, message, self.filename, line, column, self.source_lines, width, hint)

    def error_at_node(self, node, message, hint=None, kind=SyntaxError):
        return make_error(
            kind, message, getattr(node, "filename", self.filename), getattr(node, "line", 0),
            getattr(node, "column", 0), self.source_lines, 1, hint,
        )

    def describe_token(self, token):
        if token is None:
            return "end of input"
        return f"'{token.text}'"

    def peek(self):
        return self.tokens[self.position] if self.position < len(self.tokens) else None

    def at_word(self, word):
        token = self.peek()
        return token is not None and token.kind == "IDENTIFIER" and token.text == word

    def consume(self, expected_kind=None, expected_text=None):
        token = self.peek()
        if not token:
            wanted = f"'{expected_text}'" if expected_text else KIND_NAMES.get(expected_kind, expected_kind or "more input")
            raise self.error(f"Unexpected end of input: expected {wanted}")
        if expected_kind and token.kind != expected_kind:
            raise self.error(
                f"Expected {KIND_NAMES.get(expected_kind, expected_kind)}, got {self.describe_token(token)}", token)
        if expected_text and token.text != expected_text:
            raise self.error(f"Expected '{expected_text}', got '{token.text}'", token)
        self.position += 1
        return token

    def expect_name(self, what):
        token = self.peek()
        if token is None:
            raise self.error(f"Unexpected end of input: expected {what}")
        if token.kind != "IDENTIFIER":
            hint = None
            if token.kind in ("TYPE", "KEYWORD", "CAST", "BOOL", "IMPORT"):
                hint = f"'{token.text}' is a reserved word and cannot be used as a name"
            raise self.error(f"Expected {what}, got {self.describe_token(token)}", token, hint)
        self.position += 1
        return token

    def expect_string(self, what):
        token = self.peek()
        if token is None:
            raise self.error(f"Unexpected end of input: expected {what}")
        if token.kind != "STRING_LITERAL":
            raise self.error(f"Expected {what}, got {self.describe_token(token)}", token,
                             'write the path in double quotes, for example "helpers.vp"')
        self.position += 1
        return token

    def parse_program(self, flatten=True):
        stmts = []
        while self.peek():
            node = self.parse_statement(top_level=True)
            if flatten and isinstance(node, ModuleImportNode):
                stmts.extend(node.statements)
            else:
                stmts.append(node)
        return stmts

    def parse_statement(self, top_level=False):
        first_token = self.peek()
        node = self._parse_statement(top_level)
        if first_token is not None and node is not None and not hasattr(node, "line"):
            node.line = first_token.line
            node.column = first_token.column
            node.filename = self.filename
        return node

    def _parse_statement(self, top_level):
        current_token = self.peek()
        if current_token is None:
            raise self.error("Unexpected end of input")

        if current_token.kind == "IMPORT":
            self.require_top_level(top_level, current_token)
            return self.parse_import_statement()

        elif (
            current_token.kind == "IDENTIFIER"
            and current_token.text == "from"
            and self.position + 1 < len(self.tokens)
            and self.tokens[self.position + 1].kind in ("IDENTIFIER", "STRING_LITERAL")
        ):
            self.require_top_level(top_level, current_token)
            return self.parse_from_import_statement()

        elif current_token.kind == "KEYWORD" and current_token.text in ("val", "const"):
            return self.parse_variable_declaration()

        elif current_token.kind == "KEYWORD" and current_token.text == "class":
            return self.parse_class_declaration()

        elif current_token.kind == "KEYWORD" and current_token.text == "var":
            return self.parse_variable_declaration()

        elif current_token.kind == "KEYWORD" and current_token.text == "for":
            return self.parse_for_loop()

        elif current_token.kind == "KEYWORD" and current_token.text == "while":
            return self.parse_while_loop()

        elif current_token.kind == "IDENTIFIER" and current_token.text == "func":
            return self.parse_function_declaration()

        elif current_token.kind == "IDENTIFIER" and current_token.text == "if":
            return self.parse_if_statement()

        elif current_token.kind == "IDENTIFIER" and current_token.text == "return":
            self.consume("IDENTIFIER")
            ret_ty = None
            if self.peek() and self.peek().kind == "COLON":
                self.consume("COLON")
                if self.at_word("void"):
                    self.consume("IDENTIFIER")
                    ret_ty = "void"
                    expr = None
                else:
                    ret_ty = self.parse_type("a return type after ':'")
                    self.consume("LPAREN")
                    expr = self.parse_expression()
                    self.consume("RPAREN")
            else:
                expr = self.parse_expression()
            return ReturnNode(expr, ret_ty)

        elif current_token.kind == "IDENTIFIER":
            next_token = self.tokens[self.position + 1] if self.position + 1 < len(self.tokens) else None
            word = current_token.text
            used_as_value = next_token is not None and (
                next_token.kind in ("DOT", "LBRACKET")
                or (next_token.kind == "OPERATOR" and next_token.text in ASSIGNMENT_OPERATORS)
            )
            if not used_as_value:
                if word in ("break", "continue") and (next_token is None or next_token.kind != "LPAREN"):
                    self.consume("IDENTIFIER")
                    return BreakNode() if word == "break" else ContinueNode()
                if word == "match" and next_token is not None and next_token.kind == "LPAREN":
                    return self.parse_match_statement()
                if word == "enum" and next_token is not None and next_token.kind == "IDENTIFIER":
                    return self.parse_enum_declaration()
                if word == "struct" and next_token is not None and next_token.kind == "IDENTIFIER":
                    return self.parse_class_declaration(is_struct=True)
                if word == "try" and next_token is not None and next_token.kind == "COLON":
                    return self.parse_try_statement()
                if word == "throw" and next_token is not None and next_token.kind == "LPAREN":
                    self.consume("IDENTIFIER")
                    self.consume("LPAREN")
                    msg = self.parse_expression()
                    self.consume("RPAREN")
                    return ThrowNode(msg)

            if next_token is not None and next_token.kind == "LBRACKET":
                saved_position = self.position
                array = VariableAccessNode(self.consume("IDENTIFIER").text)
                self.consume("LBRACKET")
                idx = self.parse_expression()
                self.consume("RBRACKET")
                if (
                    self.peek()
                    and self.peek().kind == "OPERATOR"
                    and self.peek().text in ASSIGNMENT_OPERATORS
                ):
                    operator = self.consume("OPERATOR").text
                    expr = self.parse_expression()
                    return ArrayAssignmentNode(array, idx, operator, expr)
                self.position = saved_position
                return self.parse_target_statement()

            if (
                next_token is not None
                and next_token.kind == "OPERATOR"
                and next_token.text in ASSIGNMENT_OPERATORS
            ):
                return self.parse_assignment_or_class_instance()

            if next_token is not None and next_token.kind == "DOT":
                saved_position = self.position
                receiver_token = self.consume("IDENTIFIER")
                receiver_name = receiver_token.text
                self.consume("DOT")
                method_token = self.expect_name("a method name after '.'")
                meth_name = method_token.text
                if self.peek() and self.peek().kind == "LPAREN":
                    self.consume("LPAREN")
                    args = self.parse_call_arguments()
                    self.consume("RPAREN")
                    after = self.peek()
                    chained = after is not None and (
                        after.kind in ("DOT", "LBRACKET")
                        or (after.kind == "OPERATOR" and after.text in ASSIGNMENT_OPERATORS)
                    )
                    if not chained:
                        resolved = self.resolve_qualified_call(receiver_token, method_token, args)
                        if resolved is not None:
                            return resolved
                        if receiver_name in ("os", "Directory"):
                            return LibraryCallNode(receiver_name, meth_name, args)
                        return MethodCallNode(VariableAccessNode(receiver_name), meth_name, args)
                self.position = saved_position
                return self.parse_target_statement()

            if current_token.text in ("println", "print"):
                is_println = current_token.text == "println"
                self.consume("IDENTIFIER")
                self.consume("LPAREN")
                expr = self.parse_expression()
                self.consume("RPAREN")
                return PrintNode(expr, newline=is_println)
            elif current_token.text == "exit":
                self.consume("IDENTIFIER")
                self.consume("LPAREN")
                exit_code = self.parse_expression()
                self.consume("RPAREN")
                return ExitNode(exit_code)
            elif current_token.text == "free":
                self.consume("IDENTIFIER")
                self.consume("LPAREN")
                pointer_expression = self.parse_expression()
                self.consume("RPAREN")
                return FreeNode(pointer_expression)

        if (
            current_token.kind == "IDENTIFIER"
            and self.position + 1 < len(self.tokens)
            and self.tokens[self.position + 1].kind == "LPAREN"
        ):
            name_token = self.consume("IDENTIFIER")
            self.consume("LPAREN")
            args = self.parse_call_arguments()
            self.consume("RPAREN")
            return self.resolve_call(name_token, args)

        raise self.error(f"Unsupported statement starting with {self.describe_token(current_token)}", current_token)

    def parse_target_statement(self):
        start_token = self.peek()
        target = self.parse_postfix_expression()
        token = self.peek()
        if token is not None and token.kind == "OPERATOR" and token.text in ASSIGNMENT_OPERATORS:
            if not isinstance(target, (VariableAccessNode, ArrayAccessNode, DictionaryAccessNode)):
                raise self.error("Only variables, fields and indexed values can be assigned to", start_token)
            operator = self.consume("OPERATOR").text
            return TargetAssignmentNode(target, operator, self.parse_expression())
        if isinstance(target, (FunctionCallNode, MethodCallNode, LibraryCallNode, NativeCallNode)):
            return target
        raise self.error(
            f"Unsupported statement starting with {self.describe_token(start_token)}",
            start_token,
            "a statement that starts with a value must assign to it or call something",
        )

    def parse_type(self, what="a type"):
        token = self.peek()
        if token is None:
            raise self.error(f"Unexpected end of input: expected {what}")
        if token.kind in ("TYPE", "CAST"):
            self.position += 1
            return TYPE_ALIASES.get(token.text, token.text)
        if token.kind == "IDENTIFIER":
            following = self.tokens[self.position + 1] if self.position + 1 < len(self.tokens) else None
            if token.text in ("list", "map") and following is not None and following.kind == "LBRACKET":
                self.position += 2
                if token.text == "list":
                    elem_ty = self.parse_type("a list element type")
                    self.consume("RBRACKET")
                    return f"list:{elem_ty}"
                key_token = self.peek()
                key_ty = self.parse_type("a map key type")
                if key_ty not in MAP_KEY_TYPES:
                    raise self.error("Map keys must be str, char or an integer type", key_token)
                self.consume("COMMA")
                val_ty = self.parse_type("a map value type")
                self.consume("RBRACKET")
                return f"map:{key_ty}:{val_ty}"
            self.position += 1
            if token.text == "json":
                return "json"
            return f"named:{token.text}"
        raise self.error(
            f"Expected {what}, got {self.describe_token(token)}",
            token,
            "types are int, float, bool, str, double, char, i8 to i64, u8 to u64, list[T], map[K, V], "
            "or the name of a class, struct or enum",
        )

    def parse_match_statement(self):
        match_token = self.consume("IDENTIFIER", "match")
        subject = self.parse_parenthesized_condition()
        self.consume("COLON")
        self.consume("LPAREN")
        cases = []
        else_body = None
        while self.peek() and self.peek().kind != "RPAREN":
            following = self.tokens[self.position + 1] if self.position + 1 < len(self.tokens) else None
            if self.at_word("else") and following is not None and following.kind == "COLON":
                self.consume("IDENTIFIER")
                self.consume("COLON")
                else_body = self.parse_block()
                break
            patterns = [self.parse_expression()]
            while self.peek() and self.peek().kind == "COMMA":
                self.consume("COMMA")
                patterns.append(self.parse_expression())
            self.consume("COLON")
            cases.append((patterns, self.parse_block()))
        if self.peek() and self.peek().kind != "RPAREN":
            raise self.error("'else' must be the last branch of a match", self.peek())
        self.consume("RPAREN")
        if not cases and else_body is None:
            raise self.error("A match needs at least one branch", match_token)
        return MatchNode(subject, cases, else_body)

    def parse_enum_declaration(self):
        self.consume("IDENTIFIER", "enum")
        name_token = self.expect_name("an enum name after 'enum'")
        self.consume("COLON")
        self.consume("LPAREN")
        members = []
        seen = set()
        next_value = 0
        while self.peek() and self.peek().kind != "RPAREN":
            member_token = self.expect_name("an enum member name")
            if member_token.text in seen:
                raise self.error(f"Enum member '{member_token.text}' is declared twice", member_token)
            seen.add(member_token.text)
            if self.peek() and self.peek().kind == "OPERATOR" and self.peek().text == "=":
                self.consume("OPERATOR")
                negative = False
                if self.peek() and self.peek().kind == "OPERATOR" and self.peek().text == "-":
                    self.consume("OPERATOR")
                    negative = True
                next_value = self.parse_integer_text(self.consume("INT_LITERAL").text)
                if negative:
                    next_value = -next_value
            members.append((member_token.text, next_value))
            next_value += 1
            if self.peek() and self.peek().kind == "COMMA":
                self.consume("COMMA")
        self.consume("RPAREN")
        if not members:
            raise self.error(f"Enum '{name_token.text}' must declare at least one member", name_token)
        return EnumDeclarationNode(name_token.text, members)

    def parse_try_statement(self):
        self.consume("IDENTIFIER", "try")
        self.consume("COLON")
        body = self.parse_block()
        if not self.at_word("catch"):
            raise self.error(
                f"Expected 'catch' after a try block, got {self.describe_token(self.peek())}",
                self.peek(),
                "the form is: try : ( ... ) catch (error) : ( ... )",
            )
        self.consume("IDENTIFIER")
        error_name = None
        if self.peek() and self.peek().kind == "LPAREN":
            self.consume("LPAREN")
            error_name = self.expect_name("a name for the caught error").text
            self.consume("RPAREN")
        self.consume("COLON")
        return TryNode(body, error_name, self.parse_block())

    @staticmethod
    def parse_integer_text(text):
        if text[:2].lower() in ("0x", "0b"):
            return int(text, 0)
        return int(text)

    def parse_class_declaration(self, is_struct=False):
        if is_struct:
            self.consume("IDENTIFIER", "struct")
        else:
            self.consume("KEYWORD", "class")
        class_token = self.expect_name("a struct name after 'struct'" if is_struct else "a class name after 'class'")
        cls_name = class_token.text
        parent_name = None
        if not is_struct and self.peek() and self.peek().kind == "LPAREN":
            self.consume("LPAREN")
            parent_name = self.expect_name("the name of the class to inherit from").text
            self.consume("RPAREN")
        previous_origin = self.session.class_origins.get(cls_name)
        if previous_origin is not None and previous_origin[0] != self.filename:
            raise self.error(
                f"Class '{cls_name}' is already declared in {previous_origin[0]}:{previous_origin[1]}",
                class_token,
                "classes share one global namespace across imported files; rename one of them",
            )
        self.session.class_origins.setdefault(cls_name, (self.filename, class_token.line))
        self.consume("COLON")
        self.consume("LPAREN")

        fields = []
        nested_classes = []
        meths = []
        while self.peek() and self.peek().kind != "RPAREN":
            if self.peek().kind == "KEYWORD" and self.peek().text == "class":
                nested_classes.append(self.parse_class_declaration())
                continue
            if self.peek().kind == "IDENTIFIER" and self.peek().text == "func":
                if is_struct:
                    raise self.error("A struct can only declare fields", self.peek(),
                                     "use a class if you need methods")
                meths.append(self.parse_function_declaration(is_method=True))
                continue

            declaration_keyword = self.consume("KEYWORD").text
            if declaration_keyword not in ("val", "const"):
                raise self.error("Class members must be fields, nested classes, or func methods")
            field_name = self.consume("IDENTIFIER").text
            self.consume("COLON")
            field_ty = self.parse_type()
            fields.append((field_name, field_ty, declaration_keyword == "const"))

        self.consume("RPAREN")
        if not fields and not nested_classes and not meths and parent_name is None:
            raise self.error(f"Class '{cls_name}' must declare a field, nested class, or method")
        return ClassDeclarationNode(cls_name, fields, nested_classes, meths, parent_name, is_struct)

    def parse_assignment_or_class_instance(self):
        var_name = self.consume("IDENTIFIER").text
        operator = self.consume("OPERATOR").text
        initializer = self.parse_expression()
        return AssignmentNode(var_name, operator, initializer)

    def parse_call_arguments(self):
        args = []
        if self.peek() and self.peek().kind != "RPAREN":
            args.append(self.parse_expression())
            while self.peek() and self.peek().kind == "COMMA":
                self.consume("COMMA")
                args.append(self.parse_expression())
        return args

    def parse_if_statement(self):
        self.consume("IDENTIFIER", "if")
        cond = self.parse_parenthesized_condition()
        self.consume("COLON")
        branches = [(cond, self.parse_block())]
        else_body = None

        while self.peek() and self.peek().kind == "IDENTIFIER" and self.peek().text == "else":
            self.consume("IDENTIFIER", "else")
            if self.peek() and self.peek().kind == "IDENTIFIER" and self.peek().text == "if":
                self.consume("IDENTIFIER", "if")
                cond = self.parse_parenthesized_condition()
                self.consume("COLON")
                branches.append((cond, self.parse_block()))
            else:
                self.consume("COLON")
                else_body = self.parse_block()
                break

        return IfNode(branches, else_body)

    def parse_parenthesized_condition(self):
        self.consume("LPAREN")
        cond = self.parse_expression()
        self.consume("RPAREN")
        return cond

    def parse_block(self):
        self.consume("LPAREN")
        stmts = []
        while self.peek() and self.peek().kind != "RPAREN":
            stmts.append(self.parse_statement())
        self.consume("RPAREN")
        return stmts

    def parse_for_loop(self):
        self.consume("KEYWORD", "for")
        self.consume("LPAREN")
        item_name = self.consume("IDENTIFIER").text
        self.consume("RPAREN")
        self.consume("KEYWORD", "in")
        self.consume("LPAREN")
        iterable = self.parse_expression()
        self.consume("RPAREN")
        self.consume("COLON")
        return ForLoopNode(item_name, iterable, self.parse_block())

    def parse_while_loop(self):
        self.consume("KEYWORD", "while")
        cond = self.parse_parenthesized_condition()
        self.consume("COLON")
        return WhileLoopNode(cond, self.parse_block())

    def parse_function_declaration(self, is_method=False):
        self.consume("IDENTIFIER", "func")
        function_token = self.expect_name("a function name after 'func'")
        function_name = function_token.text
        if not is_method:
            self.check_name_not_imported(function_token, "function")
            self.declared_functions[function_name] = function_token
        self.consume("LPAREN")
        params = []
        defaults = {}
        while self.peek() and self.peek().kind != "RPAREN":
            parameter_token = self.expect_name("a parameter name")
            self.consume("COLON")
            parameter_type = self.parse_type()
            if self.peek() and self.peek().kind == "OPERATOR" and self.peek().text == "=":
                self.consume("OPERATOR")
                defaults[len(params)] = self.parse_expression()
            elif defaults:
                raise self.error(
                    f"Parameter '{parameter_token.text}' needs a default value",
                    parameter_token,
                    "parameters without a default value must come before the ones that have one",
                )
            params.append((parameter_token.text, parameter_type))
            if self.peek() and self.peek().kind == "COMMA":
                self.consume("COMMA")
            else:
                break
        self.consume("RPAREN")

        function_return_type = None
        if self.peek() and self.peek().kind == "COLON":
            self.consume("COLON")
            if self.peek() and self.peek().kind != "LPAREN":
                if self.at_word("void"):
                    self.consume("IDENTIFIER")
                    function_return_type = "void"
                else:
                    function_return_type = self.parse_type("a return type")
                self.consume("COLON")

        self.consume("LPAREN")
        body = []
        while self.peek() and self.peek().kind != "RPAREN":
            body.append(self.parse_statement())
        self.consume("RPAREN")

        all_returns = collect_returns(body)
        annotated_return_types = {
            stmt.return_type
            for stmt in all_returns
            if stmt.return_type is not None
        }
        if len(annotated_return_types) > 1:
            raise self.error("Return type annotations in a function must match")
        if annotated_return_types:
            annotated_type = next(iter(annotated_return_types))
            if function_return_type is not None and function_return_type != annotated_type:
                raise self.error("Function and return statement types must match")
            function_return_type = annotated_type
        if function_return_type is None:
            function_return_type = "int" if all_returns else "void"

        return FunctionDeclarationNode(function_name, params, function_return_type, body, defaults)

    def parse_variable_declaration(self):
        declaration_keyword = self.consume("KEYWORD").text
        is_constant = declaration_keyword == "const"
        first_name_token = self.expect_name(f"a variable name after '{declaration_keyword}'")
        self.check_name_not_imported(first_name_token, "variable")
        variable_names = [first_name_token.text]
        while self.peek() and self.peek().kind == "COMMA":
            self.consume("COMMA")
            more_token = self.expect_name("a variable name after ','")
            self.check_name_not_imported(more_token, "variable")
            variable_names.append(more_token.text)

        variable_type = None
        if self.peek() and self.peek().kind == "COLON":
            self.consume("COLON")
            variable_type = self.parse_type()
        elif is_constant:
            raise self.error("const declarations require an explicit type")
        elif len(variable_names) > 1:
            raise self.error("Grouped declarations require an explicit type")

        has_initializer = self.peek() and self.peek().kind == "OPERATOR" and self.peek().text == "="
        if has_initializer:
            self.consume("OPERATOR", "=")
            initializers = [self.parse_expression()]
            while self.peek() and self.peek().kind == "COMMA":
                self.consume("COMMA")
                initializers.append(self.parse_expression())
        else:
            initializers = None
            if is_constant:
                raise self.error("const declarations require an initializer")

        if len(variable_names) == 1 and initializers is not None:
            return VariableDeclarationNode(
                is_constant,
                variable_names[0],
                variable_type,
                initializers[0],
            )
        return GroupVariableDeclarationNode(
            is_constant,
            variable_names,
            variable_type,
            initializers,
        )

    def at_operator(self, *operators):
        token = self.peek()
        return token is not None and token.kind == "OPERATOR" and token.text in operators

    def parse_expression(self):
        left = self.parse_logical_and_expression()
        while self.at_operator("||", "or"):
            self.consume("OPERATOR")
            left = LogicalNode(left, "||", self.parse_logical_and_expression())
        return left

    def parse_logical_and_expression(self):
        left = self.parse_logical_not_expression()
        while self.at_operator("&&", "and"):
            self.consume("OPERATOR")
            left = LogicalNode(left, "&&", self.parse_logical_not_expression())
        return left

    def parse_logical_not_expression(self):
        if self.at_operator("not"):
            self.consume("OPERATOR")
            return UnaryOpNode("!", self.parse_logical_not_expression())
        return self.parse_comparison_expression()

    def parse_comparison_expression(self):
        left = self.parse_binary_level(0)
        while self.peek() and self.peek().kind == "COMPARISON_OPERATOR":
            operator = self.consume("COMPARISON_OPERATOR").text
            left = ComparisonNode(left, operator, self.parse_binary_level(0))
        return left

    BINARY_LEVELS = (("|",), ("^",), ("&",), ("<<", ">>"), ("+", "-"), ("*", "/", "%"))

    def parse_binary_level(self, level):
        if level == len(self.BINARY_LEVELS):
            return self.parse_unary_expression()
        left = self.parse_binary_level(level + 1)
        while self.at_operator(*self.BINARY_LEVELS[level]):
            operator = self.consume("OPERATOR").text
            left = BinaryOpNode(left, operator, self.parse_binary_level(level + 1))
        return left

    def parse_additive_expression(self):
        return self.parse_binary_level(4)

    def parse_unary_expression(self):
        if self.at_operator("-", "!", "~"):
            operator = self.consume("OPERATOR").text
            operand = self.parse_unary_expression()
            if operator == "-" and isinstance(operand, LiteralNode) and operand.literal_type in ("int", "float"):
                return LiteralNode(operand.literal_type, -operand.value)
            return UnaryOpNode(operator, operand)
        return self.parse_postfix_expression()

    def parse_postfix_expression(self):
        node = self.parse_primary_expression()
        while True:
            token = self.peek()
            if token is None:
                break
            if token.kind == "LBRACKET":
                self.consume("LBRACKET")
                idx = self.parse_expression()
                self.consume("RBRACKET")
                node = ArrayAccessNode(node, idx)
            elif token.kind == "DOT":
                self.consume("DOT")
                member_token = self.expect_name("a name after '.'")
                if self.peek() and self.peek().kind == "LPAREN":
                    self.consume("LPAREN")
                    args = self.parse_call_arguments()
                    self.consume("RPAREN")
                    node = MethodCallNode(node, member_token.text, args)
                else:
                    node = DictionaryAccessNode(node, member_token.text)
            else:
                break
        return node

    def parse_primary_expression(self):
        current_token = self.peek()
        if current_token is None:
            raise self.error("Unexpected end of input: expected a value")
        if current_token.kind == "LBRACKET":
            self.consume("LBRACKET")
            elems = []
            if self.peek() and self.peek().kind != "RBRACKET":
                elems.append(self.parse_expression())
                while self.peek() and self.peek().kind == "COMMA":
                    self.consume("COMMA")
                    elems.append(self.parse_expression())
            self.consume("RBRACKET")
            return ArrayLiteralNode(elems)
        elif current_token.kind == "LBRACE":
            self.consume("LBRACE")
            after_key = self.tokens[self.position + 1] if self.position + 1 < len(self.tokens) else None
            after_colon = self.tokens[self.position + 2] if self.position + 2 < len(self.tokens) else None
            is_dictionary = (
                self.peek() is not None
                and self.peek().kind in ("IDENTIFIER", "STRING_LITERAL")
                and after_key is not None and after_key.kind == "COLON"
                and after_colon is not None and after_colon.kind == "TYPE"
            )
            if not is_dictionary:
                map_entries = []
                while self.peek() and self.peek().kind != "RBRACE":
                    key = self.parse_expression()
                    self.consume("COLON")
                    map_entries.append((key, self.parse_expression()))
                    if self.peek() and self.peek().kind == "COMMA":
                        self.consume("COMMA")
                    else:
                        break
                self.consume("RBRACE")
                return MapLiteralNode(map_entries)
            entries = []
            if self.peek() and self.peek().kind != "RBRACE":
                entries.append(self.parse_dictionary_entry())
                while self.peek() and self.peek().kind == "COMMA":
                    self.consume("COMMA")
                    entries.append(self.parse_dictionary_entry())
            self.consume("RBRACE")
            return DictionaryLiteralNode(entries)
        elif current_token.kind == "CAST":
            tgt_ty = self.consume("CAST").text
            tgt_ty = TYPE_ALIASES.get(tgt_ty, tgt_ty)
            self.consume("LPAREN")
            expr = self.parse_expression()
            self.consume("RPAREN")
            return CastNode(tgt_ty, expr)
        elif current_token.kind == "LPAREN":
            self.consume("LPAREN")

            # Check if this parenthesized block is a WindowConfigNode (e.g. size = (260, 36))
            if (
                self.peek()
                and self.peek().kind == "IDENTIFIER"
                and self.position + 1 < len(self.tokens)
                and self.tokens[self.position + 1].kind == "OPERATOR"
                and self.tokens[self.position + 1].text == "="
            ):
                return self.parse_window_configuration("RPAREN")

            first_expr = self.parse_expression()

            # Handle tuples like (260, 36)
            if self.peek() and self.peek().kind == "COMMA":
                elems = [first_expr]
                while self.peek() and self.peek().kind == "COMMA":
                    self.consume("COMMA")
                    elems.append(self.parse_expression())
                self.consume("RPAREN")

                if len(elems) == 2:
                    return WindowSizeNode(elems[0], elems[1])
                return TupleNode(elems)

            # Single expression inside parentheses
            self.consume("RPAREN")
            return first_expr
        elif current_token.kind == "INT_LITERAL":
            return LiteralNode("int", self.parse_integer_text(self.consume().text))
        elif current_token.kind == "CHAR_LITERAL":
            inner = self.consume().text[1:-1]
            code = CHAR_ESCAPES[inner[1:]] if inner.startswith("\\") else ord(inner)
            if code > 255:
                raise self.error("A char holds one byte; this character does not fit", current_token,
                                 "use a str for characters outside the basic Latin range")
            return LiteralNode("char", code)
        elif current_token.kind == "FLOAT_LITERAL":
            return LiteralNode("float", float(self.consume().text))
        elif current_token.kind == "BOOL":
            return LiteralNode("bool", self.consume().text == "true")
        elif current_token.kind == "STRING_LITERAL":
            return LiteralNode("str", unescape_string(self.consume().text[1:-1]))
        elif current_token.kind == "IDENTIFIER":
            if self.position + 1 < len(self.tokens) and self.tokens[self.position + 1].kind == "LPAREN":
                name_token = self.consume("IDENTIFIER")
                self.consume("LPAREN")
                if name_token.text == "malloc" and "malloc" not in self.bindings and "malloc" not in self.declared_functions:
                    elem_ty = self.parse_type("an element type")
                    self.consume("COMMA")
                    cnt = self.parse_expression()
                    self.consume("RPAREN")
                    return MallocNode(elem_ty, cnt)
                args = self.parse_call_arguments()
                self.consume("RPAREN")
                return self.resolve_call(name_token, args)

            if self.position + 1 < len(self.tokens) and self.tokens[self.position + 1].kind == "DOT":
                receiver_token = self.consume("IDENTIFIER")
                library_name = receiver_token.text
                self.consume("DOT")
                method_token = self.expect_name("a name after '.'")
                meth_name = method_token.text
                if self.peek() and self.peek().kind == "LPAREN":
                    self.consume("LPAREN")
                    args = self.parse_call_arguments()
                    self.consume("RPAREN")
                    resolved = self.resolve_qualified_call(receiver_token, method_token, args)
                    if resolved is not None:
                        return resolved
                    return LibraryCallNode(library_name, meth_name, args)
                self.reject_member_access(receiver_token, method_token)
                return DictionaryAccessNode(VariableAccessNode(library_name), meth_name)

            return VariableAccessNode(self.consume("IDENTIFIER").text)
        else:
            raise self.error(
                f"Unexpected {self.describe_token(current_token)} in an expression",
                current_token,
                "an expression is a value: a number, string, true/false, a name, or a call",
            )

    def parse_dictionary_entry(self):
        key_token = self.consume()
        if key_token.kind == "IDENTIFIER":
            key = key_token.text
        elif key_token.kind == "STRING_LITERAL":
            key = key_token.text[1:-1]
        else:
            raise self.error("Dictionary keys must be names or strings")
        self.consume("COLON")
        val_ty = self.parse_type()
        self.consume("OPERATOR", "=")
        value = self.parse_expression()
        return key, val_ty, value

    def parse_window_configuration(self, closing_token):
        properties = {}
        while self.peek() and self.peek().kind != closing_token:
            property_name = self.consume("IDENTIFIER").text
            if property_name in properties:
                raise self.error(f"Duplicate configuration property '{property_name}'")
            self.consume("OPERATOR", "=")
            if property_name in ("size", "position"):
                self.consume("LPAREN")
                first = self.parse_expression()
                self.consume("COMMA")
                second = self.parse_expression()
                self.consume("RPAREN")
                properties[property_name] = (
                    WindowSizeNode(first, second)
                    if property_name == "size"
                    else WindowPointNode(first, second)
                )
            else:
                properties[property_name] = self.parse_expression()
            if self.peek() and self.peek().kind == "COMMA":
                self.consume("COMMA")
            elif self.peek() and self.peek().kind != closing_token:
                raise self.error("Configuration properties must be separated by commas")
        self.consume(closing_token)
        return WindowConfigNode(properties)
    def require_top_level(self, top_level, token):
        if not top_level:
            raise self.error(
                "Imports are only allowed at the top level of a file", token,
                "move this import above your functions, loops and classes",
                ImportError,
            )

    def check_name_not_imported(self, token, what):
        binding = self.bindings.get(token.text)
        if binding is not None:
            raise self.error(
                f"Cannot declare {what} '{token.text}': the name is already imported on line {binding.line}",
                token,
                f"rename the {what}, or import the other one under a different name with 'as'",
                NameError,
            )

    def bind_name(self, name, kind, target, token, extra=None):
        prev = self.bindings.get(name)
        if prev is not None:
            raise self.error(
                f"The name '{name}' is already used by the import on line {prev.line}",
                token,
                f"give one of them a different name, for example: ... as {name}2",
                ImportError,
            )
        declared = self.declared_functions.get(name)
        if declared is not None:
            raise self.error(
                f"The name '{name}' is already declared as a function on line {declared.line}",
                token,
                "rename the function, or import under a different name with 'as'",
                ImportError,
            )
        self.bindings[name] = Binding(kind, target, token.line, token.column, extra)

    def parse_link_clause(self):
        names = []
        if self.at_word("link"):
            self.consume("IDENTIFIER")
            names.append(self.expect_string("a quoted library after 'link'").text[1:-1])
            while self.peek() and self.peek().kind == "COMMA":
                self.consume("COMMA")
                names.append(self.expect_string("a quoted library after ','").text[1:-1])
        return names

    def parse_optional_alias(self):
        if self.at_word("as"):
            as_token = self.consume("IDENTIFIER")
            if self.peek() is None:
                raise self.error("Unexpected end of input: expected a name after 'as'", as_token)
            return self.expect_name("a name after 'as'")
        return None

    def file_stem_name(self, path_token):
        raw = path_token.text[1:-1]
        stem = os.path.splitext(os.path.basename(raw))[0]
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", stem):
            raise self.error(
                f"Cannot use the file name '{stem}' as an import name",
                path_token,
                f'choose a name yourself: import "{raw}" as my_name',
                ImportError,
            )
        return stem

    def parse_import_statement(self):
        import_token = self.consume("IMPORT")
        token = self.peek()
        if token is None:
            raise self.error("Unexpected end of input: expected a library name or a quoted file path after 'import'",
                             import_token)
        name_token = path_token = None
        if token.kind == "STRING_LITERAL":
            path_token = self.consume()
        elif token.kind == "IDENTIFIER":
            name_token = self.consume()
            if self.peek() and self.peek().kind == "COLON":
                self.consume("COLON")
                path_token = self.expect_string("a quoted file path after ':'")
        else:
            raise self.error(
                f"Expected a library name or a quoted file path after 'import', got {self.describe_token(token)}",
                token,
            )

        if path_token is None:
            library = name_token.text
            if library not in BUILTIN_LIBRARIES:
                close = suggest(library, BUILTIN_LIBRARIES)
                hint = f"did you mean '{close}'?" if close else (
                    f'to import a file, write: import {library} : "{library}.vp"')
                raise self.error(
                    f"Unknown library '{library}' (built-in libraries: {describe_choices(BUILTIN_LIBRARIES)})",
                    name_token, hint, ImportError,
                )
            alias_token = self.parse_optional_alias()
            bound = alias_token.text if alias_token else library
            self.bind_name(bound, "library", library, alias_token or name_token)
            return LibraryImportNode(library, alias_token.text if alias_token else None)

        links = self.parse_link_clause()
        alias_token = self.parse_optional_alias()
        module, is_new = self.load_module(path_token, links)
        if alias_token is not None:
            bound_token = alias_token
        elif name_token is not None:
            bound_token = name_token
        else:
            bound_token = path_token
        bound = bound_token.text if bound_token is not path_token else self.file_stem_name(path_token)
        self.bind_name(bound, "module", module, bound_token)
        return self.module_statement(module, is_new)

    def module_statement(self, module, is_new):
        if isinstance(module, native.NativeModule):
            return NativeImportNode(module) if is_new else ModuleImportNode(module.module_id, module.path, [])
        return ModuleImportNode(module.module_id, module.path, module.statements if is_new else [])

    def parse_from_import_statement(self):
        from_token = self.consume("IDENTIFIER", "from")
        source_token = self.peek()
        name_token = path_token = None
        if source_token.kind == "STRING_LITERAL":
            path_token = self.consume()
        else:
            name_token = self.consume("IDENTIFIER")
            if self.peek() and self.peek().kind == "COLON":
                self.consume("COLON")
                path_token = self.expect_string("a quoted file path after ':'")
        links = self.parse_link_clause() if path_token is not None else []

        if not (self.peek() and self.peek().kind == "IMPORT"):
            raise self.error(
                f"Expected 'import' after the module name in a 'from' statement, got {self.describe_token(self.peek())}",
                self.peek() or from_token,
                "the form is: from <library or file> import <name>, <name> as <alias>",
            )
        self.consume("IMPORT")

        requested = self.parse_import_names()

        if path_token is None:
            library = name_token.text
            if library not in BUILTIN_LIBRARIES:
                close = suggest(library, BUILTIN_LIBRARIES)
                hint = f"did you mean '{close}'?" if close else (
                    f'to import from a file, write: from {library} : "{library}.vp" import ...')
                raise self.error(
                    f"Unknown library '{library}' (built-in libraries: {describe_choices(BUILTIN_LIBRARIES)})",
                    name_token, hint, ImportError,
                )
            members = BUILTIN_LIBRARIES[library]
            names = []
            for item_token, alias_token in requested:
                if item_token.text == "*":
                    for member in sorted(members):
                        self.bind_name(member, "library_member", (library, member), item_token)
                        names.append(member)
                    continue
                if item_token.text not in members:
                    close = suggest(item_token.text, members)
                    raise self.error(
                        f"Library '{library}' has no method named '{item_token.text}'",
                        item_token,
                        f"did you mean '{close}'?" if close else f"available methods: {describe_choices(members)}",
                        ImportError,
                    )
                bound = alias_token or item_token
                self.bind_name(bound.text, "library_member", (library, item_token.text), bound)
                names.append(item_token.text)
            return LibraryImportNode(library, None, names)

        module, is_new = self.load_module(path_token, links)
        for item_token, alias_token in requested:
            self.bind_from_module(module, item_token, alias_token)
        return self.module_statement(module, is_new)

    def parse_import_names(self):
        requested = []
        first = self.peek()
        if first is None:
            raise self.error("Unexpected end of input: expected a name to import after 'import'")
        if first.kind == "OPERATOR" and first.text == "*":
            requested.append((self.consume(), None))
            return requested
        while True:
            item_token = self.expect_name("the name of something to import")
            requested.append((item_token, self.parse_optional_alias()))
            if self.peek() and self.peek().kind == "COMMA":
                self.consume("COMMA")
                continue
            break
        return requested

    def bind_from_module(self, module, item_token, alias_token):
        name = item_token.text
        if isinstance(module, native.NativeModule):
            if name == "*":
                for function_name in sorted(module.functions):
                    if not function_name.startswith("_"):
                        self.bind_name(function_name, "native_member", module, item_token, function_name)
                return
            self.require_native_name(module, item_token)
            bound = alias_token or item_token
            self.bind_name(bound.text, "native_member", module, bound, name)
            return
        if name == "*":
            for function_name, symbol in sorted(module.functions.items()):
                if not function_name.startswith("_"):
                    self.bind_name(function_name, "function", symbol, item_token)
            for cls_name in sorted(module.classes):
                if not cls_name.startswith("_"):
                    self.bind_name(cls_name, "class", cls_name, item_token)
            return
        if name in module.functions:
            bound = alias_token or item_token
            self.bind_name(bound.text, "function", module.functions[name], bound)
        elif name in module.classes:
            if alias_token is not None and alias_token.text != name:
                raise self.error(
                    f"Class '{name}' cannot be imported under another name",
                    alias_token,
                    f"classes keep one global name; use 'from ... import {name}' or call it as module.{name}(...)",
                    ImportError,
                )
            self.bind_name(name, "class", name, item_token)
        else:
            self.raise_missing_export(module, item_token)

    def exported_names(self, module):
        if isinstance(module, native.NativeModule):
            return set(module.functions)
        return set(module.functions) | set(module.classes)

    def raise_missing_export(self, module, token):
        names = self.exported_names(module)
        close = suggest(token.text, names)
        where = os.path.basename(module.path)
        available = describe_choices(names) if names else "nothing (the file has no functions or classes)"
        raise self.error(
            f"'{where}' has no function or class named '{token.text}'",
            token,
            f"did you mean '{close}'?" if close else f"available names: {available}",
            ImportError,
        )

    def require_native_name(self, module, token):
        if token.text in module.functions:
            return
        kind = module.other_names.get(token.text)
        where = os.path.basename(module.path)
        if kind:
            hints = {
                "class": "C++ classes cannot be imported yet; wrap them in free functions that take and return ints, floats, bools or strings",
                "struct": "C/C++ structs cannot be imported yet; wrap them in free functions",
                "template": "templates cannot be imported directly; add a normal function that instantiates it, for example `int max_int(int a, int b) { return max<int>(a, b); }`",
                "class template": "class templates cannot be imported; add a normal function that uses a concrete instantiation",
                "variable": "global variables cannot be imported yet; add a getter function",
                "enum": "enums cannot be imported yet; use int constants through functions",
            }
            raise self.error(f"'{token.text}' in '{where}' is a {kind}, not a function", token, hints.get(kind), ImportError)
        names = set(module.functions)
        close = suggest(token.text, names)
        raise self.error(
            f"'{where}' declares no function named '{token.text}'",
            token,
            f"did you mean '{close}'?" if close else (
                f"available functions: {describe_choices(names)}" if names else "no importable functions were found"),
            ImportError,
        )

    # .vp, .vpdata and C/C++ imports all come through here. modules are cached per real path
    def load_module(self, path_token, link_names):
        raw = path_token.text[1:-1]
        if not raw.strip():
            raise self.error("The import path is empty", path_token, kind=ImportError)
        extension = os.path.splitext(raw)[1].lower()
        allowed = SOURCE_EXTENSIONS + NATIVE_EXTENSIONS
        directory_candidate = raw if os.path.isabs(raw) else os.path.join(self.base_dir, raw)
        if os.path.isdir(directory_candidate):
            raise self.error(f"Cannot import '{raw}': it is a directory, not a file", path_token, kind=ImportError)
        if extension not in allowed:
            shown = extension or "(no extension)"
            raise self.error(
                f"Cannot import '{raw}': unsupported file type {shown}",
                path_token,
                "use .vp for Vamp files, or " + " ".join(NATIVE_EXTENSIONS) + " for C/C++ files",
                ImportError,
            )
        full = raw if os.path.isabs(raw) else os.path.join(self.base_dir, raw)
        full = os.path.normpath(full)
        if os.path.isdir(full):
            raise self.error(f"Cannot import '{raw}': it is a directory, not a file", path_token, kind=ImportError)
        if not os.path.isfile(full):
            raise self.error(
                f"Cannot find the file '{raw}' to import",
                path_token,
                f"looked for: {full} (paths are relative to the importing file)",
                ImportError,
            )
        real = os.path.realpath(full)
        session = self.session

        if extension in SOURCE_EXTENSIONS:
            if real in session.stack:
                chain = " -> ".join(os.path.basename(item) for item in session.stack + [real])
                raise self.error(f"Circular import: {chain}", path_token,
                                 "move the shared code into a third file that both can import", ImportError)
            cached = session.modules.get(real)
            if cached is not None:
                return cached, False
            module = self.parse_vamp_module(real, full, path_token)
            session.modules[real] = module
            return module, True

        cached = session.modules.get(real)
        if cached is not None:
            return cached, False
        module_id = self.unique_module_id(real)

        def report(kind, message, hint=None):
            return self.error(message, path_token, hint, kind)

        resolved_links = [name for name in link_names]
        module = native.load_native_module(module_id, real, resolved_links, report, self.base_dir)
        session.modules[real] = module
        return module, True

    def unique_module_id(self, real_path):
        stem = re.sub(r"[^A-Za-z0-9_]", "_", os.path.splitext(os.path.basename(real_path))[0]) or "module"
        candidate, counter = stem, 2
        while candidate in self.session.module_ids:
            candidate = f"{stem}_{counter}"
            counter += 1
        self.session.module_ids.add(candidate)
        return candidate

    def parse_vamp_module(self, real, display_path, path_token):
        try:
            with open(real, "rb") as fh:
                src = fh.read().decode("utf-8")
        except UnicodeDecodeError:
            raise self.error(f"Cannot import '{os.path.basename(real)}': the file is not valid UTF-8",
                             path_token, kind=ImportError)
        except OSError as err:
            raise self.error(f"Cannot read '{display_path}': {err.strerror}", path_token, kind=ImportError)

        module_id = self.unique_module_id(real)
        module = ModuleInfo(module_id, real)
        sub_parser = Parser(tokenize(src, real), filename=real, session=self.session)
        self.session.stack.append(real)
        try:
            try:
                own_statements = sub_parser.parse_program(flatten=False)
                self.validate_module_statements(sub_parser, own_statements, real)
            except (SyntaxError, NameError, TypeError, ValueError, ImportError) as err:
                note = f"\n  note: while importing '{os.path.basename(real)}' from {self.filename or '<source>'}:{path_token.line}:{path_token.column}"
                chained = type(err)(str(err) + note)
                chained.vamp_located = True
                raise chained from None
        finally:
            self.session.stack.pop()

        own = [node for node in own_statements if not isinstance(node, (ModuleImportNode, NativeImportNode))]
        rename = {}
        for node in own:
            if isinstance(node, FunctionDeclarationNode):
                rename[node.function_name] = f"{module_id}.{node.function_name}"
            elif isinstance(node, ClassDeclarationNode):
                module.classes.add(node.class_name)
        module.functions = {name: symbol for name, symbol in rename.items()}
        rename_calls(own, rename)

        flattened = []
        for node in own_statements:
            if isinstance(node, ModuleImportNode):
                flattened.extend(node.statements)
            else:
                flattened.append(node)
        module.statements = flattened
        return module

    def validate_module_statements(self, sub_parser, statements, path):
        allowed = (FunctionDeclarationNode, ClassDeclarationNode, EnumDeclarationNode, LibraryImportNode,
                   ModuleImportNode, NativeImportNode)
        for node in statements:
            if isinstance(node, allowed):
                continue
            description = STATEMENT_DESCRIPTIONS.get(type(node).__name__, type(node).__name__)
            raise sub_parser.error_at_node(
                node,
                f"{description[0].upper() + description[1:]} is not allowed at the top level of an imported file",
                "imported files can only contain functions, classes, structs, enums and imports; "
                "put this inside a function, or in the file that imports this one",
                ImportError,
            )

    def resolve_call(self, name_token, arguments):
        name = name_token.text
        binding = self.bindings.get(name)
        if binding is None:
            return FunctionCallNode(name, arguments)
        if binding.kind == "function":
            return FunctionCallNode(binding.target, arguments)
        if binding.kind == "class":
            return FunctionCallNode(binding.target, arguments)
        if binding.kind == "library_member":
            library, meth = binding.target
            call = LibraryCallNode(library, meth, arguments)
            call.resolved = True
            return call
        if binding.kind == "native_member":
            return NativeCallNode(binding.target, binding.extra, arguments)
        what = "a library" if binding.kind == "library" else "an imported file"
        raise self.error(
            f"'{name}' is {what}, not a function",
            name_token,
            f"call something inside it, for example {name}.Name(...)",
            TypeError,
        )

    def resolve_qualified_call(self, receiver_token, member_token, arguments):
        receiver = receiver_token.text
        member = member_token.text
        binding = self.bindings.get(receiver)
        if binding is None:
            if receiver in BUILTIN_LIBRARIES:
                for other_name, other in self.bindings.items():
                    if other.kind == "library" and other.target == receiver:
                        raise self.error(
                            f"Library '{receiver}' was imported as '{other_name}' (line {other.line}), "
                            f"so '{receiver}' is not a name here",
                            receiver_token, f"write {other_name}.{member}(...)", NameError,
                        )
            return None
        if binding.kind == "library":
            members = BUILTIN_LIBRARIES[binding.target]
            if member not in members:
                close = suggest(member, members)
                raise self.error(
                    f"Library '{binding.target}' has no method named '{member}'",
                    member_token,
                    f"did you mean '{close}'?" if close else f"available methods: {describe_choices(members)}",
                    NameError,
                )
            call = LibraryCallNode(binding.target, member, arguments)
            call.resolved = True
            return call
        if binding.kind == "module":
            module = binding.target
            if isinstance(module, native.NativeModule):
                self.require_native_name(module, member_token)
                return NativeCallNode(module, member, arguments)
            if member in module.functions:
                return FunctionCallNode(module.functions[member], arguments)
            if member in module.classes:
                return FunctionCallNode(member, arguments)
            self.raise_missing_export(module, member_token)
        raise self.error(
            f"'{receiver}' is an imported name, not a module or library",
            receiver_token, f"'{receiver}.{member}' only works on names bound with 'import'", TypeError,
        )

    def reject_member_access(self, receiver_token, member_token):
        binding = self.bindings.get(receiver_token.text)
        if binding is not None and binding.kind in ("library", "module"):
            what = "a library" if binding.kind == "library" else "an imported file"
            raise self.error(
                f"'{receiver_token.text}.{member_token.text}' is not a call: {what} only exposes functions",
                member_token,
                f"add parentheses: {receiver_token.text}.{member_token.text}(...)",
                TypeError,
            )


def rename_calls(value, rename):
    if isinstance(value, FunctionDeclarationNode) and value.function_name in rename:
        value.function_name = rename[value.function_name]
    elif isinstance(value, FunctionCallNode) and value.function_name in rename:
        value.function_name = rename[value.function_name]
    elif (
        isinstance(value, LibraryCallNode)
        and value.library_name == "thread"
        and value.method_name == "Start"
        and value.arguments
        and isinstance(value.arguments[0], VariableAccessNode)
        and value.arguments[0].variable_name in rename
    ):
        value.arguments[0].variable_name = rename[value.arguments[0].variable_name]
    if isinstance(value, ASTNode):
        for child in list(vars(value).values()):
            rename_calls(child, rename)
    elif isinstance(value, (list, tuple)):
        for child in value:
            rename_calls(child, rename)
    elif isinstance(value, dict):
        for child in value.values():
            rename_calls(child, rename)
