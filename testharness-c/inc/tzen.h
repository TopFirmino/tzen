#ifndef TEST_HARNESS_H
#define TEST_HARNESS_H

#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>
#include "tzen_cfg.h"

#ifdef __cplusplus
extern "C" {
#endif

// ============================================================================
// 1. CONFIGURAZIONE DIMENSIONI STATICHE (Override via compiler flags -D)
// ============================================================================

/** Dimensione in byte dello Scratchpad condiviso per passare dati tra step */
#ifndef TH_SCRATCHPAD_SIZE
#define TH_SCRATCHPAD_SIZE      128U
#endif

/* Frame storage is governed by TTP_MAX_FRAME_SIZE in the protocol layer. */

// ============================================================================
// 2. TIPI BASE ED ENUMERAZIONI (Allineati al protocollo .proto)
// ============================================================================

/** Livelli di log (mappati 1:1 con LogEvent.Level nel .proto) */
typedef enum {
    TH_LOG_INFO    = 0,
    TH_LOG_WARNING = 1,
    TH_LOG_ERROR   = 2
} th_log_level_t;

/** Esito finale del test (mappato 1:1 con TestFinishedEvent.Status nel .proto) */
typedef enum {
    TH_TEST_STATUS_SUCCESS = 0,
    TH_TEST_STATUS_FAIL    = 1,
    TH_TEST_STATUS_ABORTED = 2
} th_test_status_t;

/**
 * Valore di ritorno di ogni singola funzione di Step.
 * Guida la macchina a stati senza mai bloccare la CPU.
 */
typedef enum {
    TH_STEP_PASS_NEXT = 0, /**< Step superato: avanza al prossimo step (o chiude con SUCCESS se era l'ultimo) */
    TH_STEP_WAIT_SYNC = 1, /**< Step sospeso: attende SyncRelease(sync_id) dal Master prima di avanzare */
    TH_STEP_YIELD     = 2, /**< Operazione non finita: riesegui questo STESSO step al prossimo giro di poll() */
    TH_STEP_FAIL      = 3, /**< Step fallito: interrompe il test immediatamente con stato FAIL */
    TH_STEP_DONE_PASS = 4  /**< Early exit: termina subito l'intero test con SUCCESS ignorando eventuali step rimanenti */
} th_step_result_t;

/** Stato interno del motore di esecuzione */
typedef enum {
    TH_ENGINE_IDLE         = 0,
    TH_ENGINE_RUNNING_STEP = 1,
    TH_ENGINE_WAITING_SYNC = 2
} th_engine_state_t;

// Forward declaration del contesto di esecuzione
typedef struct th_context_s th_context_t;

// ============================================================================
// 3. STRUTTURA DEL CONTESTO E SCRATCHPAD (Zero-Static State Sharing)
// ============================================================================

struct th_context_s {
    uint32_t run_id;          /**< ID sessione assegnato dal Master (ExecuteTest) */
    uint32_t test_index;      /**< Indice del test in corso */
    uint32_t current_step;    /**< Indice 0-based dello step attuale */
    uint32_t step_Iterations; /**< Contatore di quante volte lo step corrente ha fatto TH_STEP_YIELD */
    uint32_t pending_sync_id; /**< ID del punto di sync atteso (valido se state == WAITING_SYNC) */

    /**
     * Scratchpad condiviso allineato a 8 byte.
     * Viene azzerato (memset 0) automaticamente all'avvio di ogni test.
     * Permette agli step di condividere stato senza variabili 'static' globali.
     */
    TH_ALIGNAS(8) uint8_t scratchpad[TH_SCRATCHPAD_SIZE];

    /**
     * Puntatore opaco per estensioni future (es. puntatore alla VM Berry per i test dinamici).
     * Nei test statici C è NULL.
     */
    void *ext_vm_ctx;
};

/**
 * @brief Macro sicura per accedere allo Scratchpad tipizzato dentro gli step.
 * Esegue una verifica a tempo di compilazione che la struct dell'utente entri nel buffer.
 *
 * Esempio: my_state_t *st = TH_GET_STATE(ctx, my_state_t);
 */
#define TH_GET_STATE(ctx, state_type_t) \
    ((state_type_t *)((void)(sizeof(char[(sizeof(state_type_t) <= TH_SCRATCHPAD_SIZE && \
        TH_ALIGNOF(state_type_t) <= 8) ? 1 : -1])), (void *)((ctx)->scratchpad)))

// ============================================================================
// 4. DEFINIZIONE DEI TEST E DEGLI STEP (Metodo 2)
// ============================================================================

/** Firma di un singolo Step di test */
typedef th_step_result_t (*th_step_fn_t)(th_context_t *ctx);

/** Firma per i ganci opzionali di Setup iniziale e Teardown/Abort */
typedef bool (*th_setup_fn_t)(th_context_t *ctx);
typedef void (*th_teardown_fn_t)(th_context_t *ctx, th_test_status_t final_status);

/**
 * Descrittore di un Test Statico (pensato per risiedere in Flash: const).
 */
typedef struct {
    const char       *name;        /**< Nome del test restituito da GetTestInfo */
    const th_step_fn_t *steps;     /**< Array ordinato delle funzioni di step */
    uint32_t          num_steps;   /**< Calcolato in automatico dalla macro TH_DEFINE_TEST */
    th_setup_fn_t     on_setup;    /**< Opzionale: chiamata prima dello step 0 (NULL se non usata) */
    th_teardown_fn_t  on_teardown; /**< Opzionale: chiamata SEMPRE a fine test (PASS, FAIL o ABORT) per mettere in sicurezza l'HW */
} th_test_descriptor_t;

/**
 * @brief Macro helper per dichiarare un test statico calcolando il numero di step a compilazione.
 *
 * Esempio:
 * static const th_step_fn_t my_steps[] = { step1_init, step2_verify };
 * // Dentro l'array dei test:
 * TH_TEST_ENTRY("Power Rail Test", my_steps, NULL, cleanup_power_rails)
 */
#define TH_TEST_ENTRY(test_name, steps_array, setup_fn, teardown_fn) \
    { \
        .name        = (test_name), \
        .steps       = (steps_array), \
        .num_steps   = (uint32_t)(sizeof(steps_array) / sizeof((steps_array)[0])), \
        .on_setup    = (setup_fn), \
        .on_teardown = (teardown_fn) \
    }

// ============================================================================
// 5. CONFIGURAZIONE DI SISTEMA (Trasporto & OSAL Astratto Bare-Metal / RTOS)
// ============================================================================

typedef struct {
    /**
     * [OBBLIGATORIO] Invia un pacchetto già codificato (COBS + delimitatore 0x00) sul canale fisico.
     * Ritorna true se il pacchetto è stato preso in carico dal driver (es. DMA o RingBuffer TX).
     */
    bool (*transport_send)(const uint8_t *frame, size_t len, void *user_data);

    /** [OPZIONALE] Ritorna il timestamp di sistema in millisecondi (per log/telemetria) */
    uint32_t (*get_time_ms)(void *user_data);

    /**
     * [OPZIONALI - Solo per RTOS]
     * Se usati in Bare-Metal, lasciarli a NULL.
     * Su RTOS proteggono l'accesso alla coda comandi e svegliano il worker thread quando arriva un frame.
     */
    void (*mutex_lock)(void *user_data);
    void (*mutex_unlock)(void *user_data);
    void (*notify_worker)(void *user_data);

    /** Puntatore opaco passato a tutte le callback qui sopra (es. handle UART o struct RTOS) */
    void *user_data;
} th_config_t;

// ============================================================================
// 6. API DEL MOTORE (Chiamate dal main.c / Driver UART / Task RTOS)
// ============================================================================

/**
 * @brief Inizializza il Test Harness con la configurazione e il registro statico dei test.
 */
/* Single engine instance. init/poll/utilities belong to one worker. RX may
 * run in another task with paired mutex callbacks; not directly in an ISR.
 * transport_send must consume or copy the frame before returning.
 * Reinitialization during a run is rejected. No heap allocation is used. */
bool th_init(const th_config_t *config,
             const th_test_descriptor_t *test_table,
             size_t test_count);

/**
 * @brief Consegna al motore un frame grezzo ricevuto dal trasporto (es. frame COBS).
 * Può essere chiamata dal loop principale o dal task/callback di ricezione UART.
 *
 * @param raw_frame Puntatore al buffer ricevuto (solo corpo COBS, senza entrambi i delimitatori 0x00).
 * @param len       Lunghezza del frame ricevuto.
 * @return true se il frame è stato accodato per l'elaborazione, false se il buffer RX è pieno.
 */
bool th_on_rx_frame(const uint8_t *raw_frame, size_t len);

/**
 * @brief Funzione Worker non-bloccante.
 * - Elabora eventuali comandi pendenti (GetTests, ExecuteTest, SyncRelease, AbortTest).
 * - Se un test è nello stato TH_ENGINE_RUNNING_STEP, esegue UN singolo step e ritorna subito.
 *
 * Su Bare-Metal: chiamare continuamente nel while(1).
 * Su RTOS: chiamare nel loop del task worker (svegliato da notify_worker o con breve timeout se th_is_step_active() == true).
 */
void th_poll(void);

/**
 * @brief Ritorna lo stato attuale del motore.
 * Utile su RTOS per decidere quanto dormire:
 * - Se TH_ENGINE_RUNNING_STEP -> dormi 0 o 1 tick (ci sono altri step da macinare).
 * - Se TH_ENGINE_IDLE o TH_ENGINE_WAITING_SYNC -> dormi indefinitamente (portMAX_DELAY) finché non arriva un frame UART!
 */
th_engine_state_t th_get_state(void);

/* Sticky TX result since init. Failure aborts the active run with teardown. */
bool th_transport_ok(void);

// ============================================================================
// 7. API UTILITY PER GLI STEP (Usate dentro i test statici C e futuri binding Berry)
// ============================================================================

/**
 * @brief Invia al Master un evento TestStep (con numero 1-based automatico, esito e descrizione).
 *
 * @param ctx         Contesto del test passato alla funzione di step.
 * @param success     true se lo step ha avuto esito positivo, false altrimenti.
 * @param description Stringa descrittiva dello step.
 */
void th_report_step(th_context_t *ctx, bool success, const char *description);

/**
 * @brief Registra l'attesa di un punto di sincronizzazione ed emette il messaggio SyncWait al Master.
 * Nota: dopo aver chiamato questa funzione, lo step deve ritornare TH_STEP_WAIT_SYNC.
 *
 * @param ctx     Contesto del test.
 * @param sync_id Identificativo numerico del punto di sincronizzazione atteso in SyncRelease.
 */
void th_request_sync(th_context_t *ctx, uint32_t sync_id);

/**
 * @brief Invia un messaggio diagnostico Log al Master Python.
 */
void th_log(th_context_t *ctx, th_log_level_t level, const char *message);

/**
 * @brief Versione formattata opzionale (può essere disabilitata se non si vuole printf su MCU).
 */
void th_logf(th_context_t *ctx, th_log_level_t level, const char *fmt, ...);

#ifdef __cplusplus
}
#endif

#endif /* TEST_HARNESS_H */