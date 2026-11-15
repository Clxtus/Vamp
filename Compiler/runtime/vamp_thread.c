#include "vamp_runtime.h"

#include <stdlib.h>

#define WIN32_LEAN_AND_MEAN
#include <windows.h>

#define VAMP_MAX_THREADS 1024
#define VAMP_MAX_LOCKS 1024

typedef struct {
    void (*entry)(int32_t);
    int32_t argument;
} VampThreadStart;

static HANDLE vamp_threads[VAMP_MAX_THREADS];
static CRITICAL_SECTION *vamp_locks[VAMP_MAX_LOCKS];
static volatile LONG vamp_table_guard = 0;

static void vamp_table_enter(void) {
    while (InterlockedCompareExchange(&vamp_table_guard, 1, 0) != 0) {
        Sleep(0);
    }
}

static void vamp_table_leave(void) {
    InterlockedExchange(&vamp_table_guard, 0);
}

static DWORD WINAPI vamp_thread_main(LPVOID parameter) {
    VampThreadStart start = *(VampThreadStart *)parameter;
    free(parameter);
    start.entry(start.argument);
    return 0;
}

int32_t vamp_thread_start(void *entry, int32_t argument) {
    VampThreadStart *start = (VampThreadStart *)malloc(sizeof(VampThreadStart));
    HANDLE handle;
    int32_t slot = -1;
    if (!start) {
        vamp_throw("out of memory while starting a thread");
    }
    start->entry = (void (*)(int32_t))entry;
    start->argument = argument;
    vamp_table_enter();
    for (int32_t index = 0; index < VAMP_MAX_THREADS; index++) {
        if (vamp_threads[index] == NULL) {
            slot = index;
            vamp_threads[index] = INVALID_HANDLE_VALUE;
            break;
        }
    }
    vamp_table_leave();
    if (slot < 0) {
        free(start);
        vamp_throw("too many threads are alive at once; join finished threads to free their numbers");
    }
    handle = CreateThread(NULL, 0, vamp_thread_main, start, 0, NULL);
    if (!handle) {
        vamp_table_enter();
        vamp_threads[slot] = NULL;
        vamp_table_leave();
        free(start);
        vamp_throw("Windows could not start a new thread");
    }
    vamp_table_enter();
    vamp_threads[slot] = handle;
    vamp_table_leave();
    return slot + 1;
}

static HANDLE vamp_thread_handle(int32_t thread) {
    HANDLE handle = NULL;
    if (thread >= 1 && thread <= VAMP_MAX_THREADS) {
        vamp_table_enter();
        handle = vamp_threads[thread - 1];
        vamp_table_leave();
    }
    return handle == INVALID_HANDLE_VALUE ? NULL : handle;
}

int32_t vamp_thread_join(int32_t thread) {
    HANDLE handle = vamp_thread_handle(thread);
    if (!handle) {
        return 0;
    }
    WaitForSingleObject(handle, INFINITE);
    vamp_table_enter();
    if (vamp_threads[thread - 1] == handle) {
        vamp_threads[thread - 1] = NULL;
        CloseHandle(handle);
    }
    vamp_table_leave();
    return 1;
}

int32_t vamp_thread_running(int32_t thread) {
    HANDLE handle = vamp_thread_handle(thread);
    return handle != NULL && WaitForSingleObject(handle, 0) == WAIT_TIMEOUT;
}

void vamp_thread_sleep(int32_t milliseconds) {
    Sleep(milliseconds < 0 ? 0 : (DWORD)milliseconds);
}

int32_t vamp_thread_current_id(void) {
    return (int32_t)GetCurrentThreadId();
}

int32_t vamp_thread_make_lock(void) {
    CRITICAL_SECTION *section = (CRITICAL_SECTION *)malloc(sizeof(CRITICAL_SECTION));
    int32_t slot = -1;
    if (!section) {
        vamp_throw("out of memory while creating a lock");
    }
    InitializeCriticalSection(section);
    vamp_table_enter();
    for (int32_t index = 0; index < VAMP_MAX_LOCKS; index++) {
        if (vamp_locks[index] == NULL) {
            vamp_locks[index] = section;
            slot = index;
            break;
        }
    }
    vamp_table_leave();
    if (slot < 0) {
        DeleteCriticalSection(section);
        free(section);
        vamp_throw("too many locks");
    }
    return slot + 1;
}

static CRITICAL_SECTION *vamp_lock_find(int32_t lock) {
    CRITICAL_SECTION *section = NULL;
    if (lock >= 1 && lock <= VAMP_MAX_LOCKS) {
        section = vamp_locks[lock - 1];
    }
    if (!section) {
        vamp_throw_format("%d is not a lock made by thread.Make_Lock", lock);
    }
    return section;
}

void vamp_thread_lock(int32_t lock) {
    EnterCriticalSection(vamp_lock_find(lock));
}

void vamp_thread_unlock(int32_t lock) {
    LeaveCriticalSection(vamp_lock_find(lock));
}
