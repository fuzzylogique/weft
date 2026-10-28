"""Directed tests of instruction semantics on the ISS (layer 1 of the plan)."""

import pytest

from weft import asm, isa
from weft.bench import HOST_IDLE
from weft.iss import Weft


def run(text, cycles=200, pad=HOST_IDLE, prefill=()):
    sim = Weft()
    sim.load(asm.assemble(text).words)
    for w in prefill:
        sim.host_push(w)
    sim.run()
    for _ in range(cycles):
        sim.step(pad)
        if not sim.running:
            break
    return sim


def test_add_sub_flags():
    s = run("LDW r1, 0xFFFF\nLDI r2, 1\nADD r3, r1, r2\nHALT")
    assert s.regs[3] == 0 and s.z == 1 and s.c == 1
    s = run("LDI r1, 5\nLDI r2, 7\nSUB r3, r1, r2\nHALT")
    assert s.regs[3] == 0xFFFE and s.c == 1 and s.z == 0
    s = run("LDI r1, 7\nLDI r2, 7\nSUB r3, r1, r2\nHALT")
    assert s.regs[3] == 0 and s.c == 0 and s.z == 1


def test_addi_cmpi():
    s = run("LDI r1, 5\nADDI r1, -1\nHALT")
    assert s.regs[1] == 4 and s.c == 1  # add of 0xFFFF carries
    s = run("LDI r1, 5\nCMPI r1, 6\nHALT")
    assert s.c == 1 and s.z == 0 and s.regs[1] == 5
    s = run("LDI r1, 6\nCMPI r1, 6\nHALT")
    assert s.c == 0 and s.z == 1


def test_shifts_through_carry():
    s = run("LDI r1, 0x81\nSHRC r1, r1\nHALT")
    assert s.regs[1] == 0x40 and s.c == 1
    s = run("LDI r1, 0x81\nSHRC r1, r1\nSHLC r1, r1\nHALT")
    assert s.regs[1] == 0x81 and s.c == 0
    s = run("LDW r1, 0x8000\nSHLC r1, r1\nHALT")
    assert s.regs[1] == 0 and s.c == 1 and s.z == 1


def test_ldi_ldih_logi():
    s = run("LDW r1, 0x12FF\nLDI r1, 0x34\nHALT")
    assert s.regs[1] == 0x0034
    s = run("LDI r1, 0x34\nLDIH r1, 0x12\nANDI r1, 0xF0\nHALT")
    assert s.regs[1] == 0x0030
    s = run("LDI r1, 0x01\nORI r1, 0x80\nHALT")
    assert s.regs[1] == 0x81


def test_djnz_keeps_flags_and_loops():
    s = run("LDI r1, 3\nLDI r2, 0\nADD r2, r2, r2\nLDI r4, 0\nloop: ADDI r4, 1\nDJNZ r1, loop\nHALT")
    assert s.regs[4] == 3 and s.regs[1] == 0
    # flags come from the last ADDI (r4=3: Z=0, C=0), DJNZ does not touch them
    assert s.z == 0 and s.c == 0


def test_branches():
    s = run("LDI r1, 0\nBEQ ok\nLDI r7, 1\nHALT\nok: LDI r7, 2\nHALT")
    assert s.regs[7] == 2
    s = run("LDI r1, 1\nBNE ok\nLDI r7, 1\nHALT\nok: LDI r7, 2\nHALT")
    assert s.regs[7] == 2
    s = run("LDW r1, 0xFFFF\nADDI r1, 1\nBCS ok\nLDI r7, 1\nHALT\nok: LDI r7, 2\nHALT")
    assert s.regs[7] == 2
    s = run("LDI r1, 1\nBCC ok\nLDI r7, 1\nHALT\nok: LDI r7, 2\nHALT")
    assert s.regs[7] == 2  # C is 0 after reset and LDI leaves it alone


def test_call_ret_and_lr():
    s = run("CALL f\nLDI r7, 2\nHALT\nf: LDI r6, 1\nRET")
    assert s.regs[6] == 1 and s.regs[7] == 2 and s.lr == 1


def test_delay_takes_n_plus_one_cycles():
    for n in (0, 1, 5, 17):
        s = run(f"RDCYC r1\nDELAY {n}\nRDCYC r2\nHALT")
        # RDCYC r1 at cycle 0 reads 0; DELAY occupies n+1 cycles; RDCYC r2 reads n+2
        assert s.regs[2] - s.regs[1] == n + 2, n


def test_timer_period_exact():
    for p in (2, 3, 20, 434):
        s = run(f"LDW r3, {p}\nTSET r3\nWAITT\nRDCYC r1\nWAITT\nRDCYC r2\nWAITT\nRDCYC r4\nHALT", cycles=3000)
        assert s.regs[2] - s.regs[1] == p and s.regs[4] - s.regs[2] == p


def test_timer_first_tick_latency():
    s = run("LDI r3, 10\nTSET r3\nRDCYC r1\nWAITT\nRDCYC r2\nHALT")
    # TSET at cycle 2 (after LDW's two words? no: LDI is one word) -> tick visible 11 cycles later
    # RDCYC r1 executes the cycle after TSET; WAITT completes when tick is visible.
    assert s.regs[2] - s.regs[1] == 11


def test_tick_does_not_queue_and_btick():
    s = run("LDI r3, 4\nTSET r3\nDELAY 40\nLDI r5, 0\nBTICK yes\nHALT\nyes: LDI r5, 1\nWAITT\nBTICK two\nLDI r5, 2\nHALT\ntwo: LDI r5, 3\nHALT", cycles=200)
    assert s.regs[5] == 2  # one pending tick, consumed, none left behind it


def test_wait_pin_levels_and_edges():
    # pad input pin 2 goes high at some cycle; WAITP sees it two cycles later.
    sim = Weft()
    sim.load(asm.assemble("WAITP 2, 1\nRDCYC r1\nWAITF 2\nRDCYC r2\nHALT").words)
    sim.run()
    pad = HOST_IDLE
    for k in range(100):
        if k == 10:
            pad = HOST_IDLE | (1 << 2)
        if k == 30:
            pad = HOST_IDLE
        sim.step(pad)
        if not sim.running:
            break
    assert sim.regs[1] == 13  # visible in cycle 12, RDCYC fires in cycle 13 reading cyc=13
    assert sim.regs[2] == 33


def test_in_instructions():
    sim = Weft()
    sim.load(asm.assemble("INC 3\nINR r1, 3\nINALL r2\nHALT").words)
    sim.step(HOST_IDLE | (1 << 3) | (1 << 12))  # let the pads propagate through the synchronizer
    sim.step(HOST_IDLE | (1 << 3) | (1 << 12))
    sim.run()
    for _ in range(10):
        sim.step(HOST_IDLE | (1 << 3) | (1 << 12))
        if not sim.running:
            break
    assert sim.c == 1 and sim.regs[1] == 1 and sim.regs[2] == (HOST_IDLE | (1 << 3) | (1 << 12))


def test_out_and_oe():
    s = run("OUT 0, 1\nOUT 9, 1\nOE 9, 1\nOE 3, 1\nLDI r1, 1\nADD r1, r1, r1\nLDW r1, 0xFFFF\nADDI r1, 1\nOUTC 2\nOENC 10\nHALT")
    assert s.pout == (1 << 0) | (1 << 9) | (1 << 2)
    assert s.poe == (1 << 1)  # OE on pin 3 ignored; OENC 10 with C=1 -> released


def test_fifo_push_pull_stall():
    s = run("PULL r1\nPULL r2\nPUSH r1\nPUSH r2\nPUSH r1\nPUSH r2\nPUSH r1\nHALT", prefill=[0x1234, 0xABCD], cycles=50)
    assert s.regs[1] == 0x1234 and s.regs[2] == 0xABCD
    assert list(s.ofifo) == [0x1234, 0xABCD, 0x1234, 0xABCD]
    assert s.running == 1 and s.pc == 6  # the fifth PUSH stalls on a full FIFO
    s.host_pull()
    s.step(HOST_IDLE)
    s.step(HOST_IDLE)
    assert s.halted == 1


def test_crc_ccitt_msb_and_reflected():
    # CRC-16/CCITT-FALSE of 0x00 from 0xFFFF is 0xE1F0; feed 8 zero bits.
    s = run("LDW r1, 0x1021\nCRCPOLY r1\nLDW r1, 0xFFFF\nCRCINIT r1\nLDI r1, 0\nADD r1, r1, r1\nLDI r2, 8\nl: CRCIN\nDJNZ r2, l\nCRCRD r4\nHALT")
    assert s.regs[4] == 0xE1F0
    # Reflected CRC-16 (0xA001) of one 0x00 byte from 0 stays 0; of 0xFF byte from 0 is 0x4040.
    s = run("LDW r1, 0xA001\nCRCPOLY r1\nLDI r1, 0\nCRCINIT r1\nLDI r1, 0xFF\nLDI r2, 8\nl: SHRC r1, r1\nCRCINR\nDJNZ r2, l\nCRCRD r4\nHALT")
    assert s.regs[4] == 0x4040


def test_halt_and_resume():
    s = run("LDI r1, 1\nHALT\nLDI r1, 2\nHALT")
    assert s.halted and not s.running and s.regs[1] == 1 and s.pc == 2
    s.run()
    for _ in range(5):
        s.step(HOST_IDLE)
    assert s.regs[1] == 2 and s.halted


def test_illegal_halts_with_ill():
    s = run("LDI r1, 1\n.word 0xFE00\nLDI r1, 2\nHALT")
    assert s.ill == 1 and s.halted == 1 and s.running == 0 and s.pc == 1 and s.regs[1] == 1


def test_peek_words():
    s = run("LDI r1, 0x55\nLDI r3, 9\nTSET r3\nOUT 4, 1\nOE 9, 1\nCALL f\nHALT\nf: RET")
    assert s.peek(isa.DBG["R1"]) == 0x55
    assert s.peek(isa.DBG["POUT"]) == 1 << 4
    assert s.peek(isa.DBG["POE"]) == 1 << 1
    assert s.peek(isa.DBG["LR"]) == 6
    assert s.peek(isa.DBG["FLAGS"]) & (1 << isa.FLAG_BITS["HALTED"])
    assert s.peek(isa.DBG["CYC"]) == s.cyc
