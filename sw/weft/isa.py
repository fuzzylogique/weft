"""Weft ISA v0.1: the single source of truth.

Everything that knows the instruction encoding reads this file: the assembler,
the disassembler, the instruction-set simulator, the Verilog decode constants
(regenerated into ``src/weft_core.v`` by :mod:`weft.gen`) and the ISA reference
in ``docs/isa.md``.  Change an encoding here, run ``make gen``, and every layer
moves together.

Word format: 16-bit instructions, opcode in bits [15:12].  Fields a form does
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
"""

from __future__ import annotations

from dataclasses import dataclass, field

WORD_BITS = 16
NREGS = 8
PMEM_DEPTH_DEFAULT = 128
NPINS_OUT = 16  # pins 0..7 -> uo_out, 8..15 -> uio_out (with output enable)
NPINS_IN = 16  # pins 0..7 -> ui_in,  8..15 -> uio_in
FIFO_DEPTH = 4

# ---------------------------------------------------------------------------
# Opcode and sub-field tables
# ---------------------------------------------------------------------------

OP = {
    "SYS": 0x0, "LDI": 0x1, "ALU": 0x2, "ADDI": 0x3, "CMPI": 0x4, "BR": 0x5,
    "DJNZ": 0x6, "OUT": 0x7, "IN": 0x8, "WAIT": 0x9, "DELAY": 0xA, "TIMER": 0xB,
    "LOGI": 0xC, "FIFO": 0xD, "CRC": 0xE, "CALL": 0xF,
}
SYS_SUB = {"NOP": 0, "HALT": 1, "RET": 2}
ALU_FN = {"ADD": 0, "SUB": 1, "AND": 2, "OR": 3, "XOR": 4, "SHLC": 5, "SHRC": 6, "MOV": 7}
BR_COND = {"AL": 0, "EQ": 1, "NE": 2, "CS": 3, "CC": 4, "INE": 5, "OUTF": 6, "TICK": 7}
OUT_SUB = {"OUT0": 0, "OUT1": 1, "OUTC": 2, "OUTR": 3, "OE0": 4, "OE1": 5, "OEC": 6, "OENC": 7}
IN_SUB = {"INC": 0, "INR": 1, "INALL": 2}
WAIT_SUB = {"WAITP0": 0, "WAITP1": 1, "WAITR": 2, "WAITF": 3, "WAITT": 4}
TIMER_SUB = {"TSET": 0, "TSTOP": 1, "RDCYC": 2, "RDT": 3}
LOGI_SUB = {"ANDI": 0, "ORI": 1}
FIFO_SUB = {"PUSH": 0, "PULL": 1}
CRC_SUB = {"CRCPOLY": 0, "CRCINIT": 1, "CRCIN": 2, "CRCINR": 3, "CRCRD": 4}

# Debug (PEEK) word selectors, read by the host over SPI.
DBG = {
    "R0": 0, "R1": 1, "R2": 2, "R3": 3, "R4": 4, "R5": 5, "R6": 6, "R7": 7,
    "PC": 8, "FLAGS": 9, "CYC": 10, "TCNT": 11, "CRC": 12, "POUT": 13, "POE": 14, "LR": 15,
}
# Bit positions inside the FLAGS debug word.
FLAG_BITS = {"Z": 0, "C": 1, "TICK": 2, "RUNNING": 3, "HALTED": 4, "ILL": 5, "TRUN": 6}

# Host SPI command bytes (see docs/host-interface.md).
HOST_CMD = {
    "STATUS": 0x00, "LOAD": 0x01, "RESET": 0x02, "RUN": 0x03, "STOP": 0x04,
    "STEP": 0x05, "PUSH": 0x06, "PULL": 0x07, "PEEK": 0x08,
}
HOST_VERSION = 0x01

# Bit ranges (msb, lsb) of every field name used in the syntax templates.
FIELDS = {
    "op": (15, 12), "sub": (11, 9), "cond": (11, 9), "fn": (2, 0), "h": (8, 8),
    "rd": (11, 9), "rs": (8, 6), "rx": (8, 6), "rt": (5, 3),
    "imm8": (7, 0), "simm9": (8, 0), "imm12": (11, 0), "pin": (3, 0), "target": (7, 0),
}
# How operand placeholders are shown in the reference document.
FIELD_DISPLAY = {"rx": "rd"}


@dataclass(frozen=True)
class Instr:
    """One assembler-visible instruction form."""

    name: str  # internal unique name
    syntax: str  # e.g. "ADD {rd}, {rs}, {rt}" or "OUT {pin}, 0"
    fixed: dict  # fixed field values that identify this form
    cycles: str  # "1", "wait" or "delay"
    desc: str  # semantics, one line
    flags: str = ""  # flags written

    @property
    def mnemonic(self) -> str:
        return self.syntax.split()[0]

    @property
    def operands(self) -> tuple[str, ...]:
        rest = self.syntax[len(self.mnemonic):].strip()
        return tuple(o.strip() for o in rest.split(",")) if rest else ()

    @property
    def placeholders(self) -> list[str]:
        return [o[1:-1] for o in self.operands if o.startswith("{")]

    def match_mask(self) -> tuple[int, int]:
        """(mask, value): a word w is this form iff (w & mask) == value."""
        mask = value = 0
        for f, v in self.fixed.items():
            msb, lsb = FIELDS[f]
            width = msb - lsb + 1
            mask |= ((1 << width) - 1) << lsb
            value |= (v & ((1 << width) - 1)) << lsb
        return mask, value


def _i(syntax, cycles, desc, flags="", **fixed):
    name = syntax.split()[0]
    # Forms sharing a mnemonic (OUT/OE/WAITP with a literal level) get a suffix.
    lit = [o for o in syntax.split()[1:] if o.strip(",") in ("0", "1")]
    if lit:
        name += lit[0].strip(",")
    return Instr(name, syntax, fixed, cycles, desc, flags)


INSTRUCTIONS: list[Instr] = [
    # SYS
    _i("NOP", "1", "No operation.", op=OP["SYS"], sub=SYS_SUB["NOP"]),
    _i("HALT", "1", "Stop the core (running=0, halted=1). PC advances; a host RUN resumes after it.", op=OP["SYS"], sub=SYS_SUB["HALT"]),
    _i("RET", "1", "PC = LR (link register written by CALL). One level deep.", op=OP["SYS"], sub=SYS_SUB["RET"]),
    # LDI
    _i("LDI {rd}, {imm8}", "1", "rd = imm8 (zero-extended; the high byte is cleared).", "Z", op=OP["LDI"], h=0),
    _i("LDIH {rd}, {imm8}", "1", "rd[15:8] = imm8; rd[7:0] unchanged. LDI then LDIH loads a 16-bit constant.", "Z", op=OP["LDI"], h=1),
    # ALU
    _i("ADD {rd}, {rs}, {rt}", "1", "rd = rs + rt.", "Z, C=carry out", op=OP["ALU"], fn=ALU_FN["ADD"]),
    _i("SUB {rd}, {rs}, {rt}", "1", "rd = rs - rt.", "Z, C=borrow (rs < rt unsigned)", op=OP["ALU"], fn=ALU_FN["SUB"]),
    _i("AND {rd}, {rs}, {rt}", "1", "rd = rs & rt.", "Z", op=OP["ALU"], fn=ALU_FN["AND"]),
    _i("OR {rd}, {rs}, {rt}", "1", "rd = rs | rt.", "Z", op=OP["ALU"], fn=ALU_FN["OR"]),
    _i("XOR {rd}, {rs}, {rt}", "1", "rd = rs ^ rt.", "Z", op=OP["ALU"], fn=ALU_FN["XOR"]),
    _i("SHLC {rd}, {rs}", "1", "rd = {rs[14:0], C}; shift left, carry in at bit 0.", "Z, C=rs[15]", op=OP["ALU"], fn=ALU_FN["SHLC"]),
    _i("SHRC {rd}, {rs}", "1", "rd = {C, rs[15:1]}; shift right, carry in at bit 15.", "Z, C=rs[0]", op=OP["ALU"], fn=ALU_FN["SHRC"]),
    _i("MOV {rd}, {rs}", "1", "rd = rs.", "Z", op=OP["ALU"], fn=ALU_FN["MOV"]),
    # Immediates
    _i("ADDI {rd}, {simm9}", "1", "rd = rd + sign_extend(imm9), imm9 in -256..255 (SUBI is ADDI of a negative).", "Z, C=carry out of the 16-bit add", op=OP["ADDI"]),
    _i("CMPI {rd}, {imm8}", "1", "Compare: flags of rd - imm8, rd unchanged.", "Z, C=borrow (rd < imm8)", op=OP["CMPI"], h=0),
    _i("ANDI {rd}, {imm8}", "1", "rd = rd & imm8 (clears the high byte).", "Z", op=OP["LOGI"], h=LOGI_SUB["ANDI"]),
    _i("ORI {rd}, {imm8}", "1", "rd = rd | imm8.", "Z", op=OP["LOGI"], h=LOGI_SUB["ORI"]),
    # Branches
    _i("JMP {target}", "1", "PC = target.", op=OP["BR"], cond=BR_COND["AL"], h=0),
    _i("BEQ {target}", "1", "Branch if Z.", op=OP["BR"], cond=BR_COND["EQ"], h=0),
    _i("BNE {target}", "1", "Branch if not Z.", op=OP["BR"], cond=BR_COND["NE"], h=0),
    _i("BCS {target}", "1", "Branch if C.", op=OP["BR"], cond=BR_COND["CS"], h=0),
    _i("BCC {target}", "1", "Branch if not C.", op=OP["BR"], cond=BR_COND["CC"], h=0),
    _i("BINE {target}", "1", "Branch if the host-to-core FIFO is empty.", op=OP["BR"], cond=BR_COND["INE"], h=0),
    _i("BOUTF {target}", "1", "Branch if the core-to-host FIFO is full.", op=OP["BR"], cond=BR_COND["OUTF"], h=0),
    _i("BTICK {target}", "1", "Branch if a timer tick is pending (does not consume it).", op=OP["BR"], cond=BR_COND["TICK"], h=0),
    _i("DJNZ {rd}, {target}", "1", "rd = rd - 1; branch if the new rd != 0. Flags unchanged.", op=OP["DJNZ"], h=0),
    _i("CALL {target}", "1", "LR = PC + 1; PC = target. One level: a nested CALL overwrites LR.", op=OP["CALL"], sub=0, h=0),
    # Pins out
    _i("OUT {pin}, 0", "1", "Drive output pin low (effective at the pad from the next cycle).", op=OP["OUT"], sub=OUT_SUB["OUT0"]),
    _i("OUT {pin}, 1", "1", "Drive output pin high.", op=OP["OUT"], sub=OUT_SUB["OUT1"]),
    _i("OUTC {pin}", "1", "Output pin = C.", op=OP["OUT"], sub=OUT_SUB["OUTC"]),
    _i("OUTR {pin}, {rs}", "1", "Output pin = rs[0].", op=OP["OUT"], sub=OUT_SUB["OUTR"]),
    _i("OE {pin}, 0", "1", "Release bidirectional pin (input / open-drain high). Pins 0-7 ignore OE.", op=OP["OUT"], sub=OUT_SUB["OE0"]),
    _i("OE {pin}, 1", "1", "Drive bidirectional pin.", op=OP["OUT"], sub=OUT_SUB["OE1"]),
    _i("OEC {pin}", "1", "Output enable = C.", op=OP["OUT"], sub=OUT_SUB["OEC"]),
    _i("OENC {pin}", "1", "Output enable = !C (open-drain bit: with OUT pin,0 set once, C=0 pulls low and C=1 releases).", op=OP["OUT"], sub=OUT_SUB["OENC"]),
    # Pins in
    _i("INC {pin}", "1", "C = input pin (synchronized, 2 cycles old).", "C", op=OP["IN"], sub=IN_SUB["INC"]),
    _i("INR {rx}, {pin}", "1", "rd = input pin as 0 or 1.", "Z", op=OP["IN"], sub=IN_SUB["INR"]),
    _i("INALL {rx}", "1", "rd = all 16 input pins {uio_in, ui_in} sampled in the same cycle.", "Z", op=OP["IN"], sub=IN_SUB["INALL"]),
    # Waits
    _i("WAITP {pin}, 0", "wait", "Stall until input pin reads 0.", op=OP["WAIT"], sub=WAIT_SUB["WAITP0"]),
    _i("WAITP {pin}, 1", "wait", "Stall until input pin reads 1.", op=OP["WAIT"], sub=WAIT_SUB["WAITP1"]),
    _i("WAITR {pin}", "wait", "Stall until a rising edge is seen on input pin.", op=OP["WAIT"], sub=WAIT_SUB["WAITR"]),
    _i("WAITF {pin}", "wait", "Stall until a falling edge is seen on input pin.", op=OP["WAIT"], sub=WAIT_SUB["WAITF"]),
    _i("WAITT", "wait", "Stall until the bit timer ticks, then consume the tick. Consecutive WAITTs complete exactly one period apart.", op=OP["WAIT"], sub=WAIT_SUB["WAITT"]),
    _i("DELAY {imm12}", "delay", "Stall for imm12 extra cycles (the instruction occupies imm12+1 cycles).", op=OP["DELAY"]),
    # Timer
    _i("TSET {rs}", "1", "Bit timer period = rs cycles (0 means 65536); restart counting; clear any pending tick.", op=OP["TIMER"], sub=TIMER_SUB["TSET"]),
    _i("TSTOP", "1", "Stop the bit timer and clear any pending tick.", op=OP["TIMER"], sub=TIMER_SUB["TSTOP"]),
    _i("RDCYC {rx}", "1", "rd = free-running 16-bit cycle counter (counts every cycle the core is running).", "Z", op=OP["TIMER"], sub=TIMER_SUB["RDCYC"]),
    _i("RDT {rx}", "1", "rd = current bit timer count (cycles until the next tick, minus one).", "Z", op=OP["TIMER"], sub=TIMER_SUB["RDT"]),
    # FIFO
    _i("PUSH {rs}", "wait", "Push rs to the core-to-host FIFO; stalls while it is full.", op=OP["FIFO"], sub=FIFO_SUB["PUSH"]),
    _i("PULL {rx}", "wait", "Pop the host-to-core FIFO into rd; stalls while it is empty.", "Z", op=OP["FIFO"], sub=FIFO_SUB["PULL"]),
    # CRC
    _i("CRCPOLY {rs}", "1", "CRC polynomial register = rs.", op=OP["CRC"], sub=CRC_SUB["CRCPOLY"]),
    _i("CRCINIT {rs}", "1", "CRC state = rs.", op=OP["CRC"], sub=CRC_SUB["CRCINIT"]),
    _i("CRCIN", "1", "Shift C into the CRC, MSB first: fb = crc[15]^C; crc = (crc<<1) ^ (fb ? poly : 0).", op=OP["CRC"], sub=CRC_SUB["CRCIN"]),
    _i("CRCINR", "1", "Shift C into the CRC, reflected (LSB first): fb = crc[0]^C; crc = (crc>>1) ^ (fb ? poly : 0).", op=OP["CRC"], sub=CRC_SUB["CRCINR"]),
    _i("CRCRD {rx}", "1", "rd = CRC state.", "Z", op=OP["CRC"], sub=CRC_SUB["CRCRD"]),
]

BY_NAME = {i.name: i for i in INSTRUCTIONS}
assert len(BY_NAME) == len(INSTRUCTIONS), "duplicate instruction names"

# Pseudo-instructions expanded by the assembler.
PSEUDO = {
    "LDW {rd}, {imm16}": "LDI rd, lo8(imm16); LDIH rd, hi8(imm16)",
    "SUBI {rd}, {imm}": "ADDI rd, -imm",
    "CLR {rd}": "LDI rd, 0",
}


def field_get(word: int, name: str) -> int:
    msb, lsb = FIELDS[name]
    return (word >> lsb) & ((1 << (msb - lsb + 1)) - 1)


def field_set(word: int, name: str, value: int) -> int:
    msb, lsb = FIELDS[name]
    width = msb - lsb + 1
    mask = ((1 << width) - 1) << lsb
    return (word & ~mask) | ((value & ((1 << width) - 1)) << lsb)


def sext(value: int, bits: int) -> int:
    value &= (1 << bits) - 1
    return value - (1 << bits) if value & (1 << (bits - 1)) else value


def is_illegal(word: int) -> bool:
    """True if the word is not a defined instruction (the core halts with ILL set)."""
    op = field_get(word, "op")
    sub = field_get(word, "sub")
    b8 = field_get(word, "h")
    if op == OP["SYS"]:
        return sub > SYS_SUB["RET"]
    if op == OP["IN"]:
        return sub > IN_SUB["INALL"]
    if op == OP["WAIT"]:
        return sub > WAIT_SUB["WAITT"]
    if op == OP["TIMER"]:
        return sub > TIMER_SUB["RDT"]
    if op == OP["FIFO"]:
        return sub > FIFO_SUB["PULL"]
    if op == OP["CRC"]:
        return sub > CRC_SUB["CRCRD"]
    if op in (OP["CMPI"], OP["BR"], OP["DJNZ"]):
        return b8 == 1
    if op == OP["CALL"]:
        return field_get(word, "sub") != 0 or b8 == 1
    return False


def decode(word: int) -> Instr | None:
    """Return the instruction form a word encodes, or None if illegal."""
    if is_illegal(word):
        return None
    # Most specific match first: forms with more fixed bits win.
    best = None
    for ins in INSTRUCTIONS:
        mask, value = ins.match_mask()
        if (word & mask) == value and (best is None or bin(mask).count("1") > bin(best.match_mask()[0]).count("1")):
            best = ins
    return best


def cycle_contract() -> str:
    return (
        "Every instruction completes in exactly one clock cycle, except: WAIT-class "
        "instructions (WAITP, WAITR, WAITF, WAITT, PUSH, PULL) hold the PC until their "
        "condition is true and complete in the first cycle in which it is observed; "
        "DELAY n occupies n+1 cycles. There is no pipeline, no cache, no interrupt and "
        "no other stall. A pin written by an instruction that completes in cycle N is "
        "driven at the pad register at the end of cycle N. An input read in cycle N "
        "returns the pad value from the start of cycle N-2 (two synchronizer stages)."
    )
