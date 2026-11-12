#include "tzen_host_cfg.h"
#include "testcases.h"
#include <stdio.h>
#include <errno.h>
#ifdef _WIN32
#include <windows.h>
#include <io.h>
#include <fcntl.h>
#else
#include <unistd.h>
#include <sys/select.h>
#include <signal.h>
#endif

static bool send_bytes(const uint8_t *frame, size_t len, void *user_data)
{
    (void)user_data;
    return fwrite(frame, 1, len, stdout) == len && fflush(stdout) == 0;
}
const TzenConfig_t host_configuration = {
    .send_bytes = send_bytes,
    .get_us = NULL,
    .user_data = NULL,
    .tests = host_tests,
    .num_tests = HOST_TEST_COUNT
};
bool host_io_init(void)
{
#ifdef _WIN32
    if (_setmode(_fileno(stdin), _O_BINARY) == -1 ||
        _setmode(_fileno(stdout), _O_BINARY) == -1) return false;
#else
    if (signal(SIGPIPE, SIG_IGN) == SIG_ERR) return false;
#endif
    return true;
}
int host_read_byte(uint8_t *byte)
{
#ifdef _WIN32
    HANDLE input = (HANDLE)_get_osfhandle(_fileno(stdin));
    DWORD available = 0;
    if (!PeekNamedPipe(input, NULL, 0, NULL, &available, NULL)) return -1;
    if (!available) { Sleep(1); return 0; }
    return _read(_fileno(stdin), byte, 1) == 1 ? 1 : -1;
#else
    fd_set input;
    FD_ZERO(&input);
    FD_SET(STDIN_FILENO, &input);
    struct timeval timeout = {0, 1000};
    int ready = select(STDIN_FILENO + 1, &input, NULL, NULL, &timeout);
    if (ready < 0) return errno == EINTR ? 0 : -1;
    if (!ready) return 0;
    ssize_t count = read(STDIN_FILENO, byte, 1);
    if (count < 0 && errno == EINTR) return 0;
    return count == 1 ? 1 : -1;
#endif
}
