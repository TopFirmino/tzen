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
  /* User callback for sending bytes. */
  TzenSendBytesFn_t send_bytes;

  /* User callback for reading the current time in microseconds. */
  TzenGetUsFn_t get_us;

  /* User data passed to callbacks. */
  void *user_data;

  /* Static test table and number of entries. */
  TzenTestDescriptor_t *tests;
  size_t num_tests;

} TzenConfig_t;

// ============================================================================
// 6. ENGINE API (called by the application, receive driver, or RTOS task)
// ============================================================================

/**
 * Reset the RX queue and decoder. Returns false if cfg is NULL.
 * Configuration callbacks and test execution are not used yet.
 * Call only while the producer and consumer are stopped.
 */
bool tzen_th_init(const TzenConfig_t *cfg);

/**
 * Feed one received byte from a single producer, in arrival order.
 * Decodes COBS directly into the current RX slot. Slots hold decoded payloads,
 * including CRC bytes, with capacity TZEN_TH_MAX_PACKET_SIZE each.
 * A 0x00 delimiter publishes a nonempty, complete frame if space is available.
 * Usable queue capacity is TZEN_TH_RX_SLOTS - 1 frames; a full queue drops
 * the newly completed frame. Oversized frames are dropped until a delimiter.
 * CRC and Protobuf validation are left to tzen_th_main_function.
 * Call tzen_th_init before feeding bytes. Synchronization is unfinished;
 * the current volatile indices alone do not guarantee safe ISR/task access.
 */
void tzen_th_feed_b(uint8_t byte);

/**
 * Intended protocol processing entry point for a single consumer.
 * Drain completed RX slots, validate CRC16, and decode Protobuf commands.
 * Reply to queries, forward control requests, and queue test executions.
 * Not implemented in tzen.c yet.
 */
void tzen_th_main_function(void);

/**
 * Intended worker processing entry point. Not implemented in tzen.c yet.
 * Take a queued test and execute its steps cooperatively.
 *
 * @param worker_id Worker index (0 .. TZEN_TH_MAX_WORKERS - 1).
 */
void tzen_th_worker_main_function(uint8_t worker_id);

/* Sticky TX result since init. Failure aborts the active run with teardown. */
bool tzen_th_transport_ok(void);

/**
 * @brief Intended aggregate state: RUNNING_STEP if work is ready, otherwise
 * WAITING_SYNC if a worker is waiting, otherwise IDLE.
 * tzen_th_worker_get_state reports the state of an individual worker.
 * These state queries are not implemented in tzen.c yet.
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
 * @brief Request a synchronization point and send SyncWait to the host.
 * The step must return TZEN_STEP_WAIT_SYNC after calling this function.
 *
 * @param ctx     Test context.
 * @param sync_id Numeric synchronization ID expected in SyncRelease.
 */
void tzen_sync(TzenContext_t *ctx, uint32_t sync_id);

/**
 * @brief Send a diagnostic log message to the Python host.
 */
void tzen_log(TzenContext_t *ctx, TzenLogLevel_t level, const char *message);

/**
 * @brief Send a formatted diagnostic log message.
 */
void tzen_logf(TzenContext_t *ctx, TzenLogLevel_t level, const char *fmt, ...);

#ifdef __cplusplus
}
#endif

#endif /* TZEN_H */
