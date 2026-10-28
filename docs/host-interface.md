# Host interface

Weft is controlled over an SPI target port on four Tiny Tapeout pins. The demo
board's microcontroller (or any SPI controller) loads programs, starts and stops
the core, moves data through two 4-word FIFOs and inspects architectural state.

| Signal | Pin | Direction |
| --- | --- | --- |
| SCK | `ui_in[5]` | in |
| MOSI | `ui_in[6]` | in |
| CSn | `ui_in[7]` | in, active low |
| MISO | `uo_out[7]` | out |

SPI mode 0 (clock idles low, data sampled on the rising edge), MSB first, 8-bit
bytes. The port samples its inputs through the chip's two-flop synchronizers and
reacts a few cycles later, so **SCK must be at most clk/8** (6.25 MHz at 50 MHz).
The cocotb host driver uses clk/10.

## Transactions

A transaction is: CSn low, one command byte, zero or more data bytes, CSn high.
While the command byte is clocked in, MISO returns status byte 0, so any
transaction doubles as an "are you alive" check (bit 0 is always 1).

| Command | Byte | Data bytes in | Data bytes out |
| --- | --- | --- | --- |
| STATUS | `0x00` | any number of zeros | status bytes 0, 1, 2, 3, 0, 1, ... |
| LOAD | `0x01` | address, then (hi, lo) word pairs | - |
| RESET | `0x02` | - | - |
| RUN | `0x03` | - | - |
| STOP | `0x04` | - | - |
| STEP | `0x05` | - | - |
| PUSH | `0x06` | (hi, lo) word pairs into the host-to-core FIFO | - |
| PULL | `0x07` | zeros, two per word | (hi, lo) of each word popped from the core-to-host FIFO |
| PEEK | `0x08` | selector | (hi, lo) of the selected debug word, repeating |

Status bytes:

| Byte | Bits |
| --- | --- |
| 0 | `[0]` alive (always 1), `[1]` running, `[2]` halted, `[3]` illegal instruction, `[6]` host-to-core FIFO empty, `[7]` core-to-host FIFO full |
| 1 | program counter |
| 2 | `[2:0]` host-to-core FIFO count, `[6:4]` core-to-host FIFO count |
| 3 | host interface version (`0x01`) |

Core control:

- **RESET** returns every architectural register, the pins (all low, all
  released), the timer, the CRC unit and both FIFOs to their reset values. It
  does not touch program memory.
- **RUN** sets `running` and clears `halted`; the core continues at the current
  PC. After a `HALT` instruction, RUN resumes with the instruction after it.
- **STOP** freezes the core with all state intact, including the bit timer and
  cycle counter. **STEP** executes exactly one clock cycle (which may be a stall
  cycle of a WAIT or DELAY); the timer advances one cycle with it.
- **LOAD** writes 16-bit words starting at the given address, incrementing after
  each word. Program memory is not reset, so a loader should write every word
  the program can reach; the reference loader zero-fills the whole memory
  (0x0000 is NOP).
- **PEEK** selectors: 0-7 = r0..r7 (valid only while stopped), 8 = PC,
  9 = FLAGS (`[0]` Z, `[1]` C, `[2]` tick pending, `[3]` running, `[4]` halted,
  `[5]` illegal, `[6]` timer running), 10 = cycle counter, 11 = timer count,
  12 = CRC state, 13 = output pin register, 14 = output enables, 15 = link register.

## Typical bring-up sequence

```
RESET
LOAD 0, <program words, zero-filled to 128>
RESET
PUSH <initial data words, at most 4>
RUN
... poll STATUS, PULL results, PUSH more data ...
STOP, PEEK 8 (PC), PEEK 0..7
```

A MicroPython sketch for the Tiny Tapeout demo board is in `docs/bringup.md`.
