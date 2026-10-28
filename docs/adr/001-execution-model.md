# ADR-001: Simple single-cycle core with timing hardware beside it

Date: 2026-10-28 / Status: accepted
Owner: ARCH

Context: The research doc compares twelve execution models for a 24K-cell,
50 MHz budget and concludes that the real choice is where area and critical
path go: many things per cycle in a wide PIO-style instruction, or a trivial
core with timers, shift registers and timed pins beside it (PRU, XMOS, BIO
style). bunnie Huang's PIO clone spent its area and timing on pin muxing,
barrel shifters and FIFO thresholds and came to 39K cells, more than the whole
budget.

Options:
- A. PIO-style state machine: 16-bit instructions with delay/side-set fields,
  ISR/OSR shift registers, autopush. Dense programs, but the hard parts (pin
  mapping shifters, side-effect priority) are the hardest to verify, and it
  reads as a clone. Estimated 15K to 40K cells.
- B. Small off-the-shelf RISC-V (PicoRV32/SERV) with I/O registers and a
  quantum register. Mature toolchain, but 3+ cycles per instruction leaves
  about 11 instructions per low-speed USB bit, and program memory in the
  kilobytes needs SRAM macros that are unproven on CMOS5L.
- C. Own 16-bit single-cycle core, 8 registers, one instruction per cycle,
  plus a bit timer with WAITT, edge waits, a cycle counter and a CRC unit.
  Estimated under 60K µm² of logic before program memory.

Decision: C. Every instruction is one cycle except explicit waits, which
makes the cycle contract a single sentence that can be proven. Timing comes
from the timer, so bit periods do not depend on instruction counts. The core is
our own design, which is what the competition asks for and what the team learns
most from.

Consequences: Programs are longer than PIO programs (a UART TX bit is three
instructions rather than one), which is fine at 434 cycles per bit and still
fine at 50 cycles per bit (1 Mbaud). Protocols above about 5 MHz need
hardware help that this core does not have (no serializer); low-speed USB is
possible only with a dedicated shifter, which is out of scope for the first
chip. The 16-bit datapath wastes nothing: baud divisors (434, 5208) and CRC
state need 16 bits.

Revisit if: the first full GDS run shows the core logic above 100K µm², or a
target protocol needs more than one pin write per cycle.
