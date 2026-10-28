<!---
This file is used to generate your project datasheet. Please fill in the information below and delete any unused
sections.

You can also include images in this folder and reference them in the markdown. Each image must be less than
512 kb in size, and the combined size of all images must be less than 1 MB.
-->

## How it works

Weft is a tiny programmable protocol engine: a 16-bit CPU that executes exactly
one instruction per clock cycle, with timing hardware beside it so that
firmware, not fixed-function blocks, produces protocol waveforms with exact bit
timing. UART, SPI and I2C ship as programs (`sw/programs`), and new protocols
can be loaded after fabrication.

The core has eight 16-bit registers, Z and C flags, a link register for one
level of `CALL`/`RET`, and 128 words of program memory loaded by the host. Its
determinism contract is one sentence: every instruction takes one cycle except
the explicit waits (`WAITP`/`WAITR`/`WAITF` on a pin level or edge, `WAITT` on
the bit timer, `PUSH`/`PULL` on the host FIFOs) and `DELAY n` (n+1 cycles).

Beside the core:

- a **bit timer**: `TSET P` raises a tick every `P` cycles; `WAITT` consumes
  the next one. Firmware puts each pin write exactly one instruction after a
  `WAITT`, so every bit is exactly `P` cycles long regardless of the work done
  in between. 434 cycles gives 115200 baud at 50 MHz with 0.03% error.
- a free-running **cycle counter** (`RDCYC`) for timestamps and measurement,
- a 16-bit **CRC/LFSR unit** with a programmable polynomial, one bit per
  instruction, MSB-first or reflected,
- **carry as the serial bit**: `SHLC`/`SHRC` shift through C; `OUTC`, `OENC`,
  `INC` and `CRCIN` move C to and from pins and the CRC,
- **open-drain pins**: every `uio` pin has an output enable; `OENC` drives the
  enable from `!C`, so I2C needs no special hardware and clock stretching is a
  `WAITP SCL, 1`.

The host talks to the chip over an SPI target port on four pins
(`ui_in[7:5]`, `uo_out[7]`): load program memory, reset, run, stop,
single-step, push and pull 16-bit words through two 4-deep FIFOs, and peek at
every architectural register. See `docs/host-interface.md`.

The whole ISA is one Python table (`sw/weft/isa.py`) that generates the Verilog
decode constants, the assembler, the disassembler, the cycle-accurate
simulator's decoder and the ISA reference (`docs/isa.md`).

## How to test

1. Connect an SPI controller (the demo board's RP2350 works) to SCK `ui_in[5]`,
   MOSI `ui_in[6]`, CSn `ui_in[7]`, MISO `uo_out[7]`, mode 0, at most clk/8.
2. Send the STATUS command (`0x00` then four zero bytes): the first byte back is
   `0x01` (alive, stopped), the fifth is the host version `0x01`.
3. LOAD `sw/programs/selftest.hex` at address 0, then RESET and RUN. After about
   a thousand cycles STATUS reports halted and PULL returns `0xC0DE`: the ALU,
   shifts through carry, the CRC unit, the timer and CALL/RET all passed.
4. LOAD `blink.hex` and RUN: `uo_out[4]` toggles every 100 cycles exactly.
5. LOAD `uart_tx.hex`, RUN, PUSH a byte: it comes out on `uo_out[0]` at 115200
   8N1. LOAD `uart_rx.hex` and feed `ui_in[0]`: received bytes arrive via PULL.
6. `spi_master.hex` drives SCLK/MOSI/CSn on `uo_out[1..3]` and reads MISO on
   `ui_in[1]` at 2.5 MHz; `i2c_master.hex` runs a 100 kHz I2C controller on
   `uio[0]` (SCL) and `uio[1]` (SDA) with external pull-ups.

The cocotb suite in `test/` runs every one of these programs on the RTL in
lockstep with the Python simulator, comparing all output pins every cycle, and
decodes the resulting UART/SPI/I2C waveforms with independent protocol models.

## External hardware

None required. For the demos: a USB-UART adapter (3.3 V) on `uo_out[0]` /
`ui_in[0]`, any SPI target on `uo_out[1..3]` / `ui_in[1]`, an I2C device with
1 k to 10 k pull-ups on `uio[0..1]`.
