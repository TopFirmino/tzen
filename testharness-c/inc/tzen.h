/*
    Description: Header file for tzen testharness API.

    Author: TopFirmino (L. Furcas)
    License: see LICENSE.md.
*/

#ifndef TZEN_H
#define TZEN_H

#include "tzen_context.h"

#ifdef __cplusplus
extern "C" {
#endif

// ============================================================================
// 1. ENGINE API (called by the application, receive driver, or RTOS task)
// ============================================================================

/**
 * Reset RX and transport status. Returns false if cfg is NULL.
 * Copies transport settings and the table pointer/count; cfg may expire.
 * Rejects a missing nonempty table, count above UINT32_MAX, NULL names, or
 * names longer than 31 bytes. Empty tables/names are permitted.
 * Nonzero step counts require non-NULL step arrays/callbacks. Zero-step entries
 * are discoverable but cannot execute. Rejects reinit with pending jobs/results
 * or active workers. get_us is reserved. Call with all callers stopped.
 */
bool tzen_th_init(const TzenConfig_t *cfg);

/**
 * Feed one received byte from a single producer, in arrival order.
 * Decodes COBS directly into the current RX slot. Slots hold decoded payloads,
 * including CRC bytes, with capacity TZEN_TH_MAX_PACKET_SIZE each.
 * A 0x00 delimiter publishes a nonempty, complete frame if space is available.
 * Usable queue capacity is TZEN_TH_RX_SLOTS - 1 frames; a full queue drops
 * the newly completed frame. Oversized frames are dropped until a delimiter.
 * CRC validation is left to tzen_th_main_function.
 * Call tzen_th_init before starting either task. One producer task may run
 * concurrently with one consumer task calling tzen_th_main_function.
 * Concurrent callers must configure TZEN_TH_ENTER_CRITICAL_SECTION and
 * TZEN_TH_EXIT_CRITICAL_SECTION in tzen_cfg.h or the application's build.
 * The default hooks do nothing and require serialized calls (one task).
 * ISR use requires ISR-safe hooks; task mutexes are not suitable for an ISR.
 */
void tzen_th_feed_b(uint8_t byte);

/**
 * Process up to TZEN_TH_RX_SLOTS - 1 queued packets per call.
 * Verify CRC-16/CCITT-FALSE over the payload, excluding the final two CRC
 * bytes (high byte first). Missing or invalid CRC trailers are discarded
 * without a response. Decode protobuf using the public TTP API after CRC.
 * Malformed protobuf and sequence ID zero receive no reply. GetTests and
 * GetTestInfo return metadata; invalid indices return ERR_INDEX. Execute queues
 * a run; duplicate queued/active IDs or a full queue return ERR_BUSY. Abort
 * and SyncRelease route by run_id; absent/already finished runs or wrong sync
 * IDs return ERR_NOT_FOUND. Main drains worker events/results and alone sends
 * protocol replies/events. Keep polling main while workers are running.
 * Call from one consumer task only; it may run concurrently with feed_b.
 */
void tzen_th_main_function(void);

/**
 * Poll the protected request queue and execute at most one step callback.
 * Each worker has its own context/scratchpad. Calls on different worker IDs may
 * run on different threads/cores with suitable worker-queue hooks. Overlapping
 * calls on the same ID are ignored. Callbacks run outside all queue locks.
 * Event queue backpressure pauses polling before executing user code. Workers
 * enqueue results/logs; main transmits them. A transport failure causes cleanup
 * on subsequent worker polls. Setup failure still receives exactly one teardown;
 * a cancelled queued run receives neither setup nor teardown. Releasing a sync
 * completes its step; the next step runs on a subsequent poll.
 *
 * @param worker_id Worker index (0 .. TZEN_TH_MAX_WORKERS - 1).
 */
void tzen_th_worker_main_function(uint8_t worker_id);

/* True after init until transport/internal protocol encoding failure; reset by reinit.
 * False before the first init. Workers abort/clean up after transport failure. */
bool tzen_th_transport_ok(void);

/**
 * @brief Aggregate state: RUNNING_STEP if work/results are pending, otherwise
 * WAITING_SYNC if a worker is waiting, otherwise IDLE.
 * tzen_th_worker_get_state reports the state of an individual worker.
 * These are synchronized snapshots, not scheduling notifications.
 */
TzenEngineState_t tzen_get_state(void);
TzenEngineState_t tzen_th_worker_get_state(uint8_t worker_id);

// ============================================================================
// 2. STEP UTILITIES (for static C tests and future Berry bindings)
// ============================================================================

/* Step results are emitted internally from the returned TzenStepResult_t.
 * YIELD emits no result; WAIT_SYNC completes on matching release.
 * Testcases use tzen_log/tzen_logf for explanatory text. */

/**
 * @brief Request a synchronization point for this context/run.
 * Call exactly once from the step, then return TZEN_STEP_WAIT_SYNC. A SyncWait
 * event is queued only after that return. Contract violations fail the step.
 *
 * @param ctx     Test context.
 * @param sync_id Numeric synchronization ID expected in SyncRelease.
 */
void tzen_sync(TzenContext_t *ctx, uint32_t sync_id);

/**
 * @brief Queue a diagnostic log with this context's run_id and test_index.
 * Use only the supplied context in its owning setup/step/teardown callback;
 * do not retain it or modify the identity/step bookkeeping fields.
 * Returns false on queue backpressure, transport failure, invalid context/level,
 * NULL text, or text longer than 63 bytes. No blocking and no truncation.
 */
bool tzen_log(TzenContext_t *ctx, TzenLogLevel_t level, const char *message);

/**
 * @brief Queue a formatted diagnostic log; same return contract as tzen_log.
 * Formatting failure or output over 63 bytes returns false without enqueueing.
 */
bool tzen_logf(TzenContext_t *ctx, TzenLogLevel_t level, const char *fmt, ...);

#ifdef __cplusplus
}
#endif

#endif /* TZEN_H */
