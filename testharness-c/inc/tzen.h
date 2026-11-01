/*
    Description: Header file for tzen testharness API.

    Author: TopFirmino (L. Furcas)
    License: see LICENSE.md.
*/

#ifndef TZEN_H
#define TZEN_H

#include "tzen_cfg.h"
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

// ============================================================================
// 1. STATIC STORAGE LIMITS (override with compiler -D flags)
// ============================================================================

/* Static storage limits are configured in tzen_cfg.h; no protocol headers
 * are needed by the integrating application. */

// ============================================================================
// 2. BASIC TYPES AND ENUMERATIONS (aligned with the .proto protocol)
// ============================================================================

/** Log levels (mapped 1:1 to LogEvent.Level in the .proto file). */
typedef enum {
  TZEN_LOG_INFO = 0,
  TZEN_LOG_WARNING = 1,
  TZEN_LOG_ERROR = 2
} TzenLogLevel_t;

/** Final test result (mapped 1:1 to TestFinishedEvent.Status in the .proto file).
 */
typedef enum {
  TZEN_TEST_STATUS_SUCCESS = 0,
  TZEN_TEST_STATUS_FAIL = 1,
  TZEN_TEST_STATUS_ABORTED = 2
} TzenTestStatus_t;

/**
 * Return value of each test step function.
 * Drives the cooperative execution state machine.
 */
typedef enum {
  TZEN_STEP_PASS_NEXT = 0, /**< Step passed: advance, or finish with SUCCESS
                              after the last step. */
  TZEN_STEP_WAIT_SYNC = 1, /**< Wait for SyncRelease(sync_id) from the host
                              before advancing. */
  TZEN_STEP_YIELD = 2, /**< Run this same step again on the next call to
                          tzen_th_worker_main_function. */
  TZEN_STEP_FAIL =
      3, /**< Step failed: end the test immediately with FAIL. */
  TZEN_STEP_DONE_PASS = 4 /**< End the test immediately with SUCCESS,
                             skipping any remaining steps. */
} TzenStepResult_t;

/** Internal execution engine state. */
typedef enum {
  TZEN_ENGINE_IDLE = 0,
  TZEN_ENGINE_RUNNING_STEP = 1,
  TZEN_ENGINE_WAITING_SYNC = 2
} TzenEngineState_t;

// Forward declaration of the execution context.
typedef struct TzenContext_s TzenContext_t;

// ============================================================================
// 3. EXECUTION CONTEXT AND SCRATCHPAD
// ============================================================================

struct TzenContext_s {
  uint32_t run_id;       /**< Run ID assigned by the host (ExecuteTest). */
  uint32_t test_index;   /**< Index of the current test. */
  uint32_t current_step; /**< Zero-based index of the current step. */
  uint32_t step_Iterations; /**< Number of times the current step has returned
                               TZEN_STEP_YIELD. */
  uint32_t pending_sync_id; /**< Expected synchronization ID while waiting
                               for SyncRelease. */

  /**
   * Shared scratchpad aligned to 8 bytes.
   * Cleared automatically at the start of each test.
   * Allows steps to share state without global static variables.
   */
  TZEN_ALIGNAS(8)
  uint8_t scratchpad[TZEN_TEST_SCRATCHPAD_SIZE];

  /**
   * Opaque pointer for future extensions, such as a Berry VM for dynamic
   * tests. NULL for static C tests.
   */
  void *ext_vm_ctx;
};

/**
 * @brief Access the scratchpad as the requested state type.
 * Checks at compile time that the type fits the buffer and its alignment.
 *
 * Example: my_state_t *st = TZEN_GET_STATE(ctx, my_state_t);
 */
#define TZEN_GET_STATE(ctx, state_type_t)                                      \
  ((state_type_t *)((void)(sizeof(char[(sizeof(state_type_t) <=                \
                                            TZEN_TEST_SCRATCHPAD_SIZE &&       \
                                        TZEN_ALIGNOF(state_type_t) <= 8)       \
                                           ? 1                                 \
                                           : -1])),                            \
                    (void *)((ctx)->scratchpad)))

// ============================================================================
// 4. TEST AND STEP DEFINITIONS
// ============================================================================

/** Test step callback. */
typedef TzenStepResult_t (*TzenStepFn_t)(TzenContext_t *ctx);

/** Optional setup and teardown callbacks. */
typedef bool (*TzenSetupFn_t)(TzenContext_t *ctx);
typedef void (*TzenTeardownFn_t)(TzenContext_t *ctx,
                                 TzenTestStatus_t final_status);
/** Send one complete frame, including both zero delimiters. Return true only
 * after consuming/copying all bytes. The frame pointer expires on return.
 * Do not reenter harness APIs from this callback. */
typedef bool (*TzenSendBytesFn_t)(const uint8_t *frame, size_t len,
                                  void *user_data);
typedef uint32_t (*TzenGetUsFn_t)(void *user_data);

/**
 * Static test descriptor, suitable for const storage in flash.
 */
typedef struct {
  const char *name;          /**< Test name returned by GetTestInfo. */
  const TzenStepFn_t *steps; /**< Ordered array of step callbacks. */
  uint32_t
      num_steps; /**< Calculated automatically by TZEN_TEST_ENTRY. */
  TzenSetupFn_t on_setup; /**< Optional callback before step 0; NULL if
                             unused. */
  TzenTeardownFn_t
      on_teardown; /**< Optional cleanup after a started test finishes with
                      SUCCESS, FAIL, or ABORTED. */
} TzenTestDescriptor_t;

/**
 * @brief Declare a static test and calculate its step count at compile time.
 *
 * Example:
 * static const TzenStepFn_t my_steps[] = { step1_init, step2_verify };
 * // Inside the test array:
 * TZEN_TEST_ENTRY("Power Rail Test", my_steps, NULL, cleanup_power_rails)
 */
#define TZEN_TEST_ENTRY(test_name, steps_array, setup_fn, teardown_fn)         \
  {.name = (test_name),                                                        \
   .steps = (steps_array),                                                     \
   .num_steps = (uint32_t)(sizeof(steps_array) / sizeof((steps_array)[0])),    \
   .on_setup = (setup_fn),                                                     \
   .on_teardown = (teardown_fn)}

// ============================================================================
// 5. SYSTEM CONFIGURATION
// ============================================================================

typedef struct {
  /* Full-frame transport callback; NULL permits RX-only use. */
  TzenSendBytesFn_t send_bytes;

  /* User callback for reading the current time in microseconds. */
  TzenGetUsFn_t get_us;

  /* User data passed to callbacks. */
  void *user_data;

  /* Static test table. Keep descriptors/names/steps valid until reinit. */
  const TzenTestDescriptor_t *tests;
  size_t num_tests;

} TzenConfig_t;

// ============================================================================
// 6. ENGINE API (called by the application, receive driver, or RTOS task)
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
bool tzen_th_send_packet(const uint8_t *payload, size_t len);

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
// 7. STEP UTILITIES (for static C tests and future Berry bindings)
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
