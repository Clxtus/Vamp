#define _CRT_SECURE_NO_WARNINGS
#include "vamp_runtime.h"

#include <ctype.h>
#include <stdlib.h>
#include <string.h>

#define WIN32_LEAN_AND_MEAN
#include <windows.h>

enum { NODE_CHAR, NODE_ANY, NODE_CLASS, NODE_GROUP, NODE_START, NODE_END, NODE_WORD_EDGE, NODE_NOT_WORD_EDGE };

typedef struct Alternation Alternation;

typedef struct {
    int kind;
    unsigned char character;
    unsigned char set[32];
    int group;
    Alternation *inner;
    int minimum;
    int maximum;
    int lazy;
} Item;

typedef struct {
    Item *items;
    int count;
} Sequence;

struct Alternation {
    Sequence *options;
    int count;
};

typedef struct {
    char *source;
    Alternation *root;
    int groups;
} Pattern;

typedef struct {
    const char *text;
    size_t length;
    size_t *starts;
    size_t *ends;
    int steps_left_high;
    long long steps;
} Matcher;

typedef struct Continuation {
    const Sequence *sequence;
    int index;
    const Item *repeat;
    int repeat_count;
    size_t repeat_start;
    int group_end;
    const struct Continuation *next;
} Continuation;

static const char *parse_error;

static void *regex_alloc(size_t size) {
    void *memory = calloc(1, size);
    if (!memory) {
        vamp_throw("out of memory while compiling a pattern");
    }
    return memory;
}

static void set_bit(unsigned char *set, int character) {
    set[(unsigned char)character >> 3] |= (unsigned char)(1u << ((unsigned char)character & 7));
}

static int has_bit(const unsigned char *set, int character) {
    return (set[(unsigned char)character >> 3] >> ((unsigned char)character & 7)) & 1;
}

static void add_shorthand(unsigned char *set, char kind) {
    for (int character = 0; character < 256; character++) {
        int digit = character >= '0' && character <= '9';
        int word = isalnum(character) || character == '_';
        int space = character == ' ' || (character >= 9 && character <= 13);
        int hit = (kind == 'd' && digit) || (kind == 'D' && !digit) || (kind == 'w' && word) ||
                  (kind == 'W' && !word) || (kind == 's' && space) || (kind == 'S' && !space);
        if (hit) {
            set_bit(set, character);
        }
    }
}

static int escape_character(char next) {
    switch (next) {
    case 'n': return '\n';
    case 't': return '\t';
    case 'r': return '\r';
    case '0': return 0;
    default: return (unsigned char)next;
    }
}

static Alternation *parse_alternation(const char **cursor, int *groups);

static int parse_number(const char **cursor) {
    int value = 0;
    if (!isdigit((unsigned char)**cursor)) {
        return -1;
    }
    while (isdigit((unsigned char)**cursor)) {
        value = value * 10 + (*(*cursor)++ - '0');
    }
    return value;
}

static int parse_class(const char **cursor, Item *item) {
    int negate = 0;
    int first = 1;
    item->kind = NODE_CLASS;
    if (**cursor == '^') {
        negate = 1;
        (*cursor)++;
    }
    while (**cursor && (**cursor != ']' || first)) {
        int low;
        first = 0;
        if (**cursor == '\\' && (*cursor)[1]) {
            char kind = (*cursor)[1];
            if (strchr("dDwWsS", kind)) {
                add_shorthand(item->set, kind);
                *cursor += 2;
                continue;
            }
            low = escape_character(kind);
            *cursor += 2;
        } else {
            low = (unsigned char)*(*cursor)++;
        }
        if (**cursor == '-' && (*cursor)[1] && (*cursor)[1] != ']') {
            int high;
            (*cursor)++;
            if (**cursor == '\\' && (*cursor)[1]) {
                high = escape_character((*cursor)[1]);
                *cursor += 2;
            } else {
                high = (unsigned char)*(*cursor)++;
            }
            if (high < low) {
                parse_error = "a character range is backwards, for example [z-a]";
                return 0;
            }
            for (int character = low; character <= high; character++) {
                set_bit(item->set, character);
            }
        } else {
            set_bit(item->set, low);
        }
    }
    if (**cursor != ']') {
        parse_error = "a [ is not closed with ]";
        return 0;
    }
    (*cursor)++;
    if (negate) {
        for (int index = 0; index < 32; index++) {
            item->set[index] = (unsigned char)~item->set[index];
        }
    }
    return 1;
}

static int parse_atom(const char **cursor, Item *item, int *groups) {
    char character = **cursor;
    item->minimum = 1;
    item->maximum = 1;
    if (character == '(') {
        (*cursor)++;
        item->kind = NODE_GROUP;
        item->group = -1;
        if ((*cursor)[0] == '?' && (*cursor)[1] == ':') {
            *cursor += 2;
        } else {
            item->group = ++*groups;
        }
        item->inner = parse_alternation(cursor, groups);
        if (!item->inner) {
            return 0;
        }
        if (**cursor != ')') {
            parse_error = "a ( is not closed with )";
            return 0;
        }
        (*cursor)++;
        return 1;
    }
    (*cursor)++;
    switch (character) {
    case '.':
        item->kind = NODE_ANY;
        return 1;
    case '^':
        item->kind = NODE_START;
        return 1;
    case '$':
        item->kind = NODE_END;
        return 1;
    case '[':
        return parse_class(cursor, item);
    case '\\': {
        char next = **cursor;
        if (!next) {
            parse_error = "a pattern cannot end with a single backslash";
            return 0;
        }
        (*cursor)++;
        if (strchr("dDwWsS", next)) {
            item->kind = NODE_CLASS;
            add_shorthand(item->set, next);
        } else if (next == 'b') {
            item->kind = NODE_WORD_EDGE;
        } else if (next == 'B') {
            item->kind = NODE_NOT_WORD_EDGE;
        } else {
            item->kind = NODE_CHAR;
            item->character = (unsigned char)escape_character(next);
        }
        return 1;
    }
    case '*': case '+': case '?': case '{':
        parse_error = "a repeat (*, +, ? or {}) has nothing before it to repeat";
        return 0;
    default:
        item->kind = NODE_CHAR;
        item->character = (unsigned char)character;
        return 1;
    }
}

static int parse_repeat(const char **cursor, Item *item) {
    char character = **cursor;
    if (character == '*' || character == '+' || character == '?') {
        (*cursor)++;
        item->minimum = character == '+' ? 1 : 0;
        item->maximum = character == '?' ? 1 : -1;
    } else if (character == '{' && isdigit((unsigned char)(*cursor)[1])) {
        const char *start = *cursor;
        (*cursor)++;
        item->minimum = parse_number(cursor);
        item->maximum = item->minimum;
        if (**cursor == ',') {
            (*cursor)++;
            item->maximum = **cursor == '}' ? -1 : parse_number(cursor);
        }
        if (**cursor != '}' || (item->maximum >= 0 && item->maximum < item->minimum)) {
            *cursor = start;
            parse_error = "a {min,max} repeat is not written correctly";
            return 0;
        }
        (*cursor)++;
    } else {
        return 1;
    }
    if (item->kind == NODE_START || item->kind == NODE_END || item->kind == NODE_WORD_EDGE ||
        item->kind == NODE_NOT_WORD_EDGE) {
        parse_error = "^, $ and \\b cannot be repeated";
        return 0;
    }
    if (**cursor == '?') {
        item->lazy = 1;
        (*cursor)++;
    }
    return 1;
}

static Alternation *parse_alternation(const char **cursor, int *groups) {
    Alternation *alternation = (Alternation *)regex_alloc(sizeof(Alternation));
    int option_capacity = 2;
    alternation->options = (Sequence *)regex_alloc(sizeof(Sequence) * (size_t)option_capacity);
    for (;;) {
        Sequence *sequence;
        int item_capacity = 8;
        if (alternation->count == option_capacity) {
            option_capacity *= 2;
            alternation->options = (Sequence *)realloc(alternation->options, sizeof(Sequence) * (size_t)option_capacity);
            if (!alternation->options) {
                vamp_throw("out of memory while compiling a pattern");
            }
        }
        sequence = &alternation->options[alternation->count++];
        sequence->items = (Item *)regex_alloc(sizeof(Item) * (size_t)item_capacity);
        sequence->count = 0;
        while (**cursor && **cursor != '|' && **cursor != ')') {
            Item *item;
            if (sequence->count == item_capacity) {
                item_capacity *= 2;
                sequence->items = (Item *)realloc(sequence->items, sizeof(Item) * (size_t)item_capacity);
                if (!sequence->items) {
                    vamp_throw("out of memory while compiling a pattern");
                }
            }
            item = &sequence->items[sequence->count];
            memset(item, 0, sizeof(*item));
            if (!parse_atom(cursor, item, groups) || !parse_repeat(cursor, item)) {
                return NULL;
            }
            sequence->count++;
        }
        if (**cursor != '|') {
            return alternation;
        }
        (*cursor)++;
    }
}

static Pattern *pattern_cache[32];
static int pattern_next;
static SRWLOCK pattern_lock = SRWLOCK_INIT;

static Pattern *compile_pattern(const char *source) {
    Pattern *pattern;
    const char *cursor = source;
    int groups = 0;
    AcquireSRWLockShared(&pattern_lock);
    for (int index = 0; index < 32; index++) {
        if (pattern_cache[index] && strcmp(pattern_cache[index]->source, source) == 0) {
            pattern = pattern_cache[index];
            ReleaseSRWLockShared(&pattern_lock);
            return pattern;
        }
    }
    ReleaseSRWLockShared(&pattern_lock);
    parse_error = NULL;
    pattern = (Pattern *)regex_alloc(sizeof(Pattern));
    pattern->root = parse_alternation(&cursor, &groups);
    if (pattern->root && *cursor == ')') {
        parse_error = "a ) has no matching (";
    }
    if (parse_error || !pattern->root) {
        vamp_throw_format("invalid pattern \"%s\": %s", source, parse_error ? parse_error : "could not read it");
    }
    pattern->groups = groups;
    pattern->source = (char *)regex_alloc(strlen(source) + 1);
    strcpy(pattern->source, source);
    AcquireSRWLockExclusive(&pattern_lock);
    pattern_cache[pattern_next] = pattern;
    pattern_next = (pattern_next + 1) % 32;
    ReleaseSRWLockExclusive(&pattern_lock);
    return pattern;
}

static int is_word(const Matcher *matcher, size_t position) {
    unsigned char character;
    if (position >= matcher->length) {
        return 0;
    }
    character = (unsigned char)matcher->text[position];
    return isalnum(character) || character == '_';
}

static int single_matches(const Item *item, const Matcher *matcher, size_t position) {
    unsigned char character;
    if (position >= matcher->length) {
        return 0;
    }
    character = (unsigned char)matcher->text[position];
    switch (item->kind) {
    case NODE_CHAR: return character == item->character;
    case NODE_ANY: return character != '\n';
    case NODE_CLASS: return has_bit(item->set, character);
    default: return 0;
    }
}

static int match_sequence(Matcher *matcher, const Sequence *sequence, int index, size_t position,
                          const Continuation *next, size_t *end);

static int continue_with(Matcher *matcher, const Continuation *next, size_t position, size_t *end) {
    if (!next) {
        *end = position;
        return 1;
    }
    if (next->group_end >= 0) {
        size_t saved = matcher->ends[next->group_end];
        matcher->ends[next->group_end] = position;
        if (continue_with(matcher, next->next, position, end)) {
            return 1;
        }
        matcher->ends[next->group_end] = saved;
        return 0;
    }
    if (next->repeat) {
        const Item *item = next->repeat;
        int count = next->repeat_count;
        Continuation again;
        if (position == next->repeat_start && count > item->minimum) {
            return 0;
        }
        again = *next;
        again.repeat_count = count + 1;
        again.repeat_start = position;
        if (item->lazy && count >= item->minimum &&
            match_sequence(matcher, next->sequence, next->index, position, next->next, end)) {
            return 1;
        }
        if (item->maximum < 0 || count < item->maximum) {
            for (int option = 0; option < item->inner->count; option++) {
                Continuation close = {NULL, 0, NULL, 0, 0, item->group, &again};
                size_t saved_start = item->group >= 0 ? matcher->starts[item->group] : 0;
                if (item->group >= 0) {
                    matcher->starts[item->group] = position;
                }
                if (match_sequence(matcher, &item->inner->options[option], 0, position,
                                   item->group >= 0 ? &close : &again, end)) {
                    return 1;
                }
                if (item->group >= 0) {
                    matcher->starts[item->group] = saved_start;
                }
            }
        }
        if (!item->lazy && count >= item->minimum) {
            return match_sequence(matcher, next->sequence, next->index, position, next->next, end);
        }
        return 0;
    }
    return match_sequence(matcher, next->sequence, next->index, position, next->next, end);
}

static int match_sequence(Matcher *matcher, const Sequence *sequence, int index, size_t position,
                          const Continuation *next, size_t *end) {
    if (++matcher->steps > 50000000) {
        vamp_throw("a pattern took too long to match; simplify nested repeats such as (a+)+");
    }
    while (index < sequence->count) {
        const Item *item = &sequence->items[index];
        switch (item->kind) {
        case NODE_START:
            if (position != 0) {
                return 0;
            }
            index++;
            continue;
        case NODE_END:
            if (position != matcher->length) {
                return 0;
            }
            index++;
            continue;
        case NODE_WORD_EDGE:
        case NODE_NOT_WORD_EDGE: {
            int edge = (position > 0 && is_word(matcher, position - 1)) != is_word(matcher, position);
            if (edge != (item->kind == NODE_WORD_EDGE)) {
                return 0;
            }
            index++;
            continue;
        }
        case NODE_GROUP: {
            Continuation rest = {sequence, index + 1, NULL, 0, 0, -1, next};
            Continuation repeat = {sequence, index + 1, item, 0, (size_t)-1, -1, next};
            if (item->minimum == 1 && item->maximum == 1) {
                for (int option = 0; option < item->inner->count; option++) {
                    Continuation close = {NULL, 0, NULL, 0, 0, item->group, &rest};
                    size_t saved_start = item->group >= 0 ? matcher->starts[item->group] : 0;
                    if (item->group >= 0) {
                        matcher->starts[item->group] = position;
                    }
                    if (match_sequence(matcher, &item->inner->options[option], 0, position,
                                       item->group >= 0 ? &close : &rest, end)) {
                        return 1;
                    }
                    if (item->group >= 0) {
                        matcher->starts[item->group] = saved_start;
                    }
                }
                return 0;
            }
            return continue_with(matcher, &repeat, position, end);
        }
        default: {
            size_t count = 0;
            size_t maximum = item->maximum < 0 ? (size_t)-1 : (size_t)item->maximum;
            if (item->minimum == 1 && item->maximum == 1) {
                if (!single_matches(item, matcher, position)) {
                    return 0;
                }
                position++;
                index++;
                continue;
            }
            if (item->lazy) {
                for (;;) {
                    if (count >= (size_t)item->minimum &&
                        match_sequence(matcher, sequence, index + 1, position + count, next, end)) {
                        return 1;
                    }
                    if (count >= maximum || !single_matches(item, matcher, position + count)) {
                        return 0;
                    }
                    count++;
                }
            }
            while (count < maximum && single_matches(item, matcher, position + count)) {
                count++;
            }
            for (;;) {
                if (count < (size_t)item->minimum) {
                    return 0;
                }
                if (match_sequence(matcher, sequence, index + 1, position + count, next, end)) {
                    return 1;
                }
                if (count == 0) {
                    return 0;
                }
                count--;
            }
        }
        }
    }
    return continue_with(matcher, next, position, end);
}

static int search(Pattern *pattern, Matcher *matcher, size_t from, int anchored_whole, size_t *start, size_t *end) {
    for (size_t position = from; position <= matcher->length; position++) {
        for (int index = 0; index <= pattern->groups; index++) {
            matcher->starts[index] = (size_t)-1;
            matcher->ends[index] = (size_t)-1;
        }
        for (int option = 0; option < pattern->root->count; option++) {
            size_t found_end;
            if (match_sequence(matcher, &pattern->root->options[option], 0, position, NULL, &found_end) &&
                (!anchored_whole || found_end == matcher->length)) {
                *start = position;
                *end = found_end;
                matcher->starts[0] = position;
                matcher->ends[0] = found_end;
                return 1;
            }
        }
        if (anchored_whole) {
            return 0;
        }
    }
    return 0;
}

typedef struct {
    Pattern *pattern;
    Matcher matcher;
    size_t buffer[64];
} Search;

static void begin(Search *state, const char *pattern, const char *text) {
    size_t slots;
    state->pattern = compile_pattern(pattern);
    memset(&state->matcher, 0, sizeof(state->matcher));
    state->matcher.text = text;
    state->matcher.length = strlen(text);
    slots = (size_t)state->pattern->groups + 1;
    if (slots * 2 <= 64) {
        state->matcher.starts = state->buffer;
    } else {
        state->matcher.starts = (size_t *)regex_alloc(sizeof(size_t) * slots * 2);
    }
    state->matcher.ends = state->matcher.starts + slots;
}

static void finish(Search *state) {
    if (state->matcher.starts != state->buffer) {
        free(state->matcher.starts);
    }
}

static void push_text(VampList *list, const char *text, size_t length) {
    char *copy = vamp_string_copy_length(text, length);
    memcpy(vamp_list_push_slot(list), &copy, sizeof(char *));
}

int32_t vamp_regex_matches(const char *pattern, const char *text) {
    Search state;
    size_t start;
    size_t end;
    int found;
    begin(&state, pattern, text);
    found = search(state.pattern, &state.matcher, 0, 1, &start, &end);
    finish(&state);
    return found;
}

int32_t vamp_regex_contains(const char *pattern, const char *text) {
    Search state;
    size_t start;
    size_t end;
    int found;
    begin(&state, pattern, text);
    found = search(state.pattern, &state.matcher, 0, 0, &start, &end);
    finish(&state);
    return found;
}

char *vamp_regex_find(const char *pattern, const char *text) {
    Search state;
    size_t start;
    size_t end;
    char *result;
    begin(&state, pattern, text);
    result = search(state.pattern, &state.matcher, 0, 0, &start, &end)
                 ? vamp_string_copy_length(text + start, end - start) : vamp_string_copy("");
    finish(&state);
    return result;
}

VampList *vamp_regex_find_all(const char *pattern, const char *text) {
    Search state;
    VampList *list = vamp_list_new((int32_t)sizeof(char *), 4);
    size_t from = 0;
    size_t start;
    size_t end;
    begin(&state, pattern, text);
    while (from <= state.matcher.length && search(state.pattern, &state.matcher, from, 0, &start, &end)) {
        push_text(list, text + start, end - start);
        from = end > start ? end : end + 1;
    }
    finish(&state);
    return list;
}

VampList *vamp_regex_groups(const char *pattern, const char *text) {
    Search state;
    VampList *list = vamp_list_new((int32_t)sizeof(char *), 4);
    size_t start;
    size_t end;
    begin(&state, pattern, text);
    if (search(state.pattern, &state.matcher, 0, 0, &start, &end)) {
        for (int index = 0; index <= state.pattern->groups; index++) {
            size_t group_start = state.matcher.starts[index];
            size_t group_end = state.matcher.ends[index];
            if (group_start == (size_t)-1 || group_end == (size_t)-1) {
                push_text(list, "", 0);
            } else {
                push_text(list, text + group_start, group_end - group_start);
            }
        }
    }
    finish(&state);
    return list;
}

typedef struct {
    char *data;
    size_t length;
    size_t capacity;
} Text;

static void text_add(Text *text, const char *part, size_t length) {
    if (text->length + length + 1 > text->capacity) {
        size_t capacity = text->capacity ? text->capacity * 2 : 64;
        while (capacity < text->length + length + 1) {
            capacity *= 2;
        }
        text->data = (char *)realloc(text->data, capacity);
        if (!text->data) {
            vamp_throw("out of memory");
        }
        text->capacity = capacity;
    }
    memcpy(text->data + text->length, part, length);
    text->length += length;
}

static char *text_result(Text *text) {
    char *result = vamp_string_copy_length(text->data ? text->data : "", text->length);
    free(text->data);
    return result;
}

char *vamp_regex_replace(const char *pattern, const char *text, const char *replacement) {
    Search state;
    Text out = {NULL, 0, 0};
    size_t from = 0;
    size_t copied = 0;
    size_t start;
    size_t end;
    begin(&state, pattern, text);
    while (from <= state.matcher.length && search(state.pattern, &state.matcher, from, 0, &start, &end)) {
        text_add(&out, text + copied, start - copied);
        for (const char *cursor = replacement; *cursor; cursor++) {
            if (*cursor == '$' && isdigit((unsigned char)cursor[1])) {
                int group = cursor[1] - '0';
                cursor++;
                if (group <= state.pattern->groups && state.matcher.starts[group] != (size_t)-1 &&
                    state.matcher.ends[group] != (size_t)-1) {
                    text_add(&out, text + state.matcher.starts[group],
                             state.matcher.ends[group] - state.matcher.starts[group]);
                }
            } else if (*cursor == '$' && cursor[1] == '$') {
                text_add(&out, "$", 1);
                cursor++;
            } else {
                text_add(&out, cursor, 1);
            }
        }
        copied = end;
        if (end == start) {
            if (end < state.matcher.length) {
                text_add(&out, text + end, 1);
            }
            copied = end + 1;
        }
        from = copied;
    }
    if (copied < state.matcher.length) {
        text_add(&out, text + copied, state.matcher.length - copied);
    }
    finish(&state);
    return text_result(&out);
}

VampList *vamp_regex_split(const char *pattern, const char *text) {
    Search state;
    VampList *list = vamp_list_new((int32_t)sizeof(char *), 4);
    size_t from = 0;
    size_t piece = 0;
    size_t start;
    size_t end;
    begin(&state, pattern, text);
    while (from <= state.matcher.length && search(state.pattern, &state.matcher, from, 0, &start, &end)) {
        if (end == start) {
            from = end + 1;
            continue;
        }
        push_text(list, text + piece, start - piece);
        piece = end;
        from = end;
    }
    push_text(list, text + piece, state.matcher.length - piece);
    finish(&state);
    return list;
}
