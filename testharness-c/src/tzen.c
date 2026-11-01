/*
    Description: Main Tzen implementation.

    Author: TopFirmino (L. Furcas)
    License: see LICENSE.md.
*/
#include "tzen_cfg.h"


/*
*   STATIC VARIABLES
*/

/* Definition of the current state of the testharness*/
static struct tzen_state_s {
    struct rx_queue {
        struct {
            uint8_t  data[TZEN_TH_MAX_PACKET_SIZE];
            uint16_t len;
        } slots[TZEN_TH_RX_SLOTS];

        volatile uint8_t write_idx; // Modificato SOLO da tzen_th_feed_b (ISR)
        volatile uint8_t read_idx;  // Modificato SOLO da tzen_th_main_function

        // Stato del decodificatore COBS in streaming
        uint8_t  cobs_code;
        uint8_t  cobs_block;
        uint16_t cur_pos;
        bool     drop_frame;
    }

} testharness_state;

// Stato privato del ricevitore (Zero Lock tra 1 Produttore ISR e 1 Consumatore Main)
static struct {
    struct {
        uint8_t  data[TZEN_TH_MAX_PACKET_SIZE];
        uint16_t len;
    } slots[TZEN_TH_RX_SLOTS];

    volatile uint8_t write_idx; // Modificato SOLO da tzen_th_feed_b (ISR)
    volatile uint8_t read_idx;  // Modificato SOLO da tzen_th_main_function

    // Stato del decodificatore COBS in streaming
    uint8_t  cobs_code;
    uint8_t  cobs_block;
    uint16_t cur_pos;
    bool     drop_frame;
} g_rx;



/* */
bool tzen_th_init(const TzenConfig_t *cfg)
{
    
}

void tzen_th_feed_b(uint8_t byte) {
    // 1. Se arriva 0x00, è il delimitatore di fine frame COBS!
    if (byte == 0x00U) {
        // Il frame è valido se non era in overflow, non è vuoto e COBS è terminato pulito
        if (!g_rx.drop_frame && (g_rx.cur_pos > 0U) && (g_rx.cobs_block == 0U)) {
            uint8_t next_w = (g_rx.write_idx + 1U) % TZEN_TH_RX_SLOTS;
            if (next_w != g_rx.read_idx) { // C'è spazio nella coda slot!
                g_rx.slots[g_rx.write_idx].len = g_rx.cur_pos;
                g_rx.write_idx = next_w;   // Pubblica il frame a tzen_th_main_function!
            }
        }
        // Reset stato COBS per il prossimo frame
        g_rx.cobs_code  = 0xFFU;
        g_rx.cobs_block = 0U;
        g_rx.cur_pos    = 0U;
        g_rx.drop_frame = false;
        return;
    }

    if (g_rx.drop_frame) {
        return; // Scarta byte finché non arriva 0x00 per risincronizzarsi
    }

    // 2. Decodifica COBS on-the-fly (Zero-Copy!)
    if (g_rx.cobs_block > 0U) {
        if (g_rx.cur_pos < TZEN_TH_MAX_PACKET_SIZE) {
            g_rx.slots[g_rx.write_idx].data[g_rx.cur_pos++] = byte;
        } else {
            g_rx.drop_frame = true; // Frame troppo lungo, scarta fino a 0x00
        }
    } else {
        if (g_rx.cobs_code != 0xFFU) {
            if (g_rx.cur_pos < TZEN_TH_MAX_PACKET_SIZE) {
                g_rx.slots[g_rx.write_idx].data[g_rx.cur_pos++] = 0x00U;
            } else {
                g_rx.drop_frame = true;
            }
        }
        g_rx.cobs_code  = byte;
        g_rx.cobs_block = byte;
        if (g_rx.cobs_code == 0x00U) {
            g_rx.drop_frame = true;
        }
    }
    g_rx.cobs_block--;
}
