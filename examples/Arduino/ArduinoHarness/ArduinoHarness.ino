#include <Arduino.h>
#include "tzen.h"
#include "board.h"
extern "C" {
extern const TzenTestDescriptor_t g_test_table[];
extern const size_t g_test_count;
void example_led(bool enabled) { digitalWrite(LED_BUILTIN, enabled ? HIGH : LOW); }
bool example_led_read(void) { return digitalRead(LED_BUILTIN) == HIGH; }
uint32_t example_millis(void) { return millis(); }
}
static bool transport_send(const uint8_t *frame, size_t size, void *) {
    return Serial.write(frame, size) == size;
}
static uint32_t get_time(void *) { return millis(); }
void setup() {
    pinMode(LED_BUILTIN, OUTPUT);
    example_led(false);
    Serial.begin(115200);
    TzenConfig_t config = {};
    config.transport_send = transport_send;
    config.get_time_ms = get_time;
    if (!tzen_th_init(&config, g_test_table, g_test_count)) {
        // Keep the protocol stream free of unframed debug prints.
        while (true) { example_led(true); delay(100); example_led(false); delay(100); }
    }
}
void loop() {
    // Limit RX work so a continuously transmitting host cannot starve steps.
    for (unsigned int budget = 0; budget < 32 && Serial.available(); ++budget) {
        tzen_th_feed_b((uint8_t)Serial.read());
    }
    tzen_th_main_function();
    for (unsigned int worker = 0; worker < TZEN_TH_MAX_WORKERS; ++worker)
        tzen_th_worker_main_function((uint8_t)worker);
}
