import json
import os
import re
import shutil
import subprocess

from libraries import BUILTIN_LIBRARIES, OS_RUNTIME, STANDARD_LIBRARIES
from parser import (
    AssignmentNode, ClassDeclarationNode, ComparisonNode, EnumDeclarationNode, ExitNode, FormatStringNode,
    FunctionDeclarationNode, GroupVariableDeclarationNode, IfNode, ImportFileNode, InterfaceDeclarationNode,
    LibraryImportNode, LiteralNode, NativeImportNode, PrintNode, TestNode, TryNode, VariableAccessNode,
    VariableDeclarationNode,
)

DECLARATIONS = (
    FunctionDeclarationNode, ClassDeclarationNode, EnumDeclarationNode, InterfaceDeclarationNode, LibraryImportNode,
    NativeImportNode, ImportFileNode, VariableDeclarationNode, GroupVariableDeclarationNode,
)
PACKAGES_FOLDER = "vamp_packages"


def make_test_program(program, main_file):
    main_file = os.path.normcase(os.path.abspath(main_file))
    tests = [node for node in program if isinstance(node, TestNode)
             and os.path.normcase(os.path.abspath(getattr(node, "filename", "") or main_file)) == main_file]
    stmts = [node for node in program if isinstance(node, DECLARATIONS)]
    stmts.append(VariableDeclarationNode(False, "vamp_test_failures", "int", LiteralNode("int", 0)))
    for test in tests:
        passed = PrintNode(LiteralNode("str", f"PASS  {test.name}"))
        failed = PrintNode(FormatStringNode([f"FAIL  {test.name}: ", (VariableAccessNode("vamp_test_error"), None)]))
        cnt = AssignmentNode("vamp_test_failures", "+=", LiteralNode("int", 1))
        stmts.append(TryNode(list(test.body) + [passed], "vamp_test_error", [failed, cnt]))
    stmts.append(PrintNode(FormatStringNode(
        [f"\n{len(tests)} test{'s' if len(tests) != 1 else ''}, ", (VariableAccessNode("vamp_test_failures"), None),
         " failed"])))
    stmts.append(IfNode(
        [(ComparisonNode(VariableAccessNode("vamp_test_failures"), ">", LiteralNode("int", 0)),
          [ExitNode(LiteralNode("int", 1))])], None))
    return stmts, len(tests)


OPENERS = "([{"
CLOSERS = ")]}"


def format_source(source, indent="    "):
    lines = source.replace("\r\n", "\n").split("\n")
    output = []
    depth = 0
    in_block_comment = False
    blank_run = 0
    for raw in lines:
        line = raw.strip()
        if in_block_comment:
            output.append(raw.rstrip())
            if "*/" in raw:
                in_block_comment = False
            continue
        if not line:
            blank_run += 1
            if blank_run <= 2:
                output.append("")
            continue
        blank_run = 0
        code = strip_strings_and_comments(line)
        leading_closers = len(code) - len(code.lstrip(CLOSERS + " "))
        closers_first = sum(1 for ch in code[:leading_closers] if ch in CLOSERS)
        level = max(depth - closers_first, 0)
        output.append(indent * level + line)
        for ch in code:
            if ch in OPENERS:
                depth += 1
            elif ch in CLOSERS:
                depth = max(depth - 1, 0)
        if "/*" in code and "*/" not in code[code.index("/*"):]:
            in_block_comment = True
    while output and output[-1] == "":
        output.pop()
    return "\n".join(output) + "\n"


def strip_strings_and_comments(line):
    res = []
    idx = 0
    while idx < len(line):
        ch = line[idx]
        if line.startswith("//", idx):
            break
        if line.startswith("/*", idx):
            end = line.find("*/", idx + 2)
            if end == -1:
                res.append("/*")
                break
            idx = end + 2
            continue
        if ch in "\"'":
            quote = ch
            idx += 1
            while idx < len(line) and line[idx] != quote:
                idx += 2 if line[idx] == "\\" else 1
            idx += 1
            res.append(" ")
            continue
        res.append(ch)
        idx += 1
    return "".join(res)


def describe(type_name):
    if type_name is None:
        return None
    from language import describe_type
    return describe_type(type_name)


def function_detail(node, prefix="func"):
    params = ", ".join(f"{name} : {describe(type_name)}" for name, type_name in node.parameters)
    res = "" if node.return_type == "void" else f" : {describe(node.return_type)}"
    type_parameters = getattr(node, "type_parameters", None)
    generic = f"[{', '.join(type_parameters)}]" if type_parameters else ""
    return f"{prefix} {node.function_name}{generic}({params}){res}"


def collect_symbols(program):
    symbols = []

    def add(kind, name, detail, node, container=None):
        symbols.append({
            "kind": kind, "name": name, "detail": detail, "container": container,
            "file": getattr(node, "filename", None), "line": getattr(node, "line", 0),
            "column": getattr(node, "column", 0),
        })

    def walk_body(statements, container):
        for stmt in statements or []:
            if isinstance(stmt, VariableDeclarationNode):
                keyword = "const" if stmt.is_constant else "val"
                shown = f" : {describe(stmt.variable_type)}" if stmt.variable_type else ""
                add("variable", stmt.variable_name, f"{keyword} {stmt.variable_name}{shown}", stmt,
                    container)
            for child in vars(stmt).values() if hasattr(stmt, "__dict__") else []:
                if isinstance(child, list) and child and all(hasattr(item, "__dict__") for item in child):
                    walk_body(child, container)

    for node in program:
        if isinstance(node, FunctionDeclarationNode):
            add("function", node.function_name, function_detail(node), node)
            for name, ty_name in node.parameters:
                add("parameter", name, f"{name} : {describe(ty_name)}", node, node.function_name)
            walk_body(node.body, node.function_name)
        elif isinstance(node, ClassDeclarationNode):
            kind = "struct" if node.is_struct else "class"
            parents = getattr(node, "parents", None) or ([node.parent] if node.parent else [])
            shown = f"({', '.join(parents)})" if parents else ""
            add(kind, node.class_name, f"{kind} {node.class_name}{shown}", node)
            for field_name, field_ty, is_constant in node.fields:
                add("field", field_name, f"{'const' if is_constant else 'val'} {field_name} : {describe(field_ty)}",
                    node, node.class_name)
            for meth in node.methods:
                add("method", meth.function_name, function_detail(meth), meth, node.class_name)
                walk_body(meth.body, f"{node.class_name}.{meth.function_name}")
        elif isinstance(node, EnumDeclarationNode):
            add("enum", node.enum_name, f"enum {node.enum_name}", node)
            for member, value in node.members:
                add("enum_member", member, f"{node.enum_name}.{member} = {value}", node, node.enum_name)
        elif isinstance(node, InterfaceDeclarationNode):
            add("interface", node.interface_name, f"interface {node.interface_name}", node)
        elif isinstance(node, VariableDeclarationNode):
            keyword = "const" if node.is_constant else "val"
            shown = f" : {describe(node.variable_type)}" if node.variable_type else ""
            add("variable", node.variable_name, f"{keyword} {node.variable_name}{shown}", node)
        elif isinstance(node, TestNode):
            add("test", node.name, f'test "{node.name}"', node)
    return symbols


def describe_library_entry(name, entry):
    _, params, res = entry[:3]
    shown = ", ".join("int" if item == "c_i64" else describe(item) if item not in ("number", "function")
                      else ("number" if item == "number" else "function") for item in params)
    result_text = {"c_i64": "int", "number": "float", "number_same": "number"}.get(res, describe(res))
    return f"{name}({shown})" + ("" if res == "void" else f" : {result_text}")


def library_catalog():
    catalog = {}
    for library, meths in BUILTIN_LIBRARIES.items():
        entries = []
        table = STANDARD_LIBRARIES.get(library, OS_RUNTIME if library == "os" else {})
        for meth in sorted(meths):
            entry = table.get(meth)
            entries.append({"name": meth, "detail": describe_library_entry(meth, entry) if entry else meth})
        catalog[library] = entries
    return catalog


def find_packages_folder(start):
    dirpath = os.path.abspath(start)
    while True:
        candidate = os.path.join(dirpath, PACKAGES_FOLDER)
        if os.path.isdir(candidate):
            return candidate
        parent = os.path.dirname(dirpath)
        if parent == dirpath:
            return None
        dirpath = parent


def resolve_package_path(raw, base_dir):
    if not raw.startswith("@"):
        return raw
    name, _, rest = raw[1:].partition("/")
    folder = find_packages_folder(base_dir)
    if folder is None:
        return None
    return os.path.join(folder, name, rest or f"{name}.vp")


def install_package(url, name=None, directory="."):
    if name is None:
        name = re.sub(r"\.git$", "", url.rstrip("/").split("/")[-1])
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_\-]*", name):
        raise ValueError(f"'{name}' cannot be a package name; give one with: vamp install <url> <name>")
    folder = os.path.join(directory, PACKAGES_FOLDER)
    target = os.path.join(folder, name)
    if os.path.exists(target):
        raise ValueError(f"Package '{name}' is already installed in {target}; remove it first with: vamp remove {name}")
    if shutil.which("git") is None:
        raise ValueError("Installing packages needs git on the PATH")
    os.makedirs(folder, exist_ok=True)
    res = subprocess.run(["git", "clone", "--depth", "1", url, target], capture_output=True, text=True)
    if res.returncode != 0:
        raise ValueError(f"git could not download {url}:\n{res.stderr.strip()}")
    return name, target


def remove_package(name, directory="."):
    target = os.path.join(directory, PACKAGES_FOLDER, name)
    if not os.path.isdir(target):
        raise ValueError(f"Package '{name}' is not installed here")

    def writable(function, path, _):
        os.chmod(path, 0o666)
        function(path)

    shutil.rmtree(target, onerror=writable)
    return target


def list_packages(directory="."):
    folder = os.path.join(directory, PACKAGES_FOLDER)
    if not os.path.isdir(folder):
        return []
    return sorted(name for name in os.listdir(folder) if os.path.isdir(os.path.join(folder, name)))


def diagnostics_json(problem, fallback_file):
    return json.dumps([{
        "file": getattr(problem, "vamp_file", None) or fallback_file,
        "line": getattr(problem, "vamp_line", 0) or 1,
        "column": getattr(problem, "vamp_column", 0) or 1,
        "width": getattr(problem, "vamp_width", 1) or 1,
        "message": getattr(problem, "vamp_message", None) or str(problem).split("\n")[0],
        "hint": getattr(problem, "vamp_hint", None),
        "severity": "error",
    }])


def find_build_tools():
    vswhere = os.path.join(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
                           r"Microsoft Visual Studio\Installer\vswhere.exe")
    if not os.path.exists(vswhere):
        return None
    res = subprocess.run([vswhere, "-products", "*", "-requires", "Microsoft.VisualStudio.Component.VC.Tools.x86.x64",
                             "-property", "installationPath"], capture_output=True, text=True)
    lines = [line for line in res.stdout.splitlines() if line.strip()]
    return lines[0] if lines else None


def find_clang_path():
    from native import find_clang
    clang = find_clang()
    return clang if os.path.exists(clang) else shutil.which(clang)


def find_vscode():
    for candidate in (shutil.which("code.cmd"), shutil.which("code"),
                      os.path.join(os.environ.get("LOCALAPPDATA", ""), r"Programs\Microsoft VS Code\bin\code.cmd"),
                      r"C:\Program Files\Microsoft VS Code\bin\code.cmd"):
        if candidate and os.path.exists(candidate):
            return candidate
    return None


def bundled_extension(folder):
    files = sorted(name for name in os.listdir(folder) if name.startswith("vamp-lang-") and name.endswith(".vsix"))
    return os.path.join(folder, files[-1]) if files else None


def setup_vscode(folder, remove=False):
    code = find_vscode()
    if code is None:
        return "Visual Studio Code was not found; install it from https://code.visualstudio.com"
    if remove:
        subprocess.run([code, "--uninstall-extension", "clxtus.vamp-lang"], capture_output=True)
        return "Removed the Vamp extension from Visual Studio Code"
    extension = bundled_extension(folder)
    if extension is None:
        return "No vamp-lang .vsix file was found next to vamp.exe"
    res = subprocess.run([code, "--install-extension", extension, "--force"], capture_output=True, text=True)
    if res.returncode != 0:
        raise ValueError("Visual Studio Code could not install the extension:\n" + res.stderr.strip())
    return "Installed the Vamp extension in Visual Studio Code"


BUILD_TOOLS = (
    ("LLVM (clang)", find_clang_path, ["--id", "LLVM.LLVM"]),
    ("Visual Studio C++ Build Tools", find_build_tools,
     ["--id", "Microsoft.VisualStudio.2022.BuildTools", "--override",
      "--passive --wait --norestart --add Microsoft.VisualStudio.Workload.VCTools --includeRecommended"]),
)


# also run by the msi's finish page (vamp setup --pause)
def setup_build_tools(say=print):
    missing = []
    for name, finder, args in BUILD_TOOLS:
        found = finder()
        say(f"  {name}: {found}" if found else f"  {name}: missing")
        if not found:
            missing.append((name, finder, args))
    if not missing:
        say("\nEverything Vamp needs to build programs is installed.")
        return True
    winget = shutil.which("winget")
    if winget is None:
        say("\nwinget is not available. Install LLVM from https://github.com/llvm/llvm-project/releases and the "
            "Build Tools from https://visualstudio.microsoft.com/downloads (workload: Desktop development with C++).")
        return False
    ok = True
    for name, finder, args in missing:
        say(f"\nDownloading and installing {name} with winget. Windows may ask for permission.")
        res = subprocess.run([winget, "install", "-e", "--accept-package-agreements", "--accept-source-agreements",
                                 *args])
        if finder() is None and res.returncode != 0:
            say(f"{name} did not install (winget exit code {res.returncode}).")
            ok = False
    say("\nDone." if ok else "\nSome tools are still missing; run 'vamp setup' again to retry.")
    return ok
