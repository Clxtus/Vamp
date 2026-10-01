class ASTNode:
    pass

class ImportFileNode(ASTNode):
    def __init__(self, alias, filepath):
        self.alias = alias
        self.filepath = filepath

class ImportLibNode(ASTNode):
    def __init__(self, lib_name):
        self.lib_name = lib_name

class LibCallNode(ASTNode):
    def __init__(self, lib_name, method, args):
        self.lib_name = lib_name
        self.method = method
        self.args = args

class VariableDeclNode(ASTNode):
    def __init__(self, is_const, name, var_type, value_node):
        self.is_const = is_const
        self.name = name
        self.var_type = var_type
        self.value_node = value_node

class PrintNode(ASTNode):
    def __init__(self, expr_node, newline=True):
        self.expr_node = expr_node
        self.newline = newline

class ExitNode(ASTNode):
    def __init__(self, code_node):
        self.code_node = code_node

class FreeNode(ASTNode):
    def __init__(self, ptr_node):
        self.ptr_node = ptr_node

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

class CastNode(ASTNode):
    def __init__(self, target_type, expr_node):
        self.target_type = target_type
        self.expr_node = expr_node

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
        
        # import handling
        if token.type == "IMPORT":
            self.consume("IMPORT")
            first_ident = self.consume("IDENTIFIER").value
            if self.peek() and self.peek().type == "COLON":
                self.consume("COLON")
                filepath = self.consume("STRING_LITERAL").value[1:-1]
                return ImportFileNode(first_ident, filepath)
            else:
                return ImportLibNode(first_ident)

        elif token.type == "KEYWORD" and token.value in ("val", "const"):
            return self.parse_var_decl()

        elif token.type == "IDENTIFIER":
            # Check for library call: os.Make_Directory(...)
            if self.pos + 1 < len(self.tokens) and self.tokens[self.pos + 1].type == "DOT":
                lib_name = self.consume("IDENTIFIER").value
                self.consume("DOT")
                meth = self.consume("IDENTIFIER").value
                self.consume("LPAREN")
                args = []
                if self.peek() and self.peek().type != "RPAREN":
                    args.append(self.parse_expression())
                self.consume("RPAREN")
                return LibCallNode(lib_name, meth, args)

            # Built-in statement calls
            if token.value in ("println", "print"):
                is_println = token.value == "println"
                self.consume("IDENTIFIER")
                self.consume("LPAREN")
                expr = self.parse_expression()
                self.consume("RPAREN")
                return PrintNode(expr, newline=is_println)
            elif token.value == "exit":
                self.consume("IDENTIFIER")
                self.consume("LPAREN")
                code = self.parse_expression()
                self.consume("RPAREN")
                return ExitNode(code)
            elif token.value == "free":
                self.consume("IDENTIFIER")
                self.consume("LPAREN")
                ptr = self.parse_expression()
                self.consume("RPAREN")
                return FreeNode(ptr)

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
        if token.type == "CAST":
            tgt_ty = self.consume("CAST").value
            self.consume("LPAREN")
            expr = self.parse_expression()
            self.consume("RPAREN")
            return CastNode(tgt_ty, expr)
        elif token.type == "LPAREN":
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
            return LiteralNode("str", self.consume().value[1:-1])
        elif token.type == "IDENTIFIER":
            # Check for library call in expression context (e.g., Directory.exists("path"))
            if self.pos + 1 < len(self.tokens) and self.tokens[self.pos + 1].type == "DOT":
                lib_name = self.consume("IDENTIFIER").value
                self.consume("DOT")
                meth = self.consume("IDENTIFIER").value
                self.consume("LPAREN")
                args = []
                if self.peek() and self.peek().type != "RPAREN":
                    args.append(self.parse_expression())
                self.consume("RPAREN")
                return LibCallNode(lib_name, meth, args)
            return VarAccessNode(self.consume().value)
        else:
            raise SyntaxError(f"Unexpected token in expression: {token}")