#include "tzen.h"

#include <pthread.h>
#include <sched.h>
#include <stdio.h>
#include <stdlib.h>

static bool producer_done;

static bool producer_has_finished(void)
{
    bool done;
    TZEN_TH_ENTER_CRITICAL_SECTION();
    done = producer_done;
    TZEN_TH_EXIT_CRITICAL_SECTION();
    return done;
}

static void *feed_packets(void *user_data)
{
    (void)user_data;

    /* "123456789" with CRC 0x29B1, followed by a corrupted copy.
     * These are CRC examples, not Protobuf commands. */
    const uint8_t frames[] = {
        0x00U, 0x0CU, '1', '2', '3', '4', '5', '6', '7', '8', '9', 0x29U, 0xB1U, 0x00U,
        0x00U, 0x0CU, '1', '2', '3', '4', '5', '6', '7', '8', '9', 0x29U, 0xB0U, 0x00U
    };

    for (size_t i = 0U; i < sizeof(frames); ++i) {
        tzen_th_feed_b(frames[i]);
    }

    TZEN_TH_ENTER_CRITICAL_SECTION();
    producer_done = true;
    TZEN_TH_EXIT_CRITICAL_SECTION();
    return NULL;
}

int main(void)
{
    /* Callbacks and tests are unused by the current RX-only implementation. */
    const TzenConfig_t cfg = {0};
    pthread_t producer;

    if (!tzen_th_init(&cfg)) {
        fputs("Test harness initialization failed.\n", stderr);
        return EXIT_FAILURE;
    }

    if (pthread_create(&producer, NULL, feed_packets, NULL) != 0) {
        fputs("Failed to start the receive task.\n", stderr);
        return EXIT_FAILURE;
    }

    /* This thread owns packet processing; the producer owns byte reception. */
    while (!producer_has_finished()) {
        tzen_th_main_function();
        sched_yield();
    }

    if (pthread_join(producer, NULL) != 0) {
        fputs("Failed to join the receive task.\n", stderr);
        return EXIT_FAILURE;
    }
    tzen_th_main_function(); /* Drain packets queued before completion. */

    puts("Receive task finished; CRC processing completed.");
    return EXIT_SUCCESS;
}
