#define _CRT_SECURE_NO_WARNINGS
#include "vamp_runtime.h"

#include <stdlib.h>

#include <windows.h>
#include <commctrl.h>
#include <dwmapi.h>
#include <uxtheme.h>

#define STYLE_CLASSIC 0
#define STYLE_NATIVE 1
#define STYLE_MODERN 2

#define KIND_LABEL 0
#define KIND_ENTRY 1
#define KIND_BUTTON 2
#define KIND_FRAME 3
#define KIND_ICON 4

#define THEME_LIGHT 0
#define THEME_DARK 1
#define THEME_SYSTEM 2

#define STATE_HOVER 1
#define STATE_PRESSED 2

static const char PROP_STYLE[] = "vamp.ui.style";
static const char PROP_KIND[] = "vamp.ui.kind";
static const char PROP_RADIUS[] = "vamp.ui.radius";
static const char PROP_STATE[] = "vamp.ui.state";
static const char PROP_THEME[] = "vamp.ui.theme";
static const char PROP_WINDOW_BG[] = "vamp.ui.background";

typedef struct {
    COLORREF window, frame, button, button_text, text, entry, entry_border, accent, disabled_text, disabled_fill;
} VampPalette;

static const VampPalette vamp_light_palette = {
    RGB(0xeb, 0xeb, 0xeb), RGB(0xdb, 0xdb, 0xdb), RGB(0x3b, 0x8e, 0xd0), RGB(0xff, 0xff, 0xff),
    RGB(0x1a, 0x1a, 0x1a), RGB(0xf9, 0xf9, 0xfa), RGB(0x97, 0x9d, 0xa2), RGB(0x3b, 0x8e, 0xd0),
    RGB(0x9e, 0x9e, 0x9e), RGB(0xc4, 0xc4, 0xc4),
};
static const VampPalette vamp_dark_palette = {
    RGB(0x24, 0x24, 0x24), RGB(0x2b, 0x2b, 0x2b), RGB(0x1f, 0x6a, 0xa5), RGB(0xdc, 0xe4, 0xee),
    RGB(0xdc, 0xe4, 0xee), RGB(0x34, 0x36, 0x38), RGB(0x56, 0x5b, 0x5e), RGB(0x1f, 0x6a, 0xa5),
    RGB(0x73, 0x73, 0x73), RGB(0x40, 0x40, 0x40),
};

typedef struct {
    UINT32 GdiplusVersion;
    void *DebugEventCallback;
    BOOL SuppressBackgroundThread;
    BOOL SuppressExternalCodecs;
} VampGdiplusStartupInput;

int WINAPI GdiplusStartup(ULONG_PTR *token, const VampGdiplusStartupInput *input, void *output);
int WINAPI GdipCreateFromHDC(HDC hdc, void **graphics);
int WINAPI GdipDeleteGraphics(void *graphics);
int WINAPI GdipSetSmoothingMode(void *graphics, int mode);
int WINAPI GdipCreatePath(int fill_mode, void **path);
int WINAPI GdipDeletePath(void *path);
int WINAPI GdipAddPathArc(void *path, float x, float y, float width, float height, float start, float sweep);
int WINAPI GdipAddPathRectangle(void *path, float x, float y, float width, float height);
int WINAPI GdipClosePathFigure(void *path);
int WINAPI GdipCreateSolidFill(DWORD argb, void **brush);
int WINAPI GdipDeleteBrush(void *brush);
int WINAPI GdipFillPath(void *graphics, void *brush, void *path);
int WINAPI GdipCreatePen1(DWORD argb, float width, int unit, void **pen);
int WINAPI GdipDeletePen(void *pen);
int WINAPI GdipDrawPath(void *graphics, void *pen, void *path);

static int vamp_gdiplus_ready(void) {
    static int state;
    if (state == 0) {
        VampGdiplusStartupInput input = {1, NULL, FALSE, FALSE};
        ULONG_PTR token = 0;
        state = GdiplusStartup(&token, &input, NULL) == 0 ? 1 : -1;
    }
    return state == 1;
}

static DWORD vamp_argb(COLORREF color) {
    return 0xff000000u | ((DWORD)GetRValue(color) << 16) | ((DWORD)GetGValue(color) << 8) | GetBValue(color);
}

static void vamp_add_rounded(void *path, float x, float y, float width, float height, float radius) {
    float diameter;
    if (radius > width / 2) {
        radius = width / 2;
    }
    if (radius > height / 2) {
        radius = height / 2;
    }
    if (radius < 0.5f) {
        GdipAddPathRectangle(path, x, y, width, height);
        return;
    }
    diameter = radius * 2;
    GdipAddPathArc(path, x, y, diameter, diameter, 180, 90);
    GdipAddPathArc(path, x + width - diameter, y, diameter, diameter, 270, 90);
    GdipAddPathArc(path, x + width - diameter, y + height - diameter, diameter, diameter, 0, 90);
    GdipAddPathArc(path, x, y + height - diameter, diameter, diameter, 90, 90);
    GdipClosePathFigure(path);
}

static void vamp_fill_rounded(HDC dc, int width, int height, int radius, COLORREF fill, int border, COLORREF border_color) {
    void *graphics = NULL;
    if (vamp_gdiplus_ready() && GdipCreateFromHDC(dc, &graphics) == 0) {
        void *path = NULL;
        void *brush = NULL;
        GdipSetSmoothingMode(graphics, 4 );
        if (border > 0) {
            GdipCreatePath(0, &path);
            vamp_add_rounded(path, 0, 0, (float)width, (float)height, (float)radius);
            GdipCreateSolidFill(vamp_argb(border_color), &brush);
            GdipFillPath(graphics, brush, path);
            GdipDeleteBrush(brush);
            GdipDeletePath(path);
            path = NULL;
            GdipCreatePath(0, &path);
            vamp_add_rounded(path, (float)border, (float)border, (float)(width - 2 * border),
                             (float)(height - 2 * border), (float)(radius > border ? radius - border : 0));
        } else {
            GdipCreatePath(0, &path);
            vamp_add_rounded(path, 0, 0, (float)width, (float)height, (float)radius);
        }
        GdipCreateSolidFill(vamp_argb(fill), &brush);
        GdipFillPath(graphics, brush, path);
        GdipDeleteBrush(brush);
        GdipDeletePath(path);
        GdipDeleteGraphics(graphics);
        return;
    }
    {
        HBRUSH brush = CreateSolidBrush(fill);
        HPEN pen = border > 0 ? CreatePen(PS_SOLID, border, border_color) : (HPEN)GetStockObject(NULL_PEN);
        HGDIOBJ old_brush = SelectObject(dc, brush);
        HGDIOBJ old_pen = SelectObject(dc, pen);
        RoundRect(dc, 0, 0, width + 1, height + 1, radius * 2, radius * 2);
        SelectObject(dc, old_brush);
        SelectObject(dc, old_pen);
        DeleteObject(brush);
        if (border > 0) {
            DeleteObject(pen);
        }
    }
}

static intptr_t vamp_prop(HWND window, const char *name) {
    return (intptr_t)GetPropA(window, name);
}

static void vamp_set_prop(HWND window, const char *name, intptr_t value) {
    SetPropA(window, name, (HANDLE)value);
}

static COLORREF vamp_blend(COLORREF top, COLORREF bottom, int alpha) {
    int inverse = 255 - alpha;
    return RGB((GetRValue(top) * alpha + GetRValue(bottom) * inverse) / 255,
               (GetGValue(top) * alpha + GetGValue(bottom) * inverse) / 255,
               (GetBValue(top) * alpha + GetBValue(bottom) * inverse) / 255);
}

static COLORREF vamp_shade(COLORREF color, int percent) {
    int keep = 100 - percent;
    return RGB(GetRValue(color) * keep / 100, GetGValue(color) * keep / 100, GetBValue(color) * keep / 100);
}

static HWND vamp_root(HWND window) {
    HWND root = GetAncestor(window, GA_ROOT);
    return root ? root : window;
}

static const VampPalette *vamp_palette(HWND window) {
    return vamp_prop(vamp_root(window), PROP_THEME) == THEME_DARK + 1 ? &vamp_dark_palette : &vamp_light_palette;
}

static int vamp_kind(HWND window) {
    return (int)vamp_prop(window, PROP_KIND) - 1;
}

static int vamp_style(HWND window) {
    return (int)vamp_prop(window, PROP_STYLE) - 1;
}

static COLORREF vamp_window_background(HWND root) {
    intptr_t color = vamp_prop(root, PROP_WINDOW_BG);
    return color ? (COLORREF)(color - 1) : GetSysColor(COLOR_WINDOW);
}

static COLORREF vamp_color_behind(HWND window, int depth);

static int vamp_control_fill(HWND window, COLORREF *fill, int depth) {
    intptr_t color;
    intptr_t opacity;
    COLORREF base;
    int modern = vamp_style(window) == STYLE_MODERN;
    int kind = vamp_kind(window);
    if (vamp_prop(window, "vamp.background.transparent")) {
        return 0;
    }
    color = vamp_prop(window, "vamp.background.color");
    if (color) {
        base = (COLORREF)(color - 1);
    } else if (modern && kind == KIND_FRAME) {
        base = vamp_palette(window)->frame;
    } else if (modern && kind == KIND_BUTTON) {
        base = vamp_palette(window)->button;
    } else {
        return 0;
    }
    opacity = vamp_prop(window, "vamp.background.opacity");
    if (opacity) {
        base = vamp_blend(base, vamp_color_behind(window, depth + 1), (int)opacity - 1);
    }
    *fill = base;
    return 1;
}

static COLORREF vamp_color_behind(HWND window, int depth) {
    RECT rect;
    HWND sibling;
    GetWindowRect(window, &rect);
    if (depth < 8) {
        for (sibling = GetWindow(window, GW_HWNDNEXT); sibling; sibling = GetWindow(sibling, GW_HWNDNEXT)) {
            RECT below;
            COLORREF fill;
            if (!IsWindowVisible(sibling)) {
                continue;
            }
            GetWindowRect(sibling, &below);
            if (below.left <= rect.left && below.top <= rect.top && below.right >= rect.right &&
                below.bottom >= rect.bottom && vamp_control_fill(sibling, &fill, depth)) {
                return fill;
            }
        }
    }
    return vamp_window_background(vamp_root(window));
}

static HFONT vamp_default_font(int style) {
    static HFONT fonts[3];
    if (!fonts[style]) {
        fonts[style] = CreateFontA(style == STYLE_MODERN ? -15 : -12, 0, 0, 0, FW_NORMAL, 0, 0, 0, DEFAULT_CHARSET,
                                   OUT_DEFAULT_PRECIS, CLIP_DEFAULT_PRECIS, CLEARTYPE_QUALITY,
                                   DEFAULT_PITCH | FF_SWISS, "Segoe UI");
    }
    return fonts[style];
}

static int vamp_radius(HWND window, int kind, int has_fill) {
    intptr_t radius = vamp_prop(window, PROP_RADIUS);
    if (radius) {
        return (int)radius - 1;
    }
    if (kind == KIND_FRAME) {
        return 8;
    }
    return has_fill ? 6 : 0;
}

static void vamp_paint_modern(HWND window, HDC target) {
    RECT client;
    HDC dc;
    HBITMAP bitmap;
    HGDIOBJ old_bitmap;
    HBRUSH behind_brush;
    const VampPalette *palette = vamp_palette(window);
    int kind = vamp_kind(window);
    int state = (int)vamp_prop(window, PROP_STATE);
    int enabled = IsWindowEnabled(window);
    int has_fill = 0;
    COLORREF fill = 0;
    COLORREF behind;
    intptr_t color;
    intptr_t opacity;
    HICON icon;

    GetClientRect(window, &client);
    if (client.right <= 0 || client.bottom <= 0) {
        return;
    }
    dc = CreateCompatibleDC(target);
    bitmap = CreateCompatibleBitmap(target, client.right, client.bottom);
    old_bitmap = SelectObject(dc, bitmap);

    behind = vamp_color_behind(window, 0);
    behind_brush = CreateSolidBrush(behind);
    FillRect(dc, &client, behind_brush);
    DeleteObject(behind_brush);

    color = vamp_prop(window, "vamp.background.color");
    if (!vamp_prop(window, "vamp.background.transparent")) {
        if (color) {
            fill = (COLORREF)(color - 1);
            has_fill = 1;
        } else if (kind == KIND_BUTTON) {
            fill = palette->button;
            has_fill = 1;
        } else if (kind == KIND_FRAME) {
            fill = palette->frame;
            has_fill = 1;
        }
    }
    if (has_fill && kind == KIND_BUTTON) {
        if (!enabled) {
            fill = palette->disabled_fill;
        } else if (state & STATE_PRESSED) {
            fill = vamp_shade(fill, 28);
        } else if (state & STATE_HOVER) {
            fill = vamp_shade(fill, 16);
        }
    }
    opacity = vamp_prop(window, "vamp.background.opacity");
    if (has_fill && opacity) {
        fill = vamp_blend(fill, behind, (int)opacity - 1);
    }
    if (has_fill) {
        vamp_fill_rounded(dc, client.right, client.bottom, vamp_radius(window, kind, 1), fill, 0, 0);
    }

    icon = (kind == KIND_BUTTON || kind == KIND_ICON) ? (HICON)SendMessageA(window, STM_GETICON, 0, 0) : NULL;
    if (icon) {
        int size = client.right < client.bottom ? client.right : client.bottom;
        if (kind == KIND_BUTTON && size > 16) {
            size -= 12;
        }
        DrawIconEx(dc, (client.right - size) / 2, (client.bottom - size) / 2, icon, size, size, 0, NULL, DI_NORMAL);
    } else if (kind == KIND_LABEL || kind == KIND_BUTTON) {
        char stack_text[256];
        char *text = stack_text;
        int length = GetWindowTextLengthA(window);
        HFONT font = (HFONT)SendMessageA(window, WM_GETFONT, 0, 0);
        HGDIOBJ old_font;
        intptr_t text_color = vamp_prop(window, "vamp.text.color");
        RECT area = client;
        UINT flags = DT_NOPREFIX;
        TEXTMETRICA metrics;
        if (length >= (int)sizeof(stack_text)) {
            text = (char *)malloc((size_t)length + 1);
        }
        if (text) {
            GetWindowTextA(window, text, length + 1);
            old_font = SelectObject(dc, font ? font : vamp_default_font(STYLE_MODERN));
            SetBkMode(dc, TRANSPARENT);
            if (!enabled) {
                SetTextColor(dc, palette->disabled_text);
            } else if (text_color) {
                SetTextColor(dc, (COLORREF)(text_color - 1));
            } else {
                SetTextColor(dc, kind == KIND_BUTTON ? palette->button_text : palette->text);
            }
            GetTextMetricsA(dc, &metrics);
            if (kind == KIND_BUTTON) {
                flags |= DT_CENTER | DT_VCENTER | DT_SINGLELINE | DT_END_ELLIPSIS;
            } else {
                LONG style = GetWindowLongA(window, GWL_STYLE) & SS_TYPEMASK;
                if (style == SS_CENTER) {
                    flags |= DT_CENTER;
                } else if (style == SS_RIGHT) {
                    flags |= DT_RIGHT;
                }
                if (has_fill) {
                    area.left += 8;
                    area.right -= 8;
                }
                if (client.bottom < metrics.tmHeight * 2) {
                    flags |= DT_VCENTER | DT_SINGLELINE | DT_END_ELLIPSIS;
                } else {
                    flags |= DT_WORDBREAK;
                    if (has_fill) {
                        area.top += 6;
                    }
                }
            }
            DrawTextA(dc, text, -1, &area, flags);
            SelectObject(dc, old_font);
            if (text != stack_text) {
                free(text);
            }
        }
    }

    BitBlt(target, 0, 0, client.right, client.bottom, dc, 0, 0, SRCCOPY);
    SelectObject(dc, old_bitmap);
    DeleteObject(bitmap);
    DeleteDC(dc);
}

static void vamp_paint_entry_frame(HWND window) {
    RECT outer;
    RECT client;
    POINT origin = {0, 0};
    HDC window_dc;
    HDC dc;
    HBITMAP bitmap;
    HGDIOBJ old_bitmap;
    HBRUSH behind_brush;
    RECT whole;
    int width;
    int height;
    const VampPalette *palette = vamp_palette(window);
    intptr_t color = vamp_prop(window, "vamp.background.color");
    COLORREF fill = color ? (COLORREF)(color - 1) : palette->entry;
    COLORREF border = GetFocus() == window ? palette->accent : palette->entry_border;
    int radius = vamp_radius(window, KIND_ENTRY, 1);

    GetWindowRect(window, &outer);
    width = outer.right - outer.left;
    height = outer.bottom - outer.top;
    if (width <= 0 || height <= 0) {
        return;
    }
    GetClientRect(window, &client);
    ClientToScreen(window, &origin);
    window_dc = GetWindowDC(window);
    ExcludeClipRect(window_dc, origin.x - outer.left, origin.y - outer.top,
                    origin.x - outer.left + client.right, origin.y - outer.top + client.bottom);
    dc = CreateCompatibleDC(window_dc);
    bitmap = CreateCompatibleBitmap(window_dc, width, height);
    old_bitmap = SelectObject(dc, bitmap);
    SetRect(&whole, 0, 0, width, height);
    behind_brush = CreateSolidBrush(vamp_color_behind(window, 0));
    FillRect(dc, &whole, behind_brush);
    DeleteObject(behind_brush);
    vamp_fill_rounded(dc, width, height, radius, fill, GetFocus() == window ? 2 : 1, border);
    BitBlt(window_dc, 0, 0, width, height, dc, 0, 0, SRCCOPY);
    SelectObject(dc, old_bitmap);
    DeleteObject(bitmap);
    DeleteDC(dc);
    ReleaseDC(window, window_dc);
}

static void vamp_entry_insets(HWND window, int height, int *horizontal, int *vertical) {
    HDC dc = GetDC(window);
    HFONT font = (HFONT)SendMessageA(window, WM_GETFONT, 0, 0);
    HGDIOBJ old_font = SelectObject(dc, font ? font : vamp_default_font(STYLE_MODERN));
    TEXTMETRICA metrics;
    GetTextMetricsA(dc, &metrics);
    SelectObject(dc, old_font);
    ReleaseDC(window, dc);
    *horizontal = 8;
    *vertical = (height - metrics.tmHeight) / 2;
    if (*vertical < 2) {
        *vertical = 2;
    }
}

static void vamp_remove_ui_props(HWND window) {
    RemovePropA(window, PROP_STYLE);
    RemovePropA(window, PROP_KIND);
    RemovePropA(window, PROP_RADIUS);
    RemovePropA(window, PROP_STATE);
}

static LRESULT CALLBACK vamp_modern_control_proc(HWND window, UINT message, WPARAM wparam, LPARAM lparam,
                                                 UINT_PTR id, DWORD_PTR data) {
    int kind = (int)data;
    int state;
    switch (message) {
    case WM_ERASEBKGND:
        if (kind != KIND_ENTRY) {
            return 1;
        }
        break;
    case WM_PAINT:
        if (kind != KIND_ENTRY) {
            PAINTSTRUCT paint;
            HDC dc = BeginPaint(window, &paint);
            vamp_paint_modern(window, dc);
            EndPaint(window, &paint);
            return 0;
        }
        break;
    case WM_PRINTCLIENT:
        if (kind != KIND_ENTRY) {
            vamp_paint_modern(window, (HDC)wparam);
            return 0;
        }
        break;
    case WM_SETTEXT:
    case WM_ENABLE:
    case WM_SETFONT:
    case WM_SIZE:
    case STM_SETICON:
    case STM_SETIMAGE: {
        LRESULT result = DefSubclassProc(window, message, wparam, lparam);
        InvalidateRect(window, NULL, FALSE);
        if (kind == KIND_ENTRY) {
            RedrawWindow(window, NULL, NULL, RDW_FRAME | RDW_INVALIDATE);
        }
        return result;
    }
    case WM_MOUSEMOVE:
        state = (int)vamp_prop(window, PROP_STATE);
        if (kind == KIND_BUTTON && !(state & STATE_HOVER)) {
            TRACKMOUSEEVENT track = {sizeof(track), TME_LEAVE, window, 0};
            TrackMouseEvent(&track);
            vamp_set_prop(window, PROP_STATE, state | STATE_HOVER);
            InvalidateRect(window, NULL, FALSE);
        }
        break;
    case WM_MOUSELEAVE:
        if (kind == KIND_BUTTON) {
            vamp_set_prop(window, PROP_STATE, 0);
            InvalidateRect(window, NULL, FALSE);
        }
        break;
    case WM_LBUTTONDBLCLK:
        if (kind == KIND_BUTTON) {
            message = WM_LBUTTONDOWN;
        }
    case WM_LBUTTONDOWN:
        if (kind == KIND_BUTTON) {
            vamp_set_prop(window, PROP_STATE, (int)vamp_prop(window, PROP_STATE) | STATE_PRESSED);
            InvalidateRect(window, NULL, FALSE);
        }
        return DefSubclassProc(window, message, wparam, lparam);
    case WM_LBUTTONUP:
        if (kind == KIND_BUTTON) {
            vamp_set_prop(window, PROP_STATE, (int)vamp_prop(window, PROP_STATE) & ~STATE_PRESSED);
            InvalidateRect(window, NULL, FALSE);
        }
        break;
    case WM_SETCURSOR:
        if (kind == KIND_BUTTON && IsWindowEnabled(window)) {
            SetCursor(LoadCursor(NULL, IDC_HAND));
            return TRUE;
        }
        break;
    case WM_NCCALCSIZE:
        if (kind == KIND_ENTRY && wparam) {
            RECT *proposed = &((NCCALCSIZE_PARAMS *)lparam)->rgrc[0];
            int horizontal;
            int vertical;
            vamp_entry_insets(window, proposed->bottom - proposed->top, &horizontal, &vertical);
            proposed->left += horizontal;
            proposed->right -= horizontal;
            proposed->top += vertical;
            proposed->bottom -= vertical;
            return 0;
        }
        break;
    case WM_NCPAINT:
        if (kind == KIND_ENTRY) {
            vamp_paint_entry_frame(window);
            return 0;
        }
        break;
    case WM_SETFOCUS:
    case WM_KILLFOCUS:
        if (kind == KIND_ENTRY) {
            LRESULT result = DefSubclassProc(window, message, wparam, lparam);
            RedrawWindow(window, NULL, NULL, RDW_FRAME | RDW_INVALIDATE);
            return result;
        }
        break;
    case WM_NCDESTROY:
        RemoveWindowSubclass(window, vamp_modern_control_proc, id);
        vamp_remove_ui_props(window);
        break;
    }
    return DefSubclassProc(window, message, wparam, lparam);
}

static LRESULT CALLBACK vamp_modern_window_proc(HWND window, UINT message, WPARAM wparam, LPARAM lparam,
                                                UINT_PTR id, DWORD_PTR data) {
    (void)data;
    if (message == WM_ERASEBKGND) {
        RECT client;
        HBRUSH brush = CreateSolidBrush(vamp_window_background(window));
        GetClientRect(window, &client);
        FillRect((HDC)wparam, &client, brush);
        DeleteObject(brush);
        return 1;
    }
    if (message == WM_NCDESTROY) {
        RemoveWindowSubclass(window, vamp_modern_window_proc, id);
        RemovePropA(window, PROP_THEME);
        RemovePropA(window, PROP_WINDOW_BG);
        RemovePropA(window, PROP_STYLE);
    }
    return DefSubclassProc(window, message, wparam, lparam);
}

static int vamp_system_uses_dark_theme(void) {
    DWORD light = 1;
    DWORD size = sizeof(light);
    if (RegGetValueA(HKEY_CURRENT_USER, "Software\\Microsoft\\Windows\\CurrentVersion\\Themes\\Personalize",
                     "AppsUseLightTheme", RRF_RT_REG_DWORD, NULL, &light, &size) != ERROR_SUCCESS) {
        return 0;
    }
    return light == 0;
}

void vamp_ui_style_window(void *handle, int32_t style, int32_t theme) {
    static int controls_ready;
    HWND window = (HWND)handle;
    if (!controls_ready) {
        INITCOMMONCONTROLSEX classes = {sizeof(classes), ICC_STANDARD_CLASSES};
        InitCommonControlsEx(&classes);
        controls_ready = 1;
    }
    if (theme == THEME_SYSTEM) {
        theme = vamp_system_uses_dark_theme() ? THEME_DARK : THEME_LIGHT;
    }
    vamp_set_prop(window, PROP_STYLE, style + 1);
    vamp_set_prop(window, PROP_THEME, theme + 1);
    if (style == STYLE_MODERN) {
        const VampPalette *palette = theme == THEME_DARK ? &vamp_dark_palette : &vamp_light_palette;
        vamp_set_prop(window, PROP_WINDOW_BG, (intptr_t)palette->window + 1);
        SetWindowSubclass(window, vamp_modern_window_proc, 1, 0);
        if (theme == THEME_DARK) {
            BOOL dark = TRUE;
            if (FAILED(DwmSetWindowAttribute(window, 20, &dark, sizeof(dark)))) {
                DwmSetWindowAttribute(window, 19, &dark, sizeof(dark));
            }
        }
    } else {
        vamp_set_prop(window, PROP_WINDOW_BG, (intptr_t)GetSysColor(COLOR_WINDOW) + 1);
    }
}

void vamp_ui_style_control(void *handle, int32_t style, int32_t kind, int32_t radius) {
    HWND control = (HWND)handle;
    vamp_set_prop(control, PROP_STYLE, style + 1);
    vamp_set_prop(control, PROP_KIND, kind + 1);
    if (radius >= 0) {
        vamp_set_prop(control, PROP_RADIUS, radius + 1);
    }
    if (style == STYLE_CLASSIC) {
        SetWindowTheme(control, L" ", L" ");
        return;
    }
    if (!SendMessageA(control, WM_GETFONT, 0, 0)) {
        SendMessageA(control, WM_SETFONT, (WPARAM)vamp_default_font(style), FALSE);
    }
    if (style == STYLE_NATIVE) {
        if (kind == KIND_LABEL && !vamp_prop(control, "vamp.background.color") &&
            !vamp_prop(control, "vamp.background.transparent")) {
            vamp_set_prop(control, "vamp.background.transparent", 1);
        } else if (kind == KIND_ENTRY) {
            SetWindowLongPtrA(control, GWL_EXSTYLE, GetWindowLongPtrA(control, GWL_EXSTYLE) | WS_EX_CLIENTEDGE);
            SetWindowPos(control, NULL, 0, 0, 0, 0,
                         SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED);
        }
        return;
    }
    if (style != STYLE_MODERN) {
        return;
    }
    if (kind == KIND_ENTRY) {
        const VampPalette *palette = vamp_palette(control);
        if (!vamp_prop(control, "vamp.background.color")) {
            vamp_set_prop(control, "vamp.background.color", (intptr_t)palette->entry + 1);
            vamp_set_prop(control, "vamp.background.brush", (intptr_t)CreateSolidBrush(palette->entry));
        }
        if (!vamp_prop(control, "vamp.text.color")) {
            vamp_set_prop(control, "vamp.text.color", (intptr_t)palette->text + 1);
        }
    }
    SetWindowSubclass(control, vamp_modern_control_proc, 1, (DWORD_PTR)kind);
    if (kind == KIND_ENTRY) {
        SetWindowPos(control, NULL, 0, 0, 0, 0,
                     SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED);
    }
    InvalidateRect(control, NULL, TRUE);
}
