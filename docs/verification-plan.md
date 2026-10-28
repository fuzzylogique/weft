# Verification plan

One row per checkable feature, following the layered strategy from the research
doc: encoding (layer 0), ISA (1), programs on the ISS (2), programs on the RTL
(3), system (4). "Status" is what has actually been run; see the README for
what has not.

| ID | Feature (checkable statement) | Method | Where | Status |
| --- | --- | --- | --- | --- |
| ENC-01 | Every instruction form assembles, disassembles and re-assembles to the same word | Hypothesis round trip, 400 cases | `sw/tests/test_asm.py` | passing |
| ENC-02 | Every 16-bit word is either a defined form or illegal, consistently in table, assembler and ISS | Hypothesis over all words | `sw/tests/test_asm.py` | passing |
| ENC-03 | Verilog decode constants, `docs/isa.md` and program `.hex` files match `isa.py` | `weft.gen --check` in CI | `.github/workflows/sw.yaml` | passing |
| ISA-01 | ADD/SUB/ADDI/CMPI set Z and C as specified | directed ISS | `sw/tests/test_iss.py` | passing |
| ISA-02 | SHLC/SHRC shift through C; LDI/LDIH/ANDI/ORI byte semantics | directed ISS | `test_iss.py` | passing |
| ISA-03 | DJNZ writes no flags; branches on Z/C/AL; CALL/RET via LR | directed ISS; formal (`weft_core.sby`) | `test_iss.py`, `formal/` | passing; core BMC (8 cycles, every instruction stream) passes locally |
| ISA-04 | DELAY n occupies exactly n+1 cycles | directed ISS; RTL single-step | `test_iss.py`, `test/test.py::test_single_step` | passing |
| ISA-05 | After TSET P, WAITT completions are exactly P cycles apart; first tick P+1 after TSET; ticks do not queue | directed ISS; formal proof (`weft_timer.sby`) | `test_iss.py`, `formal/` | ISS passing; timer BMC to depth 12 passes, induction pending |
| ISA-06 | WAITP/WAITR/WAITF see inputs two cycles late and complete in the cycle the condition is observed | directed ISS | `test_iss.py` | passing |
| ISA-07 | OUT/OE/OUTC/OENC touch exactly one pin; OE on pins 0-7 has no effect | directed ISS; formal (pins change only when fired) | `test_iss.py`, `formal/` | ISS passing; covered by the core BMC |
| ISA-08 | PUSH stalls on full, PULL stalls on empty; FIFO order preserved | directed ISS; RTL round trip; formal (`weft_fifo.sby`) | `test_iss.py`, `test/test.py::test_fifo_round_trip` | passing; FIFO BMC to depth 10 passes, induction inconclusive |
| ISA-09 | CRCIN/CRCINR compute CRC-16/CCITT and reflected CRC-16 correctly | directed ISS with known vectors; selftest on RTL | `test_iss.py`, `selftest.asm` | passing |
| ISA-10 | Illegal encodings halt with ILL set and PC on the word | directed ISS; RTL | `test_iss.py`, `test/test.py::test_illegal_instruction_halts` | passing |
| ISA-11 | HALT stops; RUN resumes after it | ISS; RTL | `test_iss.py`, `test/test.py` | passing |
| RTL-01 | RTL matches ISS on every output pin every cycle for all demo programs | lockstep cocotb | `test/test.py::test_lockstep_*` | passing (Verilator): 6 programs, up to 19,500 cycles each |
| RTL-02 | RTL matches ISS on all 16 debug words after each lockstep run | PEEK comparison | `test/test.py` | passing |
| RTL-03 | RTL matches ISS on constrained-random programs with random pin activity | 12 seeds x 600 cycles | `test/test.py::test_lockstep_random_programs` | passing: 12 seeds |
| RTL-04 | Verilator `-Wall` lint clean | lint | `make lint`, CI | passing |
| HOST-01 | STATUS alive/version; LOAD then PEEK; STEP executes exactly one cycle; FIFO push/pull | directed cocotb | `test/test.py` | passing |
| UART-01 | uart_tx.asm: every byte framed 8N1, every bit exactly 434 cycles | ISS + UartDecoder; RTL + UartDecoder; program-level formal at BIT=4 | `test_programs.py`, `test/test.py`, `formal/uart_tx_program.sby` | ISS passing; RTL passing (bits exactly 434 cycles); program-level proof passes at BIT=4, 62-cycle bound (BIT=3 was refuted: the loop is 4 instructions) |
| UART-02 | uart_rx.asm receives 8N1 at 434 cycles/bit incl. 0x00/0xFF, flags framing errors as 0x01FF | ISS + stimulus; RTL lockstep | `test_programs.py`, `test/test.py` | ISS and RTL passing |
| SPI-01 | spi_master.asm: mode 0, MSB first, both SCLK half periods exactly 10 cycles, MISO captured | ISS + SpiSlaveModel/SpiMonitor; RTL lockstep | same | ISS and RTL passing |
| I2C-01 | i2c_master.asm: START, address+W, data, STOP; ACK/NACK reported; target memory written | ISS + I2cTargetModel/I2cMonitor; RTL lockstep | same | ISS and RTL passing |
| I2C-02 | i2c_master.asm honours clock stretching | ISS with stretching target | `test_programs.py` | passing |
| SNAP-01 | ASCII waveform snapshots of blink, UART TX, SPI and I2C are stable | expect-test style snapshots | `sw/tests/snapshots/` | passing |
| GL-01 | Gate-level netlist passes the same cocotb suite | Tiny Tapeout `gds` action, `gl_test` job | GitHub Actions | passing: 13 of 13 on the LibreLane netlist (2026-10-28, run 40717152546) |
| PD-01 | Fits 6x4 at 50 MHz: utilization under 75%, positive slack, DRC/LVS clean | Tiny Tapeout `gds` action | GitHub Actions | built: placement utilization 27% plus 16.9% hold buffers; DRC, LVS, antenna, hold clean; precheck passed; setup clean at the nominal corner but **violations reported in the slow corner (1.08 V, 125 °C)**, slack value still to be read from the run artifact |
| FPGA-01 | Core runs on the iCE40UP5K breakout | `fpga` workflow | GitHub Actions | not attempted |

Methods not yet applied, in the order the research doc suggests: functional and
code coverage of the lockstep runs (week 8), mutation testing with MCY (week 13),
equivalence checking after area work, hardware-in-the-loop with real
peripherals, and the gated AI property funnel at the end.
