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
Creates a function, with arguments in the first set of parenthesis and the body in the second. A return statement can declare its type with `return : type (expression)`; the parentheses delimit the complete return expression. Return annotations in a function must match. Without an annotation, the return type defaults to int.

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
Creates a directory at the given path.

    os.Get_Directory(path)
Searches for directory using given path.

    os.List_Directory(Path)
Lists all files inside specified directory.

    os.Remove_Directory(path)
Deletes specified directory and its contents.

    Directory.exists()
Checks if the specified directory exists.