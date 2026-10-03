import sys
import os
import subprocess
from lexer import tokenize
from parser import Parser
from codegen import LLVMCodeGenerator

def get_clang_path():
    if getattr(sys, 'frozen', False):
        bundle_dir = getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
        bundled_clang = os.path.join(bundle_dir, "clang.exe")
        if os.path.exists(bundled_clang):
            return bundled_clang

    local_clang = os.path.join(os.path.dirname(__file__), "clang.exe")
    if os.path.exists(local_clang):
        return local_clang

    known_paths = [
        r"C:\Program Files\LLVM\bin\clang.exe",
        r"C:\Program Files (x86)\LLVM\bin\clang.exe",
    ]
    for path in known_paths:
        if os.path.exists(path):
            return path

    return "clang"

def compile_file(source_filepath):
    if not os.path.exists(source_filepath):
        print(f"Error: File '{source_filepath}' not found.")
        sys.exit(1)

    base_name, ext = os.path.splitext(source_filepath)
    if ext != ".vp":
        print(f"Error: Invalid extension '{ext}'. Source files must end with '.vp'.")
        sys.exit(1)

    exe_filename = f"{base_name}.exe"

    # Fast raw binary read to bypass high-level string buffering
    with open(source_filepath, "rb") as f:
        source_code = f.read().decode("utf-8")

    print(f"[1/2] Compiling {source_filepath}...")
    tokens = tokenize(source_code)
    parser = Parser(tokens)
    ast = parser.parse_program()

    codegen = LLVMCodeGenerator()
    llvm_ir = codegen.generate_code(ast)
    
    clang_bin = get_clang_path()
    print(f"[2/2] Building native binary '{exe_filename}' via Clang RAM Pipe...")

    # FIXED: Move '-x' 'ir' BEFORE the '-' so Clang explicitly expects IR syntax from stdin
    clang_cmd = [clang_bin, "-x", "ir", "-", "-O3", "-o", exe_filename, "-lshell32"]
    
    try:
        # Stream the LLVM IR string straight into system RAM (input=llvm_ir)
        res = subprocess.run(clang_cmd, input=llvm_ir, capture_output=True, text=True)
        if res.returncode != 0:
            print("Clang Compilation Error:")
            print(res.stderr)
            sys.exit(1)
    except FileNotFoundError:
        print(f"\nError: Could not find Clang executable at '{clang_bin}'.")
        sys.exit(1)

    print(f"Successfully built '{exe_filename}' at ultimate speed!")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: vamp <filename.vp>")
        sys.exit(1)

    # FIXED: Added the [1] index back so it passes the target file string
    compile_file(sys.argv[1])
