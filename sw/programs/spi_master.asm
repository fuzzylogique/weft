; spi_master.asm: SPI mode 0 (CPOL=0, CPHA=0) controller, MSB first.
; For each byte pulled from the host it drives one 8-bit transfer with CSn
; low and pushes the byte read on MISO. SCLK half period = HALF cycles
; (10 cycles = 2.5 MHz at 50 MHz; the timer keeps both halves exact).
.equ SPI_SCLK 1
.equ SPI_MOSI 2
.equ SPI_CSN  3
.equ SPI_MISO 1            ; input pin
.equ HALF     10

        OUT SPI_CSN, 1
        OUT SPI_SCLK, 0
        OUT SPI_MOSI, 0
        LDI r3, HALF
        TSET r3
loop:   PULL r1              ; byte to send in r1[7:0]
        LDI r2, 8
sh:     SHLC r1, r1          ; move it to r1[15:8] so SHLC pops the MSB first
        DJNZ r2, sh
        LDI r2, 8
        LDI r4, 0
        OUT SPI_CSN, 0
        WAITT
bit:    SHLC r1, r1          ; C = next bit, MSB first
        OUTC SPI_MOSI
        WAITT
        OUT SPI_SCLK, 1      ; target samples MOSI here
        INC SPI_MISO         ; sample MISO (synchronized value from just before the edge)
        SHLC r4, r4
        WAITT
        OUT SPI_SCLK, 0
        DJNZ r2, bit
        WAITT
        OUT SPI_CSN, 1
        ANDI r4, 0xFF
        PUSH r4
        JMP loop
