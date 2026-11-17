# Vamp for Visual Studio Code

Language support for [Vamp](https://github.com/Clxtus/Vamp), a compiled programming language for Windows with C-level speed, classes, generics, native windows and a built-in garbage collector.

## Features

- Syntax highlighting for `.vp` source files and `.vpdata` asset files, with file icons for both.
- Errors and warnings shown as you save, with the exact line and column.
- Completion for keywords, types, your own functions and classes, and every library function (`os.`, `math.`, `json.` and the rest).
- Hover to see a function's parameters and return type; Go to Definition for functions, classes and variables.
- Format Document (`Shift+Alt+F`) using Vamp's own formatter.
- Commands: **Vamp: Run File**, **Vamp: Run Tests in File** and **Vamp: Build for Debugging**.
- Breakpoints in `.vp` files: build for debugging, then debug the `.exe` with the C/C++ extension (`cppvsdbg`).

## Requirements

Install Vamp first. The Vamp installer puts `vamp.exe` in `%LOCALAPPDATA%\Programs\Vamp` and on your `PATH`; the extension finds it automatically. Vamp uses LLVM (clang) and the Visual Studio C++ build tools to build programs, and the installer can set those up too.

## Settings

| Setting | Description |
|---|---|
| `vamp.compiler` | The command that runs the Vamp compiler, for example `vamp` or `python C:/path/Compiler/main.py`. Leave empty to use `Compiler/main.py` in the open folder, then the installed `vamp.exe`, then `vamp` on the `PATH`. |

## Example

```vamp
import models : "Models.vpdata"

class Player : (
    val name : str
    val health : int
    func hit(damage : int) : ( self.health -= damage )
)

val hero = Player("Emma", 100)
hero.hit(25)
println(f"{hero.name} has {hero.health} health, model scale {models.player.scale}")
```
