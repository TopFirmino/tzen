/*
 * Tzen
 * Author: L. Furcas
 * SPDX-License-Identifier: MPL-2.0
 */

#include "tzen.h"

typedef struct {
    TzenExecutionRef_t execution;
    uint32_t current_step;
    uint32_t step_iterations;
} TzenAdaContextInfo;

unsigned int tzen_ada_worker_count(void)
{
    return TZEN_TH_MAX_WORKERS;
}

void tzen_ada_context_info(const TzenContext_t *ctx, TzenAdaContextInfo *info)
{
    info->execution.run_id = ctx->run_id;
    info->execution.test_index = ctx->test_index;
    info->current_step = ctx->current_step;
    info->step_iterations = ctx->step_Iterations;
}

void *tzen_ada_scratchpad(TzenContext_t *ctx, size_t size, size_t alignment)
{
    if (size > sizeof ctx->scratchpad || alignment == 0U ||
        alignment > 8U || 8U % alignment != 0U)
        return NULL;
    return ctx->scratchpad;
}
