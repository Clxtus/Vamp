<p align="center"><img src="vamp-vscode/icons/icon.png" width="96" alt="Vamp logo"></p>

<p align="center">
  <a href="https://github.com/Clxtus/Vamp/releases/latest"><img src="https://img.shields.io/github/v/release/clxtus/vamp?color=7d0000&label=release" alt="Release"></a>
  <a href="https://github.com/Clxtus/Vamp/releases/latest"><img src="https://img.shields.io/badge/platform-Windows%20x64-7d0000" alt="Platform"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-7d0000" alt="License"></a>
</p>

# Vamp

Vamp is a compiled programming language for Windows. Programs build into small native `.exe` files through LLVM and run at C/C++ speed, while the language takes care of memory with a garbage collector.

```vamp
import models : "Models.vpdata"

class Player : (
    val name : str
    val health : int
    func hit(damage : int) : ( self.health -= damage )
)

val hero = Player("Emma", 100)
hero.hit(25)
println(f"{hero.name} has {hero.health} health")
println(models.player.path)
```

## Features

- Typed values with 64-bit `int` and `float` by default, plus every fixed-size number type (`i8` to `u64`, `f32`).
- Functions with default values, overloading, lambdas and closures; classes with inheritance and virtual methods; structs, enums, interfaces, generics, optionals (`T?`) and operator overloading.
- Lists, maps, sets, tuples, slices, f-strings, `match`, `try`/`catch` and built-in tests.
- Automatic memory management with a fast conservative garbage collector; `malloc`/`free` when you want manual control.
- Libraries for math, random numbers, time and dates, files, the console, JSON, threads, networking, regular expressions, processes, keyboard and mouse input, and audio.
- Native Windows windows and controls in three styles (`classic`, `native`, `modern` with light and dark themes), events and a drawing canvas.
- Imports of other Vamp files, `.vpdata` asset lists, packages, and C or C++ headers and sources.
- A Visual Studio Code extension with highlighting, errors on save, completion, hover, Go to Definition, formatting and debugging.

## Install

Download `Vamp-<version>-x64.msi` from the [releases page](https://github.com/Clxtus/Vamp/releases) and open it. It installs Vamp for your account (no administrator rights needed) together with the Visual Studio Code extension, adds `vamp` to the `PATH`, and gives `.vp` and `.vpdata` files their icons with **Run with Vamp** in the right-click menu. On the last page it can download LLVM (clang) and the Visual Studio C++ build tools, which Vamp needs to build programs; `vamp setup` does the same later. Uninstall it from **Settings > Apps**.

Then, in a new terminal:

```
vamp run Examples\01_hello.vp
```

## Using the compiler

```
vamp program.vp            build program.exe
vamp run program.vp        build and run
vamp test program.vp       run the test blocks
vamp check program.vp      report errors without building
vamp format program.vp     print the formatted code (--write to save it)
vamp install <git-url>     add a package to vamp_packages
```

Add `--debug` to build with debugging information. See [DOCUMENTATION.md](./DOCUMENTATION.md) for the whole language.
