<p align="center"><img src="vamp-vscode/icons/icon.png" width="96" alt="Vamp logo"></p>

<p align="center">
  <a href="https://github.com/Clxtus/Vamp/releases/latest"><img src="https://img.shields.io/github/v/release/clxtus/vamp?color=7d0000&label=release" alt="Release"></a>
  <a href="https://github.com/Clxtus/Vamp/releases/latest"><img src="https://img.shields.io/badge/platform-Windows%20x64-7d0000" alt="Platform"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-7d0000" alt="License"></a>
</p>

# Vamp

Vamp is a compiled programming language for Windows. Programs are compiled through LLVM into small native executables that run at speeds comparable to C and C++, while a garbage collector handles memory management.

```vamp
import models : "Models.vpdata"

class Player : (
    val name : str
    val health : int
    func hit(damage : int) : ( self.health -= damage )
)

val hero = Player("Ryan", 100)
hero.hit(25)
println(f"{hero.name} has {hero.health} health")
println(models.player.path)
```

## Features

- 64-bit `int` and `float` by default, along with every fixed-size number type (`i8` to `u64`, `f32`).
- Functions with default values, overloading, lambdas and closures. Classes with inheritance and virtual methods, structs, enums, interfaces, generics, optionals (`T?`) and operator overloading.
- Lists, maps, sets, tuples, slices, f-strings, `match`, `try`/`catch` and built-in tests.
- A fast garbage collector, with `malloc`/`free` available when manual control is needed.
- Libraries for math, random numbers, dates and time, files, the console, JSON, threads, networking, regular expressions, processes, keyboard and mouse input, and audio.
- Native Windows windows and controls in three styles (`classic`, `native`, and `modern` with light and dark themes), along with events and a drawing canvas.
- Imports of other Vamp files, `.vpdata` asset lists, packages, and C or C++ headers and sources.
- A Visual Studio Code extension with highlighting, error checking on save, completion, hover information, go to definition, formatting and debugging.

## Installation

Download `Vamp-<version>-x64.msi` from the [releases page](https://github.com/Clxtus/Vamp/releases) and run it. The installer sets up Vamp for the current user (no administrator rights required), installs the Visual Studio Code extension, adds `vamp` to the `PATH`, and registers `.vp` and `.vpdata` files with their icons and a **Run with Vamp** context menu entry.

Vamp requires LLVM (clang) and the Visual Studio C++ build tools to build programs. The final page of the installer can download both, or they can be installed later with `vamp setup`. Vamp can be uninstalled from **Settings > Apps**.

After installation, open a new terminal and run:

```
vamp run Examples\01_hello.vp
```

## Usage

```
vamp program.vp            build program.exe
vamp run program.vp        build and run
vamp test program.vp       run the test blocks
vamp check program.vp      check for errors without building
vamp format program.vp     print the formatted code (--write to save it)
vamp install <git-url>     add a package to vamp_packages
```

Add `--debug` to include debugging information in the build.

## Documentation

The full documentation is available at **[clxtus.github.io/Vamp](https://clxtus.github.io/Vamp/)**.

## Notes

> During the development of Vamp, an AI assistant was used on occasion for tasks such as bug fixes, C/C++ importing and error message handling. This was done to speed up the development of the language.
