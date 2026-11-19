# Vamp for Visual Studio Code

Language support for [Vamp](https://github.com/Clxtus/Vamp), a compiled programming language for Windows with C-level performance, classes, generics, native windows and a garbage collector.

## Features

- Syntax highlighting for `.vp` source files and `.vpdata` asset files, with file icons for both.
- Errors reported on save, with the exact line and column.
- Completion for keywords, types, your own functions and classes, and every library function (`os.`, `math.`, `json.` and others).
- Hover information showing a function's parameters and return type, and Go to Definition for functions, classes and variables.
- Format Document (`Shift+Alt+F`) using Vamp's built-in formatter.
- Run and debug with F5 in any folder. With Microsoft's C/C++ extension installed, breakpoints work directly in `.vp` files; Ctrl+F5 runs without the debugger.
- Commands: **Vamp: Run File**, **Vamp: Run Tests in File** and **Vamp: Build for Debugging**, plus a run button in the editor title bar.

## Requirements

Vamp must be installed first. The installer places `vamp.exe` in `%LOCALAPPDATA%\Programs\Vamp` and adds it to the `PATH`, where the extension finds it automatically. Building programs also requires LLVM (clang) and the Visual Studio C++ build tools, which the installer can set up.

## Settings

| Setting | Description |
|---|---|
| `vamp.compiler` | The command that runs the compiler, such as `vamp` or `python C:/path/Compiler/main.py`. When empty, the extension uses `Compiler/main.py` in the open folder, then the installed `vamp.exe`, then `vamp` on the `PATH`. |

## Example

```vamp
import models : "Models.vpdata"

class Player : (
    val name : str
    val health : int
    func hit(damage : int) : ( self.health -= damage )
)

val hero = Player("Ryan", 100)
hero.hit(25)
println(f"{hero.name} has {hero.health} health, model scale {models.player.scale}")
```
