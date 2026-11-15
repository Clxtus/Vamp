#define _CRT_SECURE_NO_WARNINGS
#define _WINSOCK_DEPRECATED_NO_WARNINGS
#include "vamp_runtime.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define WIN32_LEAN_AND_MEAN
#include <winsock2.h>
#include <ws2tcpip.h>
#include <windows.h>
#include <wininet.h>

#define VAMP_MAX_SOCKETS 1024

static SOCKET vamp_sockets[VAMP_MAX_SOCKETS];
static char vamp_socket_used[VAMP_MAX_SOCKETS];
static int vamp_net_started = 0;

static void vamp_net_start(void) {
    if (!vamp_net_started) {
        WSADATA data;
        if (WSAStartup(MAKEWORD(2, 2), &data) != 0) {
            vamp_throw("Windows networking could not be started");
        }
        vamp_net_started = 1;
    }
}

static int32_t vamp_socket_store(SOCKET socket_handle) {
    for (int32_t index = 0; index < VAMP_MAX_SOCKETS; index++) {
        if (!vamp_socket_used[index]) {
            vamp_socket_used[index] = 1;
            vamp_sockets[index] = socket_handle;
            return index + 1;
        }
    }
    closesocket(socket_handle);
    vamp_throw("too many open connections; close the ones you no longer use");
    return 0;
}

static SOCKET vamp_socket_find(int32_t connection) {
    if (connection < 1 || connection > VAMP_MAX_SOCKETS || !vamp_socket_used[connection - 1]) {
        vamp_throw_format("%d is not an open connection", connection);
    }
    return vamp_sockets[connection - 1];
}

int32_t vamp_net_connect(const char *host, int32_t port) {
    struct addrinfo hints;
    struct addrinfo *addresses = NULL;
    char port_text[16];
    SOCKET connected = INVALID_SOCKET;
    vamp_net_start();
    memset(&hints, 0, sizeof(hints));
    hints.ai_family = AF_UNSPEC;
    hints.ai_socktype = SOCK_STREAM;
    snprintf(port_text, sizeof(port_text), "%d", port);
    if (getaddrinfo(host, port_text, &hints, &addresses) != 0) {
        return 0;
    }
    for (struct addrinfo *address = addresses; address; address = address->ai_next) {
        SOCKET candidate = socket(address->ai_family, address->ai_socktype, address->ai_protocol);
        if (candidate == INVALID_SOCKET) {
            continue;
        }
        if (connect(candidate, address->ai_addr, (int)address->ai_addrlen) == 0) {
            connected = candidate;
            break;
        }
        closesocket(candidate);
    }
    freeaddrinfo(addresses);
    return connected == INVALID_SOCKET ? 0 : vamp_socket_store(connected);
}

int32_t vamp_net_listen(int32_t port) {
    struct sockaddr_in address;
    SOCKET server;
    BOOL reuse = TRUE;
    vamp_net_start();
    server = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
    if (server == INVALID_SOCKET) {
        return 0;
    }
    setsockopt(server, SOL_SOCKET, SO_REUSEADDR, (const char *)&reuse, sizeof(reuse));
    memset(&address, 0, sizeof(address));
    address.sin_family = AF_INET;
    address.sin_addr.s_addr = htonl(INADDR_ANY);
    address.sin_port = htons((unsigned short)port);
    if (bind(server, (struct sockaddr *)&address, sizeof(address)) != 0 || listen(server, SOMAXCONN) != 0) {
        closesocket(server);
        return 0;
    }
    return vamp_socket_store(server);
}

int32_t vamp_net_accept(int32_t server) {
    SOCKET client = accept(vamp_socket_find(server), NULL, NULL);
    return client == INVALID_SOCKET ? 0 : vamp_socket_store(client);
}

int32_t vamp_net_send(int32_t connection, const char *text) {
    SOCKET socket_handle = vamp_socket_find(connection);
    int total = (int)strlen(text);
    int sent = 0;
    while (sent < total) {
        int step = send(socket_handle, text + sent, total - sent, 0);
        if (step <= 0) {
            return -1;
        }
        sent += step;
    }
    return sent;
}

char *vamp_net_receive(int32_t connection, int32_t limit) {
    SOCKET socket_handle = vamp_socket_find(connection);
    char *buffer;
    int received;
    if (limit < 1) {
        limit = 1;
    }
    buffer = (char *)malloc((size_t)limit + 1);
    if (!buffer) {
        vamp_throw("out of memory while receiving data");
    }
    received = recv(socket_handle, buffer, limit, 0);
    if (received < 0) {
        received = 0;
    }
    buffer[received] = 0;
    return buffer;
}

void vamp_net_close(int32_t connection) {
    if (connection >= 1 && connection <= VAMP_MAX_SOCKETS && vamp_socket_used[connection - 1]) {
        closesocket(vamp_sockets[connection - 1]);
        vamp_socket_used[connection - 1] = 0;
    }
}

static char *vamp_net_fetch(const char *url, size_t *length) {
    HINTERNET session = InternetOpenA("Vamp", INTERNET_OPEN_TYPE_PRECONFIG, NULL, NULL, 0);
    HINTERNET request;
    char *data = NULL;
    size_t size = 0;
    size_t capacity = 0;
    if (!session) {
        return NULL;
    }
    request = InternetOpenUrlA(session, url, NULL, 0, INTERNET_FLAG_RELOAD | INTERNET_FLAG_NO_CACHE_WRITE, 0);
    if (!request) {
        InternetCloseHandle(session);
        return NULL;
    }
    for (;;) {
        DWORD read = 0;
        if (size + 8192 + 1 > capacity) {
            capacity = capacity ? capacity * 2 : 16384;
            data = (char *)realloc(data, capacity);
            if (!data) {
                InternetCloseHandle(request);
                InternetCloseHandle(session);
                vamp_throw("out of memory while downloading");
            }
        }
        if (!InternetReadFile(request, data + size, 8192, &read)) {
            free(data);
            data = NULL;
            break;
        }
        if (read == 0) {
            break;
        }
        size += read;
    }
    InternetCloseHandle(request);
    InternetCloseHandle(session);
    if (data) {
        data[size] = 0;
        *length = size;
    }
    return data;
}

char *vamp_net_http_get(const char *url) {
    size_t length = 0;
    char *data = vamp_net_fetch(url, &length);
    if (!data) {
        vamp_throw_format("could not fetch '%s'", url);
    }
    return data;
}

int32_t vamp_net_download(const char *url, const char *path) {
    size_t length = 0;
    char *data = vamp_net_fetch(url, &length);
    FILE *file;
    int32_t ok;
    if (!data) {
        return 0;
    }
    file = fopen(path, "wb");
    if (!file) {
        free(data);
        return 0;
    }
    ok = fwrite(data, 1, length, file) == length;
    fclose(file);
    free(data);
    return ok;
}
