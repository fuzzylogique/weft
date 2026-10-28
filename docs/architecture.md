# Architecture

Weft is a 16-bit, one-instruction-per-cycle protocol engine with timing
hardware beside it. The research doc's conclusion drove the shape: keep the
core almost trivial and spend the area on a bit timer, edge waits, a cycle
counter and a CRC unit, so firmware can hit exact bit timing without counting
instructions.

```
                     ui_in[7:5]                 uo_out[7]
                        |                           ^
                 +------v------+  pulses   +--------+---------+
   ui_in[4:0] -->|  weft_sync  |---------->|  weft_host_spi   |<---- STATUS/PEEK
   uio_in[7:0]-->| 2 flops +1  |  pins     | SPI target, cmds |
                 +------+------+           +---+----------+---+
                        |                      | load     | push/pull/ctl
                        v                      v          v
                 +------+------+   instr   +---+----+  +--+-------+
                 |  weft_core  |<----------| weft_  |  | 2x FIFO  |
                 | PC LR Z C   |    pc     | pmem   |  | 4 x 16   |
                 | 8 x r16     |---------->| 128x16 |  +----------+
                 | ALU, decode |           +--------+
                 | timer, CRC  |
                 | pout, poe   |----> uo_out[6:0], uio_out[7:0], uio_oe[7:0]
                 +-------------+
```

## Execution model

- **Single cycle.** Fetch (`pmem[pc]`), decode, execute and write-back happen
  in one 20 ns cycle. There is no pipeline, so there are no hazards and no
  branch penalty. The critical path is the 128:1 program-memory read mux, the
  decoder, the 16-bit adder and the write-back mux: about 13 ns at the slow
  corner by the gate delays in the research doc, comfortably inside 20 ns.
- **Determinism contract.** Every instruction takes exactly one cycle except
  WAIT-class instructions (`WAITP`, `WAITR`, `WAITF`, `WAITT`, `PUSH`, `PULL`),
  which hold until their condition is true and complete in the first cycle it
  is, and `DELAY n`, which takes `n+1` cycles. Nothing else ever stalls. The
  ISS counts cycles by this contract and the lockstep tests compare every pin
  every cycle, so the contract is verified, not asserted.
- **Timing lives in hardware, not in instruction counts.** `TSET P` starts a
  16-bit down-counter that raises a tick every `P` cycles; `WAITT` waits for
  the next tick and consumes it. Firmware places the pin write exactly one
  instruction after each `WAITT`, so every bit is exactly `P` cycles regardless
  of how much work happens between ticks (as long as it is less than `P`). The
  UART, SPI and I2C programs all use this pattern; the UART snapshot shows ten
  bits of exactly 434 cycles. The timer and the cycle counter only advance
  while the core runs, so a host STOP freezes the whole engine and STEP moves
  it exactly one cycle.
- **Edge waits.** `WAITR`/`WAITF` complete in the cycle a rising or falling
  edge is observed on a synchronized input, which gives UART RX start-bit
  detection and SPI/PS/2 clock following without polling loops.
- **Carry as the serial bit.** `SHLC`/`SHRC` shift through `C`; `OUTC`,
  `OENC`, `INC` and `CRCIN` move `C` to and from pins and the CRC unit. A
  UART bit is `SHRC; WAITT; OUTC`. A reflected or MSB-first CRC is one
  instruction per bit for any polynomial up to 16 bits.
- **Open drain.** Each `uio` pin has an output enable; `OENC pin` sets the
  enable to `!C`, so with the data register held low once, `C=0` pulls the
  line low and `C=1` releases it. I2C needs no special hardware; clock
  stretching is handled by `WAITP SCL, 1` after releasing the clock.

## Programmer's model

See `docs/isa.md` (generated from `sw/weft/isa.py`). Eight 16-bit registers,
flags Z and C, a link register for one level of `CALL`/`RET`, a 7-bit PC over
128 words of program memory, a free-running cycle counter (`RDCYC`), the bit
timer, the CRC unit, and two 4-deep FIFOs to the host.

## Pin map

| Pins | Use |
| --- | --- |
| `uo_out[6:0]` | output pins 0-6 for firmware: UART TX on 0, SPI SCLK/MOSI/CSn on 1/2/3, LED on 4 in the demos |
| `uo_out[7]` | host SPI MISO |
| `ui_in[4:0]` | input pins 0-4 for firmware: UART RX on 0, SPI MISO on 1 in the demos |
| `ui_in[7:5]` | host SPI CSn, MOSI, SCK |
| `uio[7:0]` | bidirectional pins 8-15 with per-pin output enable: I2C SCL/SDA on 8/9 in the demos |

Firmware addresses pins by number: output pins 0-7 are `uo_out`, 8-15 are
`uio`; input pins 0-7 are `ui_in`, 8-15 are `uio`. Writes to output pin 7 have
no effect at the pad (it is the host MISO). Input pins 5-7 read the host lines.

All inputs pass through two synchronizer flops plus one more for edge
detection; an instruction in cycle N sees the pad value from the start of
cycle N-2. All outputs come straight from the pin registers.

## Area and timing

`docs/budget.md` has the Yosys cell counts and area against the IHP CMOS5L
liberty per module, next to the hand estimates from the research doc. Program
memory is flip-flops (the brief's "safest" option); 128 words was chosen so
three or four protocol programs fit at once, and `PMEM_AW` in the top module
shrinks it to 64 words if the first GDS run says so.

## What is different about it

- The determinism contract is machine-checked three ways: the Python ISS is
  the executable spec, the cocotb suite runs RTL and ISS in lockstep comparing
  every pin every cycle (on the demo firmware and on constrained-random
  programs), and SymbiYosys proves the timer's period and the core's stall
  rules for every instruction stream.
- A program-level proof: `formal/uart_tx_program.sby` proves that the core
  running the actual `uart_tx.asm` emits a correct 8N1 frame with every bit
  exactly BIT cycles long, for every byte value. Hardware and firmware are
  verified together, which the competition brief singled out as the open
  methodology angle.
- Single-step, PEEK and the cycle counter make the chip observable from the
  host: a judge can step the engine one cycle at a time and read every
  register through the pins.
- One source file (`sw/weft/isa.py`) generates the Verilog decode constants,
  the assembler, the disassembler, the ISS decoder and the ISA reference, so an
  encoding mismatch between layers is impossible by construction.
