from pygments.lexer import RegexLexer, bygroups, include, words
from pygments.token import Comment, Keyword, Name, Number, Operator, Punctuation, String, Text, Whitespace

KEYWORDS = (
    "import", "from", "as", "link", "val", "const", "func", "return", "if", "else", "elif", "for", "in", "while",
    "class", "struct", "enum", "interface", "match", "break", "continue", "try", "catch", "throw", "test",
)
TYPES = (
    "int", "float", "bool", "str", "double", "f32", "char", "i8", "i16", "i32", "i64", "u8", "u16", "u32", "u64",
    "void", "list", "map", "set", "tuple", "json", "builder",
)
BUILTINS = ("print", "println", "len", "range", "exit", "free", "malloc", "assert", "args", "env")
LIBRARIES = ("os", "math", "random", "time", "file", "console", "json", "thread", "net", "input", "audio", "memory",
             "regex")


class VampLexer(RegexLexer):
    name = "Vamp"
    aliases = ["vamp", "vp"]
    filenames = ["*.vp"]

    tokens = {
        "root": [
            (r"\s+", Whitespace),
            (r"//.*?$", Comment.Single),
            (r"/\*", Comment.Multiline, "comment"),
            (r'\bf"', String.Interpol, "fstring"),
            (r'"', String.Double, "string"),
            (r"'(?:\\[ntr0\\']|[^'\\\n])'", String.Char),
            (r"\b0[xX][0-9a-fA-F]+\b|\b0[bB][01]+\b", Number.Hex),
            (r"\b\d+(?:\.\d+(?:[eE][+-]?\d+)?|[eE][+-]?\d+)\b", Number.Float),
            (r"\b\d+\b", Number.Integer),
            (r"\b(func)(\s+)([A-Za-z_]\w*)", bygroups(Keyword, Whitespace, Name.Function)),
            (r"\b(class|struct|enum|interface)(\s+)([A-Za-z_]\w*)", bygroups(Keyword, Whitespace, Name.Class)),
            (words(KEYWORDS, suffix=r"\b"), Keyword),
            (words(("and", "or", "not"), suffix=r"\b"), Operator.Word),
            (words(("true", "false", "none"), suffix=r"\b"), Keyword.Constant),
            (words(("self", "super"), suffix=r"\b"), Name.Builtin.Pseudo),
            (words(TYPES, suffix=r"\b"), Keyword.Type),
            (r"\b(" + "|".join(LIBRARIES) + r")(\s*\.\s*)([A-Za-z_]\w*)",
             bygroups(Name.Namespace, Punctuation, Name.Function)),
            (words(BUILTINS, suffix=r"(?=\s*\()"), Name.Builtin),
            (r"(\.)(\s*)([A-Za-z_]\w*)(?=\s*\()", bygroups(Punctuation, Whitespace, Name.Function)),
            (r"(\.)(\s*)([A-Za-z_]\w*)", bygroups(Punctuation, Whitespace, Name.Attribute)),
            (r"\b[A-Z]\w*\b", Name.Class),
            (r"\b[A-Za-z_]\w*(?=\s*\()", Name.Function),
            (r"\b[A-Za-z_]\w*\b", Name),
            (r"<<=|>>=|==|!=|<=|>=|\+=|-=|\*=|/=|%=|&=|\|=|\^=|&&|\|\||<<|>>|[+\-*/=<>!%&|^~?]", Operator),
            (r"[()\[\]{}:,;.]", Punctuation),
            (r".", Text),
        ],
        "comment": [
            (r"[^*/]+", Comment.Multiline),
            (r"\*/", Comment.Multiline, "#pop"),
            (r"[*/]", Comment.Multiline),
        ],
        "string": [
            (r'\\.', String.Escape),
            (r'"', String.Double, "#pop"),
            (r'[^"\\]+', String.Double),
        ],
        "fstring": [
            (r'\\.', String.Escape),
            (r'"', String.Interpol, "#pop"),
            (r"\{", String.Interpol, "interpolation"),
            (r'[^"\\{]+', String.Interpol),
        ],
        "interpolation": [
            (r"\}", String.Interpol, "#pop"),
            include("root"),
        ],
    }


class VampDataLexer(RegexLexer):
    name = "Vamp Data"
    aliases = ["vpdata"]
    filenames = ["*.vpdata"]

    tokens = {
        "root": [
            (r"\b(object)(\s+)(\"[^\"]*\")", bygroups(Keyword, Whitespace, Name.Class)),
            (r"\b([A-Za-z_]\w*)(\s*)(:)", bygroups(Name.Attribute, Whitespace, Punctuation)),
            include("values"),
        ],
        "values": VampLexer.tokens["root"],
        "comment": VampLexer.tokens["comment"],
        "string": VampLexer.tokens["string"],
        "fstring": VampLexer.tokens["fstring"],
        "interpolation": VampLexer.tokens["interpolation"],
    }
