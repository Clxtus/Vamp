# Compiler/main.py
import sys
import os
import subprocess
from lexer import tokenize
from parser import Parser
from codegen import LLVMCodeGenerator

def get_clang_path():
    # 1. PyInstaller bundle
    if getattr(sys, 'frozen', False):
        bundle_dir = getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
        bundled_clang = os.path.join(bundle_dir, "clang.exe")
        if os.path.exists(bundled_clang):
            return bundled_clang

    # 2. Local directory
    local_clang = os.path.join(os.path.dirname(__file__), "clang.exe")
    if os.path.exists(local_clang):
        return local_clang

    # 3. Explicit LLVM default installation locations on Windows
    known_paths = [
        r"C:\Program Files\LLVM\bin\clang.exe",
        r"C:\Program Files (x86)\LLVM\bin\clang.exe",
    ]
    for path in known_paths:
        if os.path.exists(path):
            return path

    # 4. Fallback to system PATH
    return "clang"

def compile_file(source_filepath):
    if not os.path.exists(source_filepath):
        print(f"Error: File '{source_filepath}' not found.")
        sys.exit(1)

    base_name, ext = os.path.splitext(source_filepath)
    if ext != ".vp":
        print(f"Error: Invalid extension '{ext}'. Source files must end with '.vp'.")
        sys.exit(1)

    ir_filename = f"{base_name}.ll"
    exe_filename = f"{base_name}.exe"

    with open(source_filepath, "r", encoding="utf-8") as f:
        source_code = f.read()

    print(f"[1/3] Compiling {source_filepath}...")
    tokens = tokenize(source_code)
    parser = Parser(tokens)
    ast = parser.parse_program()

    codegen = LLVMCodeGenerator()
    llvm_ir = codegen.generate_code(ast)

    with open(ir_filename, "w", encoding="utf-8") as f:
        f.write(llvm_ir)

    clang_bin = get_clang_path()
    print(f"[2/3] Building native binary '{exe_filename}' via Clang ({clang_bin})...")

    clang_cmd = [clang_bin, ir_filename, "-o", exe_filename, "-lshell32"]
    try:
        res = subprocess.run(clang_cmd, capture_output=True, text=True)
        if res.returncode != 0:
            print("Clang Compilation Error:")
            print(res.stderr)
            sys.exit(1)
    except FileNotFoundError:
        print(f"\nError: Could not find Clang executable at '{clang_bin}'.")
        sys.exit(1)

    if os.path.exists(ir_filename):
        os.remove(ir_filename)

    print(f"[3/3] Successfully built '{exe_filename}'!")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: vamp <filename.vp>")
        sys.exit(1)

    compile_file(sys.argv[1])