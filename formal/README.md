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
| `weft_timer` | BMC passes to depth 12. k-induction and PDR were inconclusive because of a harness bug, not the design: the cycle counter saturated at 0xFFFF while the timer kept counting, so the asserted relation was false after 65535 cycles. With a modulo-PERIOD phase and an elapsed count that saturates at PERIOD+1, k-induction closes in one second (local sby with z3) |
| `weft_fifo` | BMC passes to depth 10; plain k-induction fails (no invariant ties the tag position to the pointers), PDR proves it unbounded in CI (below) |

## CI results (SymbiYosys, OSS CAD Suite 2026-10-01)

First per-task run, 2026-10-28 (workflow run 40772451647, RTL identical to the first GDS run):

| Task | Result |
| --- | --- |
| `weft_core prove` | **PASS, unbounded** (abc pdr, 1 s): for every instruction stream the core invariants hold in every reachable state |
| `weft_core bmc` | PASS, 12 cycles (smtbmc yices, 1 s; abc bmc3 was still starting) |
| `weft_core cover` | PASS |
| `weft_fifo prove` | **PASS, unbounded** (abc pdr, 4 s) |
| `weft_fifo cover` | PASS |
| `weft_timer cover` | PASS |
| `weft_timer prove` | TIMEOUT after 20 min: the harness bug above; fixed, rerun pending |
| `uart_tx_program bmc` | ERROR: the harness indexed the data byte with a 4-bit index, which leaves constant x bits that the AIGER model refuses; fixed (3-bit index), rerun pending |
| `uart_tx_program cover` | "PASS" at step 1, which was vacuous: the covers were not gated behind the reset and the arbitrary pre-reset state satisfied them. All harness covers are now gated like the asserts; this one needs the whole 62-cycle frame and is optional in CI |

Second run after the harness fixes, on the timing-restructured RTL (commit 5698fbd, workflow run 40776365356): **all nine tasks pass**.

| Task | Result |
| --- | --- |
| `weft_core prove` | PASS, unbounded (abc pdr, under a second) |
| `weft_core bmc` | PASS, 12 cycles (abc bmc3 first, under a second) |
| `weft_core cover` | PASS, all four covers |
| `weft_timer prove` | PASS, unbounded: abc pdr and k-induction (smtbmc yices) both close it |
| `weft_timer cover` | PASS: the tick is reached at step 6, PERIOD+1 cycles after TSET |
| `weft_fifo prove` | PASS, unbounded (abc pdr, 3 s) |
| `weft_fifo cover` | PASS at step 3 |
| `uart_tx_program bmc` | PASS, 60 cycles, every byte value (abc bmc3, 13 s; the array model had run past six hours) |
| `uart_tx_program cover` | PASS: a complete frame is reached at step 53, so the 60-cycle bound covers the whole transmission; the 0xA5 frame is reached too (23 s) |

Local check of the fixes beforehand with `yowasp-sby` and z3: timer `prove` by k-induction, every task's AIGER model builds, UART 60-cycle bound in 20 minutes on the bit-blasted model.

Regenerate the program ROM after changing `uart_tx.asm`:

```
python formal/gen_roms.py
```
