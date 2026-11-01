/*
    Description: Main Tzen implementation.

    Author: TopFirmino (L. Furcas)
    License: see LICENSE.md.
*/
#include "tzen.h"


/*
*   STATIC VARIABLES
*/

/* Current test harness state (work in progress). */
static struct tzen_state_s {
    struct rx_queue {
        struct {
            /* Decoded payload, including CRC bytes; excludes COBS framing. */
            uint8_t  data[TZEN_TH_MAX_PACKET_SIZE];
            uint16_t len;
        } slots[TZEN_TH_RX_SLOTS];

        volatile uint8_t write_idx; /* Written only by tzen_th_feed_b. */
        volatile uint8_t read_idx;  /* Written only by tzen_th_main_function. */

        /* Streaming COBS decoder state for the unpublished slot. */
        uint8_t  cobs_code;
        uint8_t  cobs_block;
        uint16_t cur_pos;
        bool     drop_frame;
    } rx_queue;

} testharness_state;

/* Reset RX state before feeding bytes. Configuration callbacks are not used yet.
 * Initialization requires the producer and consumer to be stopped. */
bool tzen_th_init(const TzenConfig_t *cfg)
{
    if (cfg == NULL) {
        return false;
    }

    testharness_state = (struct tzen_state_s){0};
    testharness_state.rx_queue.cobs_code = 0xFFU;
    return true;
}

void tzen_th_feed_b(uint8_t byte) {
    /* A zero byte ends the current COBS frame and resets the decoder. */
    if (byte == 0x00U) {
        /* Queue only nonempty, complete COBS frames that fit in a slot.
         * CRC and Protobuf validation belong to tzen_th_main_function. */
        if (!testharness_state.rx_queue.drop_frame && (testharness_state.rx_queue.cur_pos > 0U) && (testharness_state.rx_queue.cobs_block == 0U)) {
            uint8_t next_w = (testharness_state.rx_queue.write_idx + 1U) % TZEN_TH_RX_SLOTS;
            if (next_w != testharness_state.rx_queue.read_idx) { /* Drop the new frame if full. */
                testharness_state.rx_queue.slots[testharness_state.rx_queue.write_idx].len = testharness_state.rx_queue.cur_pos;
                testharness_state.rx_queue.write_idx = next_w; /* Publish the completed slot. */
            }
        }
        /* Start the next frame without inserting a leading zero. */
        testharness_state.rx_queue.cobs_code  = 0xFFU;
        testharness_state.rx_queue.cobs_block = 0U;
        testharness_state.rx_queue.cur_pos    = 0U;
        testharness_state.rx_queue.drop_frame = false;
        return;
    }

    if (testharness_state.rx_queue.drop_frame) {
        return; /* Discard bytes until the next delimiter. */
    }

    /* Decode directly into the unpublished slot. */
    if (testharness_state.rx_queue.cobs_block > 0U) {
        if (testharness_state.rx_queue.cur_pos < TZEN_TH_MAX_PACKET_SIZE) {
            testharness_state.rx_queue.slots[testharness_state.rx_queue.write_idx].data[testharness_state.rx_queue.cur_pos++] = byte;
        } else {
            testharness_state.rx_queue.drop_frame = true; /* Oversized frame; wait for a delimiter. */
        }
    } else {
        /* Insert an implicit zero only when another code follows. */
        if (testharness_state.rx_queue.cobs_code != 0xFFU) {
            if (testharness_state.rx_queue.cur_pos < TZEN_TH_MAX_PACKET_SIZE) {
                testharness_state.rx_queue.slots[testharness_state.rx_queue.write_idx].data[testharness_state.rx_queue.cur_pos++] = 0x00U;
            } else {
                testharness_state.rx_queue.drop_frame = true;
            }
        }
        testharness_state.rx_queue.cobs_code  = byte;
        testharness_state.rx_queue.cobs_block = byte;
        if (testharness_state.rx_queue.cobs_code == 0x00U) {
            testharness_state.rx_queue.drop_frame = true;
        }
    }
    testharness_state.rx_queue.cobs_block--;
}
