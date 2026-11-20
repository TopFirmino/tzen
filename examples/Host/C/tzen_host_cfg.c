/*
 * Tzen
 * Author: L. Furcas
 * SPDX-License-Identifier: MPL-2.0
 */

#include "tzen_host_cfg.h"
#include "testcases.h"
#include "host_io.h"

const TzenConfig_t host_configuration = {
    .send_bytes = host_send_bytes,
    .get_us = NULL,
    .user_data = NULL,
    .tests = host_tests,
    .num_tests = HOST_TEST_COUNT
};
