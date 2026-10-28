; uart_rx.asm: 8N1 UART receiver. Waits for the start bit's falling edge, then
; samples every bit at its centre using half-bit timer ticks, and pushes each
; received byte to the host. A bad stop bit pushes 0x01FF (framing error).
.equ UART_RX 0
.equ HALF    217            ; half of 434 cycles (115200 baud at 50 MHz)

        LDW r3, HALF
loop:   WAITF UART_RX        ; start bit edge
        TSET r3              ; half-bit ticks from (roughly) the edge
        LDI r2, 8
        WAITT                ; 0.5 bit
bit:    WAITT                ; x.0
        WAITT                ; x.5: centre of data bit
        INC UART_RX
        SHRC r1, r1          ; LSB first: after 8 bits the byte is in r1[15:8]
        DJNZ r2, bit
        WAITT
        WAITT                ; centre of stop bit
        INC UART_RX
        BCC err
        LDI r4, 8
sh:     SHRC r1, r1          ; move the byte down to r1[7:0]
        DJNZ r4, sh
        ANDI r1, 0xFF
        PUSH r1
        JMP loop
err:    LDW r1, 0x01FF
        PUSH r1
        JMP loop
