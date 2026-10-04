# **DOCUMENTATION**

> ## **SYNTAX**

    val x : int = 10
Creates a new variable and assigns its type and value.

    const x : int = 10
Creates a new constant and assigns its type and value.

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

    free(pointer)
Deallocates dynamically allocated memory pointers.

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