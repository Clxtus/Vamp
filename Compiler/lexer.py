# Compiler/lexer.py
import re

TOKEN_TYPES = [
    ("KEYWORD", r"\b(val|const)\b"),
    ("TYPE", r"\b(int|float|bool|string)\b"),
    ("BOOL", r"\b(true|false)\b"),
    ("IDENTIFIER", r"\b[a-zA-Z_][a-zA-Z0-9_]*\b"),
    ("FLOAT_LITERAL", r"\b\d+\.\d+\b"),
    ("INT_LITERAL", r"\b\d+\b"),
    ("STRING_LITERAL", r'"[^"]*"'),
    ("OPERATOR", r"[\+\-\*/=]"),
    ("LPAREN", r"\("),
    ("RPAREN", r"\)"),
    ("COLON", r":"),
    ("SKIP", r"[ \t\r\n]+"),
]

class Token:
    def __init__(self, type_, value):
        self.type = type_
        self.value = value

    def __repr__(self):
        return f"Token({self.type}, {self.value})"

def tokenize(source_code):
    tokens = []
    pos = 0
    while pos < len(source_code):
        match = None
        for type_, regex in TOKEN_TYPES:
            pat = re.compile(regex)
            match = pat.match(source_code, pos)
            if match:
                value = match.group(0)
                if type_ != "SKIP":
                    tokens.append(Token(type_, value))
                pos = match.end()
                break
        if not match:
            raise SyntaxError(f"Unexpected character: {source_code[pos]} at index {pos}")
    return tokens