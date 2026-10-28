# Formal proofs

SymbiYosys jobs, run by the `formal` GitHub workflow with the OSS CAD Suite
(`make formal` locally if `sby` is installed; it is not part of the conda env
on macOS/arm64).

| Job | What it proves | Mode |
| --- | --- | --- |
| `weft_core.sby` | For every instruction stream: `running` and `halted` are never both set; pins change only when an instruction fires; non-WAIT/DELAY/FIFO instructions never stall; `DJNZ` writes no flags; a consumed tick is cleared; the core never writes a full FIFO or reads an empty one. Covers show WAITT completion, taken branches, pin writes and an illegal halt are reachable. | prove (k-induction, depth 10) |
| `weft_timer.sby` | After `TSET P`, the count walks `P-1..0` and the tick rises exactly `P+1` cycles after TSET (period exactness as a contract). | prove, P=3 |
| `weft_fifo.sby` | Count equals writes minus reads, flags match the count, and a tagged word is read exactly in order. | prove |
| `uart_tx_program.sby` | The core running `sw/programs/uart_tx.asm` (BIT=3) emits a correct 8N1 frame for *every* byte value, each bit exactly BIT cycles, and the line idles high afterwards. Hardware and firmware proven together. | bmc, depth 60 |

## Results so far (2026-10-28, Yosys 0.70 SAT engine via `formal/run_local.sh`)

| Job | Result |
| --- | --- |
| `weft_core` | 8-cycle BMC passes for every instruction stream (188K variables) |
| `uart_tx_program` | 62-cycle BMC passes at BIT=4 (1.56M variables): every byte, every bit exactly 4 cycles. At BIT=3 the proof produced a counterexample: the per-bit loop is 3 instructions plus WAITT, so 3 is below the program's minimum period. The proof found the firmware's real timing limit. |
| `weft_timer` | BMC passes to depth 12 (every reachable trace of 12 cycles satisfies the period and tick properties); k-induction is still inconclusive at depth 12 even with the period register asserted, so the unbounded claim is open |
| `weft_fifo` | BMC passes to depth 10; k-induction inconclusive without invariants tying the tag position to the pointers |

The SymbiYosys jobs (`*.sby`, with covers) run in the `formal` GitHub workflow; they have not been executed locally because `sby` is not available for macOS/arm64 through conda.

Regenerate the program ROM after changing `uart_tx.asm`:

```
python formal/gen_roms.py
```
