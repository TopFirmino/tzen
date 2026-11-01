#include "tzen.h"

#include <pthread.h>
#include <sched.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

bool host_protocol_cases(void);

static bool producer_done;
static bool producer_ok;

static const uint8_t payload[] = "123456789";
static const uint8_t valid_frame[] = {
    0x00U, 0x0CU, '1', '2', '3', '4', '5', '6', '7', '8', '9', 0x29U, 0xB1U, 0x00U
};

/* The Slave transport consumes a complete frame in exactly one call. */
static bool slave_send(const uint8_t *frame, size_t len, void *user_data)
{
    FILE *slave_to_master = user_data;
    return fwrite(frame, 1U, len, slave_to_master) == len;
}

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
    FILE *master_to_slave = user_data;
    int byte;
    while ((byte = fgetc(master_to_slave)) != EOF) {
        tzen_th_feed_b((uint8_t)byte);
    }

    TZEN_TH_ENTER_CRITICAL_SECTION();
    producer_ok = !ferror(master_to_slave);
    producer_done = true;
    TZEN_TH_EXIT_CRITICAL_SECTION();
    return NULL;
}

int main(void)
{
    /* tmpfile opens buffered binary update streams (w+b), removed on close.
     * Direction changes use fflush/fseek; streams never have concurrent users. */
    FILE *master_to_slave = tmpfile();
    FILE *slave_to_master = tmpfile();
    int result = EXIT_FAILURE;
    pthread_t producer;

    if (master_to_slave == NULL || slave_to_master == NULL) {
        fputs("Failed to create binary temporary streams.\n", stderr);
        goto cleanup;
    }
    const TzenConfig_t cfg = {
        .send_bytes = slave_send,
        .user_data = slave_to_master
    };
    if (!tzen_th_init(&cfg)) {
        fputs("Test harness initialization failed.\n", stderr);
        goto cleanup;
    }

    /* Master sends a known CRC vector, then a corrupted copy. */
    uint8_t corrupt[sizeof(valid_frame)];
    memcpy(corrupt, valid_frame, sizeof(corrupt));
    corrupt[sizeof(corrupt) - 2U] ^= 1U;
    if (fwrite(valid_frame, 1U, sizeof(valid_frame), master_to_slave) != sizeof(valid_frame) ||
        fwrite(corrupt, 1U, sizeof(corrupt), master_to_slave) != sizeof(corrupt) ||
        fflush(master_to_slave) != 0 || fseek(master_to_slave, 0L, SEEK_SET) != 0) {
        fputs("Master write failed.\n", stderr);
        goto cleanup;
    }

    if (pthread_create(&producer, NULL, feed_packets, master_to_slave) != 0) {
        fputs("Failed to start the receive task.\n", stderr);
        goto cleanup;
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

    /* Send explicitly: RX command dispatch/automatic replies are not added yet.
     * Include a zero payload to verify COBS escaping as well as the CRC vector. */
    const uint8_t zero_payload[] = {0U};
    const uint8_t zero_frame[] = {0U, 1U, 3U, 0xE1U, 0xF0U, 0U};
    if (!producer_ok || !tzen_th_send_packet(payload, sizeof(payload) - 1U) ||
        !tzen_th_send_packet(zero_payload, sizeof(zero_payload)) ||
        !tzen_th_transport_ok() || fflush(slave_to_master) != 0 ||
        fseek(slave_to_master, 0L, SEEK_SET) != 0) {
        fputs("Slave transfer failed.\n", stderr);
        goto cleanup;
    }

    uint8_t received[sizeof(valid_frame) + sizeof(zero_frame)];
    if (fread(received, 1U, sizeof(received), slave_to_master) != sizeof(received) ||
        memcmp(received, valid_frame, sizeof(valid_frame)) != 0 ||
        memcmp(received + sizeof(valid_frame), zero_frame, sizeof(zero_frame)) != 0 ||
        fgetc(slave_to_master) != EOF || ferror(slave_to_master)) {
        fputs("Master verification failed: payload, COBS, CRC or frame length mismatch.\n", stderr);
        goto cleanup;
    }
    puts("Master/Slave buffered binary transfers passed: RX completed; TX COBS/CRC bytes verified.");
    if (!host_protocol_cases()) goto cleanup;
    result = EXIT_SUCCESS;

cleanup:
    if (master_to_slave != NULL && fclose(master_to_slave) != 0) result = EXIT_FAILURE;
    if (slave_to_master != NULL && fclose(slave_to_master) != 0) result = EXIT_FAILURE;
    return result;
}
