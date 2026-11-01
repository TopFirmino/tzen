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
// 1. CONFIGURAZIONE DIMENSIONI STATICHE (Override via compiler flags -D)
// ============================================================================

/* Static storage limits are configured in tzen_cfg.h; no protocol headers
 * are needed by the integrating application. */

// ============================================================================
// 2. TIPI BASE ED ENUMERAZIONI (Allineati al protocollo .proto)
// ============================================================================

/** Livelli di log (mappati 1:1 con LogEvent.Level nel .proto) */
typedef enum {
  TZEN_LOG_INFO = 0,
  TZEN_LOG_WARNING = 1,
  TZEN_LOG_ERROR = 2
} TzenLogLevel_t;

/** Esito finale del test (mappato 1:1 con TestFinishedEvent.Status nel .proto)
 */
typedef enum {
  TZEN_TEST_STATUS_SUCCESS = 0,
  TZEN_TEST_STATUS_FAIL = 1,
  TZEN_TEST_STATUS_ABORTED = 2
} TzenTestStatus_t;

/**
 * Valore di ritorno di ogni singola funzione di Step.
 * Guida la macchina a stati senza mai bloccare la CPU.
 */
typedef enum {
  TZEN_STEP_PASS_NEXT = 0, /**< Step superato: avanza al prossimo step (o chiude
                              con SUCCESS se era l'ultimo) */
  TZEN_STEP_WAIT_SYNC = 1, /**< Step sospeso: attende SyncRelease(sync_id) dal
                              Master prima di avanzare */
  TZEN_STEP_YIELD = 2, /**< Operazione non finita: riesegui questo STESSO step
                          al prossimo giro di worker_main_function() */
  TZEN_STEP_FAIL =
      3, /**< Step fallito: interrompe il test immediatamente con stato FAIL */
  TZEN_STEP_DONE_PASS = 4 /**< Early exit: termina subito l'intero test con
                             SUCCESS ignorando eventuali step rimanenti */
} TzenStepResult_t;

/** Stato interno del motore di esecuzione */
typedef enum {
  TZEN_ENGINE_IDLE = 0,
  TZEN_ENGINE_RUNNING_STEP = 1,
  TZEN_ENGINE_WAITING_SYNC = 2
} TzenEngineState_t;

// Forward declaration del contesto di esecuzione
typedef struct TzenContext_s TzenContext_t;

// ============================================================================
// 3. STRUTTURA DEL CONTESTO E SCRATCHPAD (Zero-Static State Sharing)
// ============================================================================

struct TzenContext_s {
  uint32_t run_id;       /**< ID sessione assegnato dal Master (ExecuteTest) */
  uint32_t test_index;   /**< Indice del test in corso */
  uint32_t current_step; /**< Indice 0-based dello step attuale */
  uint32_t step_Iterations; /**< Contatore di quante volte lo step corrente ha
                               fatto TZEN_STEP_YIELD */
  uint32_t pending_sync_id; /**< ID del punto di sync atteso (valido se state ==
                               WAITING_SYNC) */

  /**
   * Scratchpad condiviso allineato a 8 byte.
   * Viene azzerato (memset 0) automaticamente all'avvio di ogni test.
   * Permette agli step di condividere stato senza variabili 'static' globali.
   */
  TZEN_ALIGNAS(8)
  uint8_t scratchpad[TZEN_TEST_SCRATCHPAD_SIZE];

  /**
   * Puntatore opaco per estensioni future (es. puntatore alla VM Berry per i
   * test dinamici). Nei test statici C è NULL.
   */
  void *ext_vm_ctx;
};

/**
 * @brief Macro sicura per accedere allo Scratchpad tipizzato dentro gli step.
 * Esegue una verifica a tempo di compilazione che la struct dell'utente entri
 * nel buffer.
 *
 * Esempio: my_state_t *st = TZEN_GET_STATE(ctx, my_state_t);
 */
#define TZEN_GET_STATE(ctx, state_type_t)                                      \
  ((state_type_t *)((void)(sizeof(char[(sizeof(state_type_t) <=                \
                                            TZEN_TEST_SCRATCHPAD_SIZE &&       \
                                        TZEN_ALIGNOF(state_type_t) <= 8)       \
                                           ? 1                                 \
                                           : -1])),                            \
                    (void *)((ctx)->scratchpad)))

// ============================================================================
// 4. DEFINIZIONE DEI TEST E DEGLI STEP (Metodo 2)
// ============================================================================

/** Firma di un singolo Step di test */
typedef TzenStepResult_t (*TzenStepFn_t)(TzenContext_t *ctx);

/** Firma per i ganci opzionali di Setup iniziale e Teardown/Abort */
typedef bool (*TzenSetupFn_t)(TzenContext_t *ctx);
typedef void (*TzenTeardownFn_t)(TzenContext_t *ctx,
                                 TzenTestStatus_t final_status);
typedef bool (*TzenSendBytesFn_t)(const uint8_t *frame, size_t len,
                                  void *user_data);
typedef uint32_t (*TzenGetUsFn_t)(void *user_data);

/**
 * Descrittore di un Test Statico (pensato per risiedere in Flash: const).
 */
typedef struct {
  const char *name;          /**< Nome del test restituito da GetTestInfo */
  const TzenStepFn_t *steps; /**< Array ordinato delle funzioni di step */
  uint32_t
      num_steps; /**< Calcolato in automatico dalla macro TZEN_TEST_ENTRY */
  TzenSetupFn_t on_setup; /**< Opzionale: chiamata prima dello step 0 (NULL se
                             non usata) */
  TzenTeardownFn_t
      on_teardown; /**< Opzionale: chiamata SEMPRE a fine test (PASS, FAIL o
                      ABORT) per mettere in sicurezza l'HW */
} TzenTestDescriptor_t;

/**
 * @brief Macro helper per dichiarare un test statico calcolando il numero di
 * step a compilazione.
 *
 * Esempio:
 * static const TzenStepFn_t my_steps[] = { step1_init, step2_verify };
 * // Dentro l'array dei test:
 * TZEN_TEST_ENTRY("Power Rail Test", my_steps, NULL, cleanup_power_rails)
 */
#define TZEN_TEST_ENTRY(test_name, steps_array, setup_fn, teardown_fn)         \
  {.name = (test_name),                                                        \
   .steps = (steps_array),                                                     \
   .num_steps = (uint32_t)(sizeof(steps_array) / sizeof((steps_array)[0])),    \
   .on_setup = (setup_fn),                                                     \
   .on_teardown = (teardown_fn)}

// ============================================================================
// 5. CONFIGURAZIONE DI SISTEMA (Trasporto & OSAL Astratto Bare-Metal / RTOS)
// ============================================================================

typedef struct {
  /* Configured by user to send bytes */
  TzenSendBytesFn_t send_bytes;

  /* Configured to get current us */
  TzenGetUsFn_t get_us;

  /* Configured user data */
  void *user_data;

  /* Static testcases */
  TzenTestDescriptor_t *tests;
  size_t num_tests;

} TzenConfig_t;

// ============================================================================
// 6. API DEL MOTORE (Chiamate dal main.c / Driver UART / Task RTOS)
// ============================================================================

/**
 * Initialize the testharness with specified cfg configuration.
 */
bool tzen_th_init(const TzenConfig_t *cfg);

/**
 * 2. FEED BYTE (ISR-Safe, Lock-Free, O(1)):
 * L'utente la chiama per ogni byte ricevuto dalla UART (anche dentro l'ISR).
 * Esegue il unframing COBS al volo: quando vede 0x00, chiude lo slot corrente
 * e lo rende visibile a tzen_th_main_function(). Un solo produttore.
 * Capacita utile: TZEN_TH_RX_SLOTS - 1 frame; a coda piena scarta il nuovo.
 * Usa atomiche C11 byte lock-free (su AVR: accessi byte e compiler barrier).
 * Nessuna verifica CRC/Protobuf in ISR.
 */
void tzen_th_feed_b(uint8_t byte);

/**
 * 3. PROTOCOL MAIN (Control Plane - un solo task proprietario):
 * Polla gli slot RX pronti, verifica il CRC16, decodifica Protobuf (Nanopb).
 * - Comandi veloci (GetTests, GetTestInfo): risponde subito.
 * - Comandi di controllo (SyncRelease, Abort): aggiorna lo stato del Worker
 * associato a quel run_id; il worker applica la richiesta al prossimo poll.
 * - Comandi ExecuteTest: inserisce la richiesta nella Worker Queue (protetta da
 * mutex).
 */
void tzen_th_main_function(void);

/**
 * 4. WORKER MAIN (Execution Plane - Multi-Task / Multi-Core safe):
 * Può essere chiamata nello stesso superloop di tzen_th_main_function
 * (Bare-Metal) oppure dentro N task/core diversi su RTOS.
 *
 * @param worker_id Indice del worker (0 .. TZEN_TH_MAX_WORKERS - 1).
 * Prende il primo test disponibile dalla Worker Queue ed esegue gli step.
 */
void tzen_th_worker_main_function(uint8_t worker_id);

/* Sticky TX result since init. Failure aborts the active run with teardown. */
bool tzen_th_transport_ok(void);

/**
 * @brief Stato aggregato: RUNNING se esiste lavoro pronto, altrimenti
 * WAITING_SYNC se almeno un worker aspetta, altrimenti IDLE.
 * tzen_th_worker_get_state indica lo stato del singolo worker.
 * Utile su RTOS per decidere quanto dormire:
 * - Se TZEN_ENGINE_RUNNING_STEP -> dormi 0 o 1 tick (ci sono altri step da
 * macinare).
 * - Se TZEN_ENGINE_IDLE o TZEN_ENGINE_WAITING_SYNC -> dormi indefinitamente
 * (portMAX_DELAY) finché non arriva un frame UART!
 */
TzenEngineState_t tzen_get_state(void);
TzenEngineState_t tzen_th_worker_get_state(uint8_t worker_id);

// ============================================================================
// 7. API UTILITY PER GLI STEP (Usate dentro i test statici C e futuri binding
// Berry)
// ============================================================================

/* Step results are emitted internally from the returned TzenStepResult_t.
 * YIELD emits no result; WAIT_SYNC completes on matching release.
 * Testcases use tzen_log/tzen_logf for explanatory text. */

/**
 * @brief Registra l'attesa di un punto di sincronizzazione ed emette il
 * messaggio SyncWait al Master. Nota: dopo aver chiamato questa funzione, lo
 * step deve ritornare TZEN_STEP_WAIT_SYNC.
 *
 * @param ctx     Contesto del test.
 * @param sync_id Identificativo numerico del punto di sincronizzazione atteso
 * in SyncRelease.
 */
void tzen_sync(TzenContext_t *ctx, uint32_t sync_id);

/**
 * @brief Invia un messaggio diagnostico Log al Master Python.
 */
void tzen_log(TzenContext_t *ctx, TzenLogLevel_t level, const char *message);

/**
 * @brief Versione formattata opzionale (può essere disabilitata se non si vuole
 * printf su MCU).
 */
void tzen_logf(TzenContext_t *ctx, TzenLogLevel_t level, const char *fmt, ...);

#ifdef __cplusplus
}
#endif

#endif /* TZEN_H */