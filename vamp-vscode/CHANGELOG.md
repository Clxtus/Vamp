# Changelog

## 1.3.0

- F5 runs the current `.vp` file in any folder, no `launch.json` needed. With Microsoft's C/C++ extension installed it stops at breakpoints; without it, the program just runs.
- Ctrl+F5 builds and runs without the debugger.
- A run button in the editor title bar for `.vp` files.
- Build errors show up in a "Vamp" output panel.

## 1.2.1

- `.vpdata` files use the same colors as `.vp` files for everything they share.

## 1.2.0

- `.vpdata` asset files: highlighting and file icon.
- Highlighting for interfaces, tests, `none`, optional types (`T?`), f-strings, sets, builders, lambdas and exponent numbers.
- Finds the installed `vamp.exe` even when VS Code was open during installation.
- The Vamp terminal always uses PowerShell, so Run File works whatever your default terminal is.

## 1.1.0

- Errors on save, completion, hover, Go to Definition and formatting.
- Run, test and debug commands; breakpoints in `.vp` files.

## 1.0.0

- Syntax highlighting and file icon for `.vp` files.
