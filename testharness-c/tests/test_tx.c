/*
 * Tzen
 * Author: L. Furcas
 * SPDX-License-Identifier: MPL-2.0
 */

/* Inspect RX diagnostics to verify the complete TX -> RX path. */
#include "../src/tzen.c"

#include <assert.h>
#include <stdio.h>
#include <string.h>

static struct {
    uint8_t frame[TZEN_TH_MAX_PACKET_SIZE + TZEN_TH_MAX_PACKET_SIZE / 254U + 3U];
    size_t len;
    size_t calls;
    bool fail;
} capture;

static bool send_frame(const uint8_t *frame, size_t len, void *user_data)
{
    assert(user_data == &capture);
    assert(len <= sizeof(capture.frame));
    memcpy(capture.frame, frame, len);
    capture.len = len;
    ++capture.calls;
    return !capture.fail;
}

/* Independent bitwise CRC and block decoder, rather than a TX/RX-only test
 * where both implementations could agree on the same wrong wire format. */
static uint16_t reference_crc(const uint8_t *payload, size_t len)
{
    uint16_t crc = 0xFFFFU;
    for (size_t i = 0U; i < len; ++i) {
        for (unsigned bit = 0U; bit < 8U; ++bit) {
            bool high = (crc & 0x8000U) != 0U;
            bool input = (payload[i] & (0x80U >> bit)) != 0U;
            crc = (uint16_t)(crc << 1U);
            if (high != input) crc ^= 0x1021U;
        }
    }
    return crc;
}

static void verify(const uint8_t *payload, size_t len)
{
    size_t calls = capture.calls;
    assert(tzen_th_send_packet(payload, len));
    assert(capture.calls == calls + 1U);
    assert(capture.frame[0] == 0U && capture.frame[capture.len - 1U] == 0U);
    uint8_t decoded[TZEN_TH_MAX_PACKET_SIZE];
    size_t count = 0U;
    size_t pos = 1U;
    while (pos < capture.len - 1U) {
        uint8_t code = capture.frame[pos++];
        assert(code != 0U);
        for (unsigned i = 1U; i < code; ++i) {
            assert(pos < capture.len - 1U && count < sizeof(decoded));
            assert(capture.frame[pos] != 0U);
            decoded[count++] = capture.frame[pos++];
        }
        if (code < 255U && pos < capture.len - 1U) {
            assert(count < sizeof(decoded));
            decoded[count++] = 0U;
        }
    }
    assert(count == len + 2U);
    if (len != 0U) assert(memcmp(decoded, payload, len) == 0);
    uint16_t crc = reference_crc(payload, len);
    assert(decoded[len] == (uint8_t)(crc >> 8U));
    assert(decoded[len + 1U] == (uint8_t)crc);

    size_t valid = testharness_state.rx_valid_packets;
    for (size_t i = 0U; i < capture.len; ++i) tzen_th_feed_b(capture.frame[i]);
    tzen_th_main_function();
    assert(testharness_state.rx_valid_packets == valid + 1U);
    assert(testharness_state.rx_invalid_packets == 0U);
}

int main(void)
{
    assert(!tzen_th_transport_ok());
    assert(!tzen_th_send_packet(NULL, 0U));
    TzenConfig_t cfg = {.send_bytes = send_frame, .user_data = &capture};
    assert(tzen_th_init(&cfg));
    cfg.send_bytes = NULL; /* init copies the transport settings. */
    verify((const uint8_t *)"123456789", 9U);
    const uint8_t expected[] = {0U, 12U, '1', '2', '3', '4', '5', '6', '7', '8', '9', 0x29U, 0xB1U, 0U};
    assert(capture.len == sizeof(expected));
    assert(memcmp(capture.frame, expected, sizeof(expected)) == 0);
    verify(NULL, 0U);

    uint8_t payload[TZEN_TH_MAX_PACKET_SIZE];
    for (unsigned pattern = 0U; pattern < 3U; ++pattern) {
        for (size_t i = 0U; i < sizeof(payload); ++i) {
            payload[i] = pattern == 0U ? 0U : (pattern == 1U ? 0xA5U : (uint8_t)i);
        }
        for (size_t len = 0U; len <= sizeof(payload) - 2U; ++len) verify(payload, len);
    }
    /* Search all one/two-byte values: exercises zero bytes in both CRC positions. */
    for (unsigned value = 0U; value <= 65535U; ++value) {
        payload[0] = (uint8_t)(value >> 8U);
        payload[1] = (uint8_t)value;
        verify(payload, 2U);
    }
    size_t calls = capture.calls;
    assert(!tzen_th_send_packet(NULL, 1U));
    assert(!tzen_th_send_packet(payload, sizeof(payload) - 1U));
    assert(!tzen_th_send_packet(payload, (size_t)-1));
    assert(capture.calls == calls && tzen_th_transport_ok());
    capture.fail = true;
    assert(!tzen_th_send_packet(payload, 1U));
    assert(capture.calls == calls + 1U && !tzen_th_transport_ok());
    capture.fail = false;
    assert(tzen_th_send_packet(payload, 1U));
    assert(!tzen_th_transport_ok()); /* Sticky until reinit. */
    assert(tzen_th_init(&cfg)); /* NULL transport remains valid for RX-only use. */
    assert(tzen_th_transport_ok());
    calls = capture.calls;
    assert(!tzen_th_send_packet(payload, 1U));
    assert(capture.calls == calls && tzen_th_transport_ok());
    puts("TX checks passed: wire vectors, COBS boundaries, CRC, RX round trips and failures.");
    return 0;
}
