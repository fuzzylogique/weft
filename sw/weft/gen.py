"""Generate the Verilog decode constants and the ISA reference from weft.isa.

    python -m weft.gen            # rewrite src/weft_core.v region and docs/isa.md
    python -m weft.gen --check    # exit 1 if either file is out of date (CI)
"""

from __future__ import annotations

import argparse
import os
import sys

from . import isa

ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
CORE_V = os.path.join(ROOT, "src", "weft_core.v")
ISA_MD = os.path.join(ROOT, "docs", "isa.md")
BEGIN = "  // BEGIN GENERATED ISA (python -m weft.gen; do not edit by hand)"
END = "  // END GENERATED ISA"


def _lp(name: str, width: int, value: int) -> str:
    return f"  localparam [{width - 1}:0] {name} = {width}'d{value};"


def verilog_constants() -> str:
    lines = [BEGIN, "  /* verilator lint_off UNUSEDPARAM */"]
    lines += [_lp("OP_" + k, 4, v) for k, v in isa.OP.items()]
    tables = [
        ("SYS_", isa.SYS_SUB, 3), ("ALU_", isa.ALU_FN, 3), ("BR_", isa.BR_COND, 3), ("OUT_", isa.OUT_SUB, 3),
        ("IN_", isa.IN_SUB, 3), ("WAIT_", isa.WAIT_SUB, 3), ("TMR_", isa.TIMER_SUB, 3), ("LOGI_", isa.LOGI_SUB, 1),
        ("FIFO_", isa.FIFO_SUB, 3), ("CRC_", isa.CRC_SUB, 3), ("DBG_", isa.DBG, 4), ("FLAG_", isa.FLAG_BITS, 4),
    ]
    for prefix, table, width in tables:
        lines.append("")
        lines += [_lp(prefix + k, width, v) for k, v in table.items()]
    lines.append("")
    lines += [_lp("HOST_" + k, 8, v) for k, v in isa.HOST_CMD.items()]
    lines.append(_lp("HOST_VERSION", 8, isa.HOST_VERSION))
    lines.append("  /* verilator lint_on UNUSEDPARAM */")
    lines.append(END)
    return "\n".join(lines)


def _show(syntax: str) -> str:
    for k, v in isa.FIELD_DISPLAY.items():
        syntax = syntax.replace("{" + k + "}", v)
    return syntax.replace("{", "").replace("}", "")


def _encoding(ins: isa.Instr) -> str:
    cells = []
    for f, v in sorted(ins.fixed.items(), key=lambda kv: -isa.FIELDS[kv[0]][0]):
        msb, lsb = isa.FIELDS[f]
        cells.append(f"[{msb}:{lsb}]={v}" if msb != lsb else f"[{msb}]={v}")
    for p in ins.placeholders:
        msb, lsb = isa.FIELDS[p]
        cells.append(f"[{msb}:{lsb}]={isa.FIELD_DISPLAY.get(p, p)}")
    return " ".join(cells)


def isa_markdown() -> str:
    out = []
    out.append("# Weft ISA reference\n")
    out.append("*Generated from `sw/weft/isa.py` by `python -m weft.gen`. Do not edit by hand.*\n")
    out.append("## Cycle contract\n")
    out.append(isa.cycle_contract() + "\n")
    out.append("## Programmer's model\n")
    out.append(f"- {isa.NREGS} general registers `r0`..`r7`, {isa.WORD_BITS} bits each. No register is hardwired to zero.")
    out.append("- Flags `Z` and `C`. Every register-writing instruction sets `Z` from the value written, except `DJNZ`. Only ADD, SUB, ADDI, CMPI, SHLC, SHRC and INC write `C`.")
    out.append("- `PC` is `log2(PMEM_DEPTH)` bits wide; branch targets and `PC+1` wrap modulo the program memory depth.")
    out.append("- `LR` (link register) holds the return address of the last `CALL`; `RET` jumps to it. One level deep.")
    out.append("- Bit timer: a 16-bit period register and down-counter. After `TSET P`, a tick is raised every `P` cycles. `WAITT` consumes a tick; ticks do not queue, so a tick that arrives while one is pending is lost. The timer, like the cycle counter, only advances while the core runs: a host STOP freezes it and STEP moves it one cycle.")
    out.append("- `CYC`: free-running 16-bit cycle counter, counts every cycle the core runs (including stalls).")
    out.append("- CRC unit: 16-bit state and polynomial, shifted one bit per `CRCIN`/`CRCINR` from `C`.")
    out.append(f"- Pins: output pins 0-7 are `uo_out[7:0]`, 8-15 are `uio_out[7:0]` with an output enable per pin; input pins 0-7 are `ui_in[7:0]`, 8-15 are `uio_in[7:0]`. Inputs pass through a two-flop synchronizer.")
    out.append(f"- Host FIFOs: a {isa.FIFO_DEPTH}-deep host-to-core FIFO read by `PULL` and a {isa.FIFO_DEPTH}-deep core-to-host FIFO written by `PUSH`.\n")
    out.append("## Word format\n")
    out.append("```")
    out.append(isa.__doc__.split("Word format:", 1)[1].strip("\n"))
    out.append("```\n")
    out.append("## Instructions\n")
    out.append("| Syntax | Encoding | Cycles | Flags | Semantics |")
    out.append("| --- | --- | --- | --- | --- |")
    for ins in isa.INSTRUCTIONS:
        out.append(f"| `{_show(ins.syntax)}` | `{_encoding(ins)}` | {ins.cycles} | {ins.flags or '-'} | {ins.desc} |")
    out.append("\nCycles: `1` = exactly one cycle; `wait` = holds until its condition is true, completing in the first cycle it is; `delay` = imm12+1 cycles.\n")
    out.append("## Pseudo-instructions\n")
    out.append("| Syntax | Expands to |")
    out.append("| --- | --- |")
    for k, v in isa.PSEUDO.items():
        out.append(f"| `{_show(k)}` | `{v}` |")
    out.append("\n## Illegal encodings\n")
    out.append("Any word that is not one of the forms above (an undefined sub-field value, or a reserved bit set) halts the core with the `ILL` status bit set and leaves `PC` pointing at the offending word.\n")
    out.append("## Debug words (host PEEK)\n")
    out.append("| Index | Word |")
    out.append("| --- | --- |")
    for k, v in isa.DBG.items():
        out.append(f"| {v} | `{k}` |")
    out.append("\n`FLAGS` bits: " + ", ".join(f"bit {v} = {k}" for k, v in isa.FLAG_BITS.items()) + ".\n")
    out.append("## Host commands (SPI, see docs/host-interface.md)\n")
    out.append("| Byte | Command |")
    out.append("| --- | --- |")
    for k, v in isa.HOST_CMD.items():
        out.append(f"| 0x{v:02x} | `{k}` |")
    out.append("")
    return "\n".join(out)


def splice(text: str) -> str:
    if BEGIN not in text or END not in text:
        raise SystemExit(f"{CORE_V}: generated-region markers not found")
    head, rest = text.split(BEGIN, 1)
    _, tail = rest.split(END, 1)
    return head + verilog_constants() + tail


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    changed = []
    with open(CORE_V) as f:
        core = f.read()
    new_core = splice(core)
    if new_core != core:
        changed.append(CORE_V)
        if not a.check:
            with open(CORE_V, "w") as f:
                f.write(new_core)
    md = isa_markdown()
    old_md = open(ISA_MD).read() if os.path.exists(ISA_MD) else None
    if md != old_md:
        changed.append(ISA_MD)
        if not a.check:
            os.makedirs(os.path.dirname(ISA_MD), exist_ok=True)
            with open(ISA_MD, "w") as f:
                f.write(md)
    if a.check:
        if changed:
            print("out of date: " + ", ".join(os.path.relpath(c, ROOT) for c in changed))
            return 1
        print("generated files are up to date")
        return 0
    print("updated: " + (", ".join(os.path.relpath(c, ROOT) for c in changed) or "nothing"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
