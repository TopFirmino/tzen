Metodo 1: Esportazione dei Simboli tramite Linker (Il migliore per i test)

Questo approccio usa una funzionalità del linker (spesso GCC/LD) chiamata --just-symbols. Permette di compilare il codice di test in un file binario separato, ma dicendo al compilatore: "Non preoccuparti se non trovi questa funzione, assumi che si trovi all'indirizzo specificato nell'eseguibile del main".
1. Compila l'applicativo principale (Main in Flash)

Compila il tuo firmware normalmente. Questo genererà un file .elf che contiene tutti gli indirizzi delle funzioni flashate.
Bash

arm-none-eabi-gcc main.c [altri_file] -T flash.ld -o main.elf

2. Compila i test (in RAM) "leggendo" il main

Per compilare il modulo di test, devi usare un linker script apposito (ram_test.ld) che posizioni tutto il codice nell'area di RAM che hai riservato per i test (es. a partire da 0x20010000).

Durante il linking del test, passi il file main.elf al linker con il flag -R (o --just-symbols).
Bash

# Il test usa le funzioni del main senza definirle
arm-none-eabi-gcc test.c -T ram_test.ld -Wl,-R,main.elf -o test.elf

# Estrai solo il codice binario puro da caricare in RAM
arm-none-eabi-objcopy -O binary test.elf test.bin

In questo modo, se test.c chiama la funzione calcola_sensore(), il linker guarderà dentro main.elf, vedrà che in Flash si trova all'indirizzo 0x080045A0, e inserirà esattamente quell'indirizzo nella chiamata (branch) dentro test.bin.


