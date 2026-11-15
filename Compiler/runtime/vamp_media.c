#define _CRT_SECURE_NO_WARNINGS
#include "vamp_runtime.h"

#include <ctype.h>
#include <stdio.h>
#include <string.h>

#include <windows.h>
#include <mmsystem.h>

typedef struct {
    const char *name;
    int code;
} VampKeyName;

static const VampKeyName vamp_key_names[] = {
    {"SPACE", VK_SPACE}, {"ENTER", VK_RETURN}, {"RETURN", VK_RETURN}, {"ESCAPE", VK_ESCAPE}, {"ESC", VK_ESCAPE},
    {"TAB", VK_TAB}, {"BACKSPACE", VK_BACK}, {"DELETE", VK_DELETE}, {"INSERT", VK_INSERT},
    {"LEFT", VK_LEFT}, {"RIGHT", VK_RIGHT}, {"UP", VK_UP}, {"DOWN", VK_DOWN},
    {"HOME", VK_HOME}, {"END", VK_END}, {"PAGEUP", VK_PRIOR}, {"PAGEDOWN", VK_NEXT},
    {"SHIFT", VK_SHIFT}, {"CTRL", VK_CONTROL}, {"CONTROL", VK_CONTROL}, {"ALT", VK_MENU},
    {"LSHIFT", VK_LSHIFT}, {"RSHIFT", VK_RSHIFT}, {"LCTRL", VK_LCONTROL}, {"RCTRL", VK_RCONTROL},
    {"CAPSLOCK", VK_CAPITAL}, {"PLUS", VK_OEM_PLUS}, {"MINUS", VK_OEM_MINUS},
    {"COMMA", VK_OEM_COMMA}, {"PERIOD", VK_OEM_PERIOD},
    {"F1", VK_F1}, {"F2", VK_F2}, {"F3", VK_F3}, {"F4", VK_F4}, {"F5", VK_F5}, {"F6", VK_F6},
    {"F7", VK_F7}, {"F8", VK_F8}, {"F9", VK_F9}, {"F10", VK_F10}, {"F11", VK_F11}, {"F12", VK_F12},
};

static int vamp_key_code(const char *name) {
    char upper[16];
    size_t length = strlen(name);
    if (length == 0 || length >= sizeof(upper)) {
        vamp_throw_format("unknown key name \"%s\"", name);
    }
    for (size_t index = 0; index <= length; index++) {
        upper[index] = (char)toupper((unsigned char)name[index]);
    }
    if (length == 1 && (isalpha((unsigned char)upper[0]) || isdigit((unsigned char)upper[0]))) {
        return upper[0];
    }
    for (size_t index = 0; index < sizeof(vamp_key_names) / sizeof(vamp_key_names[0]); index++) {
        if (strcmp(vamp_key_names[index].name, upper) == 0) {
            return vamp_key_names[index].code;
        }
    }
    vamp_throw_format("unknown key name \"%s\" (use a letter, a digit, or a name such as \"SPACE\", \"LEFT\", "
                      "\"ENTER\", \"ESCAPE\", \"SHIFT\", \"F1\")", name);
    return 0;
}

static int vamp_mouse_code(const char *button) {
    if (_stricmp(button, "left") == 0) {
        return VK_LBUTTON;
    }
    if (_stricmp(button, "right") == 0) {
        return VK_RBUTTON;
    }
    if (_stricmp(button, "middle") == 0) {
        return VK_MBUTTON;
    }
    vamp_throw_format("unknown mouse button \"%s\" (use \"left\", \"right\" or \"middle\")", button);
    return 0;
}

int32_t vamp_input_key_down(const char *name) {
    return (GetAsyncKeyState(vamp_key_code(name)) & 0x8000) != 0;
}

int32_t vamp_input_key_pressed(const char *name) {
    static unsigned char was_down[256];
    int code = vamp_key_code(name) & 255;
    int down = (GetAsyncKeyState(code) & 0x8000) != 0;
    int pressed = down && !was_down[code];
    was_down[code] = (unsigned char)down;
    return pressed;
}

int32_t vamp_input_mouse_down(const char *button) {
    return (GetAsyncKeyState(vamp_mouse_code(button)) & 0x8000) != 0;
}

int32_t vamp_input_mouse_position(int32_t axis) {
    POINT point;
    if (!GetCursorPos(&point)) {
        return -1;
    }
    return axis == 0 ? point.x : point.y;
}

int32_t vamp_input_mouse_window_position(int32_t axis, const char *title) {
    HWND window = FindWindowA(NULL, title);
    POINT point;
    if (!window || !GetCursorPos(&point) || !ScreenToClient(window, &point)) {
        return -1;
    }
    return axis == 0 ? point.x : point.y;
}

int32_t vamp_audio_play(int32_t mode, const char *path) {
    DWORD flags = SND_FILENAME | SND_NODEFAULT;
    DWORD attributes = GetFileAttributesA(path);
    if (attributes == INVALID_FILE_ATTRIBUTES || (attributes & FILE_ATTRIBUTE_DIRECTORY)) {
        return 0;
    }
    if (mode == 0) {
        flags |= SND_ASYNC;
    } else if (mode == 1) {
        flags |= SND_ASYNC | SND_LOOP;
    } else {
        flags |= SND_SYNC;
    }
    return PlaySoundA(path, NULL, flags) != 0;
}

void vamp_audio_stop(void) {
    PlaySoundA(NULL, NULL, 0);
}

void vamp_audio_beep(int32_t frequency, int32_t milliseconds) {
    if (frequency < 37) {
        frequency = 37;
    }
    if (frequency > 32767) {
        frequency = 32767;
    }
    Beep((DWORD)frequency, (DWORD)(milliseconds < 0 ? 0 : milliseconds));
}

int32_t vamp_audio_music(int32_t loop, const char *path) {
    char command[1024];
    if (strlen(path) > 900 || strchr(path, '"')) {
        return 0;
    }
    mciSendStringA("close vamp_music", NULL, 0, NULL);
    snprintf(command, sizeof(command), "open \"%s\" type mpegvideo alias vamp_music", path);
    if (mciSendStringA(command, NULL, 0, NULL) != 0) {
        return 0;
    }
    return mciSendStringA(loop ? "play vamp_music repeat" : "play vamp_music", NULL, 0, NULL) == 0;
}

int32_t vamp_audio_music_command(int32_t command) {
    static const char *const commands[] = {"close vamp_music", "pause vamp_music", "resume vamp_music"};
    if (command < 0 || command > 2) {
        return 0;
    }
    return mciSendStringA(commands[command], NULL, 0, NULL) == 0;
}

int32_t vamp_audio_music_volume(int32_t volume) {
    char command[64];
    if (volume < 0) {
        volume = 0;
    }
    if (volume > 100) {
        volume = 100;
    }
    snprintf(command, sizeof(command), "setaudio vamp_music volume to %d", volume * 10);
    return mciSendStringA(command, NULL, 0, NULL) == 0;
}
