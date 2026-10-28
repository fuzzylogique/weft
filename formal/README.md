# Formal proofs

SymbiYosys jobs, run by the `formal` GitHub workflow with the OSS CAD Suite:
one CI job per (file, task) with a 50-minute limit and sby's own timeout, so a
slow solver cannot hide the other results (the first run spent six hours in a
single smtbmc task and was killed by GitHub). Locally, `yowasp-sby` can run the
smtbmc tasks with z3 (`yowasp-sby --yosys yowasp-yosys --smtbmc
yowasp-yosys-smtbmc -f weft_timer.sby cover`); the `abc` engines need the OSS
CAD Suite.

| Job | What it proves | Mode |
| --- | --- | --- |
| `weft_core.sby` | For every instruction stream: `running` and `halted` are never both set; pins change only when an instruction fires; non-WAIT/DELAY/FIFO instructions never stall; `DJNZ` writes no flags; a consumed tick is cleared; the core never writes a full FIFO or reads an empty one. Covers show WAITT completion, taken branches, pin writes and an illegal halt are reachable. | `bmc`: 12 cycles, `abc bmc3` racing `smtbmc yices`; `cover`: depth 12; `prove`: `abc pdr`, optional in CI |
| `weft_timer.sby` | After `TSET P`, the count walks `P-1..0` and the tick rises exactly `P+1` cycles after TSET (period exactness as a contract). | `prove`: `abc pdr` (IC3), P=3; `cover` |
| `weft_fifo.sby` | Count equals writes minus reads, flags match the count, and a tagged word is read exactly in order. | `prove`: `abc pdr`; `cover` |
| `uart_tx_program.sby` | The core running `sw/programs/uart_tx.asm` (BIT=4) emits a correct 8N1 frame for *every* byte value, each bit exactly BIT cycles, and the line idles high afterwards. Hardware and firmware proven together. | `bmc`: 60 cycles on a bit-blasted model, `abc bmc3` racing `smtbmc yices`; `cover`: depth 62, optional in CI |

## Results so far (2026-10-28, Yosys 0.70 SAT engine via `formal/run_local.sh`)

| Job | Result |
| --- | --- |
| `weft_core` | 8-cycle BMC passes for every instruction stream (188K variables) |
| `uart_tx_program` | 62-cycle BMC passes at BIT=4 (1.56M variables): every byte, every bit exactly 4 cycles. At BIT=3 the proof produced a counterexample: the per-bit loop is 3 instructions plus WAITT, so 3 is below the program's minimum period. The proof found the firmware's real timing limit. |
| `weft_timer` | BMC passes to depth 12 (every reachable trace of 12 cycles satisfies the period and tick properties); k-induction is still inconclusive at depth 12 even with the period register asserted, so the unbounded claim is open |
| `weft_fifo` | BMC passes to depth 10; k-induction inconclusive without invariants tying the tag position to the pointers |

Local `yowasp-sby` runs with z3 (2026-10-28): the timer and FIFO `cover` tasks pass; their `prove` tasks pass the base case and fail plain k-induction at depth 20, which is why CI uses `abc pdr` for them. The `abc` engines could not be run locally; the CI run is the first execution of those tasks.

Regenerate the program ROM after changing `uart_tx.asm`:

```
python formal/gen_roms.py
```
