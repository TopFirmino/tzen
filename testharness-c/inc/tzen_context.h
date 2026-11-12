/* Configuration-dependent execution context and scratchpad access. */
#ifndef TZEN_CONTEXT_H
#define TZEN_CONTEXT_H

#include "tzen_types.h"

/* Define consistently for every translation unit using the harness. */
#ifndef TZEN_CONFIG_HEADER
#define TZEN_CONFIG_HEADER "tzen_cfg.h"
#endif
#include TZEN_CONFIG_HEADER

#ifdef __cplusplus
#define TZEN_ALIGNAS(n) alignas(n)
#define TZEN_ALIGNOF(t) alignof(t)
#else
#define TZEN_ALIGNAS(n) _Alignas(n)
#define TZEN_ALIGNOF(t) _Alignof(t)
#endif

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

#endif /* TZEN_CONTEXT_H */
