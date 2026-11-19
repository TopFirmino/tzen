/*
    Description: Public types shared by tzen configuration and the engine.

    Author: TopFirmino (L. Furcas)
    License: see LICENSE.md.
*/

#ifndef TZEN_TYPES_H
#define TZEN_TYPES_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

// ============================================================================
// 2. BASIC TYPES AND ENUMERATIONS (aligned with the .proto protocol)
// ============================================================================

/** Log levels (mapped 1:1 to LogEvent.Level in the .proto file). */
typedef enum {
  TZEN_LOG_INFO = 0,
  TZEN_LOG_WARNING = 1,
  TZEN_LOG_ERROR = 2
} TzenLogLevel_t;

/** Source 0 is reserved for testcase diagnostics; other IDs are application-defined. */
#define TZEN_SOURCE_TEST 0U

/** Copy this identity inside a callback for emission after the worker is released. */
typedef struct {
  uint32_t run_id;
  uint32_t test_index;
} TzenExecutionRef_t;

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

#ifdef __cplusplus
}
#endif

#endif /* TZEN_TYPES_H */
