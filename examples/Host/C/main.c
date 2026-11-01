#include "tzen.h"

#include <stdio.h>
#include <stdlib.h>

int main(void)
{
    /* Callbacks and tests are unused by the current RX-only implementation. */
    const TzenConfig_t cfg = {0};

    /* COBS framing for sample bytes 0x11, 0x00, 0x22.
     * This demonstrates feeding bytes, not a CRC-valid protocol command. */
    const uint8_t frame[] = {0x00U, 0x02U, 0x11U, 0x02U, 0x22U, 0x00U};

    if (!tzen_th_init(&cfg)) {
        fputs("Test harness initialization failed.\n", stderr);
        return EXIT_FAILURE;
    }

    for (size_t i = 0; i < sizeof(frame); ++i) {
        tzen_th_feed_b(frame[i]);
    }

    puts("Test harness initialized; sample COBS frame fed.");
    return EXIT_SUCCESS;
}
