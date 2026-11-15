# Vamp

Vamp is a Windows-oriented programming language with typed values, functions, classes, collections, native memory access, filesystem operations, and native windows and interface controls.

It also has structs, enums, lists and maps, `match`, error handling with `try`/`catch`, imports of Vamp and C/C++ files, and built-in libraries for math, random numbers, time, files, the console, JSON, threads, networking, keyboard and mouse input, and audio.

Windows and controls come in three styles: `classic` (the legacy Windows look), `native` (themed Windows 10/11 controls, the default) and `modern` (flat, rounded controls with light and dark themes, in the spirit of CustomTkinter).

## Building a program

```
python Compiler/main.py program.vp
```

The compiler needs Python with `llvmlite` and LLVM's `clang`. `Compiler/runtime` holds the C runtime that programs using lists, maps, string methods, errors or the libraries are linked with; it is compiled once and cached.

To build the compiler itself as `Compiler/dist/vamp.exe`:

```
cd Compiler
python -m PyInstaller --clean --noconfirm vamp.spec
```

Always build from `vamp.spec`: it bundles the C runtime, which `vamp.exe` needs.

See [DOCUMENTATION.md](./DOCUMENTATION.md) for the language's syntax and capabilities.
