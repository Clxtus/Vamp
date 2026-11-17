#include <stdio.h>

#ifdef _WIN32
#define WIN32_LEAN_AND_MEAN
#include <windows.h>

static LONG WINAPI vamp_crash_filter(EXCEPTION_POINTERS *info) {
    DWORD code = info->ExceptionRecord->ExceptionCode;
    char message[160];
    DWORD written;
    switch (code) {
    case EXCEPTION_STACK_OVERFLOW:
        lstrcpyA(message, "Error: stack overflow (a function called itself too many times)\n");
        break;
    case EXCEPTION_ACCESS_VIOLATION:
        lstrcpyA(message, "Error: invalid memory access (a bad pointer or freed memory)\n");
        break;
    case EXCEPTION_INT_DIVIDE_BY_ZERO:
        lstrcpyA(message, "Error: division by zero\n");
        break;
    default: {
        static const char hex[] = "0123456789ABCDEF";
        char *cursor;
        lstrcpyA(message, "Error: the program crashed (exception 0x00000000)\n");
        cursor = message + lstrlenA("Error: the program crashed (exception 0x");
        for (int shift = 28; shift >= 0; shift -= 4) {
            *cursor++ = hex[(code >> shift) & 15];
        }
        break;
    }
    }
    fflush(stdout);
    WriteFile(GetStdHandle(STD_ERROR_HANDLE), message, (DWORD)lstrlenA(message), &written, NULL);
    TerminateProcess(GetCurrentProcess(), 1);
    return EXCEPTION_EXECUTE_HANDLER;
}

/* VEH and not just the unhandled filter: overflows on worker threads never reached it */
static LONG WINAPI vamp_overflow_handler(EXCEPTION_POINTERS *info) {
    if (info->ExceptionRecord->ExceptionCode == EXCEPTION_STACK_OVERFLOW) {
        return vamp_crash_filter(info);
    }
    return EXCEPTION_CONTINUE_SEARCH;
}

void vamp_start(void) {
    ULONG reserve = 64 * 1024;
    SetErrorMode(SEM_FAILCRITICALERRORS | SEM_NOGPFAULTERRORBOX);
    SetThreadStackGuarantee(&reserve);
    SetUnhandledExceptionFilter(vamp_crash_filter);
    AddVectoredExceptionHandler(1, vamp_overflow_handler);
}
#else
void vamp_start(void) {
}
#endif

