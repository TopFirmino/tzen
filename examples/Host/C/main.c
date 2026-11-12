#include "tzen.h"
#include "tzen_host_cfg.h"
#include <stdio.h>

int main(void)
{
    if (!host_io_init() || !tzen_th_init(&host_configuration)) {
        fputs("Host initialization failed\n", stderr);
        return 1;
    }
    while (tzen_th_transport_ok()) {
        uint8_t byte;
        int received = host_read_byte(&byte);
        if (received < 0) break;
        if (received > 0) tzen_th_feed_b(byte);
        tzen_th_main_function();
        for (unsigned i = 0; i < TZEN_TH_MAX_WORKERS; ++i)
            tzen_th_worker_main_function((uint8_t)i);
    }
    return tzen_th_transport_ok() ? 0 : 1;
}
