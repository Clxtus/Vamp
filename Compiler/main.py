import json
import os
import subprocess
import sys

from codegen import LLVMCodeGenerator
from lexer import tokenize
from native import build_executable, find_clang
from parser import Parser

WINDOWS_LINK_FLAGS = ["-Wl,/STACK:67108864", 
    "-lshell32",
    "-luser32",
    "-lgdi32",
    "-lmsimg32",
    "-lgdiplus",
]

COMPILE_ERRORS = (SyntaxError, NameError, TypeError, ValueError, ImportError, NotImplementedError)

USAGE = """Usage:
  vamp <file.vp>              build file.exe
  vamp run <file.vp> [args]   build and run it
  vamp test <file.vp>         run the test "..." blocks in the file
  vamp check <file.vp>        report errors without building (--json for editors)
  vamp format <file.vp>       tidy indentation (--write to save, otherwise print)
  vamp symbols <file.vp>      list declarations as JSON (for editors)
  vamp install <git url> [name]   add a package to vamp_packages
  vamp remove <name>          remove a package
  vamp packages               list installed packages
  vamp setup                  check for LLVM and the C++ build tools and install missing ones
  vamp setup --vscode         install the Vamp extension in Visual Studio Code
Add --debug to build or run with debugger information (a .pdb next to the .exe)."""


def fail(message):
    print(message, file=sys.stderr)
    sys.exit(1)


def read_source(path):
    if not os.path.exists(path):
        fail(f"Error: File '{path}' not found.")
    if os.path.splitext(path)[1] != ".vp":
        fail(f"Error: Invalid extension '{os.path.splitext(path)[1]}'. Source files must end with '.vp'.")
    with open(path, "rb") as fh:
        return fh.read().decode("utf-8")


def parse_file(path):
    return Parser(tokenize(read_source(path), os.path.abspath(path))).parse_program()


def generate(program, path, debug=False):
    gen = LLVMCodeGenerator()
    if debug:
        gen.enable_debug_info(os.path.abspath(path))
    return gen.generate_code(program), gen


def build(path, program=None, output=None, debug=False, quiet=False):
    exe_filename = output or f"{os.path.splitext(path)[0]}.exe"
    if not quiet:
        print(f"[1/2] Compiling {path}...")
    try:
        if program is None:
            program = parse_file(path)
        llvm_ir, gen = generate(program, path, debug)
    except COMPILE_ERRORS as err:
        fail(str(err))
    except RecursionError:
        fail(f"{path}: error: the code is nested too deeply to compile; split long expressions or deep "
             "blocks into functions")
    clang = find_clang()
    if not quiet:
        print(f"[2/2] Building native binary '{exe_filename}' via Clang RAM Pipe...")
    flags = list(WINDOWS_LINK_FLAGS)
    if debug:
        flags += ["-g", "-gcodeview", "-Wl,/DEBUG"]
    try:
        succeeded, errors = build_executable(llvm_ir, gen.native_build, exe_filename, flags, clang=clang,
                                             optimize=not debug)
    except FileNotFoundError:
        fail(f"\nError: Could not find clang ('{clang}'). Vamp needs LLVM and the Visual Studio C++ build tools.\n"
             "Install them with the Vamp installer, or run: winget install LLVM.LLVM")
    if not succeeded:
        print("Clang Compilation Error:")
        fail(errors)
    if not quiet:
        print(f"Successfully built '{exe_filename}'!")
    return exe_filename


def compile_file(source_filepath):
    return build(source_filepath)


def command_run(arguments):
    debug = "--debug" in arguments
    arguments = [item for item in arguments if item != "--debug"]
    if not arguments:
        fail(USAGE)
    executable = build(arguments[0], debug=debug, quiet=True)
    sys.exit(subprocess.call([os.path.abspath(executable), *arguments[1:]]))


def command_test(arguments):
    from tools import make_test_program
    if not arguments:
        fail(USAGE)
    path = arguments[0]
    try:
        prog, cnt = make_test_program(parse_file(path), path)
    except COMPILE_ERRORS as err:
        fail(str(err))
    if cnt == 0:
        fail(f'{path} has no test blocks; write one like: test "adds numbers" : ( assert(1 + 1 == 2) )')
    executable = build(path, program=prog, output=f"{os.path.splitext(path)[0]}.test.exe", quiet=True)
    code = subprocess.call([os.path.abspath(executable)])
    try:
        os.remove(executable)
    except OSError:
        pass
    sys.exit(code)


def command_check(arguments):
    from tools import diagnostics_json
    as_json = "--json" in arguments
    arguments = [item for item in arguments if item != "--json"]
    if not arguments:
        fail(USAGE)
    path = arguments[0]
    try:
        generate(parse_file(path), path)
    except COMPILE_ERRORS as err:
        if as_json:
            print(diagnostics_json(err, os.path.abspath(path)))
            sys.exit(0)
        fail(str(err))
    print("[]" if as_json else f"{path}: no errors")


def command_format(arguments):
    from tools import format_source
    write = "--write" in arguments
    arguments = [item for item in arguments if item != "--write"]
    if not arguments:
        fail(USAGE)
    path = arguments[0]
    if path == "-":
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stdout.write(format_source(sys.stdin.buffer.read().decode("utf-8")))
        return
    src = read_source(path)
    formatted = format_source(src)
    if write:
        if formatted != src.replace("\r\n", "\n"):
            with open(path, "w", encoding="utf-8", newline="\r\n" if "\r\n" in src else "\n") as fh:
                fh.write(formatted)
            print(f"Formatted {path}")
        else:
            print(f"{path} is already tidy")
    else:
        sys.stdout.write(formatted)


def command_symbols(arguments):
    from tools import collect_symbols, library_catalog
    if not arguments:
        fail(USAGE)
    path = arguments[0]
    try:
        symbols = collect_symbols(parse_file(path))
    except COMPILE_ERRORS:
        symbols = []
    print(json.dumps({"symbols": symbols, "libraries": library_catalog()}))


def command_packages(name, arguments):
    import tools
    try:
        if name == "install":
            if not arguments:
                fail("Usage: vamp install <git url> [name]")
            package, target = tools.install_package(arguments[0], arguments[1] if len(arguments) > 1 else None)
            print(f'Installed {package} in {target}\nImport it with: import {package} : "@{package}"')
        elif name == "remove":
            if not arguments:
                fail("Usage: vamp remove <name>")
            print(f"Removed {tools.remove_package(arguments[0])}")
        else:
            packages = tools.list_packages()
            print("\n".join(packages) if packages else "No packages installed in this folder")
    except ValueError as err:
        fail(f"Error: {err}")


def command_setup(arguments):
    import tools
    folder = os.path.dirname(os.path.abspath(sys.executable if getattr(sys, "frozen", False) else __file__))
    try:
        if "--vscode" in arguments or "--remove-vscode" in arguments:
            print(tools.setup_vscode(folder, remove="--remove-vscode" in arguments))
            return
        print("Vamp builds programs with LLVM (clang) and the Visual Studio C++ build tools.\n")
        ok = tools.setup_build_tools()
    except (OSError, ValueError) as err:
        print(f"Error: {err}", file=sys.stderr)
        ok = False
    if "--pause" in arguments:
        input("\nPress Enter to close this window.")
    if not ok:
        sys.exit(1)


def main(arguments):
    if not arguments or arguments[0] in ("-h", "--help", "help"):
        print(USAGE)
        sys.exit(0 if arguments else 1)
    cmd, rest = arguments[0], arguments[1:]
    if cmd == "run":
        command_run(rest)
    elif cmd == "test":
        command_test(rest)
    elif cmd == "check":
        command_check(rest)
    elif cmd == "format":
        command_format(rest)
    elif cmd == "symbols":
        command_symbols(rest)
    elif cmd in ("install", "remove", "packages"):
        command_packages(cmd, rest)
    elif cmd == "setup":
        command_setup(rest)
    else:
        debug = "--debug" in arguments
        files = [item for item in arguments if item != "--debug"]
        if len(files) != 1:
            fail(USAGE)
        build(files[0], debug=debug)


# parser + codegen recurse a lot on deeply nested code, the default py stack
# and recursion limit run out around ~300 nested ifs
def run_with_large_stack(arguments):
    import threading
    sys.setrecursionlimit(100000)
    threading.stack_size(255 * 1024 * 1024)
    outcome = []

    def target():
        try:
            main(arguments)
        except SystemExit as stop:
            outcome.append(stop.code)
        except BaseException:
            import traceback
            traceback.print_exc()
            outcome.append(1)

    worker = threading.Thread(target=target)
    worker.start()
    worker.join()
    code = outcome[0] if outcome else 0
    sys.stdout.flush()
    sys.exit(code)


if __name__ == "__main__":
    run_with_large_stack(sys.argv[1:])
