import re

TOKEN_PATTERNS = [
    ("IMPORT", r"\bimport\b"),
    ("KEYWORD", r"\b(val|const|for|in|while|class)\b"),
    ("CAST", r"\b(int|str|float|bool)(?=\s*\()"),
    ("TYPE", r"\b(int|float|bool|str)\b"),
    ("BOOL", r"\b(true|false)\b"),
    ("COMPARISON_OPERATOR", r"==|!=|<=|>=|<|>"),
    ("IDENTIFIER", r"\b[a-zA-Z_][a-zA-Z0-9_]*\b"),
    ("FLOAT_LITERAL", r"\b\d+\.\d+\b"),
    ("INT_LITERAL", r"\b\d+\b"),
    ("STRING_LITERAL", r'"[^"]*"'),
    ("OPERATOR", r"\+=|-=|\*=|/=|[+\-\*/=]"),
    ("LPAREN", r"\("),
    ("RPAREN", r"\)"),
    ("LBRACE", r"\{"),
    ("RBRACE", r"\}"),
    ("LBRACKET", r"\["),
    ("RBRACKET", r"\]"),
    ("COLON", r":"),
    ("COMMA", r","),
    ("SEMICOLON", r";"),
    ("DOT", r"\."),
    ("SKIP", r"[ \t\r\n]+"),
]

class Token:
    def __init__(self, kind, text):
        self.kind = kind
        self.text = text

    def __repr__(self):
        return f"Token({self.kind}, {self.text})"

def tokenize(source):
    tokens = []
    pos = 0
    while pos < len(source):
        match = None
        for kind, regex_pattern in TOKEN_PATTERNS:
            pat = re.compile(regex_pattern)
            match = pat.match(source, pos)
            if match:
                text = match.group(0)
                if kind != "SKIP":
                    tokens.append(Token(kind, text))
                pos = match.end()
                break
        if not match:
            raise SyntaxError(f"Unexpected character: {source[pos]} at index {pos}")
    return tokens