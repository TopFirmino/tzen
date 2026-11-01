/*
    Description: Main Tzen implementation.

    Author: TopFirmino (L. Furcas)
    License: see LICENSE.md.
*/
#include "tzen.h"

_Static_assert(TZEN_TH_RX_SLOTS >= 2U && TZEN_TH_RX_SLOTS <= 256U,
               "RX queue requires 2 to 256 slots");
_Static_assert(TZEN_TH_MAX_PACKET_SIZE >= 2U && TZEN_TH_MAX_PACKET_SIZE <= UINT16_MAX,
               "RX packet size must fit the length field and CRC trailer");


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

        uint8_t write_idx; /* Written only by tzen_th_feed_b. */
        uint8_t read_idx;  /* Written only by tzen_th_main_function. */

        /* Streaming COBS decoder state for the unpublished slot. */
        uint8_t  cobs_code;
        uint8_t  cobs_block;
        uint16_t cur_pos;
        bool     drop_frame;
    } rx_queue;

    /* Consumer-owned diagnostics, available for debugger inspection. */
    size_t rx_valid_packets;
    size_t rx_invalid_packets;

} testharness_state;

/* Reset RX state before feeding bytes. Configuration callbacks are not used yet.
 * Initialization requires the producer and consumer to be stopped. */
bool tzen_th_init(const TzenConfig_t *cfg)
{
    if (cfg == NULL) {
        return false;
    }

    testharness_state.rx_queue.write_idx = 0U;
    testharness_state.rx_queue.read_idx = 0U;
    testharness_state.rx_queue.cobs_code = 0xFFU;
    testharness_state.rx_queue.cobs_block = 0U;
    testharness_state.rx_queue.cur_pos = 0U;
    testharness_state.rx_queue.drop_frame = false;
    testharness_state.rx_valid_packets = 0U;
    testharness_state.rx_invalid_packets = 0U;
    return true;
}

void tzen_th_feed_b(uint8_t byte) {
    /* Only this producer changes write_idx. The unpublished slot stays private,
     * even when the queue is full. */
    uint8_t write_idx = testharness_state.rx_queue.write_idx;
    /* A zero byte ends the current COBS frame and resets the decoder. */
    if (byte == 0x00U) {
        /* Queue only nonempty, complete COBS frames that fit in a slot.
         * CRC validation belongs to tzen_th_main_function. */
        if (!testharness_state.rx_queue.drop_frame && (testharness_state.rx_queue.cur_pos > 0U) && (testharness_state.rx_queue.cobs_block == 0U)) {
            uint8_t next_w = (write_idx + 1U) % TZEN_TH_RX_SLOTS;
            TZEN_TH_ENTER_CRITICAL_SECTION();
            if (next_w != testharness_state.rx_queue.read_idx) {
                testharness_state.rx_queue.slots[write_idx].len = testharness_state.rx_queue.cur_pos;
                /* Publish data and length together to the consumer. */
                testharness_state.rx_queue.write_idx = next_w;
            }
            TZEN_TH_EXIT_CRITICAL_SECTION();
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
            testharness_state.rx_queue.slots[write_idx].data[testharness_state.rx_queue.cur_pos++] = byte;
        } else {
            testharness_state.rx_queue.drop_frame = true; /* Oversized frame; wait for a delimiter. */
        }
    } else {
        /* Insert an implicit zero only when another code follows. */
        if (testharness_state.rx_queue.cobs_code != 0xFFU) {
            if (testharness_state.rx_queue.cur_pos < TZEN_TH_MAX_PACKET_SIZE) {
                testharness_state.rx_queue.slots[write_idx].data[testharness_state.rx_queue.cur_pos++] = 0x00U;
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

/* CRC-16/CCITT-FALSE: poly 0x1021, init 0xFFFF, no reflection or final XOR. */
static uint16_t tzen_th_crc16(const uint8_t *data, size_t len)
{
    uint16_t crc = 0xFFFFU;

    for (size_t i = 0U; i < len; ++i) {
        crc ^= (uint16_t)((uint16_t)data[i] << 8U);
        for (uint8_t bit = 0U; bit < 8U; ++bit) {
            crc = (uint16_t)((crc & 0x8000U) != 0U
                                ? ((unsigned int)crc << 1U) ^ 0x1021U
                                : (unsigned int)crc << 1U);
        }
    }
    return crc;
}

void tzen_th_main_function(void)
{
    uint8_t read_idx = testharness_state.rx_queue.read_idx;

    /* Bound each call so a continuous producer cannot keep this task here. */
    for (size_t count = 0U; count < TZEN_TH_RX_SLOTS - 1U; ++count) {
        bool packet_available;
        TZEN_TH_ENTER_CRITICAL_SECTION();
        packet_available = read_idx != testharness_state.rx_queue.write_idx;
        TZEN_TH_EXIT_CRITICAL_SECTION();
        if (!packet_available) {
            break;
        }

        const uint8_t *data = testharness_state.rx_queue.slots[read_idx].data;
        size_t len = testharness_state.rx_queue.slots[read_idx].len;
        bool valid = false;

        if (len >= 2U) {
            size_t payload_len = len - 2U;
            uint16_t received_crc = (uint16_t)(((uint16_t)data[payload_len] << 8U)
                                             | data[payload_len + 1U]);
            valid = tzen_th_crc16(data, payload_len) == received_crc;
        }

        if (valid) {
            ++testharness_state.rx_valid_packets;
            /* Valid payload processing will be added here. */
        } else {
            ++testharness_state.rx_invalid_packets;
        }

        /* Release only after the last access to the slot's data and length. */
        read_idx = (uint8_t)((read_idx + 1U) % TZEN_TH_RX_SLOTS);
        TZEN_TH_ENTER_CRITICAL_SECTION();
        testharness_state.rx_queue.read_idx = read_idx;
        TZEN_TH_EXIT_CRITICAL_SECTION();
    }
}
