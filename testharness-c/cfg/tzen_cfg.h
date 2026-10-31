#ifndef TZEN_CFG_H
#define TZEN_CFG_H
#ifndef TH_COMMAND_QUEUE_DEPTH
#define TH_COMMAND_QUEUE_DEPTH 4U
#endif
#ifndef TH_SCRATCHPAD_SIZE
#define TH_SCRATCHPAD_SIZE 128U
#endif
#ifdef __cplusplus
#define TH_ALIGNAS(n) alignas(n)
#define TH_ALIGNOF(t) alignof(t)
#else
#define TH_ALIGNAS(n) _Alignas(n)
#define TH_ALIGNOF(t) _Alignof(t)
#endif
#endif
