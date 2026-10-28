; blink.asm: the smallest useful program. Toggles the LED pin every PERIOD
; cycles using DELAY, and pushes the cycle counter to the host every toggle so
; the host can see the core is alive and timing is exact.
.equ LED     4
.equ PERIOD  100          ; cycles per half period, exact

; DELAY n occupies n+1 cycles. Each half period also spends one cycle on OUT,
; RDCYC and PUSH, and the second half one more on JMP, so the two delays differ
; by one to keep both halves exactly PERIOD cycles.
start:  OUT LED, 0
loop:   DELAY PERIOD - 5
        OUT LED, 1
        RDCYC r1
        PUSH r1           ; stalls if the host has not drained the FIFO
        DELAY PERIOD - 4
        OUT LED, 0
        RDCYC r1
        PUSH r1
        JMP loop
