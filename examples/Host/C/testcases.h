#ifndef HOST_TESTCASES_H
#define HOST_TESTCASES_H
#include "tzen_types.h"
#define HOST_TEST_COUNT 3U
#define HOST_SOURCE_SYSTEM 1U
#define HOST_SOURCE_COVERAGE 7U
/* Main-loop-only demo producer; call after flushing worker results. */
bool host_emit_deferred_logs(void);
extern const TzenTestDescriptor_t host_tests[HOST_TEST_COUNT];
#endif
