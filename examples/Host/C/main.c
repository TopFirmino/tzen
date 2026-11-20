/*
 * Tzen
 * Author: L. Furcas
 * SPDX-License-Identifier: MPL-2.0
 */

#include "tzen.h"
#include "host_io.h"
#include "tzen_host_cfg.h"
#include "testcases.h"
#include <stdio.h>

int main(void)
{
    if (!host_io_init() || !tzen_th_init(&host_configuration)) {
        fputs("Host initialization failed\n", stderr);
        return 1;
    }
    if (!tzen_emit_log(HOST_SOURCE_SYSTEM, NULL, TZEN_LOG_INFO,
                       "Host ready: global message without a testcase")) {
        fputs("Could not queue startup log\n", stderr);
        return 1;
    }
    while (tzen_th_transport_ok()) {
        uint8_t byte;
        int received = host_read_byte(&byte);
        if (received < 0) break;
        if (received > 0) tzen_th_feed_b(byte);
        tzen_th_main_function();
        /* Terminal events from the previous worker poll have now been sent.
         * Deferred producers use copied identities, never saved contexts. */
        if (!tzen_th_transport_ok() || !host_emit_deferred_logs()) {
            fputs("Could not send deferred example logs\n", stderr);
            return 1;
        }
        for (unsigned i = 0; i < TZEN_TH_MAX_WORKERS; ++i)
            tzen_th_worker_main_function((uint8_t)i);
    }
    return tzen_th_transport_ok() ? 0 : 1;
}
