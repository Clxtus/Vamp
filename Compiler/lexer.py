import re

from diagnostics import SOURCE_CACHE, make_error

NUMBER_TYPE_NAMES = "double|f32|char|i8|i16|i32|i64|u8|u16|u32|u64"

TOKEN_PATTERNS = [
    ("IMPORT", r"\bimport\b"),
    ("KEYWORD", r"\b(val|const|for|in|while|class)\b"),
    ("CAST", r"\b(int|str|float|bool|" + NUMBER_TYPE_NAMES + r")(?=\s*\()"),
    ("TYPE", r"\b(int|float|bool|str|" + NUMBER_TYPE_NAMES + r")\b"),
    ("BOOL", r"\b(true|false)\b"),
    ("OPERATOR", r"<<=|>>=|<<|>>|&&|\|\||\b(?:and|or|not)\b"),
    ("COMPARISON_OPERATOR", r"==|!=|<=|>=|<|>"),
    ("IDENTIFIER", r"\b[a-zA-Z_][a-zA-Z0-9_]*\b"),
    ("FLOAT_LITERAL", r"\b\d+\.\d+\b"),
    ("INT_LITERAL", r"\b0[xX][0-9a-fA-F]+\b|\b0[bB][01]+\b|\b\d+\b"),
    ("STRING_LITERAL", r'"(?:\\.|[^"\\])*"'),
    ("CHAR_LITERAL", r"'(?:\\[ntr0\\']|[^'\\\n])'"),
    ("OPERATOR", r"\+=|-=|\*=|/=|%=|&=|\|=|\^=|[+\-\*/=%&|^~!]"),
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
    def __init__(self, kind, text, line=0, column=0):
        self.kind = kind
        self.text = text
        self.line = line
        self.column = column

    def __repr__(self):
        return f"Token({self.kind}, {self.text})"

class TokenList(list):
    filename = None
    source_lines = None


def tokenize(source, filename=None):
    if source.startswith("\ufeff"):
        source = source[1:]
    tokens = TokenList()
    tokens.filename = filename
    tokens.source_lines = source.split("\n")
    if filename:
        SOURCE_CACHE[filename] = tokens.source_lines
    compiled_patterns = [(kind, re.compile(regex_pattern)) for kind, regex_pattern in TOKEN_PATTERNS]
    line_starts = [0]
    for idx, ch in enumerate(source):
        if ch == "\n":
            line_starts.append(idx + 1)

    def locate(offset):
        low, high = 0, len(line_starts) - 1
        while low < high:
            middle = (low + high + 1) // 2
            if line_starts[middle] <= offset:
                low = middle
            else:
                high = middle - 1
        return low + 1, offset - line_starts[low] + 1

    def fail(message, offset, width=1, hint=None):
        line, column = locate(offset)
        raise make_error(SyntaxError, message, filename, line, column, tokens.source_lines, width, hint)

    pos = 0
    while pos < len(source):
        if source.startswith("//", pos):
            newline = source.find("\n", pos + 2)
            pos = len(source) if newline == -1 else newline + 1
            continue

        if source.startswith("/*", pos):
            comment_end = source.find("*/", pos + 2)
            if comment_end == -1:
                fail("Unterminated block comment", pos, 2, "close the comment with '*/'")
            pos = comment_end + 2
            continue

        match = None
        for kind, pat in compiled_patterns:
            match = pat.match(source, pos)
            if match:
                text = match.group(0)
                if kind != "SKIP":
                    line, column = locate(pos)
                    tokens.append(Token(kind, text, line, column))
                pos = match.end()
                break
        if not match:
            if source[pos] == '"':
                fail("Unterminated string literal", pos, 1,
                     "close the string with a matching '\"'; inside a string write \\\" for a quote "
                     "and \\\\ for a backslash")
            fail(f"Unexpected character: {source[pos]}", pos)
    return tokens
