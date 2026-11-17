#ifndef VAMP_RUNTIME_H
#define VAMP_RUNTIME_H

#include <stddef.h>
#include <stdint.h>

typedef struct VampList {
    int32_t length;
    int32_t capacity;
    int32_t element_size;
    int32_t reserved;
    char *data;
} VampList;

typedef struct VampMapEntry {
    uint64_t hash;
    int64_t integer_key;
    char *string_key;
    int32_t used;
} VampMapEntry;

typedef struct VampMap {
    int32_t length;
    int32_t entry_count;
    int32_t entry_capacity;
    int32_t value_size;
    int32_t string_keys;
    int32_t bucket_count;
    int32_t *buckets;
    VampMapEntry *entries;
    char *values;
} VampMap;

void vamp_start(void);
void *vamp_gc_alloc(size_t size);
void *vamp_gc_alloc_atomic(size_t size);
void *vamp_gc_realloc(void *pointer, size_t size);
void vamp_free(void *pointer);
void vamp_gc_register_thread(void);
void vamp_gc_unregister_thread(void);
void vamp_gc_add_root(void *address, size_t size);
void vamp_gc_remove_root(void *address);

void vamp_throw(const char *message);
void vamp_throw_format(const char *format, ...);

char *vamp_string_copy(const char *text);
char *vamp_string_copy_length(const char *text, size_t length);

VampList *vamp_list_new(int32_t element_size, int32_t capacity);
char *vamp_list_push_slot(VampList *list);

#endif
