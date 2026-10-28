; i2c_master.asm: I2C controller (100 kHz at 50 MHz: 500 cycles per bit, so
; a quarter bit is 125 cycles). Open drain on two bidirectional pins: the data
; register is set low once and OE drives (0) or releases (1) the line.
; Host command words: 0x0100 = START (or repeated START), 0x0200 = STOP,
; 0x00xx = write byte xx and push 0 (ACK) or 1 (NACK) back to the host.
; Clock stretching is honoured: after releasing SCL the program waits for it
; to actually read high.
.equ I2C_SCL 8
.equ I2C_SDA 9
.equ Q       125

        OUT I2C_SCL, 0       ; data registers low for ever: OE selects low/released
        OUT I2C_SDA, 0
        OE I2C_SCL, 0        ; both released (bus idle high)
        OE I2C_SDA, 0
        LDI r3, Q
        TSET r3
        LDW r6, 0x0100
        LDW r7, 0x0200
loop:   PULL r1
        SUB r0, r1, r6
        BEQ do_start
        SUB r0, r1, r7
        BEQ do_stop
        CALL send_byte       ; C = ACK bit read from the bus
        LDI r4, 0
        SHLC r4, r4          ; r4 = C
        PUSH r4
        JMP loop
do_start:
        CALL start
        JMP loop
do_stop:
        CALL stop
        JMP loop

; START: with SCL high, pull SDA low, then pull SCL low.
start:  OE I2C_SDA, 0
        WAITT
        OE I2C_SCL, 0
        WAITP I2C_SCL, 1
        WAITT
        OE I2C_SDA, 1
        WAITT
        OE I2C_SCL, 1
        WAITT
        RET

; STOP: with SCL low, pull SDA low, release SCL, release SDA.
stop:   OE I2C_SDA, 1
        WAITT
        OE I2C_SCL, 0
        WAITP I2C_SCL, 1
        WAITT
        OE I2C_SDA, 0
        WAITT
        RET

; send_byte: r1[7:0] on the bus MSB first, SCL low on entry and exit, ACK in C.
send_byte:
        LDI r2, 8
sh:     SHLC r1, r1          ; byte to r1[15:8]
        DJNZ r2, sh
        LDI r2, 8
bit:    SHLC r1, r1          ; C = bit
        OENC I2C_SDA         ; SDA = bit (release for 1, pull low for 0)
        WAITT                ; data setup while SCL low
        OE I2C_SCL, 0        ; SCL high
        WAITP I2C_SCL, 1     ; honour clock stretching
        WAITT
        WAITT
        OE I2C_SCL, 1        ; SCL low
        WAITT
        DJNZ r2, bit
        OE I2C_SDA, 0        ; release SDA for the ACK bit
        WAITT
        OE I2C_SCL, 0
        WAITP I2C_SCL, 1
        WAITT
        INC I2C_SDA          ; C = 0 means ACK
        WAITT
        OE I2C_SCL, 1
        WAITT
        RET
