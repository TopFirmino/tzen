/*
 * Tzen
 * Author: L. Furcas
 * SPDX-License-Identifier: MPL-2.0
 */

/*
    Description: Main Tzen implementation.

    Author: TopFirmino (L. Furcas)
    License: see LICENSE.md.
*/

#include "tzen.h"
#include "ttp.h"
#include <string.h>
#include <stdarg.h>
#include <stdio.h>

typedef struct {
    uint32_t run_id, test_index;
    bool ready, cancelled;
} TzenJob;

typedef struct {
    TzenContext_t ctx; /* Only the polling owner writes callback context. */
    TzenEngineState_t state;
    bool active, polling, started, finishing, terminal_queued;
    bool abort_requested, release_requested, sync_requested, in_step, contract_error;
    uint32_t sync_id;
    size_t reserved;
} TzenWorker;


/*
*   STATIC VARIABLES
*/

/* Current test harness state (work in progress). */
static struct tzen_state_s {
    TzenSendBytesFn_t send_bytes;
    void *user_data;
    bool transport_ok;
    const TzenTestDescriptor_t *tests;
    size_t num_tests;
    bool initialized;
    struct {
        TzenJob slots[TZEN_TH_WORKER_QUEUE_DEPTH];
        size_t read_idx, write_idx, count;
    } jobs;
    struct {
        struct {
            TargetToHost message;
            bool terminal;
            uint8_t worker_id;
        } slots[TZEN_TH_RESULT_QUEUE_DEPTH];
        size_t read_idx, write_idx, count, reserved;
    } results;
    TzenWorker workers[TZEN_TH_MAX_WORKERS];
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

/* Reset transport and RX state before starting callers.
 * Initialization requires the producer and consumer to be stopped. */
bool tzen_th_init(const TzenConfig_t *cfg)
{
    /* All callers are stopped: do not silently lose unfinished executions. */
    if (testharness_state.initialized) {
        if (testharness_state.jobs.count != 0U || testharness_state.results.count != 0U) return false;
        for (size_t i = 0U; i < TZEN_TH_MAX_WORKERS; ++i)
            if (testharness_state.workers[i].active || testharness_state.workers[i].polling) return false;
    }
    if (cfg == NULL || (cfg->num_tests != 0U && cfg->tests == NULL) ||
        cfg->num_tests > UINT32_MAX) {
        return false;
    }
    /* Reject names that cannot be represented without truncation on the wire.
     * Metadata-only descriptors may have zero steps. */
    for (size_t i = 0U; i < cfg->num_tests; ++i) {
        if (cfg->tests[i].name == NULL) return false;
        size_t len = 0U;
        while (len < sizeof(((GetTestInfoResp *)0)->name) && cfg->tests[i].name[len] != '\0') ++len;
        if (len == sizeof(((GetTestInfoResp *)0)->name)) return false;
        if (cfg->tests[i].num_steps != 0U && cfg->tests[i].steps == NULL) return false;
        for (uint32_t step = 0U; step < cfg->tests[i].num_steps; ++step)
            if (cfg->tests[i].steps[step] == NULL) return false;
    }

    testharness_state.tests = cfg->tests;
    testharness_state.num_tests = cfg->num_tests;
    testharness_state.send_bytes = cfg->send_bytes;
    testharness_state.user_data = cfg->user_data;
    testharness_state.transport_ok = true;
    memset(&testharness_state.jobs, 0, sizeof(testharness_state.jobs));
    memset(&testharness_state.results, 0, sizeof(testharness_state.results));
    memset(testharness_state.workers, 0, sizeof(testharness_state.workers));
    testharness_state.initialized = true;
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
            TZEN_TH_ENTER_CRITICAL_SECTION_RX_QUEUE();
            if (next_w != testharness_state.rx_queue.read_idx) {
                testharness_state.rx_queue.slots[write_idx].len = testharness_state.rx_queue.cur_pos;
                /* Publish data and length together to the consumer. */
                testharness_state.rx_queue.write_idx = next_w;
            }
            TZEN_TH_EXIT_CRITICAL_SECTION_RX_QUEUE();
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

/**
 * Send 0x00 | COBS(payload + CRC16-CCITT-FALSE) | 0x00 in one callback.
 * CRC covers only the payload; its two bytes are appended high byte first.
 * Maximum payload length is TZEN_TH_MAX_PACKET_SIZE - 2. Empty payloads are
 * allowed (NULL is valid only with len == 0). Payload must stay valid until
 * return. Returns false for invalid arguments, absent callback, or TX failure.
 * Invalid arguments/absent callback send nothing and do not change TX status.
 * No retries are made; later sends remain allowed after a callback failure.
 * Call after init from task context. Whole callbacks are serialized by the TX
 * hooks; status is protected by the worker-queue hooks. Uses bounded stack.
 */
static bool tzen_th_send_packet(const uint8_t *payload, size_t len)
{
    /* Worst case: one code per 254 decoded bytes, an extra code, delimiters.
     * Encode payload and CRC directly; no second decoded packet buffer. */
    uint8_t frame[TZEN_TH_MAX_PACKET_SIZE + TZEN_TH_MAX_PACKET_SIZE / 254U + 3U];
    size_t code_idx = 1U;
    size_t pos = 2U;
    uint8_t code = 1U;

    if (testharness_state.send_bytes == NULL ||
        (payload == NULL && len != 0U) || len > TZEN_TH_MAX_PACKET_SIZE - 2U) {
        return false;
    }

    uint16_t crc = tzen_th_crc16(payload, len);
    frame[0] = 0U;
    for (size_t i = 0U; i < len + 2U; ++i) {
        uint8_t byte = i < len ? payload[i]
                              : (i == len ? (uint8_t)(crc >> 8U) : (uint8_t)crc);
        if (byte == 0U) {
            frame[code_idx] = code;
            code_idx = pos++;
            code = 1U;
        } else {
            frame[pos++] = byte;
            if (++code == 0xFFU) {
                frame[code_idx] = code;
                code_idx = pos++;
                code = 1U;
            }
        }
    }
    frame[code_idx] = code;
    frame[pos++] = 0U;

    TZEN_TH_ENTER_CRITICAL_SECTION_TX();
    bool sent = testharness_state.send_bytes(frame, pos, testharness_state.user_data);
    TZEN_TH_EXIT_CRITICAL_SECTION_TX();
    if (!sent) {
        TZEN_TH_ENTER_CRITICAL_SECTION_WORKER_QUEUE();
        testharness_state.transport_ok = false;
        TZEN_TH_EXIT_CRITICAL_SECTION_WORKER_QUEUE();
    }
    return sent;
}

bool tzen_th_transport_ok(void)
{
    TZEN_TH_ENTER_CRITICAL_SECTION_WORKER_QUEUE();
    bool ok = testharness_state.transport_ok;
    TZEN_TH_EXIT_CRITICAL_SECTION_WORKER_QUEUE();
    return ok;
}

/* All helpers suffixed _locked require the worker-queue critical section. */
static TzenWorker *tzen_th_find_run_locked(uint32_t run_id)
{
    for (size_t i = 0U; i < TZEN_TH_MAX_WORKERS; ++i)
        if (testharness_state.workers[i].active && testharness_state.workers[i].ctx.run_id == run_id)
            return &testharness_state.workers[i];
    return NULL;
}

static TzenWorker *tzen_th_find_context_locked(const TzenContext_t *ctx)
{
    for (size_t i = 0U; i < TZEN_TH_MAX_WORKERS; ++i)
        if (ctx == &testharness_state.workers[i].ctx && testharness_state.workers[i].active &&
            testharness_state.workers[i].polling && testharness_state.workers[i].started)
            return &testharness_state.workers[i];
    return NULL;
}

static bool tzen_th_send_message(const TargetToHost *message)
{
    uint8_t encoded[TTP_MAX_MESSAGE_SIZE];
    size_t len = 0U;
    if (Ttp_EncodeTargetToHost(message, encoded, sizeof(encoded), &len) != TTP_STATUS_OK ||
        len > TZEN_TH_MAX_PACKET_SIZE - 2U) {
        TZEN_TH_ENTER_CRITICAL_SECTION_WORKER_QUEUE();
        testharness_state.transport_ok = false;
        TZEN_TH_EXIT_CRITICAL_SECTION_WORKER_QUEUE();
        return false;
    }
    return tzen_th_send_packet(encoded, len);
}

static ResultCode tzen_th_control(const HostToTarget *command, size_t *ready_slot)
{
    ResultCode status = ResultCode_RESULT_OK;
    TZEN_TH_ENTER_CRITICAL_SECTION_WORKER_QUEUE();
    if (command->which_cmd == HostToTarget_execute_test_tag) {
        uint32_t run_id = command->cmd.execute_test.run_id;
        uint32_t index = command->cmd.execute_test.index;
        bool duplicate = tzen_th_find_run_locked(run_id) != NULL;
        for (size_t i = 0U, pos = testharness_state.jobs.read_idx; i < testharness_state.jobs.count; ++i) {
            if (testharness_state.jobs.slots[pos].run_id == run_id) duplicate = true;
            pos = (pos + 1U) % TZEN_TH_WORKER_QUEUE_DEPTH;
        }
        if (!testharness_state.transport_ok || testharness_state.send_bytes == NULL)
            status = ResultCode_RESULT_ERR_INVALID;
        else if (duplicate || testharness_state.jobs.count == TZEN_TH_WORKER_QUEUE_DEPTH)
            status = ResultCode_RESULT_ERR_BUSY;
        else if (index >= testharness_state.num_tests) status = ResultCode_RESULT_ERR_INDEX;
        else if (testharness_state.tests[index].num_steps == 0U) status = ResultCode_RESULT_ERR_INVALID;
        else {
            size_t pos = testharness_state.jobs.write_idx;
            testharness_state.jobs.slots[pos] = (TzenJob){.run_id = run_id, .test_index = index};
            testharness_state.jobs.write_idx = (pos + 1U) % TZEN_TH_WORKER_QUEUE_DEPTH;
            ++testharness_state.jobs.count;
            *ready_slot = pos; /* Publish to workers only after sending acceptance. */
        }
    } else if (command->which_cmd == HostToTarget_abort_test_tag) {
        TzenWorker *worker = tzen_th_find_run_locked(command->cmd.abort_test.run_id);
        status = ResultCode_RESULT_ERR_NOT_FOUND;
        if (worker != NULL && !worker->finishing && !worker->abort_requested) {
            worker->abort_requested = true;
            status = ResultCode_RESULT_OK;
        } else if (worker == NULL) {
            for (size_t i = 0U, pos = testharness_state.jobs.read_idx; i < testharness_state.jobs.count; ++i) {
                TzenJob *job = &testharness_state.jobs.slots[pos];
                if (job->run_id == command->cmd.abort_test.run_id && !job->cancelled) {
                    job->cancelled = true;
                    status = ResultCode_RESULT_OK;
                    break;
                }
                pos = (pos + 1U) % TZEN_TH_WORKER_QUEUE_DEPTH;
            }
        }
    } else {
        TzenWorker *worker = tzen_th_find_run_locked(command->cmd.sync_release.run_id);
        if (worker == NULL || worker->finishing || worker->abort_requested ||
            worker->state != TZEN_ENGINE_WAITING_SYNC || worker->release_requested ||
            worker->sync_id != command->cmd.sync_release.sync_id) status = ResultCode_RESULT_ERR_NOT_FOUND;
        else worker->release_requested = true;
    }
    TZEN_TH_EXIT_CRITICAL_SECTION_WORKER_QUEUE();
    return status;
}

static void tzen_th_dispatch(const uint8_t *payload, size_t len)
{
    HostToTarget command = HostToTarget_init_zero;
    TargetToHost response = TargetToHost_init_zero;
    size_t ready_slot = TZEN_TH_WORKER_QUEUE_DEPTH;

    if (Ttp_DecodeHostToTarget(&command, payload, len) != TTP_STATUS_OK || command.seq_id == 0U) {
        return;
    }
    response.seq_id = command.seq_id;
    switch (command.which_cmd) {
    case HostToTarget_get_tests_tag:
        response.which_payload = TargetToHost_tests_count_tag;
        response.payload.tests_count.total_tests = (uint32_t)testharness_state.num_tests;
        break;
    case HostToTarget_get_test_info_tag: {
        uint32_t index = command.cmd.get_test_info.index;
        if (index >= testharness_state.num_tests) {
            response.status = ResultCode_RESULT_ERR_INDEX;
            break;
        }
        const TzenTestDescriptor_t *test = &testharness_state.tests[index];
        response.which_payload = TargetToHost_test_info_tag;
        response.payload.test_info.index = index;
        response.payload.test_info.total_steps = test->num_steps;
        memcpy(response.payload.test_info.name, test->name, strlen(test->name) + 1U);
        break;
    }
    case HostToTarget_execute_test_tag:
    case HostToTarget_abort_test_tag:
    case HostToTarget_sync_release_tag:
        response.status = tzen_th_control(&command, &ready_slot);
        break;
    default:
        response.status = ResultCode_RESULT_ERR_INVALID;
        break;
    }
    bool sent = tzen_th_send_message(&response);
    if (ready_slot != TZEN_TH_WORKER_QUEUE_DEPTH) {
        TZEN_TH_ENTER_CRITICAL_SECTION_WORKER_QUEUE();
        testharness_state.jobs.slots[ready_slot].cancelled = !sent;
        testharness_state.jobs.slots[ready_slot].ready = true;
        TZEN_TH_EXIT_CRITICAL_SECTION_WORKER_QUEUE();
    }
}

static void tzen_th_flush_results(void);

void tzen_th_main_function(void)
{
    if (!testharness_state.initialized) return;
    uint8_t read_idx = testharness_state.rx_queue.read_idx;

    /* Bound each call so a continuous producer cannot keep this task here. */
    for (size_t count = 0U; count < TZEN_TH_RX_SLOTS - 1U; ++count) {
        bool packet_available;
        TZEN_TH_ENTER_CRITICAL_SECTION_RX_QUEUE();
        packet_available = read_idx != testharness_state.rx_queue.write_idx;
        TZEN_TH_EXIT_CRITICAL_SECTION_RX_QUEUE();
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
            tzen_th_dispatch(data, len - 2U);
        } else {
            ++testharness_state.rx_invalid_packets;
        }

        /* Release only after the last access to the slot's data and length. */
        read_idx = (uint8_t)((read_idx + 1U) % TZEN_TH_RX_SLOTS);
        TZEN_TH_ENTER_CRITICAL_SECTION_RX_QUEUE();
        testharness_state.rx_queue.read_idx = read_idx;
        TZEN_TH_EXIT_CRITICAL_SECTION_RX_QUEUE();
    }
    tzen_th_flush_results();
}

/* The result ring owns copies; it never retains callback stack pointers. */
static void tzen_th_result_locked(const TargetToHost *message, TzenWorker *worker, bool terminal)
{
    size_t pos = testharness_state.results.write_idx;
    testharness_state.results.slots[pos].message = *message;
    testharness_state.results.slots[pos].terminal = terminal;
    testharness_state.results.slots[pos].worker_id = worker != NULL ? (uint8_t)(worker - testharness_state.workers) : 0U;
    testharness_state.results.write_idx = (pos + 1U) % TZEN_TH_RESULT_QUEUE_DEPTH;
    ++testharness_state.results.count;
}

static TargetToHost tzen_th_event(const TzenWorker *worker, pb_size_t tag)
{
    TargetToHost message = TargetToHost_init_zero;
    message.which_payload = TargetToHost_test_event_tag;
    message.payload.test_event.run_id = worker->ctx.run_id;
    message.payload.test_event.test_index = worker->ctx.test_index;
    message.payload.test_event.which_event = tag;
    return message;
}

/* A polling worker exclusively owns its reservation, even while a callback is
 * running. Unbounded application logging cannot consume these two slots. */
static void tzen_th_critical_result_locked(TzenWorker *worker, const TargetToHost *message, bool terminal)
{
    --worker->reserved;
    --testharness_state.results.reserved;
    tzen_th_result_locked(message, worker, terminal);
}

static void tzen_th_flush_results(void)
{
    for (size_t budget = 0U; budget < TZEN_TH_RESULT_QUEUE_DEPTH; ++budget) {
        TargetToHost message;
        bool terminal, available, deliver;
        uint8_t worker_id = 0U;
        TZEN_TH_ENTER_CRITICAL_SECTION_WORKER_QUEUE();
        available = testharness_state.results.count != 0U;
        deliver = testharness_state.transport_ok;
        if (available) {
            size_t pos = testharness_state.results.read_idx;
            message = testharness_state.results.slots[pos].message;
            terminal = testharness_state.results.slots[pos].terminal;
            worker_id = testharness_state.results.slots[pos].worker_id;
            testharness_state.results.read_idx = (pos + 1U) % TZEN_TH_RESULT_QUEUE_DEPTH;
            --testharness_state.results.count;
        } else terminal = false;
        TZEN_TH_EXIT_CRITICAL_SECTION_WORKER_QUEUE();
        if (!available) break;
        if (deliver) (void)tzen_th_send_message(&message);
        if (terminal) {
            TZEN_TH_ENTER_CRITICAL_SECTION_WORKER_QUEUE();
            /* Keep the ID reserved through the terminal transport attempt. The
             * polling owner releases its guard separately; never clear it here. */
            testharness_state.workers[worker_id].active = false;
            if (!testharness_state.workers[worker_id].polling)
                testharness_state.workers[worker_id].terminal_queued = false;
            TZEN_TH_EXIT_CRITICAL_SECTION_WORKER_QUEUE();
        }
    }
}

static bool tzen_th_aborting(TzenWorker *worker)
{
    TZEN_TH_ENTER_CRITICAL_SECTION_WORKER_QUEUE();
    bool aborting = worker->abort_requested || !testharness_state.transport_ok;
    TZEN_TH_EXIT_CRITICAL_SECTION_WORKER_QUEUE();
    return aborting;
}

static void tzen_th_finish(TzenWorker *worker, TzenTestStatus_t status)
{
    TZEN_TH_ENTER_CRITICAL_SECTION_WORKER_QUEUE();
    if (worker->abort_requested || !testharness_state.transport_ok) status = TZEN_TEST_STATUS_ABORTED;
    worker->finishing = true; /* Linearization point: later aborts are rejected. */
    TZEN_TH_EXIT_CRITICAL_SECTION_WORKER_QUEUE();

    const TzenTestDescriptor_t *test = &testharness_state.tests[worker->ctx.test_index];
    if (worker->started && test->on_teardown != NULL) test->on_teardown(&worker->ctx, status);

    TargetToHost message = tzen_th_event(worker, TestEvent_finished_tag);
    message.payload.test_event.event.finished.status = (TestFinishedEvent_Status)status;
    TZEN_TH_ENTER_CRITICAL_SECTION_WORKER_QUEUE();
    tzen_th_critical_result_locked(worker, &message, true);
    worker->terminal_queued = true;
    worker->state = TZEN_ENGINE_IDLE;
    TZEN_TH_EXIT_CRITICAL_SECTION_WORKER_QUEUE();
}

static void tzen_th_step_result(TzenWorker *worker, bool success)
{
    TargetToHost message = tzen_th_event(worker, TestEvent_step_tag);
    message.payload.test_event.event.step.step_number = worker->ctx.current_step + 1U;
    message.payload.test_event.event.step.success = success;
    TZEN_TH_ENTER_CRITICAL_SECTION_WORKER_QUEUE();
    tzen_th_critical_result_locked(worker, &message, false);
    TZEN_TH_EXIT_CRITICAL_SECTION_WORKER_QUEUE();
}

static void tzen_th_advance(TzenWorker *worker)
{
    ++worker->ctx.current_step;
    worker->ctx.step_Iterations = 0U;
    TZEN_TH_ENTER_CRITICAL_SECTION_WORKER_QUEUE();
    worker->sync_requested = false;
    worker->release_requested = false;
    worker->state = TZEN_ENGINE_RUNNING_STEP;
    TZEN_TH_EXIT_CRITICAL_SECTION_WORKER_QUEUE();
    if (worker->ctx.current_step == testharness_state.tests[worker->ctx.test_index].num_steps)
        tzen_th_finish(worker, TZEN_TEST_STATUS_SUCCESS);
}

void tzen_th_worker_main_function(uint8_t worker_id)
{
    if (!testharness_state.initialized || worker_id >= TZEN_TH_MAX_WORKERS) return;
    TzenWorker *worker = &testharness_state.workers[worker_id];
    bool starting = false, cancelled = false, released = false, runnable = false;

    TZEN_TH_ENTER_CRITICAL_SECTION_WORKER_QUEUE();
    bool pending = testharness_state.jobs.count != 0U &&
        testharness_state.jobs.slots[testharness_state.jobs.read_idx].ready;
    bool waiting = worker->active && worker->state == TZEN_ENGINE_WAITING_SYNC &&
        !worker->abort_requested && !worker->release_requested && testharness_state.transport_ok;
    if (!worker->polling && !worker->terminal_queued && !waiting && (worker->active || pending) &&
        testharness_state.results.count + testharness_state.results.reserved <= TZEN_TH_RESULT_QUEUE_DEPTH - 2U) {
        if (!worker->active) {
            size_t pos = testharness_state.jobs.read_idx;
            TzenJob job = testharness_state.jobs.slots[pos];
            testharness_state.jobs.read_idx = (pos + 1U) % TZEN_TH_WORKER_QUEUE_DEPTH;
            --testharness_state.jobs.count;
            memset(worker, 0, sizeof(*worker));
            worker->ctx.run_id = job.run_id;
            worker->ctx.test_index = job.test_index;
            worker->active = true;
            worker->state = TZEN_ENGINE_RUNNING_STEP;
            cancelled = job.cancelled;
            starting = true;
        }
        worker->polling = true;
        worker->reserved = 2U;
        testharness_state.results.reserved += 2U;
        released = worker->release_requested;
        worker->release_requested = false;
        if (released) worker->state = TZEN_ENGINE_RUNNING_STEP;
        runnable = true;
    }
    TZEN_TH_EXIT_CRITICAL_SECTION_WORKER_QUEUE();
    if (!runnable) return;

    if (cancelled || tzen_th_aborting(worker)) {
        tzen_th_finish(worker, TZEN_TEST_STATUS_ABORTED);
        goto done;
    }
    const TzenTestDescriptor_t *test = &testharness_state.tests[worker->ctx.test_index];
    if (starting) {
        /* started is read by context utilities under the queue lock. */
        TZEN_TH_ENTER_CRITICAL_SECTION_WORKER_QUEUE();
        worker->started = true;
        TZEN_TH_EXIT_CRITICAL_SECTION_WORKER_QUEUE();
        bool setup_ok = test->on_setup == NULL || test->on_setup(&worker->ctx);
        if (!setup_ok || tzen_th_aborting(worker)) {
            tzen_th_finish(worker, setup_ok ? TZEN_TEST_STATUS_ABORTED : TZEN_TEST_STATUS_FAIL);
            goto done;
        }
    }
    if (released) {
        tzen_th_step_result(worker, true);
        tzen_th_advance(worker);
        goto done; /* Release completes the waiting step; next step is next poll. */
    }

    TZEN_TH_ENTER_CRITICAL_SECTION_WORKER_QUEUE();
    worker->sync_requested = false;
    worker->contract_error = false;
    worker->in_step = true;
    TZEN_TH_EXIT_CRITICAL_SECTION_WORKER_QUEUE();
    TzenStepResult_t result = test->steps[worker->ctx.current_step](&worker->ctx);
    TZEN_TH_ENTER_CRITICAL_SECTION_WORKER_QUEUE();
    worker->in_step = false;
    bool sync_requested = worker->sync_requested;
    bool contract_error = worker->contract_error;
    TZEN_TH_EXIT_CRITICAL_SECTION_WORKER_QUEUE();
    if (tzen_th_aborting(worker)) {
        tzen_th_finish(worker, TZEN_TEST_STATUS_ABORTED);
        goto done;
    }
    if (contract_error || (sync_requested != (result == TZEN_STEP_WAIT_SYNC))) result = TZEN_STEP_FAIL;
    switch (result) {
    case TZEN_STEP_PASS_NEXT:
        tzen_th_step_result(worker, true);
        tzen_th_advance(worker);
        break;
    case TZEN_STEP_DONE_PASS:
        tzen_th_step_result(worker, true);
        tzen_th_finish(worker, TZEN_TEST_STATUS_SUCCESS);
        break;
    case TZEN_STEP_YIELD:
        if (worker->ctx.step_Iterations != UINT32_MAX) ++worker->ctx.step_Iterations;
        break;
    case TZEN_STEP_WAIT_SYNC: {
        TargetToHost message = tzen_th_event(worker, TestEvent_sync_tag);
        message.payload.test_event.event.sync.sync_id = worker->ctx.pending_sync_id;
        TZEN_TH_ENTER_CRITICAL_SECTION_WORKER_QUEUE();
        tzen_th_critical_result_locked(worker, &message, false);
        worker->state = TZEN_ENGINE_WAITING_SYNC;
        TZEN_TH_EXIT_CRITICAL_SECTION_WORKER_QUEUE();
        break;
    }
    default:
        tzen_th_step_result(worker, false);
        tzen_th_finish(worker, TZEN_TEST_STATUS_FAIL);
        break;
    }

done:
    TZEN_TH_ENTER_CRITICAL_SECTION_WORKER_QUEUE();
    testharness_state.results.reserved -= worker->reserved;
    worker->reserved = 0U;
    worker->polling = false;
    /* Main may already have transmitted the terminal result. */
    if (!worker->active) worker->terminal_queued = false;
    TZEN_TH_EXIT_CRITICAL_SECTION_WORKER_QUEUE();
}

void tzen_sync(TzenContext_t *ctx, uint32_t sync_id)
{
    TZEN_TH_ENTER_CRITICAL_SECTION_WORKER_QUEUE();
    TzenWorker *worker = tzen_th_find_context_locked(ctx);
    if (worker != NULL && worker->in_step) {
        if (worker->sync_requested) worker->contract_error = true;
        worker->sync_requested = true;
        worker->sync_id = sync_id;
        worker->ctx.pending_sync_id = sync_id;
    }
    TZEN_TH_EXIT_CRITICAL_SECTION_WORKER_QUEUE();
}

bool tzen_log(TzenContext_t *ctx, TzenLogLevel_t level, const char *text)
{
    TargetToHost message = TargetToHost_init_zero;
    if (text == NULL || level < TZEN_LOG_INFO || level > TZEN_LOG_ERROR) return false;
    size_t len = 0U;
    while (len < sizeof(message.payload.log.message) && text[len] != '\0') ++len;
    if (len == sizeof(message.payload.log.message)) return false;
    message.which_payload = TargetToHost_log_tag;
    message.payload.log.level = (LogEvent_Level)level;
    memcpy(message.payload.log.message, text, len + 1U);
    bool queued = false;
    TZEN_TH_ENTER_CRITICAL_SECTION_WORKER_QUEUE();
    TzenWorker *worker = tzen_th_find_context_locked(ctx);
    if (worker != NULL && !worker->terminal_queued && testharness_state.transport_ok &&
        testharness_state.results.count + testharness_state.results.reserved < TZEN_TH_RESULT_QUEUE_DEPTH) {
        message.payload.log.source = TZEN_SOURCE_TEST;
        message.payload.log.scope = LogEvent_Scope_EXECUTION;
        message.payload.log.run_id = worker->ctx.run_id;
        message.payload.log.test_index = worker->ctx.test_index;
        tzen_th_result_locked(&message, worker, false);
        queued = true;
    }
    TZEN_TH_EXIT_CRITICAL_SECTION_WORKER_QUEUE();
    return queued;
}

bool tzen_emit_log(uint32_t source, const TzenExecutionRef_t *execution,
                   TzenLogLevel_t level, const char *text)
{
    TargetToHost message = TargetToHost_init_zero;
    if (text == NULL || level < TZEN_LOG_INFO || level > TZEN_LOG_ERROR ||
        (source == TZEN_SOURCE_TEST && execution == NULL)) return false;
    size_t len = 0U;
    while (len < sizeof(message.payload.log.message) && text[len] != '\0') ++len;
    if (len == sizeof(message.payload.log.message)) return false;
    message.which_payload = TargetToHost_log_tag;
    message.payload.log.level = (LogEvent_Level)level;
    message.payload.log.source = source;
    message.payload.log.scope = execution == NULL ? LogEvent_Scope_GLOBAL : LogEvent_Scope_EXECUTION;
    if (execution != NULL) {
        message.payload.log.run_id = execution->run_id;
        message.payload.log.test_index = execution->test_index;
    }
    memcpy(message.payload.log.message, text, len + 1U);
    bool queued = false;
    TZEN_TH_ENTER_CRITICAL_SECTION_WORKER_QUEUE();
    if (testharness_state.initialized && testharness_state.send_bytes != NULL &&
        testharness_state.transport_ok && testharness_state.results.count +
        testharness_state.results.reserved < TZEN_TH_RESULT_QUEUE_DEPTH) {
        tzen_th_result_locked(&message, NULL, false);
        queued = true;
    }
    TZEN_TH_EXIT_CRITICAL_SECTION_WORKER_QUEUE();
    return queued;
}

bool tzen_logf(TzenContext_t *ctx, TzenLogLevel_t level, const char *fmt, ...)
{
    char text[sizeof(((LogEvent *)0)->message)];
    if (fmt == NULL) return false;
    va_list args;
    va_start(args, fmt);
    int len = vsnprintf(text, sizeof(text), fmt, args);
    va_end(args);
    if (len < 0 || (size_t)len >= sizeof(text)) return false;
    return tzen_log(ctx, level, text);
}

static TzenEngineState_t tzen_th_state_locked(const TzenWorker *worker)
{
    if (!worker->active) return TZEN_ENGINE_IDLE;
    if (worker->terminal_queued || worker->finishing || worker->abort_requested ||
        worker->release_requested || !testharness_state.transport_ok) return TZEN_ENGINE_RUNNING_STEP;
    return worker->state;
}

TzenEngineState_t tzen_th_worker_get_state(uint8_t worker_id)
{
    if (worker_id >= TZEN_TH_MAX_WORKERS) return TZEN_ENGINE_IDLE;
    TZEN_TH_ENTER_CRITICAL_SECTION_WORKER_QUEUE();
    TzenEngineState_t state = tzen_th_state_locked(&testharness_state.workers[worker_id]);
    TZEN_TH_EXIT_CRITICAL_SECTION_WORKER_QUEUE();
    return state;
}

TzenEngineState_t tzen_get_state(void)
{
    TzenEngineState_t state = TZEN_ENGINE_IDLE;
    TZEN_TH_ENTER_CRITICAL_SECTION_WORKER_QUEUE();
    if (testharness_state.jobs.count != 0U || testharness_state.results.count != 0U)
        state = TZEN_ENGINE_RUNNING_STEP;
    for (size_t i = 0U; i < TZEN_TH_MAX_WORKERS && state != TZEN_ENGINE_RUNNING_STEP; ++i) {
        TzenEngineState_t worker_state = tzen_th_state_locked(&testharness_state.workers[i]);
        if (worker_state != TZEN_ENGINE_IDLE) state = worker_state;
    }
    TZEN_TH_EXIT_CRITICAL_SECTION_WORKER_QUEUE();
    return state;
}
