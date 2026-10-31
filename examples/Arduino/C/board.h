#ifndef EXAMPLE_BOARD_H
#define EXAMPLE_BOARD_H
#include <stdbool.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
void example_led(bool enabled);
bool example_led_read(void);
uint32_t example_millis(void);
#ifdef __cplusplus
}
#endif
#endif
