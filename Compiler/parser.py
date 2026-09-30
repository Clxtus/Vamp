# Compiler/parser.py

class ASTNode:
    pass

class VariableDeclNode(ASTNode):
    def __init__(self, is_const, name, var_type, value_node):
        self.is_const = is_const
        self.name = name
        self.var_type = var_type
        self.value_node = value_node

class PrintlnNode(ASTNode):
    def __init__(self, expr_node):
        self.expr_node = expr_node

class LiteralNode(ASTNode):
    def __init__(self, type_, value):
        self.type = type_
        self.value = value

class VarAccessNode(ASTNode):
    def __init__(self, name):
        self.name = name

class BinaryOpNode(ASTNode):
    def __init__(self, left, op, right):
        self.left = left
        self.op = op
        self.right = right

class Parser:
    def __init__(self, tokens):
        self.tokens = tokens
        self.pos = 0

    def peek(self):
        return self.tokens[self.pos] if self.pos < len(self.tokens) else None

    def consume(self, expected_type=None, expected_value=None):
        token = self.peek()
        if not token:
            raise SyntaxError("Unexpected end of input")
        if expected_type and token.type != expected_type:
            raise SyntaxError(f"Expected {expected_type}, got {token.type}")
        if expected_value and token.value != expected_value:
            raise SyntaxError(f"Expected '{expected_value}', got '{token.value}'")
        self.pos += 1
        return token

    def parse_program(self):
        stmts = []
        while self.peek():
            stmts.append(self.parse_statement())
        return stmts

    def parse_statement(self):
        token = self.peek()
        if token.type == "KEYWORD" and token.value in ("val", "const"):
            return self.parse_var_decl()
        elif token.type == "IDENTIFIER" and token.value in ("println", "print"):
            self.consume("IDENTIFIER")
            self.consume("LPAREN")
            expr = self.parse_expression()
            self.consume("RPAREN")
            return PrintlnNode(expr)
        else:
            raise SyntaxError(f"Unsupported statement: {token}")

    def parse_var_decl(self):
        kw = self.consume("KEYWORD").value
        is_const = kw == "const"
        name = self.consume("IDENTIFIER").value
        self.consume("COLON")
        var_type = self.consume("TYPE").value
        self.consume("OPERATOR", "=")
        value_node = self.parse_expression()
        return VariableDeclNode(is_const, name, var_type, value_node)

    # Expression Parser with Precedence
    def parse_expression(self):
        return self.parse_additive()

    def parse_additive(self):
        left = self.parse_multiplicative()
        while self.peek() and self.peek().type == "OPERATOR" and self.peek().value in ("+", "-"):
            op = self.consume("OPERATOR").value
            right = self.parse_multiplicative()
            left = BinaryOpNode(left, op, right)
        return left

    def parse_multiplicative(self):
        left = self.parse_primary()
        while self.peek() and self.peek().type == "OPERATOR" and self.peek().value in ("*", "/"):
            op = self.consume("OPERATOR").value
            right = self.parse_primary()
            left = BinaryOpNode(left, op, right)
        return left

    def parse_primary(self):
        token = self.peek()
        if token.type == "LPAREN":
            self.consume("LPAREN")
            expr = self.parse_expression()
            self.consume("RPAREN")
            return expr
        elif token.type == "INT_LITERAL":
            return LiteralNode("int", int(self.consume().value))
        elif token.type == "FLOAT_LITERAL":
            return LiteralNode("float", float(self.consume().value))
        elif token.type == "BOOL":
            return LiteralNode("bool", self.consume().value == "true")
        elif token.type == "STRING_LITERAL":
            return LiteralNode("string", self.consume().value[1:-1])
        elif token.type == "IDENTIFIER":
            return VarAccessNode(self.consume().value)
        else:
            raise SyntaxError(f"Unexpected token in expression: {token}")