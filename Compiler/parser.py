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
    def __init__(self, class_name, fields, nested_classes=None, methods=None):
        self.class_name = class_name
        self.fields = fields
        self.nested_classes = nested_classes or []
        self.methods = methods or []

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
                annotation_token = self.peek()
                if (
                    not annotation_token
                    or annotation_token.kind not in ("TYPE", "CAST", "IDENTIFIER")
                    or (annotation_token.kind == "IDENTIFIER" and annotation_token.text != "void")
                ):
                    raise SyntaxError("Expected a return type after ':'")
                ret_ty = self.consume().text
                if ret_ty == "void":
                    expr = None
                else:
                    self.consume("LPAREN")
                    expr = self.parse_expression()
                    self.consume("RPAREN")
            else:
                expr = self.parse_expression()
            return ReturnNode(expr, ret_ty)

        elif current_token.kind == "IDENTIFIER":
            if (
                self.position + 1 < len(self.tokens)
                and self.tokens[self.position + 1].kind == "LBRACKET"
            ):
                array = VariableAccessNode(self.consume("IDENTIFIER").text)
                self.consume("LBRACKET")
                idx = self.parse_expression()
                self.consume("RBRACKET")
                if (
                    self.peek()
                    and self.peek().kind == "OPERATOR"
                    and self.peek().text in ("=", "+=", "-=", "*=", "/=")
                ):
                    operator = self.consume("OPERATOR").text
                    expr = self.parse_expression()
                    return ArrayAssignmentNode(array, idx, operator, expr)
                raise SyntaxError("Indexed values can only be used in assignments as statements")

            if (
                self.position + 1 < len(self.tokens)
                and self.tokens[self.position + 1].kind == "OPERATOR"
                and self.tokens[self.position + 1].text in ("=", "+=", "-=", "*=", "/=")
            ):
                return self.parse_assignment_or_class_instance()

            if self.position + 1 < len(self.tokens) and self.tokens[self.position + 1].kind == "DOT":
                receiver_name = self.consume("IDENTIFIER").text
                self.consume("DOT")
                meth_name = self.consume("IDENTIFIER").text
                self.consume("LPAREN")
                args = self.parse_call_arguments()
                self.consume("RPAREN")
                if receiver_name in ("os", "Directory"):
                    return LibraryCallNode(receiver_name, meth_name, args)
                return MethodCallNode(VariableAccessNode(receiver_name), meth_name, args)

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

    def parse_class_declaration(self):
        self.consume("KEYWORD", "class")
        cls_name = self.consume("IDENTIFIER").text
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
                meths.append(self.parse_function_declaration())
                continue

            declaration_keyword = self.consume("KEYWORD").text
            if declaration_keyword not in ("val", "const"):
                raise SyntaxError("Class members must be fields, nested classes, or func methods")
            field_name = self.consume("IDENTIFIER").text
            self.consume("COLON")
            field_ty = self.consume("TYPE").text
            fields.append((field_name, field_ty, declaration_keyword == "const"))

        self.consume("RPAREN")
        if not fields and not nested_classes and not meths:
            raise SyntaxError(f"Class '{cls_name}' must declare a field, nested class, or method")
        return ClassDeclarationNode(cls_name, fields, nested_classes, meths)

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
            function_return_type = "int" if any(
                isinstance(stmt, ReturnNode) for stmt in body
            ) else "void"

        return FunctionDeclarationNode(function_name, params, function_return_type, body)

    def parse_variable_declaration(self):
        declaration_keyword = self.consume("KEYWORD").text
        is_constant = declaration_keyword == "const"
        variable_names = [self.consume("IDENTIFIER").text]
        while self.peek() and self.peek().kind == "COMMA":
            self.consume("COMMA")
            variable_names.append(self.consume("IDENTIFIER").text)

        variable_type = None
        if self.peek() and self.peek().kind == "COLON":
            self.consume("COLON")
            variable_type = self.consume("TYPE").text
        elif is_constant:
            raise SyntaxError("const declarations require an explicit type")
        elif len(variable_names) > 1:
            raise SyntaxError("Grouped declarations require an explicit type")

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
                raise SyntaxError("const declarations require an initializer")

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

    def parse_expression(self):
        left = self.parse_additive_expression()
        if self.peek() and self.peek().kind == "COMPARISON_OPERATOR":
            operator = self.consume("COMPARISON_OPERATOR").text
            right = self.parse_additive_expression()
            return ComparisonNode(left, operator, right)
        return left

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
                args = self.parse_call_arguments()  # Use the new function
                self.consume("RPAREN")
                return FunctionCallNode(function_name, args)

            if self.position + 1 < len(self.tokens) and self.tokens[self.position + 1].kind == "DOT":
                library_name = self.consume("IDENTIFIER").text
                self.consume("DOT")
                meth_name = self.consume("IDENTIFIER").text
                if self.peek() and self.peek().kind == "LPAREN":
                    self.consume("LPAREN")
                    args = self.parse_call_arguments()  # Use the new function
                    self.consume("RPAREN")
                    return LibraryCallNode(library_name, meth_name, args)
                return DictionaryAccessNode(VariableAccessNode(library_name), meth_name)

            array = VariableAccessNode(self.consume("IDENTIFIER").text)
            if self.peek() and self.peek().kind == "LBRACKET":
                self.consume("LBRACKET")
                idx = self.parse_expression()
                self.consume("RBRACKET")
                return ArrayAccessNode(array, idx)
            return array
        else:
            raise SyntaxError(f"Unexpected token in expression: {current_token}")

    def parse_dictionary_entry(self):
        key_token = self.consume()
        if key_token.kind == "IDENTIFIER":
            key = key_token.text
        elif key_token.kind == "STRING_LITERAL":
            key = key_token.text[1:-1]
        else:
            raise SyntaxError("Dictionary keys must be names or strings")
        self.consume("COLON")
        val_ty = self.consume("TYPE").text
        self.consume("OPERATOR", "=")
        value = self.parse_expression()
        return key, val_ty, value

    def parse_window_configuration(self, closing_token):
        properties = {}
        while self.peek() and self.peek().kind != closing_token:
            property_name = self.consume("IDENTIFIER").text
            if property_name in properties:
                raise SyntaxError(f"Duplicate configuration property '{property_name}'")
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
                raise SyntaxError("Configuration properties must be separated by commas")
        self.consume(closing_token)
        return WindowConfigNode(properties)