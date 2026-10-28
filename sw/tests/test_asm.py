"""Assembler and encoding tests: round trips, illegal words, errors, golden files."""

import glob
import os

import pytest
from hypothesis import given, settings, strategies as st

from weft import asm, isa

HERE = os.path.dirname(__file__)
PROGRAMS = sorted(glob.glob(os.path.join(HERE, "..", "programs", "*.asm")))


def _operand_strategy(kind: str):
    if kind in ("rd", "rs", "rt", "rx"):
        return st.integers(0, 7).map(lambda v: f"r{v}")
    if kind == "imm8":
        return st.integers(0, 255).map(str)
    if kind == "simm9":
        return st.integers(-256, 255).map(str)
    if kind == "imm12":
        return st.integers(0, 4095).map(str)
    if kind == "pin":
        return st.integers(0, 15).map(str)
    if kind == "target":
        return st.integers(0, 127).map(str)
    raise ValueError(kind)


def _instruction_text():
    def build(ins, draws):
        ops = []
        i = 0
        for tmpl in ins.operands:
            if tmpl.startswith("{"):
                ops.append(draws[i])
                i += 1
            else:
                ops.append(tmpl)
        return ins, ins.mnemonic + (" " + ", ".join(ops) if ops else "")

    @st.composite
    def strat(draw):
        ins = draw(st.sampled_from(isa.INSTRUCTIONS))
        draws = [draw(_operand_strategy(p)) for p in ins.placeholders]
        return build(ins, draws)

    return strat()


@settings(max_examples=400)
@given(_instruction_text())
def test_assemble_disassemble_round_trip(case):
    ins, text = case
    word = asm.assemble(text).words[0]
    assert isa.decode(word) is ins, (text, hex(word))
    text2 = asm.disassemble(word)
    word2 = asm.assemble(text2).words[0]
    assert word2 == word, (text, text2)


@settings(max_examples=400)
@given(st.integers(0, 0xFFFF))
def test_every_word_is_legal_or_illegal_consistently(word):
    ins = isa.decode(word)
    if isa.is_illegal(word):
        assert ins is None
        assert "illegal" in asm.disassemble(word)
    else:
        assert ins is not None
        mask, value = ins.match_mask()
        assert (word & mask) == value
        # Re-encoding the disassembly must reproduce every defined field (targets may exceed
        # the default depth, so re-assemble for a 256-word memory).
        word2 = asm.assemble(asm.disassemble(word), depth=256).words[0]
        defined = mask
        for p in ins.placeholders:
            msb, lsb = isa.FIELDS[p]
            defined |= ((1 << (msb - lsb + 1)) - 1) << lsb
        assert (word2 & defined) == (word & defined)


def test_opcode_map_is_complete_and_unique():
    assert sorted(isa.OP.values()) == list(range(16))
    for table in (isa.SYS_SUB, isa.ALU_FN, isa.BR_COND, isa.OUT_SUB, isa.IN_SUB, isa.WAIT_SUB, isa.TIMER_SUB,
                  isa.FIFO_SUB, isa.CRC_SUB, isa.DBG, isa.HOST_CMD):
        assert len(set(table.values())) == len(table)


def test_base_address_shifts_labels():
    prog = asm.assemble("start: NOP\nJMP start", base=1)
    assert prog.symbols["start"] == 1 and len(prog.words) == 2
    assert prog.words[1] == asm.assemble("JMP 1").words[0]


def test_predefined_symbols_override_equ():
    prog = asm.assemble(".equ BIT 434\nLDW r1, BIT", symbols={"BIT": 3})
    assert prog.words[0] == asm.assemble("LDI r1, 3").words[0]


def test_labels_equ_pseudo_and_expressions():
    prog = asm.assemble(
        """
        .equ TX 3
        .equ BIT 400 + 34
        start:  OUT TX, 1
                LDW r1, BIT
                SUBI r1, 4
                CLR r2
        loop:   DJNZ r1, loop
                JMP start
                .word 0xBEEF
        """
    )
    assert prog.symbols["start"] == 0 and prog.symbols["loop"] == 5
    assert prog.words[0] == asm.assemble("OUT 3, 1").words[0]
    assert prog.words[1] == asm.assemble("LDI r1, 0xB2").words[0]  # 434 = 0x01B2
    assert prog.words[2] == asm.assemble("LDIH r1, 0x01").words[0]
    assert prog.words[3] == asm.assemble("ADDI r1, -4").words[0]
    assert prog.words[4] == asm.assemble("LDI r2, 0").words[0]
    assert prog.words[5] == asm.assemble("DJNZ r1, 5").words[0]
    assert prog.words[7] == 0xBEEF


@pytest.mark.parametrize(
    "text, msg",
    [
        ("LDI r1, 256", "out of range"),
        ("ADDI r1, -257", "out of range"),
        ("OUT 16, 1", "out of range"),
        ("FOO r1", "unknown mnemonic"),
        ("ADD r1, r2", "takes"),
        ("LDI r8, 1", "expected register"),
        ("a: NOP\na: NOP", "duplicate symbol"),
        ("JMP nowhere", "undefined symbol"),
        ("OUT 1, 2", "no form"),
    ],
)
def test_errors(text, msg):
    with pytest.raises(asm.AsmError, match=msg):
        asm.assemble(text)


def test_program_too_large():
    with pytest.raises(asm.AsmError, match="exceeds"):
        asm.assemble("\n".join(["NOP"] * 129))


@pytest.mark.parametrize("path", PROGRAMS, ids=[os.path.basename(p) for p in PROGRAMS])
def test_programs_assemble_and_match_golden_hex(path):
    prog = asm.assemble_file(path)
    assert 0 < len(prog.words) <= isa.PMEM_DEPTH_DEFAULT
    golden = path[:-4] + ".hex"
    assert os.path.exists(golden), f"missing {golden}: run make asm"
    with open(golden) as f:
        words = [int(line, 16) for line in f.read().split()]
    assert words == prog.words, f"{golden} is stale: run make asm"
