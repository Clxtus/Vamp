#define _CRT_SECURE_NO_WARNINGS
#include "vamp_runtime.h"

#include <ctype.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

enum { JSON_NULL, JSON_BOOL, JSON_NUMBER, JSON_STRING, JSON_ARRAY, JSON_OBJECT };

typedef struct VampJson {
    int type;
    int count;
    int capacity;
    int is_integer;
    double number;
    char *string;
    char **keys;
    struct VampJson **items;
} VampJson;

static const char *const vamp_json_type_names[] = {"null", "bool", "number", "string", "array", "object"};

static VampJson *json_make(int type) {
    VampJson *node = (VampJson *)calloc(1, sizeof(VampJson));
    if (!node) {
        vamp_throw("out of memory while building JSON");
    }
    node->type = type;
    return node;
}

static void json_clear(VampJson *node) {
    for (int index = 0; index < node->count; index++) {
        if (node->keys) {
            free(node->keys[index]);
        }
        if (node->items[index]) {
            json_clear(node->items[index]);
            free(node->items[index]);
        }
    }
    free(node->keys);
    free(node->items);
    free(node->string);
    memset(node, 0, sizeof(VampJson));
}

void vamp_json_free(VampJson *node) {
    if (node) {
        json_clear(node);
        free(node);
    }
}

static void json_reserve(VampJson *node) {
    if (node->count == node->capacity) {
        int capacity = node->capacity ? node->capacity * 2 : 4;
        node->items = (VampJson **)realloc(node->items, sizeof(VampJson *) * (size_t)capacity);
        if (node->type == JSON_OBJECT) {
            node->keys = (char **)realloc(node->keys, sizeof(char *) * (size_t)capacity);
        }
        if (!node->items || (node->type == JSON_OBJECT && !node->keys)) {
            vamp_throw("out of memory while building JSON");
        }
        node->capacity = capacity;
    }
}

static VampJson *json_append(VampJson *container, const char *key, size_t key_length, VampJson *child) {
    json_reserve(container);
    if (container->type == JSON_OBJECT) {
        container->keys[container->count] = vamp_string_copy_length(key, key_length);
    }
    container->items[container->count++] = child;
    return child;
}

static VampJson *json_member(VampJson *object, const char *key, size_t key_length) {
    for (int index = 0; index < object->count; index++) {
        if (strlen(object->keys[index]) == key_length && memcmp(object->keys[index], key, key_length) == 0) {
            return object->items[index];
        }
    }
    return NULL;
}

typedef struct {
    const char *start;
    const char *cursor;
    char error[160];
} JsonParser;

static void json_skip(JsonParser *parser) {
    while (*parser->cursor && isspace((unsigned char)*parser->cursor)) {
        parser->cursor++;
    }
}

static int json_fail(JsonParser *parser, const char *message) {
    if (!parser->error[0]) {
        int line = 1;
        int column = 1;
        for (const char *scan = parser->start; scan < parser->cursor; scan++) {
            if (*scan == '\n') {
                line++;
                column = 1;
            } else {
                column++;
            }
        }
        snprintf(parser->error, sizeof(parser->error), "invalid JSON at line %d, column %d: %s", line, column,
                 message);
    }
    return 0;
}

static void json_put_utf8(char **output, unsigned code) {
    char *out = *output;
    if (code < 0x80) {
        *out++ = (char)code;
    } else if (code < 0x800) {
        *out++ = (char)(0xC0 | (code >> 6));
        *out++ = (char)(0x80 | (code & 0x3F));
    } else if (code < 0x10000) {
        *out++ = (char)(0xE0 | (code >> 12));
        *out++ = (char)(0x80 | ((code >> 6) & 0x3F));
        *out++ = (char)(0x80 | (code & 0x3F));
    } else {
        *out++ = (char)(0xF0 | (code >> 18));
        *out++ = (char)(0x80 | ((code >> 12) & 0x3F));
        *out++ = (char)(0x80 | ((code >> 6) & 0x3F));
        *out++ = (char)(0x80 | (code & 0x3F));
    }
    *output = out;
}

static int json_hex4(const char *text, unsigned *code) {
    unsigned value = 0;
    for (int index = 0; index < 4; index++) {
        char digit = text[index];
        value <<= 4;
        if (digit >= '0' && digit <= '9') {
            value |= (unsigned)(digit - '0');
        } else if (digit >= 'a' && digit <= 'f') {
            value |= (unsigned)(digit - 'a' + 10);
        } else if (digit >= 'A' && digit <= 'F') {
            value |= (unsigned)(digit - 'A' + 10);
        } else {
            return 0;
        }
    }
    *code = value;
    return 1;
}

static char *json_parse_string(JsonParser *parser) {
    const char *scan = parser->cursor + 1;
    char *result;
    char *out;
    while (*scan && *scan != '"') {
        if (*scan == '\\' && scan[1]) {
            scan++;
        }
        scan++;
    }
    if (*scan != '"') {
        json_fail(parser, "a string is missing its closing quote");
        return NULL;
    }
    result = (char *)malloc((size_t)(scan - parser->cursor) + 1);
    if (!result) {
        vamp_throw("out of memory while reading JSON");
    }
    out = result;
    for (scan = parser->cursor + 1; *scan != '"'; scan++) {
        if (*scan != '\\') {
            *out++ = *scan;
            continue;
        }
        scan++;
        switch (*scan) {
        case 'n': *out++ = '\n'; break;
        case 't': *out++ = '\t'; break;
        case 'r': *out++ = '\r'; break;
        case 'b': *out++ = '\b'; break;
        case 'f': *out++ = '\f'; break;
        case 'u': {
            unsigned code = 0;
            if (!json_hex4(scan + 1, &code)) {
                free(result);
                parser->cursor = scan;
                json_fail(parser, "\\u must be followed by four hex digits");
                return NULL;
            }
            scan += 4;
            if (code >= 0xD800 && code <= 0xDBFF && scan[1] == '\\' && scan[2] == 'u') {
                unsigned low = 0;
                if (json_hex4(scan + 3, &low) && low >= 0xDC00 && low <= 0xDFFF) {
                    code = 0x10000 + ((code - 0xD800) << 10) + (low - 0xDC00);
                    scan += 6;
                }
            }
            json_put_utf8(&out, code);
            break;
        }
        default: *out++ = *scan; break;
        }
    }
    *out = 0;
    parser->cursor = scan + 1;
    return result;
}

static VampJson *json_parse_value(JsonParser *parser, int depth);

static VampJson *json_parse_container(JsonParser *parser, int depth, int type) {
    VampJson *node = json_make(type);
    char closing = type == JSON_ARRAY ? ']' : '}';
    parser->cursor++;
    json_skip(parser);
    if (*parser->cursor == closing) {
        parser->cursor++;
        return node;
    }
    for (;;) {
        char *key = NULL;
        VampJson *child;
        json_skip(parser);
        if (type == JSON_OBJECT) {
            if (*parser->cursor != '"') {
                json_fail(parser, "expected a quoted key");
                break;
            }
            key = json_parse_string(parser);
            if (!key) {
                break;
            }
            json_skip(parser);
            if (*parser->cursor != ':') {
                free(key);
                json_fail(parser, "expected ':' after a key");
                break;
            }
            parser->cursor++;
        }
        child = json_parse_value(parser, depth + 1);
        if (!child) {
            free(key);
            break;
        }
        json_append(node, key ? key : "", key ? strlen(key) : 0, child);
        free(key);
        json_skip(parser);
        if (*parser->cursor == ',') {
            parser->cursor++;
            continue;
        }
        if (*parser->cursor == closing) {
            parser->cursor++;
            return node;
        }
        json_fail(parser, type == JSON_ARRAY ? "expected ',' or ']'" : "expected ',' or '}'");
        break;
    }
    vamp_json_free(node);
    return NULL;
}

static VampJson *json_parse_value(JsonParser *parser, int depth) {
    VampJson *node;
    const char *cursor;
    json_skip(parser);
    cursor = parser->cursor;
    if (depth > 512) {
        json_fail(parser, "the document is nested too deeply");
        return NULL;
    }
    if (*cursor == '{') {
        return json_parse_container(parser, depth, JSON_OBJECT);
    }
    if (*cursor == '[') {
        return json_parse_container(parser, depth, JSON_ARRAY);
    }
    if (*cursor == '"') {
        char *text = json_parse_string(parser);
        if (!text) {
            return NULL;
        }
        node = json_make(JSON_STRING);
        node->string = text;
        return node;
    }
    if (strncmp(cursor, "true", 4) == 0 || strncmp(cursor, "false", 5) == 0) {
        node = json_make(JSON_BOOL);
        node->number = *cursor == 't';
        parser->cursor += *cursor == 't' ? 4 : 5;
        return node;
    }
    if (strncmp(cursor, "null", 4) == 0) {
        parser->cursor += 4;
        return json_make(JSON_NULL);
    }
    if (*cursor == '-' || isdigit((unsigned char)*cursor)) {
        char *end = NULL;
        double value = strtod(cursor, &end);
        int is_integer = 1;
        if (end == cursor) {
            json_fail(parser, "expected a number");
            return NULL;
        }
        for (const char *scan = cursor; scan < end; scan++) {
            if (*scan == '.' || *scan == 'e' || *scan == 'E') {
                is_integer = 0;
            }
        }
        node = json_make(JSON_NUMBER);
        node->number = value;
        node->is_integer = is_integer;
        parser->cursor = end;
        return node;
    }
    json_fail(parser, *cursor ? "expected a value" : "the document ends too early");
    return NULL;
}

VampJson *vamp_json_parse(const char *text) {
    JsonParser parser;
    VampJson *root;
    parser.start = text;
    parser.cursor = text;
    parser.error[0] = 0;
    if ((unsigned char)text[0] == 0xEF && (unsigned char)text[1] == 0xBB && (unsigned char)text[2] == 0xBF) {
        parser.cursor += 3;
    }
    root = json_parse_value(&parser, 0);
    if (root) {
        json_skip(&parser);
        if (*parser.cursor) {
            json_fail(&parser, "unexpected text after the document");
            vamp_json_free(root);
            root = NULL;
        }
    }
    if (!root) {
        vamp_throw(parser.error);
    }
    return root;
}

VampJson *vamp_json_load(const char *path) {
    FILE *file = fopen(path, "rb");
    long size;
    char *text;
    size_t read;
    VampJson *root;
    if (!file) {
        vamp_throw_format("cannot open JSON file '%s'", path);
    }
    fseek(file, 0, SEEK_END);
    size = ftell(file);
    fseek(file, 0, SEEK_SET);
    text = (char *)malloc((size_t)size + 1);
    if (!text) {
        fclose(file);
        vamp_throw("out of memory while reading JSON");
    }
    read = fread(text, 1, (size_t)size, file);
    text[read] = 0;
    fclose(file);
    {
        JsonParser parser;
        parser.start = text;
        parser.cursor = text;
        parser.error[0] = 0;
        if (read >= 3 && (unsigned char)text[0] == 0xEF && (unsigned char)text[1] == 0xBB &&
            (unsigned char)text[2] == 0xBF) {
            parser.cursor += 3;
        }
        root = json_parse_value(&parser, 0);
        if (root) {
            json_skip(&parser);
            if (*parser.cursor) {
                json_fail(&parser, "unexpected text after the document");
                vamp_json_free(root);
                root = NULL;
            }
        }
        free(text);
        if (!root) {
            vamp_throw_format("%s (in '%s')", parser.error, path);
        }
    }
    return root;
}

VampJson *vamp_json_new(int32_t array) {
    return json_make(array ? JSON_ARRAY : JSON_OBJECT);
}

static VampJson *json_walk(VampJson *node, const char *path, int create) {
    const char *cursor = path;
    while (node && *cursor) {
        if (*cursor == '.') {
            cursor++;
            continue;
        }
        if (*cursor == '[') {
            char *end = NULL;
            long index = strtol(cursor + 1, &end, 10);
            if (end == cursor + 1 || *end != ']') {
                vamp_throw_format("invalid JSON path '%s': expected a number and ']' after '['", path);
            }
            cursor = end + 1;
            if (node->type == JSON_NULL && create) {
                node->type = JSON_ARRAY;
            }
            if (node->type != JSON_ARRAY || index < 0) {
                return NULL;
            }
            if (index == node->count && create) {
                json_append(node, "", 0, json_make(JSON_NULL));
            }
            node = index < node->count ? node->items[index] : NULL;
        } else {
            const char *start = cursor;
            VampJson *member;
            while (*cursor && *cursor != '.' && *cursor != '[') {
                cursor++;
            }
            if (node->type == JSON_NULL && create) {
                node->type = JSON_OBJECT;
            }
            if (node->type != JSON_OBJECT) {
                return NULL;
            }
            member = json_member(node, start, (size_t)(cursor - start));
            if (!member && create) {
                member = json_append(node, start, (size_t)(cursor - start), json_make(JSON_NULL));
            }
            node = member;
        }
    }
    return node;
}

static VampJson *json_require(VampJson *root, const char *path, int type, const char *wanted) {
    VampJson *node = json_walk(root, path, 0);
    if (!node) {
        vamp_throw_format("JSON has no value at '%s'", path);
    }
    if (type >= 0 && node->type != type) {
        vamp_throw_format("JSON value at '%s' is %s, not %s", path, vamp_json_type_names[node->type], wanted);
    }
    return node;
}

static VampJson *json_target(VampJson *root, const char *path) {
    VampJson *node = json_walk(root, path, 1);
    if (!node) {
        vamp_throw_format("cannot set JSON value at '%s': part of the path is not an object or array", path);
    }
    json_clear(node);
    return node;
}

int32_t vamp_json_has(VampJson *root, const char *path) {
    return json_walk(root, path, 0) != NULL;
}

const char *vamp_json_type(VampJson *root, const char *path) {
    VampJson *node = json_walk(root, path, 0);
    return node ? vamp_json_type_names[node->type] : "missing";
}

int32_t vamp_json_length(VampJson *root, const char *path) {
    VampJson *node = json_require(root, path, -1, "");
    if (node->type == JSON_ARRAY || node->type == JSON_OBJECT) {
        return node->count;
    }
    if (node->type == JSON_STRING) {
        return (int32_t)strlen(node->string);
    }
    return 0;
}

VampList *vamp_json_keys(VampJson *root, const char *path) {
    VampJson *node = json_require(root, path, JSON_OBJECT, "an object");
    VampList *keys = vamp_list_new((int32_t)sizeof(char *), node->count);
    for (int index = 0; index < node->count; index++) {
        *(char **)vamp_list_push_slot(keys) = vamp_string_copy(node->keys[index]);
    }
    return keys;
}

VampJson *vamp_json_get(VampJson *root, const char *path) {
    return json_require(root, path, -1, "");
}

static char *json_number_text(const VampJson *node) {
    char buffer[64];
    if (node->is_integer && fabs(node->number) < 9.0e15) {
        snprintf(buffer, sizeof(buffer), "%lld", (long long)node->number);
    } else {
        snprintf(buffer, sizeof(buffer), "%.17g", node->number);
    }
    return vamp_string_copy(buffer);
}

char *vamp_json_get_str(VampJson *root, const char *path) {
    VampJson *node = json_require(root, path, -1, "");
    switch (node->type) {
    case JSON_STRING: return vamp_string_copy(node->string);
    case JSON_NUMBER: return json_number_text(node);
    case JSON_BOOL: return vamp_string_copy(node->number != 0 ? "true" : "false");
    default:
        vamp_throw_format("JSON value at '%s' is %s, not a string", path, vamp_json_type_names[node->type]);
        return NULL;
    }
}

double vamp_json_get_float(VampJson *root, const char *path) {
    return json_require(root, path, JSON_NUMBER, "a number")->number;
}

int64_t vamp_json_get_int(VampJson *root, const char *path) {
    return (int64_t)json_require(root, path, JSON_NUMBER, "a number")->number;
}

int32_t vamp_json_get_bool(VampJson *root, const char *path) {
    return json_require(root, path, JSON_BOOL, "a bool")->number != 0;
}

char *vamp_json_get_str_or(VampJson *root, const char *path, const char *fallback) {
    VampJson *node = json_walk(root, path, 0);
    return vamp_string_copy(node && node->type == JSON_STRING ? node->string : fallback);
}

int64_t vamp_json_get_int_or(VampJson *root, const char *path, int64_t fallback) {
    VampJson *node = json_walk(root, path, 0);
    return node && node->type == JSON_NUMBER ? (int64_t)node->number : fallback;
}

double vamp_json_get_float_or(VampJson *root, const char *path, double fallback) {
    VampJson *node = json_walk(root, path, 0);
    return node && node->type == JSON_NUMBER ? node->number : fallback;
}

int32_t vamp_json_get_bool_or(VampJson *root, const char *path, int32_t fallback) {
    VampJson *node = json_walk(root, path, 0);
    return node && node->type == JSON_BOOL ? node->number != 0 : fallback != 0;
}

void vamp_json_set_str(VampJson *root, const char *path, const char *value) {
    VampJson *node = json_target(root, path);
    node->type = JSON_STRING;
    node->string = vamp_string_copy(value);
}

void vamp_json_set_int(VampJson *root, const char *path, int64_t value) {
    VampJson *node = json_target(root, path);
    node->type = JSON_NUMBER;
    node->number = (double)value;
    node->is_integer = 1;
}

void vamp_json_set_float(VampJson *root, const char *path, double value) {
    VampJson *node = json_target(root, path);
    node->type = JSON_NUMBER;
    node->number = value;
}

void vamp_json_set_bool(VampJson *root, const char *path, int32_t value) {
    VampJson *node = json_target(root, path);
    node->type = JSON_BOOL;
    node->number = value != 0;
}

void vamp_json_set_null(VampJson *root, const char *path) {
    json_target(root, path);
}

void vamp_json_set_container(int32_t array, VampJson *root, const char *path) {
    json_target(root, path)->type = array ? JSON_ARRAY : JSON_OBJECT;
}

static VampJson *json_new_element(VampJson *root, const char *path) {
    VampJson *array = json_walk(root, path, 1);
    if (array && array->type == JSON_NULL) {
        array->type = JSON_ARRAY;
    }
    if (!array || array->type != JSON_ARRAY) {
        vamp_throw_format("cannot append to JSON value at '%s': it is not an array", path);
    }
    return json_append(array, "", 0, json_make(JSON_NULL));
}

void vamp_json_append_str(VampJson *root, const char *path, const char *value) {
    VampJson *node = json_new_element(root, path);
    node->type = JSON_STRING;
    node->string = vamp_string_copy(value);
}

void vamp_json_append_int(VampJson *root, const char *path, int64_t value) {
    VampJson *node = json_new_element(root, path);
    node->type = JSON_NUMBER;
    node->number = (double)value;
    node->is_integer = 1;
}

void vamp_json_append_float(VampJson *root, const char *path, double value) {
    VampJson *node = json_new_element(root, path);
    node->type = JSON_NUMBER;
    node->number = value;
}

void vamp_json_append_bool(VampJson *root, const char *path, int32_t value) {
    VampJson *node = json_new_element(root, path);
    node->type = JSON_BOOL;
    node->number = value != 0;
}

void vamp_json_append_container(int32_t array, VampJson *root, const char *path) {
    json_new_element(root, path)->type = array ? JSON_ARRAY : JSON_OBJECT;
}

int32_t vamp_json_remove(VampJson *root, const char *path) {
    size_t length = strlen(path);
    size_t split = length;
    char *parent_path;
    VampJson *parent;
    int found = -1;
    if (length == 0) {
        return 0;
    }
    if (path[length - 1] == ']') {
        while (split > 0 && path[split - 1] != '[') {
            split--;
        }
        if (split == 0) {
            return 0;
        }
        split--;
    } else {
        while (split > 0 && path[split - 1] != '.' && path[split - 1] != ']') {
            split--;
        }
    }
    parent_path = vamp_string_copy_length(path, split);
    parent = json_walk(root, parent_path, 0);
    free(parent_path);
    if (!parent) {
        return 0;
    }
    if (path[split] == '[') {
        long index = strtol(path + split + 1, NULL, 10);
        if (parent->type == JSON_ARRAY && index >= 0 && index < parent->count) {
            found = (int)index;
        }
    } else if (parent->type == JSON_OBJECT) {
        const char *key = path + split;
        for (int index = 0; index < parent->count; index++) {
            if (strcmp(parent->keys[index], key) == 0) {
                found = index;
            }
        }
    }
    if (found < 0) {
        return 0;
    }
    vamp_json_free(parent->items[found]);
    if (parent->keys) {
        free(parent->keys[found]);
    }
    for (int index = found; index < parent->count - 1; index++) {
        parent->items[index] = parent->items[index + 1];
        if (parent->keys) {
            parent->keys[index] = parent->keys[index + 1];
        }
    }
    parent->count--;
    return 1;
}

typedef struct {
    char *text;
    size_t length;
    size_t capacity;
} JsonWriter;

static void json_write(JsonWriter *writer, const char *text, size_t length) {
    if (writer->length + length + 1 > writer->capacity) {
        size_t capacity = writer->capacity ? writer->capacity * 2 : 256;
        while (capacity < writer->length + length + 1) {
            capacity *= 2;
        }
        writer->text = (char *)realloc(writer->text, capacity);
        if (!writer->text) {
            vamp_throw("out of memory while writing JSON");
        }
        writer->capacity = capacity;
    }
    memcpy(writer->text + writer->length, text, length);
    writer->length += length;
    writer->text[writer->length] = 0;
}

static void json_write_string(JsonWriter *writer, const char *text) {
    json_write(writer, "\"", 1);
    for (; *text; text++) {
        unsigned char character = (unsigned char)*text;
        char escape[8];
        switch (character) {
        case '"': json_write(writer, "\\\"", 2); break;
        case '\\': json_write(writer, "\\\\", 2); break;
        case '\n': json_write(writer, "\\n", 2); break;
        case '\t': json_write(writer, "\\t", 2); break;
        case '\r': json_write(writer, "\\r", 2); break;
        default:
            if (character < 0x20) {
                snprintf(escape, sizeof(escape), "\\u%04x", character);
                json_write(writer, escape, 6);
            } else {
                json_write(writer, text, 1);
            }
        }
    }
    json_write(writer, "\"", 1);
}

static void json_write_indent(JsonWriter *writer, int pretty, int depth) {
    if (pretty) {
        json_write(writer, "\n", 1);
        for (int index = 0; index < depth; index++) {
            json_write(writer, "    ", 4);
        }
    }
}

static void json_write_node(JsonWriter *writer, const VampJson *node, int pretty, int depth) {
    switch (node->type) {
    case JSON_NULL: json_write(writer, "null", 4); break;
    case JSON_BOOL:
        json_write(writer, node->number != 0 ? "true" : "false", node->number != 0 ? 4 : 5);
        break;
    case JSON_NUMBER: {
        char *text = json_number_text(node);
        json_write(writer, text, strlen(text));
        free(text);
        break;
    }
    case JSON_STRING: json_write_string(writer, node->string); break;
    default: {
        int is_object = node->type == JSON_OBJECT;
        json_write(writer, is_object ? "{" : "[", 1);
        for (int index = 0; index < node->count; index++) {
            if (index) {
                json_write(writer, ",", 1);
            }
            json_write_indent(writer, pretty, depth + 1);
            if (is_object) {
                json_write_string(writer, node->keys[index]);
                json_write(writer, pretty ? ": " : ":", pretty ? 2 : 1);
            }
            json_write_node(writer, node->items[index], pretty, depth + 1);
        }
        if (node->count) {
            json_write_indent(writer, pretty, depth);
        }
        json_write(writer, is_object ? "}" : "]", 1);
    }
    }
}

char *vamp_json_to_text(int32_t pretty, VampJson *root) {
    JsonWriter writer = {NULL, 0, 0};
    json_write(&writer, "", 0);
    json_write_node(&writer, root, pretty, 0);
    return writer.text;
}

int32_t vamp_json_save(VampJson *root, const char *path) {
    char *text = vamp_json_to_text(1, root);
    FILE *file = fopen(path, "wb");
    size_t length = strlen(text);
    int32_t ok = 0;
    if (file) {
        ok = fwrite(text, 1, length, file) == length;
        fclose(file);
    }
    free(text);
    return ok;
}
