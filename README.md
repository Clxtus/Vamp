# **DOCUMENTATION**

> ## **VS CODE SUPPORT**

The `vamp-vscode` folder contains the Vamp language extension. Open that folder in VS Code and run **Developer: Install Extension from Location...** from the Command Palette to load it for development, or package it with `vsce package` and install the resulting VSIX. The extension associates `.vp` files with Vamp syntax highlighting and line/block comment commands, while Explorer keeps the active VS Code file icon theme for every file type.

Vamp comments can be written with either `//` for the rest of the line or `/* ... */` for a block.

> ## **SYNTAX**

    val x : int = 10
Creates a new variable and assigns its type and value.

    const x : int = 10
Creates a new constant and assigns its type and value.

    val x, y, z : int = 10, 20, 30
    val first, second, third : int
Grouped declarations share one type. Initializers are assigned in order and must match the number of names. Without initializers, `val` variables start at the type default (`0`, `0.0`, `false`, or `""`).

    int: integer
    str: string
    float: float
    bool: boolean 
All variable and constant types.

    int()
    str()
    float()
    bool()
Use to swap variable/constant type.

    func function(argument1 : float, argument2 : float) : (
        return : float (argument1 + argument2)
    )
Creates a function, with arguments in the first set of parenthesis and the body in the second. Every function and method must explicitly return: use `return : type (expression)` for a value or `return : void` for no value. The parentheses delimit the complete value expression. A function that returns a value without an annotation defaults to int; a function with only a void return has type `void`.

    print("expression")
Prints a string or a variable/constant's value without creating a newline, use () to print in single line and {} to print in multi line.

Use "+" symbol to add to the exporession: print("Hello World" + x).

    println("expression")
Prints a string or a variable/constant's value followed by a newline, use () to print in single line and {} to print in multi line.

Use "+" symbol to add to the exporession: println("Hello World" + x).

    exit(code)
Terminates current program with a given exit code.

    val pointer = malloc(int, 4)
    pointer[0] = 42
    println(pointer[0])
    free(pointer)

`malloc(type, count)` allocates uninitialized native storage for `count` elements of type `int`, `float`, `bool`, or `str`; it returns a typed pointer that can be indexed and assigned like `pointer[index]`. The element count must be positive. Initialize elements before reading them, and call `free(pointer)` once when finished. Like raw native pointers, pointer indexing is not bounds-checked; never read, write, or free a pointer after it has been freed.

    import name : "filepath"
    import library
Imports a specified library or a filepath and calls it by the specified name.

>## **LIBRARIES**

    import os
Library used to edit and create files inside the system;

    os.Make_Directory(path)
Creates the directory and any missing parent directories. Returns `0` on success or a Windows error code on failure.

    os.Get_Directory(path)
Returns the absolute path for an existing directory, resolving relative paths from the program's current working directory. On failure, prints an error and returns an empty string. The returned string is allocated; call `free()` when finished with it.

    os.List_Directory(Path)
Prints the names of files and folders inside the specified directory, one per line, and returns the number of entries listed. The `.` and `..` navigation entries are omitted. An invalid path or enumeration error prints a message and returns `-1`.

    os.Remove_Directory(path)
Deletes the specified directory and all its contents without prompting. Returns `true` on success or `false` if the path is invalid or the operation fails.

    os.Directory_Exists(path)
Returns `true` if the specified path exists and is a directory; otherwise returns `false`.

    os.Make_Window(title, configuration)
Creates an empty, visible native Windows window with the given title and returns `true` on success. The optional settings use a parenthesized list of plain property names. Every setting is optional, and the entire settings list can be omitted:

- `icon = "path"`: image file used as the window icon. Supports ICO, PNG, and JPEG files; the path is resolved from the program's working directory.
- `size = (width, height)`: positive dimensions in pixels for windowed and borderless windows.
- `resizable = true` or `false`: enables or disables resizing for windowed/maximized styles.
- `type = "Windowed"`, `"Full Screen"`, `"Maximized"`, or `"Borderless"`: selects the native window style. Full Screen fills the primary display; Maximized uses the normal maximized window state.

The window stays open while the Vamp program runs and closes when the user closes it or `os.Remove_Window(title)` is called. Omitting configuration keeps the default resizable 800x600 window.

    os.Launch_Window(executable_path)
Launches an existing executable or application path as a separate program, allowing it to create its own window. Returns `true` if Windows accepted the launch; otherwise prints the Windows error code and returns `false`.

    os.Remove_Window(title)
Closes visible top-level windows whose title matches, case-insensitively, by sending the standard close message. The application can handle or ignore the request. Returns `true` if a close request was sent.

    os.Get_Window(title)
Returns `true` if a visible top-level window with the matching title exists; otherwise returns `false`.

    os.List_Windows()
Prints the titles of visible top-level windows, one per line, and returns the number listed.

    import os
    println("Window created: " + str(os.Make_Window("Vamp Demo", (
        icon = "assets/app.png",
        size = (1280, 720),
        resizable = true,
        type = "Windowed"
    ))))

`Make_Window` creates an empty GUI window, not a terminal. It returns after the window is visible; if the program reaches its end while windows remain open, it waits until they are closed. Use `Launch_Window` to run an existing executable. `Get_Window` and `Remove_Window` match window titles, not process names.

    if (condition) : (
        print("1")
    )
    
    else if (condition) : (
        print("2")
    )

    else: (
        print("3")
    )

Conditions must evaluate to `bool`. Comparisons support `==`, `!=`, `<`, `<=`, `>`, and `>=`; strings compare lexicographically, while booleans support `==` and `!=`.

    for (item) in (list) : (

        print(item)

    )
    Loops yield array elements or dictionary field names in declaration order. The iterable can be a collection variable or a literal expression; literals are evaluated once before iteration.

    val dictionary = {Name : str = "Cletus", Age : int = 25}
    val array = ["A", "B", "C"]

Arrays contain values of one type and have a fixed size. Read an element with `array[index]`; indexes must be valid and are not bounds-checked. Dictionaries are fixed-field records; each field declares its type and can be read with `dictionary.Name`. Iterating over a dictionary yields field names; `for (value) in (dictionary.values)` yields the field values in declaration order. Collections use inline LLVM storage rather than boxed heap objects.

    class Car : (

        val Brand : str
        val Model : str
        val Color : str
        const Max_Speed : int

        class engine : (

            const engine_type : str
            const hp : float

        )

        func max_speed_bonus(bonus : int) : (
            return : int (self.Max_Speed + bonus)
        )

    )

    Nissan = Car("Nissan", "GTR R34", "RED", 250)
    Nissan_engine = Nissan.engine("V8", 67.0)

    print(Nissan.Model)
    print(Nissan.max_speed_bonus(10))
    print(Nissan_engine.hp)

Classes are fixed-layout data types. Declare fields with `val` or `const`, then construct an instance by passing one value per field in declaration order. A nested class is declared inside its parent and constructed through a parent instance, as in `Nissan.engine(...)`. Declare methods with the regular `func` syntax inside the class; methods receive an implicit `self` and are called with `instance.method(arguments)`. The compiler checks constructor and method argument types and stores instances as inline LLVM structs. Method calls use direct native calls, with no object header, boxing, or runtime dispatch. Inheritance is not part of this syntax.

    val x : int = 10
    while (x > 0) : (

        println(x)
        x-=1

    )

While conditions must evaluate to `bool` and are checked before every iteration. Loops are lowered directly to LLVM control-flow blocks; compound assignments such as `x-=1` update the existing variable in place.
