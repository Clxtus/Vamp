import json
import os
import re
import subprocess
import sys

C_ONLY_EXTENSIONS = (".c",)
IMPLEMENTATION_EXTENSIONS = (".c", ".cc", ".cpp", ".cxx")
HEADER_EXTENSIONS = (".h", ".hh", ".hpp", ".hxx")

INTEGER_TYPES = {
    "int", "short", "long", "long long", "unsigned int", "unsigned", "unsigned short",
    "unsigned long", "unsigned long long", "short int", "long int", "long long int",
    "unsigned short int", "unsigned long int", "unsigned long long int", "signed", "signed int",
}
FLOAT_TYPES = {"float", "double"}
STRING_POINTER_TYPES = {"char *", "const char *", "char*", "const char*"}
STRING_OBJECT_TYPES = {
    "std::string", "std::basic_string<char>", "string", "std::__cxx11::basic_string<char>",
    "std::basic_string<char, std::char_traits<char>, std::allocator<char>>",
    "std::__cxx11::basic_string<char, std::char_traits<char>, std::allocator<char>>",
    "std::__1::basic_string<char>",
}

SUPPORTED_TYPES_HINT = (
    "Vamp can pass int (any C integer type), float (float or double), bool, str "
    "(const char * or std::string) and void returns"
)


class NativeFunction:
    def __init__(self, name, qualified_name, qualified_type, parameters, return_type, problem=None):
        self.name = name
        self.qualified_name = qualified_name
        self.qualified_type = qualified_type
        self.parameters = parameters
        self.return_type = return_type
        self.problem = problem

    def vamp_parameter_kinds(self):
        return [kind for _, kind, _ in self.parameters]

    def signature_text(self):
        params = ", ".join(text for text, _, _ in self.parameters)
        return f"{self.qualified_name}({params})"


class NativeModule:
    def __init__(self, module_id, path, c_mode, functions, other_names, implementations, link_inputs, include_dir):
        self.module_id = module_id
        self.path = path
        self.c_mode = c_mode
        self.functions = functions
        self.other_names = other_names
        self.implementations = implementations
        self.link_inputs = link_inputs
        self.include_dir = include_dir


class NativeBuildInfo:
    def __init__(self):
        self.sources = []
        self.link_inputs = []
        self.include_dirs = []
        self.runtime_units = []


# bundled clang next to vamp.exe wins, then the usual LLVM dirs, then PATH
def find_clang():
    if getattr(sys, "frozen", False):
        bundle_dir = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
        bundled = os.path.join(bundle_dir, "clang.exe")
        if os.path.exists(bundled):
            return bundled
    local = os.path.join(os.path.dirname(os.path.abspath(__file__)), "clang.exe")
    if os.path.exists(local):
        return local
    for path in (r"C:\Program Files\LLVM\bin\clang.exe", r"C:\Program Files (x86)\LLVM\bin\clang.exe"):
        if os.path.exists(path):
            return path
    return "clang"


def normalize_type(text):
    text = re.sub(r"\b(const|volatile)\b", "", text)
    return re.sub(r"\s+", " ", text).strip()


INTEGER_TYPEDEF = re.compile(r"^(::)?(std::)?(u?int(_fast|_least)?(8|16|32|64)_t|size_t|ssize_t|ptrdiff_t|intptr_t|uintptr_t|intmax_t|uintmax_t)$")


def classify_one(raw, is_return):
    raw = raw.strip()
    if raw.endswith("&&"):
        return None, f"rvalue reference type '{raw}' is not supported"
    ref = raw.endswith("&")
    base = raw[:-1].strip() if ref else raw
    referenced_const = bool(re.search(r"\bconst\b", base))
    core = normalize_type(base)
    pointer_core = re.sub(r"\s*\*\s*", " *", core).strip()
    if core == "void":
        if is_return:
            return "void", None
        return None, "'void' cannot be a parameter type"
    if ref and not referenced_const and not is_return:
        return None, (f"non-const reference parameter '{raw}' is not supported "
                      "(Vamp passes values; return the result instead)")
    if core in ("bool", "_Bool"):
        return "bool", None
    if core in INTEGER_TYPES or INTEGER_TYPEDEF.match(core):
        return "int", None
    if core in FLOAT_TYPES:
        return "float", None
    if pointer_core == "char *":
        return "str", None
    if core in STRING_OBJECT_TYPES:
        return "str", None
    if "*" in core:
        return None, f"pointer type '{raw}' cannot be represented (only char pointers map to str)"
    if "<" in core:
        return None, f"template type '{raw}' cannot be represented"
    return None, f"type '{raw}' cannot be represented"


def classify(type_text, desugared=None, is_return=False):
    first_reason = None
    for candidate in (type_text, desugared):
        if not candidate:
            continue
        kind, reason = classify_one(candidate, is_return)
        if kind:
            return kind, None
        first_reason = first_reason or reason
    return None, first_reason


def split_function_type(qualified_type):
    text = re.sub(r"\s+(noexcept(\([^)]*\))?|const|&|&&)\s*$", "", qualified_type.strip())
    depth = 0
    start = None
    end = None
    for idx in range(len(text) - 1, -1, -1):
        if text[idx] == ")":
            if depth == 0:
                end = idx
            depth += 1
        elif text[idx] == "(":
            depth -= 1
            if depth == 0:
                start = idx
                break
    if start is None or end is None:
        return None, []
    ret = text[:start].strip()
    inner = text[start + 1:end]
    parts, depth, cur = [], 0, ""
    for ch in inner:
        if ch in "(<[":
            depth += 1
        elif ch in ")>]":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append(cur.strip())
            cur = ""
        else:
            cur += ch
    if cur.strip():
        parts.append(cur.strip())
    return ret, parts


class _FileTracker:
    def __init__(self):
        self.current = None

    def track(self, location):
        if not isinstance(location, dict):
            return
        if "spellingLoc" in location or "expansionLoc" in location:
            self.track(location.get("spellingLoc"))
            self.track(location.get("expansionLoc"))
        elif "file" in location:
            self.current = location["file"]

    def visit_node_location(self, node):
        self.track(node.get("loc"))
        file_after_loc = self.current
        range_info = node.get("range")
        if range_info:
            self.track(range_info.get("begin"))
            self.track(range_info.get("end"))
        return file_after_loc


def same_file(first, second):
    if first is None or second is None:
        return False
    return os.path.normcase(os.path.realpath(first)) == os.path.normcase(os.path.realpath(second))


def direct_includes(clang, path, language, include_flags):
    cmd = [clang, "-H", "-fsyntax-only", "-w", "-x", language] + include_flags + [path]
    res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if res.returncode != 0:
        return []
    includes = []
    for line in res.stderr.splitlines():
        if line.startswith(". "):
            included = os.path.normpath(line[2:].strip().replace("\\\\", "\\"))
            if included not in includes:
                includes.append(included)
    return includes


def dump_with_precompiled_includes(clang, path, c_mode, include_flags):
    import tempfile
    language = "c" if c_mode else "c++"
    includes = direct_includes(clang, path, language, include_flags)
    if not includes:
        return None
    with tempfile.TemporaryDirectory(prefix="vamp_decls_") as dirpath:
        prefix = os.path.join(dirpath, "includes.h")
        with open(prefix, "w", encoding="utf-8") as fh:
            for included in includes:
                fh.write('#include "{}"\n'.format(included.replace("\\", "/")))
        compiled = os.path.join(dirpath, "includes.pch")
        built = subprocess.run(
            [clang, "-w", "-x", language + "-header"] + include_flags + [prefix, "-o", compiled],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        if built.returncode != 0 or not os.path.exists(compiled):
            return None
        res = subprocess.run(
            [clang, "-include-pch", compiled, "-Xclang", "-ast-dump=json", "-fsyntax-only", "-w", "-x", language]
            + include_flags + [path],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
    if res.returncode != 0 or not res.stdout.strip():
        return None
    return res


def run_clang_ast(clang, path, c_mode, include_dirs, error_context):
    include_flags = []
    for dirpath in include_dirs:
        include_flags += ["-I", dirpath]
    cmd = [clang, "-Xclang", "-ast-dump=json", "-fsyntax-only", "-w", "-x", "c" if c_mode else "c++"]
    cmd += include_flags
    cmd.append(path)
    try:
        res = dump_with_precompiled_includes(clang, path, c_mode, include_flags)
        if res is None:
            res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    except FileNotFoundError:
        raise error_context(ImportError, f"cannot read '{os.path.basename(path)}': clang was not found at '{clang}'",
                            "install LLVM (clang) or put clang.exe next to the compiler; C/C++ imports need it")
    if res.returncode != 0 or not res.stdout.strip():
        details = "\n".join(res.stderr.strip().splitlines()[:12])
        raise error_context(ImportError, f"clang could not parse '{path}':\n{details}")
    try:
        return json.loads(res.stdout)
    except ValueError:
        raise error_context(ImportError, f"clang produced an unreadable declaration dump for '{path}'")


def extract_declarations(tree, path):
    fns = {}
    others = {}
    tracker = _FileTracker()
    seen = set()

    def describe_params(node):
        params = []
        for child in node.get("inner", []):
            if child.get("kind") == "ParmVarDecl":
                type_info = child.get("type", {})
                text = type_info.get("qualType", "?")
                kind, reason = classify(text, type_info.get("desugaredQualType"))
                params.append((text, kind, reason))
        return params

    def visit(node, namespaces, depth):
        kind = node.get("kind")
        in_file = tracker.visit_node_location(node)
        wanted = same_file(in_file, path) and not node.get("isImplicit")

        if kind == "NamespaceDecl":
            name = node.get("name")
            for child in node.get("inner", []):
                visit(child, namespaces + [name] if name else None, depth + 1)
            return
        if kind == "LinkageSpecDecl":
            for child in node.get("inner", []):
                visit(child, namespaces, depth + 1)
            return
        if namespaces is None:
            for child in node.get("inner", []):
                visit(child, None, depth + 1)
            return

        if kind == "FunctionDecl" and wanted:
            name = node.get("name", "")
            if name.startswith("operator") or node.get("explicitlyDeleted"):
                return
            qualified = "::".join(namespaces + [name])
            qualified_type = node.get("type", {}).get("qualType", "")
            key = (qualified, re.sub(r"\s+(noexcept(\([^)]*\))?)$", "", qualified_type))
            if key in seen:
                return
            seen.add(key)
            return_text, _ = split_function_type(qualified_type)
            params = describe_params(node)
            desugared_type = node.get("type", {}).get("desugaredQualType", qualified_type)
            desugared_return, _ = split_function_type(desugared_type)
            return_kind, return_reason = classify(return_text or "?", desugared_return, is_return=True)
            err = None
            if variadic(qualified_type):
                err = "variadic (...) functions cannot be called from Vamp"
            fn = NativeFunction(
                name, qualified, re.sub(r"\s+(noexcept(\([^)]*\))?)$", "", qualified_type), params,
                (return_text or "?", return_kind, return_reason), err,
            )
            fns.setdefault(name, []).append(fn)
            for child in node.get("inner", []):
                tracker.visit_node_location(child)
            return
        if kind in ("CXXRecordDecl", "RecordDecl") and wanted and node.get("name") and node.get("completeDefinition"):
            others.setdefault(node["name"], node.get("tagUsed") or ("class" if kind == "CXXRecordDecl" else "struct"))
        elif kind == "FunctionTemplateDecl" and wanted and node.get("name"):
            others.setdefault(node["name"], "template")
        elif kind == "ClassTemplateDecl" and wanted and node.get("name"):
            others.setdefault(node["name"], "class template")
        elif kind == "VarDecl" and wanted and node.get("name"):
            others.setdefault(node["name"], "variable")
        elif kind == "EnumDecl" and wanted and node.get("name"):
            others.setdefault(node["name"], "enum")
        for child in node.get("inner", []):
            visit(child, namespaces, depth + 1)

    for top in tree.get("inner", []):
        visit(top, [], 0)
    return fns, others


def variadic(qualified_type):
    return bool(re.search(r",\s*\.\.\.\s*\)", qualified_type)) or "(...)" in qualified_type


def load_native_module(module_id, path, link_names, error_context, base_dir):
    extension = os.path.splitext(path)[1].lower()
    clang = find_clang()
    implementations = []
    stem = os.path.splitext(path)[0]
    c_mode = extension in C_ONLY_EXTENSIONS
    if extension in HEADER_EXTENSIONS:
        for candidate_extension in IMPLEMENTATION_EXTENSIONS:
            candidate = stem + candidate_extension
            if os.path.exists(candidate):
                implementations.append(candidate)
        if extension == ".h" and implementations and all(item.endswith(".c") for item in implementations):
            c_mode = True
    include_dir = os.path.dirname(path)
    tree = run_clang_ast(clang, path, c_mode, [include_dir], error_context)
    fns, others = extract_declarations(tree, path)
    if any(function.qualified_name == "main" for function in fns.get("main", [])):
        raise error_context(
            ImportError,
            f"'{os.path.basename(path)}' defines main(), but Vamp programs already have one",
            "move main() out of the file you import, or into a separate file that is not imported",
        )
    link_inputs = []
    for name in link_names:
        if os.sep in name or "/" in name or "." in os.path.basename(name):
            resolved = name if os.path.isabs(name) else os.path.join(base_dir, name)
            if not os.path.exists(resolved):
                raise error_context(ImportError, f"cannot link '{name}': file '{resolved}' does not exist")
            link_inputs.append(resolved)
        else:
            link_inputs.append(f"-l{name}")
    return NativeModule(module_id, path, c_mode, fns, others, implementations, link_inputs, include_dir)


def bridge_symbol(module_id, function_name, index):
    return f"vamp_cpp_{module_id}_{re.sub(r'[^A-Za-z0-9_]', '_', function_name)}_{index}"


C_TYPE_FOR_KIND = {"int": "long long", "float": "double", "bool": "int", "str": "const char*"}


def parameter_expression(function, index, kind):
    text, _, _ = function.parameters[index]
    name = f"a{index}"
    if kind == "bool":
        return f"({name} != 0)"
    if kind == "str":
        if "*" in text:
            if re.match(r"^\s*const\s+char\s*\*|^\s*char\s+const\s*\*", text):
                return name
            return f"const_cast<char*>({name})"
        return f"std::string({name})"
    return name


def generate_bridge_source(module, used):
    lines = ["// Generated by the Vamp compiler. Do not edit.", "#include <cstdio>", "#include <cstdlib>",
             "#include <cstring>", "#include <exception>", "#include <string>", ""]
    include_path = module.path.replace("\\", "/")
    if module.c_mode:
        lines += ['extern "C" {', f'#include "{include_path}"', "}"]
    else:
        lines.append(f'#include "{include_path}"')
    lines += ["", 'extern "C" char* vamp_string_copy_length(const char* text, size_t length);',
              "static char* vamp_duplicate_string(const char* text, size_t length) {",
              "    return vamp_string_copy_length(text, length);", "}", ""]
    for fn, idx in used:
        symbol = bridge_symbol(module.module_id, fn.name, idx)
        return_kind = fn.return_type[1]
        params = ", ".join(
            f"{C_TYPE_FOR_KIND[kind]} a{position}" for position, kind in enumerate(fn.vamp_parameter_kinds())
        )
        args = ", ".join(
            parameter_expression(fn, position, kind)
            for position, kind in enumerate(fn.vamp_parameter_kinds())
        )
        pointer_parameters = ", ".join(text for text, _, _ in fn.parameters)
        return_text = fn.return_type[0]
        target = f"static_cast<{return_text} (*)({pointer_parameters})>(&{fn.qualified_name})"
        call = f"{target}({args})"
        c_return = {"int": "long long", "float": "double", "bool": "int", "str": "const char*", "void": "void"}[return_kind]
        lines.append(f'extern "C" {c_return} {symbol}({params or "void"}) {{')
        lines.append("    try {")
        if return_kind == "void":
            lines.append(f"        {call};")
            lines.append("        return;")
        elif return_kind == "int":
            lines.append(f"        return static_cast<long long>({call});")
        elif return_kind == "float":
            lines.append(f"        return static_cast<double>({call});")
        elif return_kind == "bool":
            lines.append(f"        return {call} ? 1 : 0;")
        else:
            core = normalize_type(return_text.rstrip("&").strip())
            if "*" in core:
                lines.append(f"        return {call};")
            else:
                lines.append(f"        std::string vamp_result = {call};")
                lines.append("        return vamp_duplicate_string(vamp_result.c_str(), vamp_result.size());")
        lines.append("    } catch (const std::exception& error) {")
        lines.append(f'        std::fprintf(stderr, "Vamp: C++ exception escaped from {fn.qualified_name}: %s\\n", error.what());')
        lines.append("    } catch (...) {")
        lines.append(f'        std::fprintf(stderr, "Vamp: unknown C++ exception escaped from {fn.qualified_name}\\n");')
        lines.append("    }")
        lines.append("    std::abort();")
        lines.append("}")
        lines.append("")
    return "\n".join(lines)


RUNTIME_UNIT_LIBRARIES = {
    "net": ["-lws2_32", "-lwininet"],
    "media": ["-lwinmm", "-luser32"],
    "system": ["-lshell32"],
    "ui": [
        "-lcomctl32", "-luxtheme", "-ldwmapi", "-lgdiplus", "-ladvapi32", "-lgdi32", "-luser32",
        "-Wl,/manifest:embed",
        "-Wl,/manifestdependency:type='win32' name='Microsoft.Windows.Common-Controls' version='6.0.0.0' "
        "processorArchitecture='*' publicKeyToken='6595b64144ccf1df' language='*'",
    ],
}


def runtime_directory():
    if getattr(sys, "frozen", False):
        bundled = os.path.join(getattr(sys, "_MEIPASS", os.path.dirname(sys.executable)), "runtime")
        if os.path.isdir(bundled):
            return bundled
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "runtime")


def runtime_object(unit, clang):
    import hashlib
    import tempfile
    dirpath = runtime_directory()
    src = os.path.join(dirpath, f"vamp_{unit}.c")
    header = os.path.join(dirpath, "vamp_runtime.h")
    if not os.path.isfile(src):
        return None, f"The Vamp runtime file '{src}' is missing; reinstall the compiler."
    digest = hashlib.sha1()
    for part in (src, header):
        with open(part, "rb") as fh:
            digest.update(fh.read())
    digest.update(clang.encode("utf-8", "replace"))
    cache = os.path.join(tempfile.gettempdir(), "vamp_runtime_cache")
    os.makedirs(cache, exist_ok=True)
    target = os.path.join(cache, f"vamp_{unit}_{digest.hexdigest()[:16]}.obj")
    if os.path.isfile(target):
        return target, ""
    partial = f"{target}.{os.getpid()}.tmp"
    res = subprocess.run(
        [clang, "-c", "-O3", "-w", "-ffunction-sections", "-fdata-sections", "-x", "c", src, "-o", partial],
        capture_output=True, text=True,
    )
    if res.returncode != 0 or not os.path.isfile(partial):
        return None, res.stderr
    os.replace(partial, target)
    return target, ""


def build_executable(llvm_ir, native, exe_filename, extra_flags=(), clang=None, temp_directory=None,
                     optimize=True):
    import tempfile
    clang = clang or find_clang()
    cleanup = None
    if native is not None and native.sources:
        if temp_directory is None:
            cleanup = tempfile.TemporaryDirectory(prefix="vamp_native_")
            temp_directory = cleanup.name
    cmd = [clang]
    if native is not None and native.sources:
        cmd.append("--driver-mode=g++")
    if native is not None:
        for idx, (path, text) in enumerate(native.sources):
            if text is not None:
                path = os.path.join(temp_directory, f"vamp_bridge_{idx}.cpp")
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(text)
            cmd += ["-x", "c" if path.lower().endswith(".c") else "c++", path]
        for dirpath in native.include_dirs:
            cmd += ["-I", dirpath]
    cmd += ["-x", "ir", "-", "-O3" if optimize else "-O0", "-o", exe_filename]
    if native is not None:
        runtime_inputs = []
        for unit in getattr(native, "runtime_units", []):
            compiled, err = runtime_object(unit, clang)
            if compiled is None:
                if cleanup is not None:
                    cleanup.cleanup()
                return False, err
            runtime_inputs.append(compiled)
            for library in RUNTIME_UNIT_LIBRARIES.get(unit, []):
                if library not in runtime_inputs:
                    runtime_inputs.append(library)
        if runtime_inputs:
            cmd += ["-x", "none"] + runtime_inputs
        cmd += native.link_inputs
    cmd += list(extra_flags)
    try:
        res = subprocess.run(cmd, input=llvm_ir, capture_output=True, text=True)
    finally:
        if cleanup is not None:
            cleanup.cleanup()
    return res.returncode == 0, res.stderr
