; selftest.asm: bring-up program. Exercises every functional unit and pushes a
; signature word to the host: 0xC0DE if every check passed, else the index of
; the first failing check. Intended as the first program run on silicon.
.equ LED 4

        LDI r7, 1            ; r7 = check number
        ; 1: ALU add/sub with carry
        LDW r1, 0xFFFF
        LDI r2, 1
        ADD r3, r1, r2       ; 0x0000, C=1
        BCC fail
        BNE fail
        SUB r3, r2, r1       ; 1 - 0xFFFF = 2, borrow
        BCC fail
        CMPI r3, 2
        BNE fail
        ADDI r7, 1           ; 2: shifts through carry
        LDI r1, 0x81
        LDI r2, 0            ; clear C via ADD 0+0
        ADD r2, r2, r2
        SHRC r1, r1          ; C=1, r1=0x40
        BCC fail
        SHLC r1, r1          ; r1 = 0x81, C=0
        BCS fail
        CMPI r1, 0x81
        BNE fail
        ADDI r7, 1           ; 3: CRC-16/CCITT of one zero byte from init 0xFFFF = 0xE1F0
        LDW r1, 0x1021
        CRCPOLY r1
        LDW r1, 0xFFFF
        CRCINIT r1
        LDI r2, 8
        LDI r1, 0
        ADD r1, r1, r1       ; C = 0
crc:    CRCIN
        DJNZ r2, crc
        CRCRD r1
        LDW r2, 0xE1F0
        SUB r0, r1, r2
        BNE fail
        ADDI r7, 1           ; 4: timer ticks exactly PERIOD apart
        LDI r3, 20
        TSET r3
        WAITT
        RDCYC r1
        WAITT
        RDCYC r2
        SUB r2, r2, r1
        CMPI r2, 20
        BNE fail
        ADDI r7, 1           ; 5: CALL/RET and the LED
        CALL sub
        OUT LED, 0
        LDW r1, 0xC0DE
        PUSH r1
        HALT
sub:    OUT LED, 1
        RET
fail:   PUSH r7
        HALT
