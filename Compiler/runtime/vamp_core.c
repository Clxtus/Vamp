#define _CRT_SECURE_NO_WARNINGS
#include "vamp_runtime.h"

#include <ctype.h>
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
    return vamp_last_error ? vamp_last_error : "";
}

void vamp_keep(void *address) {
    (void)address;
}

/* try/catch = setjmp/longjmp on a per-thread frame stack.
   no frame means uncaught -> print + exit(1) */
void vamp_throw(const char *message) {
    VampTryFrame *frame = vamp_try_top;
    char *copy = vamp_string_copy(message ? message : "");
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
    void *memory = malloc(size ? size : 1);
    if (!memory) {
        vamp_throw("out of memory");
    }
    return memory;
}

char *vamp_string_copy_length(const char *text, size_t length) {
    char *copy = (char *)malloc(length + 1);
    if (!copy) {
        fprintf(stderr, "Error: out of memory\n");
        exit(1);
    }
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
    return (int32_t)strlen(text);
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
    result = (char *)vamp_allocate(strlen(text) + count * to_length - count * from_length + 1);
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
    result = (char *)vamp_allocate(length * (size_t)count + 1);
    for (int32_t index = 0; index < count; index++) {
        memcpy(result + (size_t)index * length, text, length);
    }
    result[length * (size_t)count] = 0;
    return result;
}

char *vamp_str_reverse(const char *text) {
    size_t length = strlen(text);
    char *result = (char *)vamp_allocate(length + 1);
    for (size_t index = 0; index < length; index++) {
        result[index] = text[length - 1 - index];
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
    result = (char *)vamp_allocate(total);
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

/* strict on purpose, int("abc") used to silently give 0 */
int64_t vamp_str_to_i64(const char *text) {
    return strtoll(text, NULL, 10);
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

static void vamp_list_reserve(VampList *list, int32_t needed) {
    if (needed > list->capacity) {
        int32_t capacity = list->capacity * 2;
        char *data;
        if (capacity < needed) {
            capacity = needed;
        }
        data = (char *)realloc(list->data, (size_t)capacity * (size_t)list->element_size);
        if (!data) {
            vamp_throw("out of memory while growing a list");
        }
        list->data = data;
        list->capacity = capacity;
    }
}

char *vamp_list_push_slot(VampList *list) {
    vamp_list_reserve(list, list->length + 1);
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
    free(scratch);
}

VampList *vamp_list_copy(VampList *list) {
    VampList *copy = vamp_list_new(list->element_size, list->length);
    memcpy(copy->data, list->data, (size_t)list->length * (size_t)list->element_size);
    copy->length = list->length;
    return copy;
}

void vamp_list_free(VampList *list) {
    if (list) {
        free(list->data);
        free(list);
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
    map->buckets = (int32_t *)calloc((size_t)map->bucket_count, sizeof(int32_t));
    map->entries = (VampMapEntry *)vamp_allocate(sizeof(VampMapEntry) * (size_t)map->entry_capacity);
    map->values = (char *)vamp_allocate((size_t)value_size * (size_t)map->entry_capacity);
    if (!map->buckets) {
        vamp_throw("out of memory");
    }
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
    free(map->buckets);
    map->buckets = (int32_t *)calloc((size_t)bucket_count, sizeof(int32_t));
    if (!map->buckets) {
        vamp_throw("out of memory while growing a map");
    }
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
        int32_t capacity = map->entry_capacity * 2;
        VampMapEntry *entries = (VampMapEntry *)realloc(map->entries, sizeof(VampMapEntry) * (size_t)capacity);
        char *values = (char *)realloc(map->values, (size_t)map->value_size * (size_t)capacity);
        if (!entries || !values) {
            vamp_throw("out of memory while growing a map");
        }
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
            free(map->entries[slot - 1].string_key);
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
        free(map->entries[index].string_key);
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
        free(map->buckets);
        free(map->entries);
        free(map->values);
        free(map);
    }
}

char *vamp_console_read_line(void) {
    size_t capacity = 128;
    size_t length = 0;
    char *line = (char *)vamp_allocate(capacity);
    int character;
    fflush(stdout);
    while ((character = getchar()) != EOF && character != '\n') {
        if (length + 1 >= capacity) {
            capacity *= 2;
            line = (char *)realloc(line, capacity);
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
    free(line);
    return value;
}

double vamp_console_read_float(void) {
    char *line = vamp_console_read_line();
    double value = strtod(line, NULL);
    free(line);
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
    text = (char *)vamp_allocate((size_t)size + 1);
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
    free(text);
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
    free(text);
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
