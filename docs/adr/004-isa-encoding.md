# ADR-004: 16-bit instructions, 4-bit opcode, 3-bit register fields

Date: 2026-10-28 / Status: accepted
Owner: ARCH

Context: The ISA decision list in the design-space tab asks, per axis, what
the UART, SPI and I2C programs actually use. The hand-written programs
(`sw/programs`) need: load constants up to 16 bits, add/subtract with carry,
shift through carry, compare and branch on Z/C, a loop counter, pin set/clear
by constant and by carry, pin read into carry, wait for level/edge/tick, and
a call/return for shared byte routines.

Decision: 16-bit words, opcode in [15:12] (16 opcodes), three 3-bit register
fields where needed (rd [11:9], rs [8:6], rt [5:3]), 8-bit immediates with a
selector bit for high/low byte loads and AND/OR, a 9-bit signed immediate for
ADDI, 8-bit absolute branch targets, 4-bit pin numbers, a 12-bit DELAY count.
Fields a form does not use are ignored by hardware and written as zero by the
assembler. Undefined sub-field values are illegal and halt the core with the
ILL status bit set, PC pointing at the word.

Consequences: Constants above 255 take two instructions (LDI + LDIH, the
LDW pseudo-op). The 8-bit branch target caps program memory at 256 words,
which matches the 128-word memory with room to grow. Eight registers were
enough for every demo program with two to spare. One link register means no
nested calls; the I2C program is structured as a dispatch loop calling leaf
routines.

Revisit if: a protocol program runs out of registers or needs nested calls
(options: a 2-entry LR stack, or spill to the host FIFO).
