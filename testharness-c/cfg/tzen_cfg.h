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

/* RX ring slots: one slot is reserved; usable queued frames = slots - 1. */
#ifndef TZEN_TH_RX_SLOTS
#define TZEN_TH_RX_SLOTS 4U
#endif

/* Maximum decoded packet size, including the two CRC bytes. */
#ifndef TZEN_TH_MAX_PACKET_SIZE
#define TZEN_TH_MAX_PACKET_SIZE 256U
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
