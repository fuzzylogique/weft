# ADR-005: Registered instruction fetch, three register read ports, 13 ns implementation clock

Date: 2026-10-28. Status: accepted and confirmed: the next GDS run (40775224776)
reported +2.30 ns worst setup slack in the slow corner (from −2.68 ns), +7.79 ns
nominal, no failing endpoints, with signoff at 20 ns.

Context: the first LibreLane run on IHP CMOS5L (gds run 40717152546) built the
chip and passed DRC, LVS, precheck and the gate-level tests, but the signoff STA
reported a worst setup slack of -2.68 ns at the slow corner (1.08 V, 125 °C,
5% derate) with 119 failing endpoints; the nominal corner had +5.76 ns. The
longest topological path in the Yosys netlist was 38 cells: PC register,
128:1 program-memory read mux, operand-address decode, register-file read mux,
16-bit adder, write-back mux, register file. Tiny Tapeout treats the slow-corner
result as a warning, but the competition specifies 50 MHz and a chip that is
only correct at room temperature is not a robust entry.

Options:
- A. Accept 44 MHz in the slow corner and document it.
- B. Pipeline fetch and execute with a branch bubble. Shortens the path most
  but breaks the one-instruction-per-cycle contract the firmware, the ISS and
  the proofs are built on.
- C. Keep the contract and remove avoidable depth: (1) register the instruction
  word, reading program memory from the next PC so the 128:1 mux leaves the
  decode-execute chain; (2) give the register file three read ports addressed
  directly by the rd, rs and rt fields and choose the operand after the read,
  instead of an opcode decode in front of the read mux; (3) decide DJNZ on
  `a != 1` rather than on the decremented result. Plus (4) constrain synthesis,
  placement and routing at 13 ns while signing off at 20 ns, so ABC and the
  resizer build for the slow corner (slow/nominal delay ratio about 1.6).

Decision: C. All four changes are invisible to firmware: `instr` is still
`pmem[pc]` in every cycle, every instruction still takes the cycles the
contract says, and the ISS did not change. Yosys now reports the longest path
at 29 cells (from 38); the 13 ns implementation target makes ABC pick faster
adder structures and the resizer upsize the rest. Cost: 16 flops for the
instruction register and one more 8:1 x 16 read mux, about 1,700 µm² together
(0.3% of the budget), plus whatever the tighter target adds in cell sizes.

Consequences: a host LOAD into the word the core fetches at the same edge is
seen one cycle late; the reference flow loads while the core is stopped or in
reset, and the ISS note says so. `config.json` carries a 13 ns CLOCK_PERIOD
with a comment, `src/signoff.sdc` fixes signoff at 20 ns, and `info.yaml` still
states 50 MHz.

Revisit if: the next GDS run still shows negative slack in the slow corner
(next candidates: a shared, explicitly structured adder for ADD/SUB/ADDI/CMPI/
DJNZ, and moving the illegal-encoding check off the PC mux), or if the tighter
target pushes utilization or hold-buffer count up noticeably.
