![](../../workflows/gds/badge.svg) ![](../../workflows/test/badge.svg) ![](../../workflows/sw/badge.svg) ![](../../workflows/formal/badge.svg) ![](../../workflows/docs/badge.svg)

# Weft: a tiny programmable protocol engine

An entry for the [Jane Street protocol emulator ASIC competition](https://blog.janestreet.com/protocol-emulator-asic-competition/)
on [Tiny Tapeout](https://tinytapeout.com) IHP CMOS5L, 6x4 tiles.

Weft is a 16-bit CPU that executes exactly one instruction per clock cycle, with
a bit timer, edge waits, a cycle counter and a CRC unit beside it, so that
**firmware produces protocol waveforms with exact bit timing**. UART, SPI and
I2C ship as programs; the host loads new ones over a four-pin SPI port after
fabrication. Its determinism contract is one sentence, and that sentence is
checked three ways: a cycle-accurate Python simulator is the executable spec,
the cocotb suite runs RTL and simulator in lockstep comparing every pin every
cycle, and SymbiYosys proves the timer's period and the core's stall rules for
every instruction stream, plus one proof that the chip *running the UART
program* is a correct UART.

```
        OUT UART_TX, 1       ; idle high
        LDW r3, 434          ; 115200 baud at 50 MHz
        TSET r3              ; bit clock: a tick every 434 cycles
loop:   PULL r1              ; byte from the host
        LDI r2, 8
        WAITT
        OUT UART_TX, 0       ; start bit
bit:    SHRC r1, r1          ; C = next bit, LSB first
        WAITT
        OUTC UART_TX         ; one instruction after WAITT: every bit exactly 434 cycles
        DJNZ r2, bit
        WAITT
        OUT UART_TX, 1       ; stop bit
        JMP loop
```

```
TX /‾‾‾‾‾‾‾‾‾‾‾‾‾\_____________/‾‾‾‾‾‾‾‾‾‾‾‾‾\_____________/‾‾‾‾‾‾‾‾‾‾‾‾‾\_____________/‾‾‾‾‾‾‾‾‾‾‾‾‾\_____________/‾‾‾‾‾‾‾
runs: 0*1 1*439 0*434 1*434 0*434 1*434 0*434 1*434 0*434 1*434 0*434 1*428      (0x55, snapshot from the ISS; the RTL matches it cycle for cycle)
```

## Status (2026-10-28)

| Piece | State |
| --- | --- |
| ISA, assembler, disassembler, cycle-accurate simulator | done; 55 instruction forms, one source table generates Verilog constants and docs |
| Firmware: blink, selftest, UART TX, UART RX, SPI controller, I2C controller | done, all checked against independent protocol models on the simulator |
| RTL (Verilog-2005, 9 modules) | done, Verilator `-Wall` clean |
| Python tests | 53 passing (Hypothesis round trips, ISS semantics, firmware + snapshots) |
| cocotb RTL tests (host port, lockstep vs ISS on all firmware and 12 random programs, final state via PEEK) | 13 of 13 passing under Verilator locally, under Icarus in CI, and on the gate-level netlist |
| Yosys area against the IHP CMOS5L liberty | 227,964 µm² = 41.5% of the 6x4 budget at 60% density; 2,621 flops. LibreLane's final utilization was 34.4% of the 6x4 core area |
| Formal (core, timer, FIFO, UART program) | run locally with Yosys's SAT engine: core 8-cycle BMC passes for every instruction stream; the UART program proof passes (every byte, every bit exactly BIT cycles, 62-cycle bound); SymbiYosys in CI (nine tasks, all green): **core invariants, FIFO and timer proven unbounded** (IC3/PDR, k-induction agrees for the timer); the UART program bound passes for every byte in 13 s with a cover showing the frame completes inside it. `formal/README.md` |
| Tiny Tapeout `gds` action (LibreLane, DRC/LVS, gate-level test) | builds at 34% utilization (layout viewer: https://fuzzylogique.github.io/weft/); DRC, LVS and antenna clean; precheck passed; gate-level suite 13 of 13. **Meets 50 MHz in every corner**: worst setup slack +2.30 ns in the slow corner (1.08 V, 125 °C), +7.79 ns nominal, after the first run came in at −2.68 ns and the critical path was cut from 38 to 29 cells (ADR-005). `docs/log/2026-10-28.md` |
| FPGA build | not attempted |

## Repository layout

```
info.yaml, src/          Tiny Tapeout project: RTL (tt_um_fuzzylogique_weft.v is the top), config.json
test/                    cocotb testbench, SPI host driver, lockstep harness (Makefile from the TT template)
sw/weft/                 isa.py (single source), asm.py, iss.py, protocols.py, bench.py, waves.py, gen.py
sw/programs/             firmware (.asm) and assembled .hex
sw/tests/                pytest suite and ASCII waveform snapshots
formal/                  SymbiYosys jobs and harnesses
synth/                   Yosys script against the IHP liberty, budget report generator
docs/                    isa.md (generated), architecture, host-interface, verification-plan, budget, adr/, log/
.github/workflows/       test, gds, docs, fpga (Tiny Tapeout) + sw (pytest, lint, generated-file check) + formal
```

## Quick start

```bash
conda create -n jsasic -c conda-forge --override-channels python=3.12 verilator gh make
conda activate jsasic
pip install cocotb==2.0.1 pytest==8.4.2 hypothesis yowasp-yosys && pip install -e sw
make test-sw      # 53 Python tests
make lint         # Verilator -Wall
make sim          # cocotb under Verilator (CI uses Icarus); needs a path without spaces, see docs/setup.md
make synth        # Yosys area with the CMOS5L liberty -> docs/budget.md
```

Write a program, assemble it, run it on the simulator:

```bash
python -m weft.asm sw/programs/uart_tx.asm --list
python -c "from weft.bench import *; r = run_iss(load_program('blink').words, cycles=1000, drain=True); print(r.pulled)"
```

## Architecture in one paragraph

Decode, execute and write back happen in one 20 ns cycle, with the instruction
word fetched into a register one edge earlier from the next PC: 8 x 16-bit
registers, Z/C flags, a link register, 128 x 16 flop program memory, a 16-bit
bit timer (`TSET`/`WAITT`), rising/falling edge waits, a free-running cycle
counter, a 16-bit CRC/LFSR with programmable polynomial, 16 output pins (8 of
them with output enables for open drain) and 16 synchronized inputs, two 4-deep
FIFOs to the host, and an SPI target port with load/run/stop/step/push/pull/peek.
Details and the reasoning behind each choice: `docs/architecture.md`,
`docs/adr/`, and the generated `docs/isa.md`.

## What has been run, honestly

- Everything under `sw/` has been run on this machine and passes.
- The RTL lints clean and synthesizes with Yosys against the real CMOS5L liberty.
- The cocotb suite (12 tests) passes under Verilator on this machine; the
  Tiny Tapeout `test` workflow runs the same suite under Icarus in CI.
- Formal properties were checked with Yosys's own SAT engine
  (`make formal-local`): the core BMC and the UART program proof pass; the
  timer and FIFO proofs pass their bounded checks. SymbiYosys itself runs in CI.
- No GDS has been produced yet. The area figures are Yosys estimates; LibreLane
  will add 20% to 50%.
- This entry was built with AI assistance (Claude), used for the full build,
  which departs from the "AI only at the start and end" rule in the research
  doc. Every commit says so. The research doc that shaped the design is the
  team's own.

## License

Apache-2.0, like the Tiny Tapeout template.
