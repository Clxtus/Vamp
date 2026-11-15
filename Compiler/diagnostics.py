import difflib

SOURCE_CACHE = {}


def format_location(filename, line, column):
    name = filename or "<source>"
    if line:
        return f"{name}:{line}:{column}" if column else f"{name}:{line}"
    return name


def source_excerpt(source_lines, line, column, width=1):
    if not source_lines or not line or line > len(source_lines):
        return ""
    text = source_lines[line - 1].rstrip("\r\n")
    gutter = f"{line} | "
    ptr = " " * (len(gutter) - 2) + "| " + " " * max(column - 1, 0) + "^" * max(width, 1)
    return f"\n  {gutter}{text}\n  {ptr}"


def build_message(message, filename=None, line=0, column=0, source_lines=None, width=1, hint=None):
    text = f"{format_location(filename, line, column)}: error: {message}"
    text += source_excerpt(source_lines, line, column, width)
    if hint:
        text += f"\n  hint: {hint}"
    return text


def make_error(kind, message, filename=None, line=0, column=0, source_lines=None, width=1, hint=None):
    error = kind(build_message(message, filename, line, column, source_lines, width, hint))
    error.vamp_located = True
    return error


def suggest(name, candidates):
    matches = difflib.get_close_matches(name, sorted(candidates), n=1, cutoff=0.6)
    return matches[0] if matches else None


def describe_choices(candidates, limit=12):
    ordered = sorted(candidates)
    shown = ", ".join(ordered[:limit])
    if len(ordered) > limit:
        shown += f", ... ({len(ordered) - limit} more)"
    return shown
