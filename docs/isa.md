# Weft ISA reference

*Generated from `sw/weft/isa.py` by `python -m weft.gen`. Do not edit by hand.*

## Cycle contract

Every instruction completes in exactly one clock cycle, except: WAIT-class instructions (WAITP, WAITR, WAITF, WAITT, PUSH, PULL) hold the PC until their condition is true and complete in the first cycle in which it is observed; DELAY n occupies n+1 cycles. There is no pipeline, no cache, no interrupt and no other stall. A pin written by an instruction that completes in cycle N is driven at the pad register at the end of cycle N. An input read in cycle N returns the pad value from the start of cycle N-2 (two synchronizer stages).

## Programmer's model

- 8 general registers `r0`..`r7`, 16 bits each. No register is hardwired to zero.
- Flags `Z` and `C`. Every register-writing instruction sets `Z` from the value written, except `DJNZ`. Only ADD, SUB, ADDI, CMPI, SHLC, SHRC and INC write `C`.
- `PC` is `log2(PMEM_DEPTH)` bits wide; branch targets and `PC+1` wrap modulo the program memory depth.
- `LR` (link register) holds the return address of the last `CALL`; `RET` jumps to it. One level deep.
- Bit timer: a 16-bit period register and down-counter. After `TSET P`, a tick is raised every `P` cycles. `WAITT` consumes a tick; ticks do not queue, so a tick that arrives while one is pending is lost. The timer, like the cycle counter, only advances while the core runs: a host STOP freezes it and STEP moves it one cycle.
- `CYC`: free-running 16-bit cycle counter, counts every cycle the core runs (including stalls).
- CRC unit: 16-bit state and polynomial, shifted one bit per `CRCIN`/`CRCINR` from `C`.
- Pins: output pins 0-7 are `uo_out[7:0]`, 8-15 are `uio_out[7:0]` with an output enable per pin; input pins 0-7 are `ui_in[7:0]`, 8-15 are `uio_in[7:0]`. Inputs pass through a two-flop synchronizer.
- Host FIFOs: a 4-deep host-to-core FIFO read by `PULL` and a 4-deep core-to-host FIFO written by `PUSH`.

## Word format

```
 16-bit instructions, opcode in bits [15:12].  Fields a form does
not use are ignored by the hardware; the assembler writes them as zero.

    op   name   [11:9]   [8:6]   [5:3]  [2:0]
    0x0  SYS    sub      -       -      -        NOP, HALT, RET
    0x1  LDI    rd       h,imm8[7:0]             rd = imm8 (h=0) | rd[15:8] = imm8 (h=1)
    0x2  ALU    rd       rs      rt     fn       ADD SUB AND OR XOR SHLC SHRC MOV
    0x3  ADDI   rd       simm9[8:0]              rd = rd + sext(imm9)
    0x4  CMPI   rd       0,imm8[7:0]             flags of rd - imm8
    0x5  BR     cond     0,target[7:0]           conditional branch
    0x6  DJNZ   rd       0,target[7:0]           rd -= 1; branch if rd != 0
    0x7  OUT    sub      rs      0      pin[3:0] pin output / output-enable
    0x8  IN     sub      rd      0      pin[3:0] pin input
    0x9  WAIT   sub      0       0      pin[3:0] stall until pin level / edge / timer tick
    0xA  DELAY  imm12[11:0]                      stall imm12 extra cycles
    0xB  TIMER  sub      r                       TSET TSTOP RDCYC RDT
    0xC  LOGI   rd       h,imm8[7:0]             ANDI (h=0) / ORI (h=1)
    0xD  FIFO   sub      r                       PUSH PULL (host link)
    0xE  CRC    sub      r                       CRCPOLY CRCINIT CRCIN CRCINR CRCRD
    0xF  CALL   0        target[7:0]             LR = PC+1; PC = target
```

## Instructions

| Syntax | Encoding | Cycles | Flags | Semantics |
| --- | --- | --- | --- | --- |
| `NOP` | `[15:12]=0 [11:9]=0` | 1 | - | No operation. |
| `HALT` | `[15:12]=0 [11:9]=1` | 1 | - | Stop the core (running=0, halted=1). PC advances; a host RUN resumes after it. |
| `RET` | `[15:12]=0 [11:9]=2` | 1 | - | PC = LR (link register written by CALL). One level deep. |
| `LDI rd, imm8` | `[15:12]=1 [8]=0 [11:9]=rd [7:0]=imm8` | 1 | Z | rd = imm8 (zero-extended; the high byte is cleared). |
| `LDIH rd, imm8` | `[15:12]=1 [8]=1 [11:9]=rd [7:0]=imm8` | 1 | Z | rd[15:8] = imm8; rd[7:0] unchanged. LDI then LDIH loads a 16-bit constant. |
| `ADD rd, rs, rt` | `[15:12]=2 [2:0]=0 [11:9]=rd [8:6]=rs [5:3]=rt` | 1 | Z, C=carry out | rd = rs + rt. |
| `SUB rd, rs, rt` | `[15:12]=2 [2:0]=1 [11:9]=rd [8:6]=rs [5:3]=rt` | 1 | Z, C=borrow (rs < rt unsigned) | rd = rs - rt. |
| `AND rd, rs, rt` | `[15:12]=2 [2:0]=2 [11:9]=rd [8:6]=rs [5:3]=rt` | 1 | Z | rd = rs & rt. |
| `OR rd, rs, rt` | `[15:12]=2 [2:0]=3 [11:9]=rd [8:6]=rs [5:3]=rt` | 1 | Z | rd = rs | rt. |
| `XOR rd, rs, rt` | `[15:12]=2 [2:0]=4 [11:9]=rd [8:6]=rs [5:3]=rt` | 1 | Z | rd = rs ^ rt. |
| `SHLC rd, rs` | `[15:12]=2 [2:0]=5 [11:9]=rd [8:6]=rs` | 1 | Z, C=rs[15] | rd = {rs[14:0], C}; shift left, carry in at bit 0. |
| `SHRC rd, rs` | `[15:12]=2 [2:0]=6 [11:9]=rd [8:6]=rs` | 1 | Z, C=rs[0] | rd = {C, rs[15:1]}; shift right, carry in at bit 15. |
| `MOV rd, rs` | `[15:12]=2 [2:0]=7 [11:9]=rd [8:6]=rs` | 1 | Z | rd = rs. |
| `ADDI rd, simm9` | `[15:12]=3 [11:9]=rd [8:0]=simm9` | 1 | Z, C=carry out of the 16-bit add | rd = rd + sign_extend(imm9), imm9 in -256..255 (SUBI is ADDI of a negative). |
| `CMPI rd, imm8` | `[15:12]=4 [8]=0 [11:9]=rd [7:0]=imm8` | 1 | Z, C=borrow (rd < imm8) | Compare: flags of rd - imm8, rd unchanged. |
| `ANDI rd, imm8` | `[15:12]=12 [8]=0 [11:9]=rd [7:0]=imm8` | 1 | Z | rd = rd & imm8 (clears the high byte). |
| `ORI rd, imm8` | `[15:12]=12 [8]=1 [11:9]=rd [7:0]=imm8` | 1 | Z | rd = rd | imm8. |
| `JMP target` | `[15:12]=5 [11:9]=0 [8]=0 [7:0]=target` | 1 | - | PC = target. |
| `BEQ target` | `[15:12]=5 [11:9]=1 [8]=0 [7:0]=target` | 1 | - | Branch if Z. |
| `BNE target` | `[15:12]=5 [11:9]=2 [8]=0 [7:0]=target` | 1 | - | Branch if not Z. |
| `BCS target` | `[15:12]=5 [11:9]=3 [8]=0 [7:0]=target` | 1 | - | Branch if C. |
| `BCC target` | `[15:12]=5 [11:9]=4 [8]=0 [7:0]=target` | 1 | - | Branch if not C. |
| `BINE target` | `[15:12]=5 [11:9]=5 [8]=0 [7:0]=target` | 1 | - | Branch if the host-to-core FIFO is empty. |
| `BOUTF target` | `[15:12]=5 [11:9]=6 [8]=0 [7:0]=target` | 1 | - | Branch if the core-to-host FIFO is full. |
| `BTICK target` | `[15:12]=5 [11:9]=7 [8]=0 [7:0]=target` | 1 | - | Branch if a timer tick is pending (does not consume it). |
| `DJNZ rd, target` | `[15:12]=6 [8]=0 [11:9]=rd [7:0]=target` | 1 | - | rd = rd - 1; branch if the new rd != 0. Flags unchanged. |
| `CALL target` | `[15:12]=15 [11:9]=0 [8]=0 [7:0]=target` | 1 | - | LR = PC + 1; PC = target. One level: a nested CALL overwrites LR. |
| `OUT pin, 0` | `[15:12]=7 [11:9]=0 [3:0]=pin` | 1 | - | Drive output pin low (effective at the pad from the next cycle). |
| `OUT pin, 1` | `[15:12]=7 [11:9]=1 [3:0]=pin` | 1 | - | Drive output pin high. |
| `OUTC pin` | `[15:12]=7 [11:9]=2 [3:0]=pin` | 1 | - | Output pin = C. |
| `OUTR pin, rs` | `[15:12]=7 [11:9]=3 [3:0]=pin [8:6]=rs` | 1 | - | Output pin = rs[0]. |
| `OE pin, 0` | `[15:12]=7 [11:9]=4 [3:0]=pin` | 1 | - | Release bidirectional pin (input / open-drain high). Pins 0-7 ignore OE. |
| `OE pin, 1` | `[15:12]=7 [11:9]=5 [3:0]=pin` | 1 | - | Drive bidirectional pin. |
| `OEC pin` | `[15:12]=7 [11:9]=6 [3:0]=pin` | 1 | - | Output enable = C. |
| `OENC pin` | `[15:12]=7 [11:9]=7 [3:0]=pin` | 1 | - | Output enable = !C (open-drain bit: with OUT pin,0 set once, C=0 pulls low and C=1 releases). |
| `INC pin` | `[15:12]=8 [11:9]=0 [3:0]=pin` | 1 | C | C = input pin (synchronized, 2 cycles old). |
| `INR rd, pin` | `[15:12]=8 [11:9]=1 [8:6]=rd [3:0]=pin` | 1 | Z | rd = input pin as 0 or 1. |
| `INALL rd` | `[15:12]=8 [11:9]=2 [8:6]=rd` | 1 | Z | rd = all 16 input pins {uio_in, ui_in} sampled in the same cycle. |
| `WAITP pin, 0` | `[15:12]=9 [11:9]=0 [3:0]=pin` | wait | - | Stall until input pin reads 0. |
| `WAITP pin, 1` | `[15:12]=9 [11:9]=1 [3:0]=pin` | wait | - | Stall until input pin reads 1. |
| `WAITR pin` | `[15:12]=9 [11:9]=2 [3:0]=pin` | wait | - | Stall until a rising edge is seen on input pin. |
| `WAITF pin` | `[15:12]=9 [11:9]=3 [3:0]=pin` | wait | - | Stall until a falling edge is seen on input pin. |
| `WAITT` | `[15:12]=9 [11:9]=4` | wait | - | Stall until the bit timer ticks, then consume the tick. Consecutive WAITTs complete exactly one period apart. |
| `DELAY imm12` | `[15:12]=10 [11:0]=imm12` | delay | - | Stall for imm12 extra cycles (the instruction occupies imm12+1 cycles). |
| `TSET rs` | `[15:12]=11 [11:9]=0 [8:6]=rs` | 1 | - | Bit timer period = rs cycles (0 means 65536); restart counting; clear any pending tick. |
| `TSTOP` | `[15:12]=11 [11:9]=1` | 1 | - | Stop the bit timer and clear any pending tick. |
| `RDCYC rd` | `[15:12]=11 [11:9]=2 [8:6]=rd` | 1 | Z | rd = free-running 16-bit cycle counter (counts every cycle the core is running). |
| `RDT rd` | `[15:12]=11 [11:9]=3 [8:6]=rd` | 1 | Z | rd = current bit timer count (cycles until the next tick, minus one). |
| `PUSH rs` | `[15:12]=13 [11:9]=0 [8:6]=rs` | wait | - | Push rs to the core-to-host FIFO; stalls while it is full. |
| `PULL rd` | `[15:12]=13 [11:9]=1 [8:6]=rd` | wait | Z | Pop the host-to-core FIFO into rd; stalls while it is empty. |
| `CRCPOLY rs` | `[15:12]=14 [11:9]=0 [8:6]=rs` | 1 | - | CRC polynomial register = rs. |
| `CRCINIT rs` | `[15:12]=14 [11:9]=1 [8:6]=rs` | 1 | - | CRC state = rs. |
| `CRCIN` | `[15:12]=14 [11:9]=2` | 1 | - | Shift C into the CRC, MSB first: fb = crc[15]^C; crc = (crc<<1) ^ (fb ? poly : 0). |
| `CRCINR` | `[15:12]=14 [11:9]=3` | 1 | - | Shift C into the CRC, reflected (LSB first): fb = crc[0]^C; crc = (crc>>1) ^ (fb ? poly : 0). |
| `CRCRD rd` | `[15:12]=14 [11:9]=4 [8:6]=rd` | 1 | Z | rd = CRC state. |

Cycles: `1` = exactly one cycle; `wait` = holds until its condition is true, completing in the first cycle it is; `delay` = imm12+1 cycles.

## Pseudo-instructions

| Syntax | Expands to |
| --- | --- |
| `LDW rd, imm16` | `LDI rd, lo8(imm16); LDIH rd, hi8(imm16)` |
| `SUBI rd, imm` | `ADDI rd, -imm` |
| `CLR rd` | `LDI rd, 0` |

## Illegal encodings

Any word that is not one of the forms above (an undefined sub-field value, or a reserved bit set) halts the core with the `ILL` status bit set and leaves `PC` pointing at the offending word.

## Debug words (host PEEK)

| Index | Word |
| --- | --- |
| 0 | `R0` |
| 1 | `R1` |
| 2 | `R2` |
| 3 | `R3` |
| 4 | `R4` |
| 5 | `R5` |
| 6 | `R6` |
| 7 | `R7` |
| 8 | `PC` |
| 9 | `FLAGS` |
| 10 | `CYC` |
| 11 | `TCNT` |
| 12 | `CRC` |
| 13 | `POUT` |
| 14 | `POE` |
| 15 | `LR` |

`FLAGS` bits: bit 0 = Z, bit 1 = C, bit 2 = TICK, bit 3 = RUNNING, bit 4 = HALTED, bit 5 = ILL, bit 6 = TRUN.

## Host commands (SPI, see docs/host-interface.md)

| Byte | Command |
| --- | --- |
| 0x00 | `STATUS` |
| 0x01 | `LOAD` |
| 0x02 | `RESET` |
| 0x03 | `RUN` |
| 0x04 | `STOP` |
| 0x05 | `STEP` |
| 0x06 | `PUSH` |
| 0x07 | `PULL` |
| 0x08 | `PEEK` |
