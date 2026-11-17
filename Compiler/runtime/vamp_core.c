#define _CRT_SECURE_NO_WARNINGS
#include "vamp_runtime.h"

#include <ctype.h>
#include <errno.h>
#include <math.h>
#include <setjmp.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#ifdef _WIN32
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#define VAMP_THREAD_LOCAL __declspec(thread)
#else
#include <sys/stat.h>
#include <unistd.h>
#define VAMP_THREAD_LOCAL _Thread_local
#endif

typedef struct VampTryFrame {
    jmp_buf buffer;
    struct VampTryFrame *previous;
} VampTryFrame;

static VAMP_THREAD_LOCAL VampTryFrame *vamp_try_top = NULL;
static VAMP_THREAD_LOCAL char *vamp_last_error = NULL;

void *vamp_try_push(void) {
    VampTryFrame *frame = (VampTryFrame *)malloc(sizeof(VampTryFrame));
    if (!frame) {
        fprintf(stderr, "Error: out of memory\n");
        exit(1);
    }
    frame->previous = vamp_try_top;
    vamp_try_top = frame;
    return frame->buffer;
}

void vamp_try_pop(void) {
    VampTryFrame *frame = vamp_try_top;
    if (frame) {
        vamp_try_top = frame->previous;
        free(frame);
    }
}

const char *vamp_error_message(void) {
    return vamp_string_copy(vamp_last_error ? vamp_last_error : "");
}

void vamp_keep(void *address) {
    (void)address;
}

/* try/catch = setjmp/longjmp on a per-thread frame stack.
   no frame means uncaught -> print + exit(1) */
void vamp_throw(const char *message) {
    VampTryFrame *frame = vamp_try_top;
    const char *text = message ? message : "";
    size_t length = strlen(text);
    char *copy = (char *)malloc(length + 1);
    if (!copy) {
        fprintf(stderr, "Error: out of memory\n");
        exit(1);
    }
    memcpy(copy, text, length + 1);
    free(vamp_last_error);
    vamp_last_error = copy;
    if (!frame) {
        fflush(stdout);
        fprintf(stderr, "Error: %s\n", copy);
        exit(1);
    }
    {
        jmp_buf target;
        memcpy(target, frame->buffer, sizeof(jmp_buf));
        vamp_try_top = frame->previous;
        free(frame);
        longjmp(target, 1);
    }
}

void vamp_throw_format(const char *format, ...) {
    char buffer[1024];
    va_list arguments;
    va_start(arguments, format);
    vsnprintf(buffer, sizeof(buffer), format, arguments);
    va_end(arguments);
    vamp_throw(buffer);
}

static void *vamp_allocate(size_t size) {
    return vamp_gc_alloc(size);
}

/* NB not zeroed, always terminate the string yourself */
static char *vamp_allocate_text(size_t size) {
    return (char *)vamp_gc_alloc_atomic(size);
}

char *vamp_string_copy_length(const char *text, size_t length) {
    char *copy = vamp_allocate_text(length + 1);
    if (length) {
        memcpy(copy, text, length);
    }
    copy[length] = 0;
    return copy;
}

char *vamp_string_copy(const char *text) {
    return vamp_string_copy_length(text, strlen(text));
}

int32_t vamp_str_length(const char *text) {
    size_t length = strlen(text);
    if (length > INT32_MAX) {
        vamp_throw("the string is longer than 2147483647 bytes");
    }
    return (int32_t)length;
}

int32_t vamp_str_at(const char *text, int32_t index) {
    size_t length = strlen(text);
    if (index < 0 || (size_t)index >= length) {
        vamp_throw_format("string index %d is out of range (length %d)", index, (int)length);
    }
    return (unsigned char)text[index];
}

char *vamp_str_from_char(int32_t character) {
    char buffer[2];
    buffer[0] = (char)character;
    buffer[1] = 0;
    return vamp_string_copy_length(buffer, character ? 1 : 0);
}

char *vamp_str_upper(const char *text) {
    char *copy = vamp_string_copy(text);
    for (char *cursor = copy; *cursor; cursor++) {
        *cursor = (char)toupper((unsigned char)*cursor);
    }
    return copy;
}

char *vamp_str_lower(const char *text) {
    char *copy = vamp_string_copy(text);
    for (char *cursor = copy; *cursor; cursor++) {
        *cursor = (char)tolower((unsigned char)*cursor);
    }
    return copy;
}

char *vamp_str_trim(const char *text) {
    const char *start = text;
    const char *end = text + strlen(text);
    while (*start && isspace((unsigned char)*start)) {
        start++;
    }
    while (end > start && isspace((unsigned char)end[-1])) {
        end--;
    }
    return vamp_string_copy_length(start, (size_t)(end - start));
}

int32_t vamp_str_find(const char *text, const char *part) {
    const char *found = strstr(text, part);
    return found ? (int32_t)(found - text) : -1;
}

int32_t vamp_str_contains(const char *text, const char *part) {
    return strstr(text, part) != NULL;
}

int32_t vamp_str_starts_with(const char *text, const char *prefix) {
    return strncmp(text, prefix, strlen(prefix)) == 0;
}

int32_t vamp_str_ends_with(const char *text, const char *suffix) {
    size_t length = strlen(text);
    size_t suffix_length = strlen(suffix);
    return suffix_length <= length && memcmp(text + length - suffix_length, suffix, suffix_length) == 0;
}

char *vamp_str_substring(const char *text, int32_t start, int32_t count) {
    int32_t length = (int32_t)strlen(text);
    if (start < 0 || start > length) {
        vamp_throw_format("substring start %d is out of range (length %d)", start, length);
    }
    if (count < 0 || count > length - start) {
        count = length - start;
    }
    return vamp_string_copy_length(text + start, (size_t)count);
}

char *vamp_str_replace(const char *text, const char *from, const char *to) {
    size_t from_length = strlen(from);
    size_t to_length = strlen(to);
    size_t count = 0;
    const char *cursor;
    char *result;
    char *output;
    if (from_length == 0) {
        return vamp_string_copy(text);
    }
    for (cursor = strstr(text, from); cursor; cursor = strstr(cursor + from_length, from)) {
        count++;
    }
    result = vamp_allocate_text(strlen(text) + count * to_length - count * from_length + 1);
    output = result;
    cursor = text;
    for (;;) {
        const char *found = strstr(cursor, from);
        if (!found) {
            strcpy(output, cursor);
            break;
        }
        memcpy(output, cursor, (size_t)(found - cursor));
        output += found - cursor;
        memcpy(output, to, to_length);
        output += to_length;
        cursor = found + from_length;
    }
    return result;
}

char *vamp_str_repeat(const char *text, int32_t count) {
    size_t length = strlen(text);
    char *result;
    if (count < 0) {
        count = 0;
    }
    result = vamp_allocate_text(length * (size_t)count + 1);
    for (int32_t index = 0; index < count; index++) {
        memcpy(result + (size_t)index * length, text, length);
    }
    result[length * (size_t)count] = 0;
    return result;
}

char *vamp_str_reverse(const char *text) {
    size_t length = strlen(text);
    char *result = vamp_allocate_text(length + 1);
    size_t index = 0;
    while (index < length) {
        size_t size = 1;
        while (index + size < length && ((unsigned char)text[index + size] & 0xC0) == 0x80) {
            size++;
        }
        memcpy(result + length - index - size, text + index, size);
        index += size;
    }
    result[length] = 0;
    return result;
}

VampList *vamp_str_split(const char *text, const char *separator) {
    VampList *parts = vamp_list_new((int32_t)sizeof(char *), 4);
    size_t separator_length = strlen(separator);
    const char *cursor = text;
    if (separator_length == 0) {
        for (; *cursor; cursor++) {
            *(char **)vamp_list_push_slot(parts) = vamp_string_copy_length(cursor, 1);
        }
        return parts;
    }
    for (;;) {
        const char *found = strstr(cursor, separator);
        if (!found) {
            *(char **)vamp_list_push_slot(parts) = vamp_string_copy(cursor);
            break;
        }
        *(char **)vamp_list_push_slot(parts) = vamp_string_copy_length(cursor, (size_t)(found - cursor));
        cursor = found + separator_length;
    }
    return parts;
}

char *vamp_str_join(VampList *parts, const char *separator) {
    size_t separator_length = strlen(separator);
    size_t total = 1;
    char *result;
    char *output;
    for (int32_t index = 0; index < parts->length; index++) {
        total += strlen(((char **)parts->data)[index]) + (index ? separator_length : 0);
    }
    result = vamp_allocate_text(total);
    output = result;
    for (int32_t index = 0; index < parts->length; index++) {
        const char *part = ((char **)parts->data)[index];
        size_t length = strlen(part);
        if (index) {
            memcpy(output, separator, separator_length);
            output += separator_length;
        }
        memcpy(output, part, length);
        output += length;
    }
    *output = 0;
    return result;
}

static const char *vamp_number_end(const char *end) {
    while (*end && isspace((unsigned char)*end)) {
        end++;
    }
    return end;
}

/* strict on purpose, int("abc") used to silently give 0 */
int64_t vamp_str_to_i64(const char *text) {
    char *end = NULL;
    long long value;
    errno = 0;
    value = strtoll(text, &end, 10);
    if (end == text || *vamp_number_end(end)) {
        vamp_throw_format("cannot convert \"%.60s\" to int", text);
    }
    if (errno == ERANGE) {
        vamp_throw_format("\"%.60s\" is too large for int", text);
    }
    return value;
}

double vamp_str_to_f64(const char *text) {
    char *end = NULL;
    double value = strtod(text, &end);
    if (end == text || *vamp_number_end(end)) {
        vamp_throw_format("cannot convert \"%.60s\" to float", text);
    }
    return value;
}

int32_t vamp_str_is_number(const char *text) {
    char *end = NULL;
    while (*text && isspace((unsigned char)*text)) {
        text++;
    }
    if (!*text) {
        return 0;
    }
    strtod(text, &end);
    while (*end && isspace((unsigned char)*end)) {
        end++;
    }
    return *end == 0;
}

char *vamp_str_format_double(double value) {
    char buffer[64];
    snprintf(buffer, sizeof(buffer), "%f", value);
    return vamp_string_copy(buffer);
}

VampList *vamp_list_new(int32_t element_size, int32_t capacity) {
    VampList *list = (VampList *)vamp_allocate(sizeof(VampList));
    if (capacity < 4) {
        capacity = 4;
    }
    list->length = 0;
    list->capacity = capacity;
    list->element_size = element_size;
    list->reserved = 0;
    list->data = (char *)vamp_allocate((size_t)capacity * (size_t)element_size);
    return list;
}

/* int64 math on purpose: capacity * 2 overflowed int32 past ~1B items */
static void vamp_list_reserve(VampList *list, int64_t needed) {
    if (needed > list->capacity) {
        int64_t capacity = (int64_t)list->capacity * 2;
        char *data;
        if (needed > INT32_MAX) {
            vamp_throw("a list cannot hold more than 2147483647 values");
        }
        if (capacity > INT32_MAX) {
            capacity = INT32_MAX;
        }
        if (capacity < needed) {
            capacity = needed;
        }
        data = (char *)vamp_gc_realloc(list->data, (size_t)capacity * (size_t)list->element_size);
        list->data = data;
        list->capacity = (int32_t)capacity;
    }
}

char *vamp_list_push_slot(VampList *list) {
    vamp_list_reserve(list, (int64_t)list->length + 1);
    list->length++;
    return list->data + (size_t)(list->length - 1) * (size_t)list->element_size;
}

char *vamp_list_resize(VampList *list, int32_t length) {
    vamp_list_reserve(list, length);
    list->length = length;
    return list->data;
}

char *vamp_list_pop_slot(VampList *list) {
    if (list->length == 0) {
        vamp_throw("cannot pop from an empty list");
    }
    list->length--;
    return list->data + (size_t)list->length * (size_t)list->element_size;
}

char *vamp_list_insert_slot(VampList *list, int32_t index) {
    size_t size = (size_t)list->element_size;
    if (index < 0 || index > list->length) {
        vamp_throw_format("list insert index %d is out of range (length %d)", index, list->length);
    }
    vamp_list_reserve(list, list->length + 1);
    memmove(list->data + (size_t)(index + 1) * size, list->data + (size_t)index * size,
            (size_t)(list->length - index) * size);
    list->length++;
    return list->data + (size_t)index * size;
}

void vamp_list_remove(VampList *list, int32_t index) {
    size_t size = (size_t)list->element_size;
    if (index < 0 || index >= list->length) {
        vamp_throw_format("list index %d is out of range (length %d)", index, list->length);
    }
    memmove(list->data + (size_t)index * size, list->data + (size_t)(index + 1) * size,
            (size_t)(list->length - index - 1) * size);
    list->length--;
}

void vamp_list_clear(VampList *list) {
    list->length = 0;
}

void vamp_list_index_error(int32_t index, int32_t length) {
    vamp_throw_format("list index %d is out of range (length %d)", index, length);
}

int32_t vamp_list_index_of(VampList *list, const char *value) {
    size_t size = (size_t)list->element_size;
    for (int32_t index = 0; index < list->length; index++) {
        if (memcmp(list->data + (size_t)index * size, value, size) == 0) {
            return index;
        }
    }
    return -1;
}

int32_t vamp_list_index_of_str(VampList *list, const char *value) {
    for (int32_t index = 0; index < list->length; index++) {
        if (strcmp(((char **)list->data)[index], value) == 0) {
            return index;
        }
    }
    return -1;
}

void vamp_list_reverse(VampList *list) {
    size_t size = (size_t)list->element_size;
    char *scratch = (char *)vamp_allocate(size);
    for (int32_t low = 0, high = list->length - 1; low < high; low++, high--) {
        memcpy(scratch, list->data + (size_t)low * size, size);
        memcpy(list->data + (size_t)low * size, list->data + (size_t)high * size, size);
        memcpy(list->data + (size_t)high * size, scratch, size);
    }
    vamp_free(scratch);
}

VampList *vamp_list_copy(VampList *list) {
    VampList *copy = vamp_list_new(list->element_size, list->length);
    memcpy(copy->data, list->data, (size_t)list->length * (size_t)list->element_size);
    copy->length = list->length;
    return copy;
}

void vamp_list_free(VampList *list) {
    if (list) {
        vamp_free(list->data);
        vamp_free(list);
    }
}

#define VAMP_COMPARE(name, type)                                   \
    static int name(const void *left, const void *right) {          \
        type a = *(const type *)left;                               \
        type b = *(const type *)right;                              \
        return (a > b) - (a < b);                                   \
    }
VAMP_COMPARE(vamp_compare_i8, int8_t)
VAMP_COMPARE(vamp_compare_i16, int16_t)
VAMP_COMPARE(vamp_compare_i32, int32_t)
VAMP_COMPARE(vamp_compare_i64, int64_t)
VAMP_COMPARE(vamp_compare_u8, uint8_t)
VAMP_COMPARE(vamp_compare_u16, uint16_t)
VAMP_COMPARE(vamp_compare_u32, uint32_t)
VAMP_COMPARE(vamp_compare_u64, uint64_t)
VAMP_COMPARE(vamp_compare_float, float)
VAMP_COMPARE(vamp_compare_double, double)

static int vamp_compare_str(const void *left, const void *right) {
    return strcmp(*(char *const *)left, *(char *const *)right);
}

void vamp_list_sort(VampList *list, int32_t kind) {
    static int (*const comparators[])(const void *, const void *) = {
        vamp_compare_i8, vamp_compare_i16, vamp_compare_i32, vamp_compare_i64,
        vamp_compare_u8, vamp_compare_u16, vamp_compare_u32, vamp_compare_u64,
        vamp_compare_float, vamp_compare_double, vamp_compare_str,
    };
    qsort(list->data, (size_t)list->length, (size_t)list->element_size, comparators[kind]);
}

static uint64_t vamp_hash_string(const char *text) {
    uint64_t hash = 1469598103934665603ULL;
    for (; *text; text++) {
        hash ^= (unsigned char)*text;
        hash *= 1099511628211ULL;
    }
    return hash;
}

static uint64_t vamp_hash_integer(int64_t key) {
    uint64_t value = (uint64_t)key;
    value ^= value >> 33;
    value *= 0xff51afd7ed558ccdULL;
    value ^= value >> 33;
    value *= 0xc4ceb9fe1a85ec53ULL;
    value ^= value >> 33;
    return value;
}

VampMap *vamp_map_new(int32_t string_keys, int32_t value_size) {
    VampMap *map = (VampMap *)vamp_allocate(sizeof(VampMap));
    map->length = 0;
    map->entry_count = 0;
    map->entry_capacity = 8;
    map->value_size = value_size;
    map->string_keys = string_keys;
    map->bucket_count = 16;
    map->buckets = (int32_t *)vamp_gc_alloc((size_t)map->bucket_count * sizeof(int32_t));
    map->entries = (VampMapEntry *)vamp_allocate(sizeof(VampMapEntry) * (size_t)map->entry_capacity);
    map->values = (char *)vamp_allocate((size_t)value_size * (size_t)map->entry_capacity);
    return map;
}

static int vamp_map_key_equal(const VampMap *map, const VampMapEntry *entry, uint64_t hash,
                              const char *string_key, int64_t integer_key) {
    if (entry->hash != hash) {
        return 0;
    }
    return map->string_keys ? strcmp(entry->string_key, string_key) == 0 : entry->integer_key == integer_key;
}

static int32_t vamp_map_lookup(const VampMap *map, uint64_t hash, const char *string_key, int64_t integer_key) {
    uint32_t mask = (uint32_t)map->bucket_count - 1;
    uint32_t position = (uint32_t)hash & mask;
    for (;;) {
        int32_t slot = map->buckets[position];
        if (slot == 0) {
            return -1;
        }
        if (slot > 0 && vamp_map_key_equal(map, &map->entries[slot - 1], hash, string_key, integer_key)) {
            return slot - 1;
        }
        position = (position + 1) & mask;
    }
}

static void vamp_map_rebuild(VampMap *map, int32_t bucket_count) {
    int32_t write = 0;
    uint32_t mask;
    vamp_free(map->buckets);
    map->buckets = (int32_t *)vamp_gc_alloc_atomic((size_t)bucket_count * sizeof(int32_t));
    memset(map->buckets, 0, (size_t)bucket_count * sizeof(int32_t));
    map->bucket_count = bucket_count;
    mask = (uint32_t)bucket_count - 1;
    for (int32_t read = 0; read < map->entry_count; read++) {
        if (!map->entries[read].used) {
            continue;
        }
        if (write != read) {
            map->entries[write] = map->entries[read];
            memcpy(map->values + (size_t)write * (size_t)map->value_size,
                   map->values + (size_t)read * (size_t)map->value_size, (size_t)map->value_size);
        }
        {
            uint32_t position = (uint32_t)map->entries[write].hash & mask;
            while (map->buckets[position] != 0) {
                position = (position + 1) & mask;
            }
            map->buckets[position] = write + 1;
        }
        write++;
    }
    map->entry_count = write;
}

static char *vamp_map_slot(VampMap *map, uint64_t hash, const char *string_key, int64_t integer_key,
                           int32_t create) {
    int32_t found = vamp_map_lookup(map, hash, string_key, integer_key);
    VampMapEntry *entry;
    uint32_t mask;
    uint32_t position;
    if (found >= 0) {
        return map->values + (size_t)found * (size_t)map->value_size;
    }
    if (!create) {
        return NULL;
    }
    if ((map->entry_count + 1) * 2 > map->bucket_count) {
        vamp_map_rebuild(map, map->length * 4 >= map->bucket_count ? map->bucket_count * 2 : map->bucket_count);
    }
    if (map->entry_count == map->entry_capacity) {
        int32_t capacity;
        if (map->entry_capacity >= 0x20000000) {
            vamp_throw("a map or set cannot hold more than 536870912 entries");
        }
        capacity = map->entry_capacity * 2;
        VampMapEntry *entries = (VampMapEntry *)vamp_gc_realloc(map->entries, sizeof(VampMapEntry) * (size_t)capacity);
        char *values = (char *)vamp_gc_realloc(map->values, (size_t)map->value_size * (size_t)capacity);
        map->entries = entries;
        map->values = values;
        map->entry_capacity = capacity;
    }
    entry = &map->entries[map->entry_count];
    entry->hash = hash;
    entry->integer_key = integer_key;
    entry->string_key = map->string_keys ? vamp_string_copy(string_key) : NULL;
    entry->used = 1;
    mask = (uint32_t)map->bucket_count - 1;
    position = (uint32_t)hash & mask;
    while (map->buckets[position] > 0) {
        position = (position + 1) & mask;
    }
    map->buckets[position] = map->entry_count + 1;
    memset(map->values + (size_t)map->entry_count * (size_t)map->value_size, 0, (size_t)map->value_size);
    map->entry_count++;
    map->length++;
    return map->values + (size_t)(map->entry_count - 1) * (size_t)map->value_size;
}

char *vamp_map_slot_s(VampMap *map, const char *key, int32_t create) {
    return vamp_map_slot(map, vamp_hash_string(key), key, 0, create);
}

char *vamp_map_slot_i(VampMap *map, int64_t key, int32_t create) {
    return vamp_map_slot(map, vamp_hash_integer(key), NULL, key, create);
}

void vamp_map_key_error_s(const char *key) {
    vamp_throw_format("map has no key \"%s\"", key);
}

void vamp_map_key_error_i(int64_t key) {
    vamp_throw_format("map has no key %lld", (long long)key);
}

static int32_t vamp_map_remove(VampMap *map, uint64_t hash, const char *string_key, int64_t integer_key) {
    uint32_t mask = (uint32_t)map->bucket_count - 1;
    uint32_t position = (uint32_t)hash & mask;
    for (;;) {
        int32_t slot = map->buckets[position];
        if (slot == 0) {
            return 0;
        }
        if (slot > 0 && vamp_map_key_equal(map, &map->entries[slot - 1], hash, string_key, integer_key)) {
            map->buckets[position] = -1;
            map->entries[slot - 1].used = 0;
            vamp_free(map->entries[slot - 1].string_key);
            map->entries[slot - 1].string_key = NULL;
            map->length--;
            return 1;
        }
        position = (position + 1) & mask;
    }
}

int32_t vamp_map_remove_s(VampMap *map, const char *key) {
    return vamp_map_remove(map, vamp_hash_string(key), key, 0);
}

int32_t vamp_map_remove_i(VampMap *map, int64_t key) {
    return vamp_map_remove(map, vamp_hash_integer(key), NULL, key);
}

int32_t vamp_map_length(VampMap *map) {
    return map->length;
}

void vamp_map_clear(VampMap *map) {
    for (int32_t index = 0; index < map->entry_count; index++) {
        vamp_free(map->entries[index].string_key);
        map->entries[index].string_key = NULL;
    }
    memset(map->buckets, 0, sizeof(int32_t) * (size_t)map->bucket_count);
    map->entry_count = 0;
    map->length = 0;
}

int32_t vamp_map_next(VampMap *map, int32_t cursor) {
    for (; cursor < map->entry_count; cursor++) {
        if (map->entries[cursor].used) {
            return cursor;
        }
    }
    return -1;
}

const char *vamp_map_key_at_s(VampMap *map, int32_t index) {
    return map->entries[index].string_key;
}

int64_t vamp_map_key_at_i(VampMap *map, int32_t index) {
    return map->entries[index].integer_key;
}

char *vamp_map_value_at(VampMap *map, int32_t index) {
    return map->values + (size_t)index * (size_t)map->value_size;
}

void vamp_map_free(VampMap *map) {
    if (map) {
        vamp_map_clear(map);
        vamp_free(map->buckets);
        vamp_free(map->entries);
        vamp_free(map->values);
        vamp_free(map);
    }
}

char *vamp_console_read_line(void) {
    size_t capacity = 128;
    size_t length = 0;
    char *line = vamp_allocate_text(capacity);
    int character;
    fflush(stdout);
    while ((character = getchar()) != EOF && character != '\n') {
        if (length + 1 >= capacity) {
            capacity *= 2;
            line = (char *)vamp_gc_realloc(line, capacity);
            if (!line) {
                vamp_throw("out of memory while reading a line");
            }
        }
        line[length++] = (char)character;
    }
    if (length && line[length - 1] == '\r') {
        length--;
    }
    line[length] = 0;
    return line;
}

int64_t vamp_console_read_int(void) {
    char *line = vamp_console_read_line();
    int64_t value = (int64_t)strtoll(line, NULL, 10);
    vamp_free(line);
    return value;
}

double vamp_console_read_float(void) {
    char *line = vamp_console_read_line();
    double value = strtod(line, NULL);
    vamp_free(line);
    return value;
}

void vamp_console_write(const char *text) {
    fputs(text, stdout);
}

void vamp_console_write_error(const char *text) {
    fputs(text, stderr);
    fputc('\n', stderr);
}

void vamp_console_flush(void) {
    fflush(stdout);
}

void vamp_console_clear(void) {
#ifdef _WIN32
    HANDLE console = GetStdHandle(STD_OUTPUT_HANDLE);
    CONSOLE_SCREEN_BUFFER_INFO information;
    DWORD written;
    COORD origin = {0, 0};
    fflush(stdout);
    if (GetConsoleScreenBufferInfo(console, &information)) {
        DWORD cells = (DWORD)information.dwSize.X * (DWORD)information.dwSize.Y;
        FillConsoleOutputCharacterA(console, ' ', cells, origin, &written);
        FillConsoleOutputAttribute(console, information.wAttributes, cells, origin, &written);
        SetConsoleCursorPosition(console, origin);
    }
#else
    fputs("\033[2J\033[H", stdout);
#endif
}

void vamp_console_set_color(int32_t color) {
#ifdef _WIN32
    fflush(stdout);
    SetConsoleTextAttribute(GetStdHandle(STD_OUTPUT_HANDLE), (WORD)(color < 0 ? 7 : (color & 15)));
#else
    (void)color;
#endif
}

void vamp_console_set_title(const char *title) {
#ifdef _WIN32
    SetConsoleTitleA(title);
#else
    (void)title;
#endif
}

char *vamp_file_read_text(const char *path) {
    FILE *file = fopen(path, "rb");
    long size;
    char *text;
    size_t read;
    if (!file) {
        vamp_throw_format("cannot open file '%s' for reading", path);
    }
    fseek(file, 0, SEEK_END);
    size = ftell(file);
    fseek(file, 0, SEEK_SET);
    text = vamp_allocate_text((size_t)size + 1);
    read = fread(text, 1, (size_t)size, file);
    text[read] = 0;
    fclose(file);
    return text;
}

static int32_t vamp_file_write(const char *path, const char *text, const char *mode) {
    FILE *file = fopen(path, mode);
    size_t length = strlen(text);
    size_t written;
    if (!file) {
        return 0;
    }
    written = fwrite(text, 1, length, file);
    fclose(file);
    return written == length;
}

int32_t vamp_file_write_text(const char *path, const char *text) {
    return vamp_file_write(path, text, "wb");
}

int32_t vamp_file_append_text(const char *path, const char *text) {
    return vamp_file_write(path, text, "ab");
}

int32_t vamp_file_exists(const char *path) {
#ifdef _WIN32
    DWORD attributes = GetFileAttributesA(path);
    return attributes != INVALID_FILE_ATTRIBUTES && !(attributes & FILE_ATTRIBUTE_DIRECTORY);
#else
    struct stat information;
    return stat(path, &information) == 0 && S_ISREG(information.st_mode);
#endif
}

int32_t vamp_file_remove(const char *path) {
    return remove(path) == 0;
}

int32_t vamp_file_rename(const char *from, const char *to) {
    return rename(from, to) == 0;
}

int32_t vamp_file_copy(const char *from, const char *to) {
#ifdef _WIN32
    return CopyFileA(from, to, FALSE) != 0;
#else
    char *text = vamp_file_read_text(from);
    int32_t ok = vamp_file_write_text(to, text);
    vamp_free(text);
    return ok;
#endif
}

int64_t vamp_file_size(const char *path) {
    FILE *file = fopen(path, "rb");
    int64_t size;
    if (!file) {
        return -1;
    }
#ifdef _WIN32
    _fseeki64(file, 0, SEEK_END);
    size = _ftelli64(file);
#else
    fseek(file, 0, SEEK_END);
    size = ftell(file);
#endif
    fclose(file);
    return size;
}

VampList *vamp_file_read_lines(const char *path) {
    char *text = vamp_file_read_text(path);
    VampList *lines = vamp_list_new((int32_t)sizeof(char *), 16);
    char *cursor = text;
    while (*cursor) {
        char *end = strchr(cursor, '\n');
        size_t length = end ? (size_t)(end - cursor) : strlen(cursor);
        size_t trimmed = length && cursor[length - 1] == '\r' ? length - 1 : length;
        *(char **)vamp_list_push_slot(lines) = vamp_string_copy_length(cursor, trimmed);
        if (!end) {
            break;
        }
        cursor = end + 1;
    }
    vamp_free(text);
    return lines;
}

double vamp_math_sqrt(double value) { return sqrt(value); }
double vamp_math_pow(double base, double exponent) { return pow(base, exponent); }
double vamp_math_sin(double value) { return sin(value); }
double vamp_math_cos(double value) { return cos(value); }
double vamp_math_tan(double value) { return tan(value); }
double vamp_math_asin(double value) { return asin(value); }
double vamp_math_acos(double value) { return acos(value); }
double vamp_math_atan(double value) { return atan(value); }
double vamp_math_atan2(double y, double x) { return atan2(y, x); }
double vamp_math_exp(double value) { return exp(value); }
double vamp_math_log(double value) { return log(value); }
double vamp_math_log10(double value) { return log10(value); }
double vamp_math_floor(double value) { return floor(value); }
double vamp_math_ceil(double value) { return ceil(value); }
double vamp_math_round(double value) { return round(value); }
double vamp_math_abs(double value) { return fabs(value); }
double vamp_math_min(double a, double b) { return a < b ? a : b; }
double vamp_math_max(double a, double b) { return a > b ? a : b; }
double vamp_math_clamp(double value, double low, double high) {
    return value < low ? low : (value > high ? high : value);
}
double vamp_math_lerp(double a, double b, double t) { return a + (b - a) * t; }
double vamp_math_pi(void) { return 3.14159265358979323846; }

static VAMP_THREAD_LOCAL uint64_t vamp_random_state = 0;

static uint64_t vamp_random_next(void) {
    uint64_t value;
    if (vamp_random_state == 0) {
        vamp_random_state = ((uint64_t)time(NULL) << 20) ^ (uint64_t)clock() ^ 0x9e3779b97f4a7c15ULL;
#ifdef _WIN32
        vamp_random_state ^= (uint64_t)GetTickCount64() << 7 ^ (uint64_t)GetCurrentThreadId() << 40;
#endif
        if (vamp_random_state == 0) {
            vamp_random_state = 0x2545f4914f6cdd1dULL;
        }
    }
    value = vamp_random_state;
    value ^= value << 13;
    value ^= value >> 7;
    value ^= value << 17;
    vamp_random_state = value;
    return value * 0x2545f4914f6cdd1dULL;
}

void vamp_random_seed(int64_t seed) {
    vamp_random_state = (uint64_t)seed * 0x9e3779b97f4a7c15ULL + 1;
}

int64_t vamp_random_int(int64_t low, int64_t high) {
    uint64_t span;
    if (high < low) {
        int64_t swap = low;
        low = high;
        high = swap;
    }
    span = (uint64_t)high - (uint64_t)low + 1;
    if (span == 0) {
        return (int64_t)vamp_random_next();
    }
    return (int64_t)((uint64_t)low + vamp_random_next() % span);
}

double vamp_random_float(void) {
    return (double)(vamp_random_next() >> 11) * (1.0 / 9007199254740992.0);
}

int32_t vamp_random_chance(double probability) {
    return vamp_random_float() < probability;
}

int64_t vamp_time_now(void) {
    return (int64_t)time(NULL);
}

int64_t vamp_time_millis(void) {
#ifdef _WIN32
    static LARGE_INTEGER frequency;
    LARGE_INTEGER counter;
    if (frequency.QuadPart == 0) {
        QueryPerformanceFrequency(&frequency);
    }
    QueryPerformanceCounter(&counter);
    return (int64_t)(counter.QuadPart * 1000 / frequency.QuadPart);
#else
    struct timespec now;
    clock_gettime(CLOCK_MONOTONIC, &now);
    return (int64_t)now.tv_sec * 1000 + now.tv_nsec / 1000000;
#endif
}

double vamp_time_seconds(void) {
#ifdef _WIN32
    static LARGE_INTEGER frequency;
    LARGE_INTEGER counter;
    if (frequency.QuadPart == 0) {
        QueryPerformanceFrequency(&frequency);
    }
    QueryPerformanceCounter(&counter);
    return (double)counter.QuadPart / (double)frequency.QuadPart;
#else
    struct timespec now;
    clock_gettime(CLOCK_MONOTONIC, &now);
    return (double)now.tv_sec + now.tv_nsec / 1e9;
#endif
}

char *vamp_time_format(const char *format) {
    char buffer[256];
    time_t now = time(NULL);
    struct tm *local = localtime(&now);
    if (!local || strftime(buffer, sizeof(buffer), format, local) == 0) {
        buffer[0] = 0;
    }
    return vamp_string_copy(buffer);
}

int32_t vamp_time_part(int32_t part) {
    time_t now = time(NULL);
    struct tm *local = localtime(&now);
    if (!local) {
        return 0;
    }
    switch (part) {
    case 0: return local->tm_year + 1900;
    case 1: return local->tm_mon + 1;
    case 2: return local->tm_mday;
    case 3: return local->tm_hour;
    case 4: return local->tm_min;
    case 5: return local->tm_sec;
    default: return local->tm_wday;
    }
}

void vamp_time_sleep(int32_t milliseconds) {
    if (milliseconds < 0) {
        return;
    }
#ifdef _WIN32
    Sleep((DWORD)milliseconds);
#else
    usleep((useconds_t)milliseconds * 1000);
#endif
}

VampList *vamp_map_keys(VampMap *map, int32_t key_size) {
    VampList *keys = vamp_list_new(map->string_keys ? (int32_t)sizeof(char *) : key_size, map->length);
    for (int32_t index = 0; index < map->entry_count; index++) {
        if (!map->entries[index].used) {
            continue;
        }
        if (map->string_keys) {
            *(char **)vamp_list_push_slot(keys) = vamp_string_copy(map->entries[index].string_key);
        } else {
            memcpy(vamp_list_push_slot(keys), &map->entries[index].integer_key, (size_t)key_size);
        }
    }
    return keys;
}

VampList *vamp_map_values(VampMap *map) {
    VampList *values = vamp_list_new(map->value_size, map->length);
    for (int32_t index = 0; index < map->entry_count; index++) {
        if (map->entries[index].used) {
            memcpy(vamp_list_push_slot(values), map->values + (size_t)index * (size_t)map->value_size,
                   (size_t)map->value_size);
        }
    }
    return values;
}

char *vamp_str_concat_n(int32_t count, const char **parts) {
    size_t total = 0;
    size_t offset = 0;
    char *result;
    for (int32_t index = 0; index < count; index++) {
        total += strlen(parts[index]);
    }
    result = vamp_allocate_text(total + 1);
    for (int32_t index = 0; index < count; index++) {
        size_t length = strlen(parts[index]);
        memcpy(result + offset, parts[index], length);
        offset += length;
    }
    result[total] = 0;
    return result;
}

char *vamp_format_float(double value, int32_t precision) {
    char buffer[400];
    if (precision < 0) {
        snprintf(buffer, sizeof(buffer), "%f", value);
    } else {
        snprintf(buffer, sizeof(buffer), "%.*f", precision > 60 ? 60 : precision, value);
    }
    return vamp_string_copy(buffer);
}

char *vamp_str_pad(const char *text, int32_t width, int32_t align) {
    size_t length = strlen(text);
    size_t padding;
    size_t before;
    char *result;
    if (width <= 0 || (size_t)width <= length) {
        return vamp_string_copy(text);
    }
    padding = (size_t)width - length;
    before = align == 1 ? padding : align == 2 ? padding / 2 : 0;
    result = vamp_allocate_text((size_t)width + 1);
    memset(result, ' ', (size_t)width);
    memcpy(result + before, text, length);
    result[width] = 0;
    return result;
}

static void vamp_slice_bounds(int64_t length, int64_t *start, int64_t *end) {
    if (*start < 0) {
        *start += length;
    }
    if (*end < 0) {
        *end += length;
    }
    if (*start < 0) {
        *start = 0;
    }
    if (*start > length) {
        *start = length;
    }
    if (*end < 0) {
        *end = 0;
    }
    if (*end > length) {
        *end = length;
    }
    if (*end < *start) {
        *end = *start;
    }
}

VampList *vamp_list_slice(VampList *list, int64_t start, int64_t end) {
    VampList *result;
    vamp_slice_bounds(list->length, &start, &end);
    result = vamp_list_new(list->element_size, (int32_t)(end - start));
    memcpy(result->data, list->data + (size_t)start * (size_t)list->element_size,
           (size_t)(end - start) * (size_t)list->element_size);
    result->length = (int32_t)(end - start);
    return result;
}

char *vamp_str_slice(const char *text, int64_t start, int64_t end) {
    vamp_slice_bounds((int64_t)strlen(text), &start, &end);
    return vamp_string_copy_length(text + start, (size_t)(end - start));
}

static void vamp_map_copy_entry(VampMap *target, VampMap *source, int32_t index) {
    VampMapEntry *entry = &source->entries[index];
    char *slot = vamp_map_slot(target, entry->hash, entry->string_key, entry->integer_key, 1);
    memcpy(slot, source->values + (size_t)index * (size_t)source->value_size, (size_t)source->value_size);
}

static int vamp_map_contains_entry(VampMap *map, VampMapEntry *entry) {
    return vamp_map_lookup(map, entry->hash, entry->string_key, entry->integer_key) >= 0;
}

VampMap *vamp_set_union(VampMap *left, VampMap *right) {
    VampMap *result = vamp_map_new(left->string_keys, left->value_size);
    for (int32_t index = 0; index < left->entry_count; index++) {
        if (left->entries[index].used) {
            vamp_map_copy_entry(result, left, index);
        }
    }
    for (int32_t index = 0; index < right->entry_count; index++) {
        if (right->entries[index].used) {
            vamp_map_copy_entry(result, right, index);
        }
    }
    return result;
}

VampMap *vamp_set_intersection(VampMap *left, VampMap *right) {
    VampMap *result = vamp_map_new(left->string_keys, left->value_size);
    for (int32_t index = 0; index < left->entry_count; index++) {
        if (left->entries[index].used && vamp_map_contains_entry(right, &left->entries[index])) {
            vamp_map_copy_entry(result, left, index);
        }
    }
    return result;
}

VampMap *vamp_set_difference(VampMap *left, VampMap *right) {
    VampMap *result = vamp_map_new(left->string_keys, left->value_size);
    for (int32_t index = 0; index < left->entry_count; index++) {
        if (left->entries[index].used && !vamp_map_contains_entry(right, &left->entries[index])) {
            vamp_map_copy_entry(result, left, index);
        }
    }
    return result;
}

int32_t vamp_set_is_subset(VampMap *left, VampMap *right) {
    for (int32_t index = 0; index < left->entry_count; index++) {
        if (left->entries[index].used && !vamp_map_contains_entry(right, &left->entries[index])) {
            return 0;
        }
    }
    return 1;
}

VampMap *vamp_map_copy(VampMap *map) {
    VampMap *result = vamp_map_new(map->string_keys, map->value_size);
    for (int32_t index = 0; index < map->entry_count; index++) {
        if (map->entries[index].used) {
            vamp_map_copy_entry(result, map, index);
        }
    }
    return result;
}

typedef int32_t (*VampLess)(void *closure, const char *left, const char *right);

static void vamp_merge_sort(char *data, char *scratch, int32_t count, size_t size, void *closure, VampLess less) {
    int32_t middle;
    int32_t left;
    int32_t right;
    int32_t out = 0;
    if (count < 2) {
        return;
    }
    middle = count / 2;
    vamp_merge_sort(data, scratch, middle, size, closure, less);
    vamp_merge_sort(data + (size_t)middle * size, scratch, count - middle, size, closure, less);
    left = 0;
    right = middle;
    while (left < middle && right < count) {
        if (less(closure, data + (size_t)right * size, data + (size_t)left * size)) {
            memcpy(scratch + (size_t)out++ * size, data + (size_t)right++ * size, size);
        } else {
            memcpy(scratch + (size_t)out++ * size, data + (size_t)left++ * size, size);
        }
    }
    while (left < middle) {
        memcpy(scratch + (size_t)out++ * size, data + (size_t)left++ * size, size);
    }
    while (right < count) {
        memcpy(scratch + (size_t)out++ * size, data + (size_t)right++ * size, size);
    }
    memcpy(data, scratch, (size_t)count * size);
}

void vamp_list_sort_with(VampList *list, void *closure, void *less) {
    char *scratch;
    if (list->length < 2) {
        return;
    }
    scratch = (char *)vamp_allocate((size_t)list->length * (size_t)list->element_size);
    vamp_merge_sort(list->data, scratch, list->length, (size_t)list->element_size, closure, (VampLess)less);
    vamp_free(scratch);
}

char *vamp_str_from_u64(uint64_t value) {
    char digits[24];
    int count = 0;
    char *text;
    do {
        digits[count++] = (char)('0' + value % 10);
        value /= 10;
    } while (value);
    text = vamp_allocate_text((size_t)count + 1);
    for (int index = 0; index < count; index++) {
        text[index] = digits[count - 1 - index];
    }
    text[count] = 0;
    return text;
}

char *vamp_str_from_i64(int64_t value) {
    char *text;
    size_t length;
    if (value >= 0) {
        return vamp_str_from_u64((uint64_t)value);
    }
    text = vamp_str_from_u64(0 - (uint64_t)value);
    length = strlen(text);
    {
        char *signed_text = vamp_allocate_text(length + 2);
        signed_text[0] = '-';
        memcpy(signed_text + 1, text, length);
        signed_text[length + 1] = 0;
        vamp_free(text);
        return signed_text;
    }
}

char *vamp_str_concat2(const char *left, const char *right) {
    size_t left_length = strlen(left);
    size_t right_length = strlen(right);
    char *text = vamp_allocate_text(left_length + right_length + 1);
    memcpy(text, left, left_length);
    memcpy(text + left_length, right, right_length);
    text[left_length + right_length] = 0;
    return text;
}

static struct tm vamp_local_time(int64_t timestamp) {
    time_t value = (time_t)timestamp;
    struct tm parts;
#ifdef _WIN32
    localtime_s(&parts, &value);
#else
    localtime_r(&value, &parts);
#endif
    return parts;
}

int64_t vamp_time_make(int32_t year, int32_t month, int32_t day, int32_t hour, int32_t minute, int32_t second) {
    struct tm parts;
    memset(&parts, 0, sizeof(parts));
    parts.tm_year = year - 1900;
    parts.tm_mon = month - 1;
    parts.tm_mday = day;
    parts.tm_hour = hour;
    parts.tm_min = minute;
    parts.tm_sec = second;
    parts.tm_isdst = -1;
    return (int64_t)mktime(&parts);
}

int64_t vamp_time_make_date(int32_t year, int32_t month, int32_t day) {
    return vamp_time_make(year, month, day, 0, 0, 0);
}

int32_t vamp_time_part_of(int32_t part, int64_t timestamp) {
    struct tm parts = vamp_local_time(timestamp);
    switch (part) {
    case 0: return parts.tm_year + 1900;
    case 1: return parts.tm_mon + 1;
    case 2: return parts.tm_mday;
    case 3: return parts.tm_hour;
    case 4: return parts.tm_min;
    case 5: return parts.tm_sec;
    default: return parts.tm_wday;
    }
}

char *vamp_time_format_time(int64_t timestamp, const char *pattern) {
    struct tm parts = vamp_local_time(timestamp);
    char buffer[512];
    size_t length = strftime(buffer, sizeof(buffer), pattern, &parts);
    return vamp_string_copy_length(buffer, length);
}

int64_t vamp_time_add_days(int64_t timestamp, int64_t days) {
    struct tm parts = vamp_local_time(timestamp);
    parts.tm_mday += (int)days;
    parts.tm_isdst = -1;
    return (int64_t)mktime(&parts);
}

static int64_t vamp_day_start(int64_t timestamp) {
    struct tm parts = vamp_local_time(timestamp);
    parts.tm_hour = 12;
    parts.tm_min = 0;
    parts.tm_sec = 0;
    parts.tm_isdst = -1;
    return (int64_t)mktime(&parts);
}

int64_t vamp_time_days_between(int64_t from, int64_t to) {
    double difference = (double)(vamp_day_start(to) - vamp_day_start(from)) / 86400.0;
    return (int64_t)(difference < 0 ? difference - 0.5 : difference + 0.5);
}

static int vamp_read_number(const char **cursor, int digits, int *value) {
    int count = 0;
    *value = 0;
    while (count < digits && isdigit((unsigned char)**cursor)) {
        *value = *value * 10 + (*(*cursor)++ - '0');
        count++;
    }
    return count > 0;
}

int64_t vamp_time_parse(const char *text, const char *pattern) {
    int year = 1970, month = 1, day = 1, hour = 0, minute = 0, second = 0;
    const char *cursor = text;
    for (const char *format = pattern; *format; format++) {
        int ok = 1;
        if (*format == '%' && format[1]) {
            format++;
            switch (*format) {
            case 'Y': ok = vamp_read_number(&cursor, 4, &year); break;
            case 'm': ok = vamp_read_number(&cursor, 2, &month); break;
            case 'd': ok = vamp_read_number(&cursor, 2, &day); break;
            case 'H': ok = vamp_read_number(&cursor, 2, &hour); break;
            case 'M': ok = vamp_read_number(&cursor, 2, &minute); break;
            case 'S': ok = vamp_read_number(&cursor, 2, &second); break;
            case '%': ok = *cursor == '%'; cursor += ok; break;
            default:
                vamp_throw_format("time.Parse understands %%Y %%m %%d %%H %%M %%S, not %%%c", *format);
            }
        } else {
            ok = *cursor == *format;
            cursor += ok;
        }
        if (!ok) {
            vamp_throw_format("\"%s\" does not match the time pattern \"%s\"", text, pattern);
        }
    }
    if (*cursor) {
        vamp_throw_format("\"%s\" has extra text after the time pattern \"%s\"", text, pattern);
    }
    return vamp_time_make(year, month, day, hour, minute, second);
}

typedef struct {
    char *data;
    int64_t length;
    int64_t capacity;
} VampBuilder;

void *vamp_builder_new(void) {
    VampBuilder *builder = (VampBuilder *)vamp_gc_alloc(sizeof(VampBuilder));
    builder->capacity = 64;
    builder->data = vamp_allocate_text(64);
    builder->data[0] = 0;
    return builder;
}

void vamp_builder_add(void *handle, const char *text) {
    VampBuilder *builder = (VampBuilder *)handle;
    size_t length = strlen(text);
    if (builder->length + (int64_t)length + 1 > builder->capacity) {
        int64_t capacity = builder->capacity * 2;
        while (capacity < builder->length + (int64_t)length + 1) {
            capacity *= 2;
        }
        builder->data = (char *)vamp_gc_realloc(builder->data, (size_t)capacity);
        builder->capacity = capacity;
    }
    memcpy(builder->data + builder->length, text, length);
    builder->length += (int64_t)length;
    builder->data[builder->length] = 0;
}

char *vamp_builder_text(void *handle) {
    VampBuilder *builder = (VampBuilder *)handle;
    return vamp_string_copy_length(builder->data, (size_t)builder->length);
}

int64_t vamp_builder_length(void *handle) {
    return ((VampBuilder *)handle)->length;
}

void vamp_builder_clear(void *handle) {
    VampBuilder *builder = (VampBuilder *)handle;
    builder->length = 0;
    builder->data[0] = 0;
}

static int vamp_utf8_length(unsigned char lead) {
    if (lead < 0x80) return 1;
    if ((lead & 0xE0) == 0xC0) return 2;
    if ((lead & 0xF0) == 0xE0) return 3;
    if ((lead & 0xF8) == 0xF0) return 4;
    return 1;
}

static size_t vamp_utf8_step(const char *text, size_t position, size_t length) {
    size_t width = (size_t)vamp_utf8_length((unsigned char)text[position]);
    for (size_t index = 1; index < width; index++) {
        if (position + index >= length || ((unsigned char)text[position + index] & 0xC0) != 0x80) {
            return 1;
        }
    }
    return width;
}

int32_t vamp_str_char_count(const char *text) {
    size_t length = strlen(text);
    int32_t count = 0;
    for (size_t position = 0; position < length; position += vamp_utf8_step(text, position, length)) {
        count++;
    }
    return count;
}

VampList *vamp_str_chars(const char *text) {
    size_t length = strlen(text);
    VampList *list = vamp_list_new((int32_t)sizeof(char *), 8);
    for (size_t position = 0; position < length;) {
        size_t width = vamp_utf8_step(text, position, length);
        char *piece = vamp_string_copy_length(text + position, width);
        memcpy(vamp_list_push_slot(list), &piece, sizeof(char *));
        position += width;
    }
    return list;
}

VampList *vamp_str_code_points(const char *text) {
    size_t length = strlen(text);
    VampList *list = vamp_list_new((int32_t)sizeof(int64_t), 8);
    for (size_t position = 0; position < length;) {
        size_t width = vamp_utf8_step(text, position, length);
        const unsigned char *bytes = (const unsigned char *)text + position;
        int64_t code = width == 1 ? bytes[0]
                     : width == 2 ? ((bytes[0] & 0x1F) << 6) | (bytes[1] & 0x3F)
                     : width == 3 ? ((bytes[0] & 0x0F) << 12) | ((bytes[1] & 0x3F) << 6) | (bytes[2] & 0x3F)
                     : ((int64_t)(bytes[0] & 0x07) << 18) | ((bytes[1] & 0x3F) << 12) | ((bytes[2] & 0x3F) << 6) |
                       (bytes[3] & 0x3F);
        memcpy(vamp_list_push_slot(list), &code, sizeof(int64_t));
        position += width;
    }
    return list;
}

char *vamp_str_from_code(int64_t code) {
    char bytes[4];
    size_t length;
    if (code < 0 || code > 0x10FFFF) {
        vamp_throw_format("%lld is not a Unicode code point", (long long)code);
    }
    if (code < 0x80) {
        bytes[0] = (char)code;
        length = 1;
    } else if (code < 0x800) {
        bytes[0] = (char)(0xC0 | (code >> 6));
        bytes[1] = (char)(0x80 | (code & 0x3F));
        length = 2;
    } else if (code < 0x10000) {
        bytes[0] = (char)(0xE0 | (code >> 12));
        bytes[1] = (char)(0x80 | ((code >> 6) & 0x3F));
        bytes[2] = (char)(0x80 | (code & 0x3F));
        length = 3;
    } else {
        bytes[0] = (char)(0xF0 | (code >> 18));
        bytes[1] = (char)(0x80 | ((code >> 12) & 0x3F));
        bytes[2] = (char)(0x80 | ((code >> 6) & 0x3F));
        bytes[3] = (char)(0x80 | (code & 0x3F));
        length = 4;
    }
    return vamp_string_copy_length(bytes, length);
}
