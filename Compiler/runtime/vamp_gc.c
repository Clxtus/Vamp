#include "vamp_runtime.h"

#include <setjmp.h>
#include <string.h>

#define WIN32_LEAN_AND_MEAN
#include <windows.h>

#define VAMP_PAGE_SIZE ((size_t)64 * 1024)
#define VAMP_PAGE_MASK (~(uintptr_t)(VAMP_PAGE_SIZE - 1))
#define VAMP_LARGE_LIMIT 8192
#define VAMP_LARGE_CACHE_LIMIT ((size_t)64 * 1024 * 1024)
#define VAMP_CLASS_COUNT 18
#define VAMP_MAX_THREADS 1024
#define VAMP_MAX_ROOTS 256

static const uint32_t vamp_size_classes[VAMP_CLASS_COUNT] = {
    16, 32, 48, 64, 96, 128, 192, 256, 384, 512, 768, 1024, 1536, 2048, 3072, 4096, 6144, 8192,
};

typedef struct VampPage {
    struct VampPage *next;
    char *first;
    size_t large_size;
    size_t chunks;
    uint32_t object_size;
    uint32_t object_count;
    uint32_t class_index;
    uint32_t live;
    uint8_t *used;
    uint8_t *marks;
} VampPage;

typedef struct {
    DWORD id;
    HANDLE handle;
    char *stack_high;
} VampThread;

typedef struct {
    char *start;
    size_t size;
} VampRoot;

static SRWLOCK vamp_gc_lock = SRWLOCK_INIT;
static VampPage *vamp_pages;
static void *vamp_free_lists[VAMP_CLASS_COUNT];
static VampPage **vamp_table;
static size_t vamp_table_capacity;
static size_t vamp_table_count;
static uintptr_t vamp_heap_low = UINTPTR_MAX;
static uintptr_t vamp_heap_high;
static size_t vamp_allocated_since_collect;
static size_t vamp_threshold = (size_t)16 * 1024 * 1024;
static size_t vamp_live_bytes;
static VampThread vamp_threads[VAMP_MAX_THREADS];
static int vamp_thread_count;
static VampRoot vamp_roots[VAMP_MAX_ROOTS];
static int vamp_root_count;
static __declspec(thread) int vamp_thread_registered;
static VampPage *vamp_large_cache;
static size_t vamp_large_cached_bytes;
static uintptr_t *vamp_mark_stack;
static size_t vamp_mark_capacity;
static size_t vamp_mark_count;

static void vamp_gc_fail(const char *message) {
    HANDLE error = GetStdHandle(STD_ERROR_HANDLE);
    DWORD written;
    WriteFile(error, message, (DWORD)strlen(message), &written, NULL);
    ExitProcess(1);
}

static void *vamp_reserve(size_t size) {
    void *memory = VirtualAlloc(NULL, size, MEM_RESERVE | MEM_COMMIT, PAGE_READWRITE);
    if (!memory) {
        vamp_gc_fail("Error: out of memory\n");
    }
    return memory;
}

static size_t vamp_hash(uintptr_t chunk) {
    uint64_t value = (uint64_t)(chunk >> 16) * 0x9e3779b97f4a7c15ULL;
    return (size_t)(value >> 20);
}

static void vamp_table_put(uintptr_t chunk, VampPage *page);

static void vamp_table_grow(void) {
    VampPage **old = vamp_table;
    size_t old_capacity = vamp_table_capacity;
    vamp_table_capacity = old_capacity ? old_capacity * 2 : 1024;
    vamp_table = (VampPage **)vamp_reserve(vamp_table_capacity * 2 * sizeof(VampPage *));
    vamp_table_count = 0;
    for (size_t index = 0; index < old_capacity; index++) {
        uintptr_t key = (uintptr_t)old[index * 2];
        if (key > 1) {
            vamp_table_put(key, old[index * 2 + 1]);
        }
    }
    if (old) {
        VirtualFree(old, 0, MEM_RELEASE);
    }
}

/* Slots hold (chunk address, page); a key of 1 marks a removed entry. */
static void vamp_table_put(uintptr_t chunk, VampPage *page) {
    size_t mask;
    size_t position;
    if ((vamp_table_count + 1) * 2 > vamp_table_capacity) {
        vamp_table_grow();
    }
    mask = vamp_table_capacity - 1;
    position = vamp_hash(chunk) & mask;
    while ((uintptr_t)vamp_table[position * 2] > 1) {
        position = (position + 1) & mask;
    }
    vamp_table[position * 2] = (VampPage *)chunk;
    vamp_table[position * 2 + 1] = page;
    vamp_table_count++;
}

static VampPage *vamp_table_get(uintptr_t chunk) {
    size_t mask;
    size_t position;
    if (!vamp_table_capacity) {
        return NULL;
    }
    mask = vamp_table_capacity - 1;
    position = vamp_hash(chunk) & mask;
    for (;;) {
        uintptr_t key = (uintptr_t)vamp_table[position * 2];
        if (key == chunk) {
            return vamp_table[position * 2 + 1];
        }
        if (key == 0) {
            return NULL;
        }
        position = (position + 1) & mask;
    }
}

static void vamp_table_remove(uintptr_t chunk) {
    size_t mask = vamp_table_capacity - 1;
    size_t position = vamp_hash(chunk) & mask;
    for (;;) {
        uintptr_t key = (uintptr_t)vamp_table[position * 2];
        if (key == chunk) {
            vamp_table[position * 2] = (VampPage *)1;
            vamp_table[position * 2 + 1] = NULL;
            return;
        }
        if (key == 0) {
            return;
        }
        position = (position + 1) & mask;
    }
}

static void vamp_note_range(uintptr_t low, uintptr_t high) {
    if (low < vamp_heap_low) {
        vamp_heap_low = low;
    }
    if (high > vamp_heap_high) {
        vamp_heap_high = high;
    }
}

static uintptr_t vamp_align(uintptr_t value) {
    return (value + 15) & ~(uintptr_t)15;
}

static VampPage *vamp_new_page(int class_index) {
    char *memory = (char *)vamp_reserve(VAMP_PAGE_SIZE);
    VampPage *page = (VampPage *)memory;
    uint32_t size = vamp_size_classes[class_index];
    uint32_t count = (uint32_t)((VAMP_PAGE_SIZE - sizeof(VampPage) - 16) / (size + 2));
    page->object_size = size;
    page->class_index = (uint32_t)class_index;
    page->used = (uint8_t *)(memory + sizeof(VampPage));
    page->marks = page->used + count;
    page->first = (char *)vamp_align((uintptr_t)(page->marks + count));
    while (page->first + (size_t)count * size > memory + VAMP_PAGE_SIZE) {
        count--;
    }
    page->object_count = count;
    page->next = vamp_pages;
    vamp_pages = page;
    vamp_table_put((uintptr_t)memory, page);
    vamp_note_range((uintptr_t)memory, (uintptr_t)memory + VAMP_PAGE_SIZE);
    for (uint32_t index = count; index-- > 0;) {
        void **object = (void **)(page->first + (size_t)index * size);
        *object = vamp_free_lists[class_index];
        vamp_free_lists[class_index] = object;
    }
    return page;
}

/* big allocs get their own pages. freed ones go in a small cache (64MB max)
   so s = s + x loops don't keep calling VirtualAlloc */
static void *vamp_new_large(size_t size, int atomic) {
    size_t header = vamp_align(sizeof(VampPage) + 2);
    size_t total = (header + size + VAMP_PAGE_SIZE - 1) & ~(VAMP_PAGE_SIZE - 1);
    char *memory;
    VampPage *page;
    for (VampPage **link = &vamp_large_cache; *link; link = &(*link)->next) {
        VampPage *cached = *link;
        size_t chunks = total / VAMP_PAGE_SIZE;
        if (cached->chunks >= chunks && cached->chunks <= chunks * 2) {
            *link = cached->next;
            vamp_large_cached_bytes -= cached->chunks * VAMP_PAGE_SIZE;
            cached->used[0] = atomic ? 2 : 1;
            cached->marks[0] = 0;
            cached->large_size = size;
            cached->next = vamp_pages;
            vamp_pages = cached;
            if (!atomic) {
                memset(cached->first, 0, size);
            }
            return cached->first;
        }
    }
    memory = (char *)vamp_reserve(total);
    page = (VampPage *)memory;
    page->object_size = 0;
    page->object_count = 1;
    page->used = (uint8_t *)(memory + sizeof(VampPage));
    page->marks = page->used + 1;
    page->used[0] = atomic ? 2 : 1;
    page->first = memory + header;
    page->large_size = size;
    page->chunks = total / VAMP_PAGE_SIZE;
    page->next = vamp_pages;
    vamp_pages = page;
    for (size_t chunk = 0; chunk < page->chunks; chunk++) {
        vamp_table_put((uintptr_t)memory + chunk * VAMP_PAGE_SIZE, page);
    }
    vamp_note_range((uintptr_t)memory, (uintptr_t)memory + total);
    return page->first;
}

static int vamp_find(uintptr_t address, VampPage **found_page, uint32_t *found_index) {
    VampPage *page;
    if (address < vamp_heap_low || address >= vamp_heap_high) {
        return 0;
    }
    page = vamp_table_get(address & VAMP_PAGE_MASK);
    if (!page || address < (uintptr_t)page->first) {
        return 0;
    }
    if (page->object_size == 0) {
        if (address >= (uintptr_t)page->first + page->large_size) {
            return 0;
        }
        *found_page = page;
        *found_index = 0;
        return page->used[0];
    }
    {
        uint32_t index = (uint32_t)((address - (uintptr_t)page->first) / page->object_size);
        if (index >= page->object_count || !page->used[index]) {
            return 0;
        }
        *found_page = page;
        *found_index = index;
        return 1;
    }
}

static size_t vamp_object_size(VampPage *page) {
    return page->object_size ? page->object_size : page->large_size;
}

static char *vamp_object_start(VampPage *page, uint32_t index) {
    return page->first + (size_t)index * page->object_size;
}

static void vamp_push_mark(uintptr_t object, size_t size) {
    if (vamp_mark_count + 2 > vamp_mark_capacity) {
        size_t capacity = vamp_mark_capacity ? vamp_mark_capacity * 2 : 65536;
        uintptr_t *grown = (uintptr_t *)vamp_reserve(capacity * sizeof(uintptr_t));
        if (vamp_mark_stack) {
            memcpy(grown, vamp_mark_stack, vamp_mark_count * sizeof(uintptr_t));
            VirtualFree(vamp_mark_stack, 0, MEM_RELEASE);
        }
        vamp_mark_stack = grown;
        vamp_mark_capacity = capacity;
    }
    vamp_mark_stack[vamp_mark_count++] = object;
    vamp_mark_stack[vamp_mark_count++] = size;
}

/* conservative: anything that looks like a heap ptr keeps its obj alive.
   atomic objs (used == 2) aren't scanned inside */
static void vamp_mark_word(uintptr_t value) {
    VampPage *page;
    uint32_t index;
    if (vamp_find(value, &page, &index) && !page->marks[index]) {
        page->marks[index] = 1;
        if (page->used[index] != 2) {
            vamp_push_mark((uintptr_t)vamp_object_start(page, index), vamp_object_size(page));
        }
    }
}

static void vamp_mark_range(const char *start, const char *end) {
    const char *cursor = (const char *)(((uintptr_t)start + 7) & ~(uintptr_t)7);
    for (; cursor + sizeof(uintptr_t) <= end; cursor += sizeof(uintptr_t)) {
        vamp_mark_word(*(const uintptr_t *)cursor);
    }
}

static void vamp_drain(void) {
    while (vamp_mark_count) {
        size_t size = vamp_mark_stack[--vamp_mark_count];
        const char *object = (const char *)vamp_mark_stack[--vamp_mark_count];
        vamp_mark_range(object, object + size);
    }
}

static void vamp_mark_globals(void) {
    char *base = (char *)GetModuleHandleA(NULL);
    IMAGE_DOS_HEADER *dos = (IMAGE_DOS_HEADER *)base;
    IMAGE_NT_HEADERS *headers = (IMAGE_NT_HEADERS *)(base + dos->e_lfanew);
    IMAGE_SECTION_HEADER *section = IMAGE_FIRST_SECTION(headers);
    for (WORD index = 0; index < headers->FileHeader.NumberOfSections; index++, section++) {
        if (section->Characteristics & IMAGE_SCN_MEM_WRITE) {
            char *start = base + section->VirtualAddress;
            vamp_mark_range(start, start + section->Misc.VirtualSize);
        }
    }
}

static void vamp_mark_this_thread(void) {
    jmp_buf registers;
    ULONG_PTR low;
    ULONG_PTR high;
    volatile char here = 0;
    setjmp(registers);
    vamp_mark_range((const char *)&registers, (const char *)&registers + sizeof(registers));
    GetCurrentThreadStackLimits(&low, &high);
    vamp_mark_range((const char *)&here, (const char *)high);
}

static void vamp_mark_other_threads(DWORD self) {
    int write = 0;
    for (int index = 0; index < vamp_thread_count; index++) {
        VampThread *thread = &vamp_threads[index];
        CONTEXT context;
        if (thread->id == self) {
            vamp_threads[write++] = *thread;
            continue;
        }
        if (WaitForSingleObject(thread->handle, 0) == WAIT_OBJECT_0) {
            CloseHandle(thread->handle);
            continue;
        }
        if (SuspendThread(thread->handle) == (DWORD)-1) {
            vamp_threads[write++] = *thread;
            continue;
        }
        memset(&context, 0, sizeof(context));
        context.ContextFlags = CONTEXT_INTEGER | CONTEXT_CONTROL;
        if (GetThreadContext(thread->handle, &context)) {
            vamp_mark_range((const char *)&context, (const char *)&context + sizeof(context));
            vamp_mark_range((const char *)context.Rsp, thread->stack_high);
        }
        vamp_threads[write++] = *thread;
    }
    vamp_thread_count = write;
}

static void vamp_resume_threads(DWORD self) {
    for (int index = 0; index < vamp_thread_count; index++) {
        if (vamp_threads[index].id != self) {
            ResumeThread(vamp_threads[index].handle);
        }
    }
}

static void vamp_sweep(void) {
    VampPage **link = &vamp_pages;
    memset(vamp_free_lists, 0, sizeof(vamp_free_lists));
    vamp_live_bytes = 0;
    while (*link) {
        VampPage *page = *link;
        if (page->object_size == 0) {
            if (!page->marks[0]) {
                *link = page->next;
                page->used[0] = 0;
                if (vamp_large_cached_bytes + page->chunks * VAMP_PAGE_SIZE <= VAMP_LARGE_CACHE_LIMIT) {
                    vamp_large_cached_bytes += page->chunks * VAMP_PAGE_SIZE;
                    page->next = vamp_large_cache;
                    vamp_large_cache = page;
                    continue;
                }
                for (size_t chunk = 0; chunk < page->chunks; chunk++) {
                    vamp_table_remove((uintptr_t)page + chunk * VAMP_PAGE_SIZE);
                }
                VirtualFree(page, 0, MEM_RELEASE);
                continue;
            }
            page->marks[0] = 0;
            vamp_live_bytes += page->large_size;
        } else {
            for (uint32_t index = page->object_count; index-- > 0;) {
                char *object = vamp_object_start(page, index);
                if (page->used[index] && page->marks[index]) {
                    page->marks[index] = 0;
                    vamp_live_bytes += page->object_size;
                    continue;
                }
                page->used[index] = 0;
                *(void **)object = vamp_free_lists[page->class_index];
                vamp_free_lists[page->class_index] = object;
            }
        }
        link = &page->next;
    }
}

static void vamp_collect_locked(void) {
    DWORD self = GetCurrentThreadId();
    vamp_mark_other_threads(self);
    vamp_mark_this_thread();
    vamp_mark_globals();
    for (int index = 0; index < vamp_root_count; index++) {
        vamp_mark_range(vamp_roots[index].start, vamp_roots[index].start + vamp_roots[index].size);
    }
    vamp_drain();
    vamp_sweep();
    vamp_resume_threads(self);
    vamp_allocated_since_collect = 0;
    /* next GC when the heap doubles, min 16MB, so short programs never collect */
    vamp_threshold = vamp_live_bytes * 2 > (size_t)16 * 1024 * 1024 ? vamp_live_bytes * 2 : (size_t)16 * 1024 * 1024;
}

void vamp_gc_register_thread(void) {
    ULONG_PTR low;
    ULONG_PTR high;
    HANDLE handle;
    if (vamp_thread_registered) {
        return;
    }
    GetCurrentThreadStackLimits(&low, &high);
    if (!DuplicateHandle(GetCurrentProcess(), GetCurrentThread(), GetCurrentProcess(), &handle,
                         THREAD_SUSPEND_RESUME | THREAD_GET_CONTEXT | SYNCHRONIZE, FALSE, 0)) {
        return;
    }
    AcquireSRWLockExclusive(&vamp_gc_lock);
    if (vamp_thread_count < VAMP_MAX_THREADS) {
        vamp_threads[vamp_thread_count].id = GetCurrentThreadId();
        vamp_threads[vamp_thread_count].handle = handle;
        vamp_threads[vamp_thread_count].stack_high = (char *)high;
        vamp_thread_count++;
        vamp_thread_registered = 1;
    } else {
        CloseHandle(handle);
    }
    ReleaseSRWLockExclusive(&vamp_gc_lock);
}

void vamp_gc_unregister_thread(void) {
    DWORD self = GetCurrentThreadId();
    if (!vamp_thread_registered) {
        return;
    }
    AcquireSRWLockExclusive(&vamp_gc_lock);
    for (int index = 0; index < vamp_thread_count; index++) {
        if (vamp_threads[index].id == self) {
            CloseHandle(vamp_threads[index].handle);
            vamp_threads[index] = vamp_threads[--vamp_thread_count];
            break;
        }
    }
    vamp_thread_registered = 0;
    ReleaseSRWLockExclusive(&vamp_gc_lock);
}

void vamp_gc_add_root(void *address, size_t size) {
    AcquireSRWLockExclusive(&vamp_gc_lock);
    if (vamp_root_count < VAMP_MAX_ROOTS) {
        vamp_roots[vamp_root_count].start = (char *)address;
        vamp_roots[vamp_root_count].size = size;
        vamp_root_count++;
    }
    ReleaseSRWLockExclusive(&vamp_gc_lock);
}

void vamp_gc_remove_root(void *address) {
    AcquireSRWLockExclusive(&vamp_gc_lock);
    for (int index = 0; index < vamp_root_count; index++) {
        if (vamp_roots[index].start == (char *)address) {
            vamp_roots[index] = vamp_roots[--vamp_root_count];
            break;
        }
    }
    ReleaseSRWLockExclusive(&vamp_gc_lock);
}

/* atomic = no ptrs inside (strings etc): not zeroed, never scanned.
   NB caller has to write every byte incl. the NUL */
static void *vamp_gc_alloc_kind(size_t size, int atomic) {
    void *object;
    if (!vamp_thread_registered) {
        vamp_gc_register_thread();
    }
    if (size == 0) {
        size = 1;
    }
    AcquireSRWLockExclusive(&vamp_gc_lock);
    vamp_allocated_since_collect += size;
    if (vamp_allocated_since_collect > vamp_threshold) {
        vamp_collect_locked();
    }
    if (size > VAMP_LARGE_LIMIT) {
        object = vamp_new_large(size, atomic);
    } else {
        int class_index = 0;
        while (vamp_size_classes[class_index] < size) {
            class_index++;
        }
        if (!vamp_free_lists[class_index]) {
            vamp_new_page(class_index);
        }
        object = vamp_free_lists[class_index];
        vamp_free_lists[class_index] = *(void **)object;
        {
            VampPage *page = vamp_table_get((uintptr_t)object & VAMP_PAGE_MASK);
            page->used[((char *)object - page->first) / page->object_size] = atomic ? 2 : 1;
        }
        if (atomic) {
            *(void **)object = NULL;
        } else {
            memset(object, 0, vamp_size_classes[class_index]);
        }
    }
    ReleaseSRWLockExclusive(&vamp_gc_lock);
    return object;
}

void *vamp_gc_alloc(size_t size) {
    return vamp_gc_alloc_kind(size, 0);
}

void *vamp_gc_alloc_atomic(size_t size) {
    return vamp_gc_alloc_kind(size, 1);
}

static size_t vamp_gc_size_locked(void *pointer) {
    VampPage *page;
    uint32_t index;
    if (!pointer || !vamp_find((uintptr_t)pointer, &page, &index)) {
        return 0;
    }
    return vamp_object_size(page) - (size_t)((char *)pointer - vamp_object_start(page, index));
}

void *vamp_gc_realloc(void *pointer, size_t size) {
    size_t old_size;
    void *grown;
    int atomic = 0;
    VampPage *page;
    uint32_t index;
    AcquireSRWLockShared(&vamp_gc_lock);
    old_size = vamp_gc_size_locked(pointer);
    if (old_size && vamp_find((uintptr_t)pointer, &page, &index)) {
        atomic = page->used[index] == 2;
    }
    ReleaseSRWLockShared(&vamp_gc_lock);
    if (pointer && old_size >= size && size > 0) {
        return pointer;
    }
    grown = vamp_gc_alloc_kind(size, atomic);
    if (pointer && old_size) {
        memcpy(grown, pointer, old_size < size ? old_size : size);
    }
    return grown;
}

void vamp_free(void *pointer) {
    VampPage *page;
    uint32_t index;
    if (!pointer) {
        return;
    }
    AcquireSRWLockExclusive(&vamp_gc_lock);
    if (vamp_find((uintptr_t)pointer, &page, &index) && (char *)pointer == vamp_object_start(page, index)) {
        if (page->object_size == 0) {
            VampPage **link = &vamp_pages;
            while (*link && *link != page) {
                link = &(*link)->next;
            }
            if (*link) {
                *link = page->next;
            }
            for (size_t chunk = 0; chunk < page->chunks; chunk++) {
                vamp_table_remove((uintptr_t)page + chunk * VAMP_PAGE_SIZE);
            }
            VirtualFree(page, 0, MEM_RELEASE);
        } else {
            page->used[index] = 0;
            *(void **)pointer = vamp_free_lists[page->class_index];
            vamp_free_lists[page->class_index] = pointer;
        }
    }
    ReleaseSRWLockExclusive(&vamp_gc_lock);
}

void vamp_gc_collect(void) {
    if (!vamp_thread_registered) {
        vamp_gc_register_thread();
    }
    AcquireSRWLockExclusive(&vamp_gc_lock);
    vamp_collect_locked();
    ReleaseSRWLockExclusive(&vamp_gc_lock);
}

int64_t vamp_gc_used(void) {
    int64_t used = 0;
    AcquireSRWLockShared(&vamp_gc_lock);
    for (VampPage *page = vamp_pages; page; page = page->next) {
        if (page->object_size == 0) {
            used += (int64_t)page->large_size;
        } else {
            for (uint32_t index = 0; index < page->object_count; index++) {
                used += page->used[index] ? page->object_size : 0;
            }
        }
    }
    ReleaseSRWLockShared(&vamp_gc_lock);
    return used;
}
