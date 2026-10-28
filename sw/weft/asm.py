"""Two-pass assembler and disassembler for the Weft ISA.

Source syntax::

    ; comment            (also '#')
    .equ NAME expr       ; constant
    .word expr           ; raw 16-bit word
    label:
        LDI r1, 0x55     ; registers r0..r7, immediates dec/0x/0b/'c', labels, + and -
        LDW r2, 0x1234   ; pseudo: LDI + LDIH
        OUT TX, 1        ; pins 0..15 (names via .equ)
        CALL send_byte

Every instruction form comes from :mod:`weft.isa`; the assembler matches the
mnemonic and operand shape against the syntax templates there, so adding an
instruction to the table is enough to teach the assembler about it.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field

from . import isa


class AsmError(Exception):
    def __init__(self, msg: str, line: int | None = None):
        super().__init__(f"line {line}: {msg}" if line else msg)
        self.line = line


@dataclass
class Program:
    words: list[int]
    symbols: dict[str, int] = field(default_factory=dict)
    listing: list[tuple[int, int, str]] = field(default_factory=list)  # (addr, word, source)

    def to_hex(self) -> str:
        return "\n".join(f"{w:04x}" for w in self.words) + "\n"

    def to_bytes(self) -> bytes:
        """Big-endian byte pairs, the order the host LOAD command sends."""
        return b"".join(bytes([w >> 8, w & 0xFF]) for w in self.words)


# ---------------------------------------------------------------------------
# Expressions
# ---------------------------------------------------------------------------

_TOKEN = re.compile(r"\s*(0[xX][0-9a-fA-F]+|0[bB][01]+|\d+|'(?:\\.|[^'])'|[A-Za-z_.$][A-Za-z0-9_.$]*|[()+\-*]|<<|>>)")


class _Expr:
    """Tiny recursive-descent evaluator: + - * << >> unary- ( ) lo8() hi8() symbols."""

    def __init__(self, text: str, symbols: dict[str, int], line: int):
        self.toks = []
        pos = 0
        text = text.strip()
        while pos < len(text):
            m = _TOKEN.match(text, pos)
            if not m:
                raise AsmError(f"bad expression {text!r}", line)
            self.toks.append(m.group(1))
            pos = m.end()
        self.i = 0
        self.symbols = symbols
        self.line = line

    def peek(self):
        return self.toks[self.i] if self.i < len(self.toks) else None

    def take(self):
        t = self.peek()
        self.i += 1
        return t

    def parse(self) -> int:
        v = self.shift()
        if self.peek() is not None:
            raise AsmError(f"unexpected {self.peek()!r}", self.line)
        return v

    def shift(self):
        v = self.sum()
        while self.peek() in ("<<", ">>"):
            op = self.take()
            r = self.sum()
            v = v << r if op == "<<" else v >> r
        return v

    def sum(self):
        v = self.term()
        while self.peek() in ("+", "-"):
            op = self.take()
            r = self.term()
            v = v + r if op == "+" else v - r
        return v

    def term(self):
        v = self.unary()
        while self.peek() == "*":
            self.take()
            v = v * self.unary()
        return v

    def unary(self):
        t = self.peek()
        if t == "-":
            self.take()
            return -self.unary()
        if t == "+":
            self.take()
            return self.unary()
        return self.atom()

    def atom(self):
        t = self.take()
        if t is None:
            raise AsmError("missing operand", self.line)
        if t == "(":
            v = self.shift()
            if self.take() != ")":
                raise AsmError("missing )", self.line)
            return v
        if t.lower().startswith("0x"):
            return int(t, 16)
        if t.lower().startswith("0b"):
            return int(t, 2)
        if t.isdigit():
            return int(t, 10)
        if t.startswith("'"):
            body = t[1:-1]
            return ord(body[1]) if body.startswith("\\") else ord(body)
        if t.lower() in ("lo8", "hi8") and self.peek() == "(":
            self.take()
            v = self.shift()
            if self.take() != ")":
                raise AsmError("missing )", self.line)
            return (v & 0xFF) if t.lower() == "lo8" else ((v >> 8) & 0xFF)
        if t in self.symbols:
            return self.symbols[t]
        raise AsmError(f"undefined symbol {t!r}", self.line)


def evaluate(text: str, symbols: dict[str, int], line: int = 0) -> int:
    return _Expr(text, symbols, line).parse()


# ---------------------------------------------------------------------------
# Operand encoding
# ---------------------------------------------------------------------------

_REG = re.compile(r"^[rR]([0-7])$")

_RANGES = {
    "imm8": (0, 255), "simm9": (-256, 255), "imm12": (0, 4095), "pin": (0, 15), "target": (0, 255),
}


def _encode_operand(kind: str, text: str, symbols: dict[str, int], line: int, depth: int) -> int:
    if kind in ("rd", "rs", "rt", "rx"):
        m = _REG.match(text.strip())
        if not m:
            raise AsmError(f"expected register r0..r7, got {text!r}", line)
        return int(m.group(1))
    value = evaluate(text, symbols, line)
    lo, hi = _RANGES[kind]
    if kind == "target":
        hi = min(hi, depth - 1)
    if not lo <= value <= hi:
        raise AsmError(f"{kind} value {value} out of range {lo}..{hi} in {text!r}", line)
    return value & ((1 << (isa.FIELDS[kind][0] - isa.FIELDS[kind][1] + 1)) - 1)


def _split_operands(rest: str) -> list[str]:
    if not rest.strip():
        return []
    out, depth, cur = [], 0, ""
    for ch in rest:
        if ch == "," and depth == 0:
            out.append(cur.strip())
            cur = ""
        else:
            depth += ch == "("
            depth -= ch == ")"
            cur += ch
    out.append(cur.strip())
    return out


def _candidates(mnemonic: str, nops: int) -> list[isa.Instr]:
    return [i for i in isa.INSTRUCTIONS if i.mnemonic == mnemonic.upper() and len(i.operands) == nops]


def encode_instruction(mnemonic: str, operands: list[str], symbols: dict[str, int], line: int = 0,
                       depth: int = isa.PMEM_DEPTH_DEFAULT) -> int:
    """Encode one real (non-pseudo) instruction to a 16-bit word."""
    cands = _candidates(mnemonic, len(operands))
    if not cands:
        if any(i.mnemonic == mnemonic.upper() for i in isa.INSTRUCTIONS):
            raise AsmError(f"{mnemonic.upper()} takes {sorted({len(i.operands) for i in isa.INSTRUCTIONS if i.mnemonic == mnemonic.upper()})} operands, got {len(operands)}", line)
        raise AsmError(f"unknown mnemonic {mnemonic!r}", line)
    errors = []
    for ins in cands:
        word = 0
        for f, v in ins.fixed.items():
            word = isa.field_set(word, f, v)
        ok = True
        for tmpl, text in zip(ins.operands, operands):
            if tmpl.startswith("{"):
                kind = tmpl[1:-1]
                word = isa.field_set(word, kind, _encode_operand(kind, text, symbols, line, depth))
            else:
                # Literal operand such as the 0/1 level of OUT/OE/WAITP.
                try:
                    if evaluate(text, symbols, line) != int(tmpl):
                        ok = False
                        break
                except AsmError as e:
                    errors.append(str(e))
                    ok = False
                    break
        if ok:
            return word
    raise AsmError(f"no form of {mnemonic.upper()} matches operands {operands}" + (f" ({errors[0]})" if errors else ""), line)


# ---------------------------------------------------------------------------
# Assembler
# ---------------------------------------------------------------------------

_LABEL = re.compile(r"^([A-Za-z_.$][A-Za-z0-9_.$]*):\s*(.*)$")


def _strip_comment(line: str) -> str:
    out, in_q = "", False
    for ch in line:
        if ch == "'":
            in_q = not in_q
        if ch in ";#" and not in_q:
            break
        out += ch
    return out.rstrip()


def _expand_pseudo(mnemonic: str, operands: list[str], line: int) -> list[tuple[str, list[str]]] | None:
    m = mnemonic.upper()
    if m == "LDW" and len(operands) == 2:
        rd, imm = operands
        return [("LDI", [rd, f"lo8({imm})"]), ("LDIH", [rd, f"hi8({imm})"])]
    if m == "SUBI" and len(operands) == 2:
        rd, imm = operands
        return [("ADDI", [rd, f"-({imm})"])]
    if m == "CLR" and len(operands) == 1:
        return [("LDI", [operands[0], "0"])]
    return None


def assemble(source: str, depth: int = isa.PMEM_DEPTH_DEFAULT, symbols: dict[str, int] | None = None,
             base: int = 0) -> Program:
    """Assemble source text into a :class:`Program`.

    ``base`` is the address of the first word (labels resolve relative to it);
    the lockstep bench loads programs at base 1 behind a marker instruction.
    """
    predefined = set(symbols or {})  # command-line style overrides win over .equ in the source
    symbols = dict(symbols or {})
    for name, value in isa.DBG.items():  # not needed by programs, but harmless and handy
        symbols.setdefault("DBG_" + name, value)

    # Pass 1: addresses, labels, .equ.
    items: list[tuple[int, str, list[str] | None, str, int]] = []  # (addr, kind, payload, text, line)
    addr = base
    for lineno, raw in enumerate(source.splitlines(), 1):
        text = _strip_comment(raw).strip()
        if not text:
            continue
        m = _LABEL.match(text)
        if m:
            label, text = m.group(1), m.group(2).strip()
            if label in symbols:
                raise AsmError(f"duplicate symbol {label!r}", lineno)
            symbols[label] = addr
            if not text:
                continue
        if text.startswith("."):
            parts = text.split(None, 1)
            directive = parts[0].lower()
            arg = parts[1] if len(parts) > 1 else ""
            if directive == ".equ":
                try:
                    name, expr = arg.split(None, 1)
                except ValueError:
                    raise AsmError(".equ needs a name and a value", lineno)
                if name in predefined:
                    continue
                if name in symbols:
                    raise AsmError(f"duplicate symbol {name!r}", lineno)
                symbols[name] = evaluate(expr, symbols, lineno)
                continue
            if directive == ".word":
                items.append((addr, "word", [arg], raw, lineno))
                addr += 1
                continue
            if directive == ".org":
                new = evaluate(arg, symbols, lineno)
                if new < addr:
                    raise AsmError(".org cannot move backwards", lineno)
                addr = new
                continue
            raise AsmError(f"unknown directive {directive}", lineno)
        parts = text.split(None, 1)
        mnemonic = parts[0]
        operands = _split_operands(parts[1]) if len(parts) > 1 else []
        expanded = _expand_pseudo(mnemonic, operands, lineno)
        if expanded is None:
            if not any(i.mnemonic == mnemonic.upper() for i in isa.INSTRUCTIONS):
                raise AsmError(f"unknown mnemonic {mnemonic!r}", lineno)
            items.append((addr, "instr", [mnemonic, *operands], raw, lineno))
            addr += 1
        else:
            for k, (mn, ops) in enumerate(expanded):
                items.append((addr, "instr", [mn, *ops], raw if k == 0 else "", lineno))
                addr += 1
        if addr > depth:
            raise AsmError(f"program exceeds {depth} words", lineno)

    # Pass 2: encode.
    words = [0] * (addr - base)
    listing = []
    for a, kind, payload, text, lineno in items:
        if kind == "word":
            w = evaluate(payload[0], symbols, lineno) & 0xFFFF
        else:
            w = encode_instruction(payload[0], payload[1:], symbols, lineno, depth)
        words[a - base] = w
        listing.append((a, w, text))
    return Program(words, symbols, listing)


def assemble_file(path: str, depth: int = isa.PMEM_DEPTH_DEFAULT, base: int = 0,
                  symbols: dict[str, int] | None = None) -> Program:
    with open(path) as f:
        return assemble(f.read(), depth, symbols, base=base)


# ---------------------------------------------------------------------------
# Disassembler
# ---------------------------------------------------------------------------

def disassemble(word: int) -> str:
    ins = isa.decode(word)
    if ins is None:
        return f".word 0x{word:04x}  ; illegal"
    ops = []
    for tmpl in ins.operands:
        if tmpl.startswith("{"):
            kind = tmpl[1:-1]
            v = isa.field_get(word, kind)
            if kind in ("rd", "rs", "rt", "rx"):
                ops.append(f"r{v}")
            elif kind == "simm9":
                ops.append(str(isa.sext(v, 9)))
            elif kind in ("imm8", "imm12"):
                ops.append(f"0x{v:02x}" if kind == "imm8" else str(v))
            else:
                ops.append(str(v))
        else:
            ops.append(tmpl)
    return ins.mnemonic + (" " + ", ".join(ops) if ops else "")


def disassemble_program(words: list[int]) -> str:
    return "\n".join(f"{a:3d}: {w:04x}  {disassemble(w)}" for a, w in enumerate(words)) + "\n"


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Weft assembler")
    p.add_argument("source")
    p.add_argument("-o", "--output", help="hex output file (one 16-bit word per line)")
    p.add_argument("--depth", type=int, default=isa.PMEM_DEPTH_DEFAULT)
    p.add_argument("--list", action="store_true", help="print a listing")
    p.add_argument("--disasm", action="store_true", help="treat source as a hex file and disassemble it")
    a = p.parse_args(argv)
    if a.disasm:
        words = [int(l, 16) for l in open(a.source).read().split()]
        sys.stdout.write(disassemble_program(words))
        return 0
    try:
        prog = assemble_file(a.source, a.depth)
    except AsmError as e:
        print(f"{a.source}:{e}", file=sys.stderr)
        return 1
    if a.output:
        with open(a.output, "w") as f:
            f.write(prog.to_hex())
    if a.list or not a.output:
        for addr, w, text in prog.listing:
            print(f"{addr:3d}: {w:04x}  {text.strip()}")
        print(f"; {len(prog.words)} words, {a.depth - len(prog.words)} free")
    return 0


if __name__ == "__main__":
    sys.exit(main())
