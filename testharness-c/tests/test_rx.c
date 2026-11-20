/*
 * Tzen
 * Author: L. Furcas
 * SPDX-License-Identifier: MPL-2.0
 */

/* Inspect private RX diagnostics without extending the public harness API. */
#include "../src/tzen.c"

#include <assert.h>
#include <stdio.h>

#ifdef TZEN_TH_TEST_CONCURRENT
#include <pthread.h>
#include <sched.h>
#endif

static const uint8_t valid_frame[] = {
    0x00U, 0x0CU, '1', '2', '3', '4', '5', '6', '7', '8', '9', 0x29U, 0xB1U, 0x00U
};

static void feed(const uint8_t *frame, size_t len)
{
    for (size_t i = 0U; i < len; ++i) {
        tzen_th_feed_b(frame[i]);
    }
}

#ifdef TZEN_TH_TEST_CONCURRENT
static bool producer_done;

static bool producer_has_finished(void)
{
    bool done;
    TZEN_TH_ENTER_CRITICAL_SECTION();
    done = producer_done;
    TZEN_TH_EXIT_CRITICAL_SECTION();
    return done;
}

static void *produce(void *unused)
{
    (void)unused;
    for (size_t i = 0U; i < 20000U; ++i) {
        feed(valid_frame, sizeof(valid_frame));
        sched_yield();
    }
    TZEN_TH_ENTER_CRITICAL_SECTION();
    producer_done = true;
    TZEN_TH_EXIT_CRITICAL_SECTION();
    return NULL;
}
#endif

int main(void)
{
    const TzenConfig_t cfg = {0};
    uint8_t corrupt[sizeof(valid_frame)];

    assert(!tzen_th_init(NULL));
    assert(tzen_th_init(&cfg));
    assert(tzen_th_crc16((const uint8_t *)"123456789", 9U) == 0x29B1U);
    tzen_th_main_function();
    assert(testharness_state.rx_valid_packets == 0U);
    for (size_t i = 0U; i < sizeof(valid_frame); ++i) {
        corrupt[i] = valid_frame[i];
    }
    corrupt[sizeof(corrupt) - 2U] ^= 1U;

    for (size_t i = 0U; i < 100U; ++i) {
        feed(valid_frame, sizeof(valid_frame));
        tzen_th_main_function();
        feed(corrupt, sizeof(corrupt));
        tzen_th_main_function();
    }
    assert(testharness_state.rx_valid_packets == 100U);
    assert(testharness_state.rx_invalid_packets == 100U);

    /* Complete COBS with a missing trailer, and incomplete COBS respectively. */
    const uint8_t short_frame[] = {0U, 2U, 0x11U, 0U};
    const uint8_t incomplete_frame[] = {0U, 3U, 0x11U, 0U};
    feed(short_frame, sizeof(short_frame));
    tzen_th_main_function();
    feed(incomplete_frame, sizeof(incomplete_frame));
    tzen_th_main_function();
    assert(testharness_state.rx_invalid_packets == 101U);

    /* A decoded zero byte is included in the CRC (CRC(0x00) == 0xE1F0). */
    const uint8_t zero_frame[] = {0U, 1U, 3U, 0xE1U, 0xF0U, 0U};
    feed(zero_frame, sizeof(zero_frame));
    tzen_th_main_function();
    assert(testharness_state.rx_valid_packets == 101U);

    /* The decoder must drop an oversized frame and recover at its delimiter. */
    tzen_th_feed_b(0U);
    for (size_t i = 0U; i < TZEN_TH_MAX_PACKET_SIZE + 2U; ++i) {
        tzen_th_feed_b(1U);
    }
    tzen_th_feed_b(0U);
    tzen_th_main_function();
    assert(testharness_state.rx_valid_packets == 101U);
    assert(testharness_state.rx_invalid_packets == 101U);
    feed(valid_frame, sizeof(valid_frame));
    tzen_th_main_function();
    assert(testharness_state.rx_valid_packets == 102U);

    /* Fill the queue, then ensure overflow cannot overwrite queued packets. */
    assert(tzen_th_init(&cfg));
    for (size_t i = 0U; i < TZEN_TH_RX_SLOTS - 1U; ++i) {
        feed(valid_frame, sizeof(valid_frame));
    }
    feed(corrupt, sizeof(corrupt));
    tzen_th_main_function();
    assert(testharness_state.rx_valid_packets == TZEN_TH_RX_SLOTS - 1U);
    assert(testharness_state.rx_invalid_packets == 0U);
    feed(valid_frame, sizeof(valid_frame));
    tzen_th_main_function();
    assert(testharness_state.rx_valid_packets == TZEN_TH_RX_SLOTS);

    /* No leading delimiter: init must suppress an implicit leading zero. */
    assert(tzen_th_init(&cfg));
    feed(valid_frame + 1U, sizeof(valid_frame) - 1U);
    tzen_th_main_function();
    assert(testharness_state.rx_valid_packets == 1U);

#ifdef TZEN_TH_TEST_CONCURRENT
    assert(tzen_th_init(&cfg));
    pthread_t producer;
    assert(pthread_create(&producer, NULL, produce, NULL) == 0);
    while (!producer_has_finished()) {
        tzen_th_main_function();
        sched_yield();
    }
    assert(pthread_join(producer, NULL) == 0);
    tzen_th_main_function();
    assert(testharness_state.rx_valid_packets > 0U);
    assert(testharness_state.rx_valid_packets <= 20000U);
    assert(testharness_state.rx_invalid_packets == 0U);
    puts("RX checks passed, including concurrent producer/consumer reception.");
#else
    puts("RX checks passed with default no-op critical sections.");
#endif
    return 0;
}
