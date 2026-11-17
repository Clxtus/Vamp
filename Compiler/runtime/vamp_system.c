#define _CRT_SECURE_NO_WARNINGS
#include "vamp_runtime.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include <windows.h>
#include <shellapi.h>

static char *vamp_utf8_from_wide(const wchar_t *text) {
    int size = WideCharToMultiByte(CP_UTF8, 0, text, -1, NULL, 0, NULL, NULL);
    char *buffer = (char *)malloc(size > 0 ? (size_t)size : 1);
    char *result;
    if (!buffer) {
        vamp_throw("out of memory");
    }
    buffer[0] = 0;
    if (size > 0) {
        WideCharToMultiByte(CP_UTF8, 0, text, -1, buffer, size, NULL, NULL);
    }
    result = vamp_string_copy(buffer);
    free(buffer);
    return result;
}

VampList *vamp_os_args(void) {
    int count = 0;
    wchar_t **arguments = CommandLineToArgvW(GetCommandLineW(), &count);
    VampList *list = vamp_list_new((int32_t)sizeof(char *), count);
    for (int index = 0; arguments && index < count; index++) {
        char *argument = vamp_utf8_from_wide(arguments[index]);
        memcpy(vamp_list_push_slot(list), &argument, sizeof(char *));
    }
    if (arguments) {
        LocalFree(arguments);
    }
    return list;
}

char *vamp_os_get_env(const char *name) {
    DWORD size = GetEnvironmentVariableA(name, NULL, 0);
    char *buffer;
    char *result;
    if (size == 0) {
        return vamp_string_copy("");
    }
    buffer = (char *)malloc(size);
    if (!buffer) {
        vamp_throw("out of memory");
    }
    GetEnvironmentVariableA(name, buffer, size);
    result = vamp_string_copy(buffer);
    free(buffer);
    return result;
}

int32_t vamp_os_env_exists(const char *name) {
    SetLastError(0);
    return GetEnvironmentVariableA(name, NULL, 0) > 0 || GetLastError() != ERROR_ENVVAR_NOT_FOUND;
}

int32_t vamp_os_set_env(const char *name, const char *value) {
    return SetEnvironmentVariableA(name, value) != 0;
}

static char *vamp_shell_command(const char *command) {
    static const char prefix[] = "cmd.exe /d /s /c \"";
    size_t length = strlen(command);
    char *line = (char *)malloc(sizeof(prefix) + length + 2);
    if (!line) {
        vamp_throw("out of memory");
    }
    memcpy(line, prefix, sizeof(prefix) - 1);
    memcpy(line + sizeof(prefix) - 1, command, length);
    line[sizeof(prefix) - 1 + length] = '"';
    line[sizeof(prefix) + length] = 0;
    return line;
}

static int vamp_spawn(const char *command, HANDLE output, PROCESS_INFORMATION *process) {
    STARTUPINFOA startup;
    char *line = vamp_shell_command(command);
    int created;
    memset(&startup, 0, sizeof(startup));
    startup.cb = sizeof(startup);
    if (output) {
        startup.dwFlags = STARTF_USESTDHANDLES;
        startup.hStdInput = GetStdHandle(STD_INPUT_HANDLE);
        startup.hStdOutput = output;
        startup.hStdError = output;
    }
    memset(process, 0, sizeof(*process));
    created = CreateProcessA(NULL, line, NULL, NULL, output != NULL, 0, NULL, NULL, &startup, process) != 0;
    free(line);
    return created;
}

int32_t vamp_os_run(const char *command) {
    PROCESS_INFORMATION process;
    DWORD code = (DWORD)-1;
    fflush(stdout);
    if (!vamp_spawn(command, NULL, &process)) {
        return -1;
    }
    WaitForSingleObject(process.hProcess, INFINITE);
    GetExitCodeProcess(process.hProcess, &code);
    CloseHandle(process.hThread);
    CloseHandle(process.hProcess);
    return (int32_t)code;
}

char *vamp_os_run_output(const char *command) {
    SECURITY_ATTRIBUTES security = {sizeof(security), NULL, TRUE};
    PROCESS_INFORMATION process;
    HANDLE reader;
    HANDLE writer;
    char *buffer;
    size_t length = 0;
    size_t capacity = 4096;
    char *result;
    if (!CreatePipe(&reader, &writer, &security, 0)) {
        vamp_throw("could not create a pipe to read the command's output");
    }
    SetHandleInformation(reader, HANDLE_FLAG_INHERIT, 0);
    if (!vamp_spawn(command, writer, &process)) {
        CloseHandle(reader);
        CloseHandle(writer);
        vamp_throw_format("could not run \"%s\"", command);
    }
    CloseHandle(writer);
    buffer = (char *)malloc(capacity);
    if (!buffer) {
        vamp_throw("out of memory");
    }
    for (;;) {
        DWORD read = 0;
        if (length + 1024 > capacity) {
            char *grown = (char *)realloc(buffer, capacity * 2);
            if (!grown) {
                free(buffer);
                vamp_throw("out of memory");
            }
            buffer = grown;
            capacity *= 2;
        }
        if (!ReadFile(reader, buffer + length, (DWORD)(capacity - length - 1), &read, NULL) || read == 0) {
            break;
        }
        length += read;
    }
    CloseHandle(reader);
    WaitForSingleObject(process.hProcess, INFINITE);
    CloseHandle(process.hThread);
    CloseHandle(process.hProcess);
    result = vamp_string_copy_length(buffer, length);
    free(buffer);
    return result;
}

typedef struct {
    DWORD id;
    HANDLE handle;
} VampProcess;

static VampProcess vamp_processes[256];
static SRWLOCK vamp_process_lock = SRWLOCK_INIT;

static HANDLE vamp_process_handle(int64_t id) {
    HANDLE handle = NULL;
    AcquireSRWLockShared(&vamp_process_lock);
    for (int index = 0; index < 256; index++) {
        if (vamp_processes[index].handle && vamp_processes[index].id == (DWORD)id) {
            handle = vamp_processes[index].handle;
            break;
        }
    }
    ReleaseSRWLockShared(&vamp_process_lock);
    return handle;
}

int64_t vamp_os_start_process(const char *command) {
    PROCESS_INFORMATION process;
    if (!vamp_spawn(command, NULL, &process)) {
        return 0;
    }
    CloseHandle(process.hThread);
    AcquireSRWLockExclusive(&vamp_process_lock);
    for (int index = 0; index < 256; index++) {
        if (!vamp_processes[index].handle) {
            vamp_processes[index].id = process.dwProcessId;
            vamp_processes[index].handle = process.hProcess;
            process.hProcess = NULL;
            break;
        }
    }
    ReleaseSRWLockExclusive(&vamp_process_lock);
    if (process.hProcess) {
        CloseHandle(process.hProcess);
    }
    return (int64_t)process.dwProcessId;
}

int32_t vamp_os_process_running(int64_t id) {
    HANDLE handle = vamp_process_handle(id);
    HANDLE opened = NULL;
    int32_t running;
    if (!handle) {
        opened = OpenProcess(SYNCHRONIZE, FALSE, (DWORD)id);
        handle = opened;
    }
    if (!handle) {
        return 0;
    }
    running = WaitForSingleObject(handle, 0) == WAIT_TIMEOUT;
    if (opened) {
        CloseHandle(opened);
    }
    return running;
}

int32_t vamp_os_wait_process(int64_t id) {
    HANDLE handle = vamp_process_handle(id);
    HANDLE opened = NULL;
    DWORD code = (DWORD)-1;
    if (!handle) {
        opened = OpenProcess(SYNCHRONIZE | PROCESS_QUERY_LIMITED_INFORMATION, FALSE, (DWORD)id);
        handle = opened;
    }
    if (!handle) {
        return -1;
    }
    WaitForSingleObject(handle, INFINITE);
    GetExitCodeProcess(handle, &code);
    if (opened) {
        CloseHandle(opened);
    }
    return (int32_t)code;
}

int32_t vamp_os_kill_process(int64_t id) {
    HANDLE handle = OpenProcess(PROCESS_TERMINATE, FALSE, (DWORD)id);
    int32_t killed;
    if (!handle) {
        return 0;
    }
    killed = TerminateProcess(handle, 1) != 0;
    CloseHandle(handle);
    return killed;
}
