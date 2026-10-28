; uart_tx.asm: 8N1 UART transmitter driven from the host FIFO.
; Every pin write sits exactly one instruction after a WAITT, so every bit is
; exactly BIT cycles long: 434 cycles = 115200 baud at 50 MHz (0.03% error).
; The per-bit loop is four instructions, so BIT must be at least 4 (the formal
; proof in formal/uart_tx_program.sby runs at BIT=4 and refutes BIT=3).
.equ UART_TX 0
.equ BIT     434

        OUT UART_TX, 1       ; idle high
        LDW r3, BIT
        TSET r3              ; bit clock running from here on
loop:   PULL r1              ; next byte from the host (stalls while empty)
        LDI r2, 8
        WAITT
        OUT UART_TX, 0       ; start bit
bit:    SHRC r1, r1          ; C = next data bit, LSB first
        WAITT
        OUTC UART_TX
        DJNZ r2, bit
        WAITT
        OUT UART_TX, 1       ; stop bit (at least one bit period: PULL may wait longer)
        JMP loop
