#include <Arduino.h>
#include "tzen.h"
#include "ttp.h"
#include "board.h"
extern "C" {
extern const th_test_descriptor_t g_test_table[];
extern const size_t g_test_count;
void example_led(bool enabled) { digitalWrite(LED_BUILTIN, enabled ? HIGH : LOW); }
bool example_led_read(void) { return digitalRead(LED_BUILTIN) == HIGH; }
uint32_t example_millis(void) { return millis(); }
}
static uint8_t body[TTP_MAX_FRAME_SIZE - 2];
static size_t body_size;
static bool in_frame, dropping;
static bool transport_send(const uint8_t *frame, size_t size, void *) {
    return Serial.write(frame, size) == size;
}
static uint32_t get_time(void *) { return millis(); }
void setup() {
    pinMode(LED_BUILTIN, OUTPUT);
    example_led(false);
    Serial.begin(115200);
    th_config_t config = {};
    config.transport_send = transport_send;
    config.get_time_ms = get_time;
    if (!th_init(&config, g_test_table, g_test_count)) {
        // Keep the protocol stream free of unframed debug prints.
        while (true) { example_led(true); delay(100); example_led(false); delay(100); }
    }
}
void loop() {
    // Limit RX work so a continuously transmitting host cannot starve steps.
    for (unsigned int budget = 0; budget < 32 && Serial.available(); ++budget) {
        uint8_t value = (uint8_t)Serial.read();
        if (value == 0) {
            if (in_frame && !dropping && body_size) th_on_rx_frame(body, body_size);
            body_size = 0; dropping = false; in_frame = true;
        } else if (in_frame && !dropping) {
            if (body_size < sizeof(body)) body[body_size++] = value;
            else { dropping = true; body_size = 0; }
        }
    }
    th_poll();
}
