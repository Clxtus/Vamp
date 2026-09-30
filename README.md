# Vamp

Documentation

-- KEYWORDS --

val - Creates a new variable and assigns its type and value .e.g. val x : int = 10
const - Creates a new constant and assigns its type and value. e.g. const x : int = 10

^--- Types are:

    - Int: integer
    - Str: string
    - Float: float
    - Bool: boolean 


func - Creates a new function that can require arguments which are placed inside the first set of parenthesis, and can execute a snippet of code which is placed in the second set. e.g. func example(arg1, arg2) : ()

print(expression) - Prints a string or a variable/constant's value without creating a newline, use () to print in single line and {} to print in multi line. e.g. print("Hello world!) --prints "Hello world!".
println(expression) - Prints a string or a variable/constant's value followed by a newline. e.g. print("Hello world!) --prints "Hello world!" and adds a newline, use () to print in single line and {} to print in multi line.

exit(code) - Terminates current program with a given exit code. e.g. exit(404) - Terminates currently running program.
free(pointer) - Deallocates dynamically allocated memory pointers.

