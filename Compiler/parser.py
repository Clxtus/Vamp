class ASTNode:
    pass

class FunctionDeclarationNode(ASTNode):
    def __init__(self, function_name, parameters, return_type, body):
        self.function_name = function_name
        self.parameters = parameters
        self.return_type = return_type
        self.body = body

class ReturnNode(ASTNode):
    def __init__(self, expression, return_type=None):
        self.expression = expression
        self.return_type = return_type

class FunctionCallNode(ASTNode):
    def __init__(self, function_name, arguments):
        self.function_name = function_name
        self.arguments = arguments

class ImportFileNode(ASTNode):
    def __init__(self, alias, filepath):
        self.alias = alias
        self.filepath = filepath

class LibraryImportNode(ASTNode):
    def __init__(self, library_name):
        self.library_name = library_name

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

class CastNode(ASTNode):
    def __init__(self, target_type, expression):
        self.target_type = target_type
        self.expression = expression

class Parser:
    def __init__(self, tokens):
        self.tokens = tokens
        self.position = 0

    def peek(self):
        return self.tokens[self.position] if self.position < len(self.tokens) else None

    def consume(self, expected_kind=None, expected_text=None):
        token = self.peek()
        if not token:
            raise SyntaxError("Unexpected end of input")
        if expected_kind and token.kind != expected_kind:
            raise SyntaxError(f"Expected {expected_kind}, got {token.kind}")
        if expected_text and token.text != expected_text:
            raise SyntaxError(f"Expected '{expected_text}', got '{token.text}'")
        self.position += 1
        return token

    def parse_program(self):
        stmts = []
        while self.peek():
            stmts.append(self.parse_statement())
        return stmts

    def parse_statement(self):
        current_token = self.peek()
        
        if current_token.kind == "IMPORT":
            self.consume("IMPORT")
            imported_name = self.consume("IDENTIFIER").text
            if self.peek() and self.peek().kind == "COLON":
                self.consume("COLON")
                file_path = self.consume("STRING_LITERAL").text[1:-1]
                return ImportFileNode(imported_name, file_path)
            else:
                return LibraryImportNode(imported_name)

        elif current_token.kind == "KEYWORD" and current_token.text in ("val", "const"):
            return self.parse_variable_declaration()

        elif current_token.kind == "IDENTIFIER" and current_token.text == "func":
            return self.parse_function_declaration()

        elif current_token.kind == "IDENTIFIER" and current_token.text == "return":
            self.consume("IDENTIFIER")
            ret_ty = None
            if self.peek() and self.peek().kind == "COLON":
                self.consume("COLON")
                annotation_token = self.peek()
                if not annotation_token or annotation_token.kind not in ("TYPE", "CAST"):
                    raise SyntaxError("Expected a return type after ':'")
                ret_ty = self.consume().text
                self.consume("LPAREN")
                expr = self.parse_expression()
                self.consume("RPAREN")
            else:
                expr = self.parse_expression()
            return ReturnNode(expr, ret_ty)

        elif current_token.kind == "IDENTIFIER":
            if self.position + 1 < len(self.tokens) and self.tokens[self.position + 1].kind == "DOT":
                library_name = self.consume("IDENTIFIER").text
                self.consume("DOT")
                meth_name = self.consume("IDENTIFIER").text
                self.consume("LPAREN")
                args = []
                if self.peek() and self.peek().kind != "RPAREN":
                    args.append(self.parse_expression())
                    while self.peek() and self.peek().kind == "COMMA":
                        self.consume("COMMA")
                        args.append(self.parse_expression())
                self.consume("RPAREN")
                return LibraryCallNode(library_name, meth_name, args)

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

        raise SyntaxError(f"Unsupported statement: {current_token}")

    def parse_function_declaration(self):
        self.consume("IDENTIFIER", "func")
        function_name = self.consume("IDENTIFIER").text
        self.consume("LPAREN")
        params = []
        if self.peek() and self.peek().kind != "RPAREN":
            parameter_name = self.consume("IDENTIFIER").text
            self.consume("COLON")
            parameter_type = self.consume("TYPE").text
            params.append((parameter_name, parameter_type))
            while self.peek() and self.peek().kind == "COMMA":
                self.consume("COMMA")
                parameter_name = self.consume("IDENTIFIER").text
                self.consume("COLON")
                parameter_type = self.consume("TYPE").text
                params.append((parameter_name, parameter_type))
        self.consume("RPAREN")
        
        function_return_type = None
        if self.peek() and self.peek().kind == "COLON":
            self.consume("COLON")
            if self.peek() and self.peek().kind == "TYPE":
                function_return_type = self.consume("TYPE").text
                self.consume("COLON")

        self.consume("LPAREN")
        body = []
        while self.peek() and self.peek().kind != "RPAREN":
            body.append(self.parse_statement())
        self.consume("RPAREN")

        annotated_return_types = {
            stmt.return_type
            for stmt in body
            if isinstance(stmt, ReturnNode) and stmt.return_type is not None
        }
        if len(annotated_return_types) > 1:
            raise SyntaxError("Return type annotations in a function must match")
        if annotated_return_types:
            annotated_type = next(iter(annotated_return_types))
            if function_return_type is not None and function_return_type != annotated_type:
                raise SyntaxError("Function and return statement types must match")
            function_return_type = annotated_type
        if function_return_type is None:
            function_return_type = "int"

        return FunctionDeclarationNode(function_name, params, function_return_type, body)

    def parse_variable_declaration(self):
        declaration_keyword = self.consume("KEYWORD").text
        is_constant = declaration_keyword == "const"
        var_name = self.consume("IDENTIFIER").text
        self.consume("COLON")
        variable_type = self.consume("TYPE").text
        self.consume("OPERATOR", "=")
        initializer = self.parse_expression()
        return VariableDeclarationNode(is_constant, var_name, variable_type, initializer)

    def parse_expression(self):
        return self.parse_additive_expression()

    def parse_additive_expression(self):
        left = self.parse_multiplicative_expression()
        while self.peek() and self.peek().kind == "OPERATOR" and self.peek().text in ("+", "-"):
            operator = self.consume("OPERATOR").text
            right = self.parse_multiplicative_expression()
            left = BinaryOpNode(left, operator, right)
        return left

    def parse_multiplicative_expression(self):
        left = self.parse_primary_expression()
        while self.peek() and self.peek().kind == "OPERATOR" and self.peek().text in ("*", "/"):
            operator = self.consume("OPERATOR").text
            right = self.parse_primary_expression()
            left = BinaryOpNode(left, operator, right)
        return left

    def parse_primary_expression(self):
        current_token = self.peek()
        if current_token.kind == "CAST":
            tgt_ty = self.consume("CAST").text
            self.consume("LPAREN")
            expr = self.parse_expression()
            self.consume("RPAREN")
            return CastNode(tgt_ty, expr)
        elif current_token.kind == "LPAREN":
            self.consume("LPAREN")
            expr = self.parse_expression()
            self.consume("RPAREN")
            return expr
        elif current_token.kind == "INT_LITERAL":
            return LiteralNode("int", int(self.consume().text))
        elif current_token.kind == "FLOAT_LITERAL":
            return LiteralNode("float", float(self.consume().text))
        elif current_token.kind == "BOOL":
            return LiteralNode("bool", self.consume().text == "true")
        elif current_token.kind == "STRING_LITERAL":
            return LiteralNode("str", self.consume().text[1:-1])
        elif current_token.kind == "IDENTIFIER":
            if self.position + 1 < len(self.tokens) and self.tokens[self.position + 1].kind == "LPAREN":
                function_name = self.consume("IDENTIFIER").text
                self.consume("LPAREN")
                args = []
                if self.peek() and self.peek().kind != "RPAREN":
                    args.append(self.parse_expression())
                    while self.peek() and self.peek().kind == "COMMA":
                        self.consume("COMMA")
                        args.append(self.parse_expression())
                self.consume("RPAREN")
                return FunctionCallNode(function_name, args)

            if self.position + 1 < len(self.tokens) and self.tokens[self.position + 1].kind == "DOT":
                library_name = self.consume("IDENTIFIER").text
                self.consume("DOT")
                meth_name = self.consume("IDENTIFIER").text
                self.consume("LPAREN")
                args = []
                if self.peek() and self.peek().kind != "RPAREN":
                    args.append(self.parse_expression())
                    while self.peek() and self.peek().kind == "COMMA":
                        self.consume("COMMA")
                        args.append(self.parse_expression())
                self.consume("RPAREN")
                return LibraryCallNode(library_name, meth_name, args)

            return VariableAccessNode(self.consume().text)
        else:
            raise SyntaxError(f"Unexpected token in expression: {current_token}")