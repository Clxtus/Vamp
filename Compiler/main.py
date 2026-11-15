import sys
import os
from lexer import tokenize
from parser import Parser
from codegen import LLVMCodeGenerator
from native import build_executable, find_clang

WINDOWS_LINK_FLAGS = [
    "-lshell32",
    "-luser32",
    "-lgdi32",
    "-lmsimg32",
    "-lgdiplus",
]

COMPILE_ERRORS = (SyntaxError, NameError, TypeError, ValueError, ImportError, NotImplementedError)


def get_clang_path():
    return find_clang()


def compile_file(source_filepath):
    if not os.path.exists(source_filepath):
        print(f"Error: File '{source_filepath}' not found.")
        sys.exit(1)

    base_name, ext = os.path.splitext(source_filepath)
    if ext != ".vp":
        print(f"Error: Invalid extension '{ext}'. Source files must end with '.vp'.")
        sys.exit(1)

    exe_filename = f"{base_name}.exe"

    with open(source_filepath, "rb") as f:
        source_code = f.read().decode("utf-8")

    print(f"[1/2] Compiling {source_filepath}...")
    try:
        tokens = tokenize(source_code, os.path.abspath(source_filepath))
        parser = Parser(tokens)
        ast = parser.parse_program()

        codegen = LLVMCodeGenerator()
        llvm_ir = codegen.generate_code(ast)
    except COMPILE_ERRORS as err:
        print(str(err), file=sys.stderr)
        sys.exit(1)

    clang_bin = get_clang_path()
    print(f"[2/2] Building native binary '{exe_filename}' via Clang RAM Pipe...")

    try:
        succeeded, errors = build_executable(
            llvm_ir, codegen.native_build, exe_filename, WINDOWS_LINK_FLAGS, clang=clang_bin
        )
    except FileNotFoundError:
        print(f"\nError: Could not find Clang executable at '{clang_bin}'.")
        sys.exit(1)
    if not succeeded:
        print("Clang Compilation Error:")
        print(errors)
        sys.exit(1)

    print(f"Successfully built '{exe_filename}'!")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: vamp <filename.vp>")
        sys.exit(1)

    compile_file(sys.argv[1])
