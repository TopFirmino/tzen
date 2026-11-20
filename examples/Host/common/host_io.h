/*
 * Tzen
 * Author: L. Furcas
 * SPDX-License-Identifier: MPL-2.0
 */

#ifndef TZEN_HOST_IO_H
#define TZEN_HOST_IO_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

bool host_io_init(void);
/* Returns 1 for a byte, 0 on timeout, -1 at EOF/error. */
int host_read_byte(uint8_t *byte);
bool host_send_bytes(const uint8_t *frame, size_t len, void *user_data);

#endif
