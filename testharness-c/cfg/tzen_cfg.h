/*
    Description: Contains all configuration variables for the tzen environment.

    Author: TopFirmino (L. Furcas)
    License: see LICENSE.md.
*/

#ifndef TZEN_CFG_H
#define TZEN_CFG_H

/**************************************************************
 * TZEN TESTHARNESS CONFIGURATION
**************************************************************/

/* Override both macros in the application's build (for example, with a
 * forced-include port header). Defaults are for serialized calls only.
 * For concurrent calls, both hooks must use the same protection mechanism
 * and provide mutual exclusion and memory visibility between callers.
 * An interrupt-based port must preserve and restore the prior interrupt state.
 * Hooks are paired in one scope, are never nested, and do not cover CRC work.
 * A task mutex is suitable for tasks; ISR callers need ISR-safe hooks. */
#if defined(TZEN_TH_ENTER_CRITICAL_SECTION) != defined(TZEN_TH_EXIT_CRITICAL_SECTION)
#error "Define both TZEN_TH critical-section hooks or neither"
#endif

#ifndef TZEN_TH_ENTER_CRITICAL_SECTION
#define TZEN_TH_ENTER_CRITICAL_SECTION() ((void)0)
#define TZEN_TH_EXIT_CRITICAL_SECTION() ((void)0)
#endif

/* RX-specific overrides may share the application's general hooks. */
#if defined(TZEN_TH_ENTER_CRITICAL_SECTION_RX_QUEUE) != defined(TZEN_TH_EXIT_CRITICAL_SECTION_RX_QUEUE)
#error "Define both TZEN_TH RX critical-section hooks or neither"
#endif
#ifndef TZEN_TH_ENTER_CRITICAL_SECTION_RX_QUEUE
#define TZEN_TH_ENTER_CRITICAL_SECTION_RX_QUEUE() TZEN_TH_ENTER_CRITICAL_SECTION()
#define TZEN_TH_EXIT_CRITICAL_SECTION_RX_QUEUE() TZEN_TH_EXIT_CRITICAL_SECTION()
#endif

/* RX ring slots: one slot is reserved; usable queued frames = slots - 1. */
#ifndef TZEN_TH_RX_SLOTS
#define TZEN_TH_RX_SLOTS 4U
#endif

/* Maximum decoded packet size, including the two CRC bytes. */
#ifndef TZEN_TH_MAX_PACKET_SIZE
#define TZEN_TH_MAX_PACKET_SIZE 256U
#endif

#if TZEN_TH_MAX_PACKET_SIZE < 2U || TZEN_TH_MAX_PACKET_SIZE > 65535U
#error "TZEN_TH_MAX_PACKET_SIZE must fit a uint16_t length and include two CRC bytes"
#endif

/* Number of Tzen Configured Workers */
#ifndef TZEN_TH_MAX_WORKERS
#define TZEN_TH_MAX_WORKERS 2U
#endif


/* Pending executions, in addition to active workers. */
#ifndef TZEN_TH_WORKER_QUEUE_DEPTH
#define TZEN_TH_WORKER_QUEUE_DEPTH 4U
#endif

/**************************************************************
 * TZEN TEST CONFIGURATION
**************************************************************/

/* Size of the context for every test. In Bytes. */
#ifndef TZEN_TEST_SCRATCHPAD_SIZE
#define TZEN_TEST_SCRATCHPAD_SIZE 128U
#endif




#ifdef __cplusplus
#define TZEN_ALIGNAS(n) alignas(n)
#define TZEN_ALIGNOF(t) alignof(t)
#else
#define TZEN_ALIGNAS(n) _Alignas(n)
#define TZEN_ALIGNOF(t) _Alignof(t)
#endif

#endif
