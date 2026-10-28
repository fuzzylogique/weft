"""Cycle-accurate instruction-set simulator (the golden model) for Weft.

The simulator advances one clock cycle per :meth:`Weft.step`.  Its internal
structure deliberately mirrors the RTL: read registered state, decode, decide
whether the instruction fires or stalls, compute next-state values, commit.
The lockstep test in ``test/test.py`` runs this model beside the RTL and
compares every output pin on every cycle, so any divergence between the two
is a bug in one of them, never a matter of interpretation.

Timing conventions (see :func:`weft.isa.cycle_contract`):

* ``step(pad_in)`` is one clock cycle.  ``pad_in`` is the 16-bit value on the
  input pads *during* that cycle ({uio_in[7:0], ui_in[7:0]}).
* After ``step`` returns, ``pout``/``poe`` hold the pin registers as they are
  during the *next* cycle (registered at the clock edge that ends this one).
* An instruction executing in cycle N sees inputs from the start of cycle N-2.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

from . import isa

MASK16 = 0xFFFF


@dataclass
class Trace:
    cycle: int
    pc: int
    word: int
    fired: bool
    pout: int
    poe: int


class Weft:
    """One Weft core plus its timer, CRC unit, pin registers and host FIFOs."""

    def __init__(self, depth: int = isa.PMEM_DEPTH_DEFAULT, fifo_depth: int = isa.FIFO_DEPTH):
        if depth & (depth - 1):
            raise ValueError("PMEM depth must be a power of two")
        self.depth = depth
        self.pc_bits = depth.bit_length() - 1
        self.fifo_depth = fifo_depth
        self.pmem = [0] * depth
        self.pad = 0
        self.sync1 = self.sync2 = self.sync3 = 0
        self.ififo: deque[int] = deque()  # host -> core
        self.ofifo: deque[int] = deque()  # core -> host
        self.trace: list[Trace] | None = None
        self.cycle = 0
        self.reset()

    # ------------------------------------------------------------------ host
    def power_on_reset(self) -> None:
        """Equivalent of asserting rst_n: everything except PMEM contents."""
        self.sync1 = self.sync2 = self.sync3 = 0
        self.cycle = 0
        self.reset()

    def reset(self) -> None:
        """Host RESET command: core state and FIFOs, not program memory."""
        self.regs = [0] * isa.NREGS
        self.pc = 0
        self.lr = 0
        self.z = 0
        self.c = 0
        self.running = 0
        self.halted = 0
        self.ill = 0
        self.pout = 0
        self.poe = 0
        self.tmr_period = 0
        self.tmr_cnt = 0
        self.tmr_run = 0
        self.tick = 0
        self.cyc = 0
        self.dly = 0
        self.crc = 0
        self.poly = 0
        self.ififo.clear()
        self.ofifo.clear()

    def load(self, words: list[int], base: int = 0) -> None:
        for i, w in enumerate(words):
            self.pmem[(base + i) % self.depth] = w & MASK16

    def run(self) -> None:
        self.running = 1
        self.halted = 0

    def stop(self) -> None:
        self.running = 0

    def host_push(self, word: int) -> bool:
        if len(self.ififo) >= self.fifo_depth:
            return False
        self.ififo.append(word & MASK16)
        return True

    def host_pull(self) -> int | None:
        return self.ofifo.popleft() if self.ofifo else None

    def flags_word(self) -> int:
        b = isa.FLAG_BITS
        return (self.z << b["Z"]) | (self.c << b["C"]) | (self.tick << b["TICK"]) | (self.running << b["RUNNING"]) \
            | (self.halted << b["HALTED"]) | (self.ill << b["ILL"]) | (self.tmr_run << b["TRUN"])

    def peek(self, sel: int) -> int:
        sel &= 0xF
        if sel < 8:
            return self.regs[sel]
        return {
            isa.DBG["PC"]: self.pc, isa.DBG["FLAGS"]: self.flags_word(), isa.DBG["CYC"]: self.cyc,
            isa.DBG["TCNT"]: self.tmr_cnt, isa.DBG["CRC"]: self.crc, isa.DBG["POUT"]: self.pout,
            isa.DBG["POE"]: self.poe, isa.DBG["LR"]: self.lr,
        }[sel]

    # -------------------------------------------------------------- outputs
    @property
    def uo_out(self) -> int:
        return self.pout & 0xFF

    @property
    def uio_out(self) -> int:
        return (self.pout >> 8) & 0xFF

    @property
    def uio_oe(self) -> int:
        return self.poe & 0xFF

    # ----------------------------------------------------------------- cycle
    def step(self, pad_in: int | None = None, step_pulse: bool = False) -> bool:
        """Advance one clock. Returns True if an instruction fired (completed)."""
        if pad_in is not None:
            self.pad = pad_in & MASK16
        sync, prev = self.sync2, self.sync3
        en = bool(self.running) or step_pulse
        regs = self.regs
        depth = self.depth

        # Defaults for next-state values.
        fired = False
        pc_n = self.pc
        lr_n = self.lr
        z_n, c_n = self.z, self.c
        running_n, halted_n, ill_n = self.running, self.halted, self.ill
        pout_n, poe_n = self.pout, self.poe
        dly_n = self.dly
        crc_n, poly_n = self.crc, self.poly
        we, wa, wd = False, 0, 0
        set_z = False
        tset = tstop = consume = False
        period_in = 0
        push_val = None
        pull = False
        word = self.pmem[self.pc]

        if en:
            w = word
            op = w >> 12
            sub = (w >> 9) & 7
            rd = (w >> 9) & 7
            rs = (w >> 6) & 7
            rt = (w >> 3) & 7
            fn = w & 7
            imm8 = w & 0xFF
            imm9 = w & 0x1FF
            imm12 = w & 0xFFF
            pin = w & 0xF
            b8 = (w >> 8) & 1
            target = (w & 0xFF) % depth
            O = isa.OP
            ra = rs if op in (O["ALU"], O["OUT"], O["TIMER"], O["FIFO"], O["CRC"]) else rd
            a = regs[ra]
            b = regs[rt]
            pin_bit = (sync >> pin) & 1
            prev_bit = (prev >> pin) & 1
            stall = False
            branch = False

            if isa.is_illegal(w):
                running_n, halted_n, ill_n = 0, 1, 1
            elif op == O["SYS"]:
                if sub == isa.SYS_SUB["HALT"]:
                    running_n, halted_n = 0, 1
                elif sub == isa.SYS_SUB["RET"]:
                    pc_n, branch = self.lr, True
            elif op == O["LDI"]:
                we, wa, set_z = True, rd, True
                wd = imm8 if b8 == 0 else ((imm8 << 8) | (a & 0xFF))
            elif op == O["ALU"]:
                we, wa, set_z = True, rd, True
                F = isa.ALU_FN
                if fn == F["ADD"]:
                    s = a + b
                    wd, c_n = s & MASK16, s >> 16
                elif fn == F["SUB"]:
                    wd, c_n = (a - b) & MASK16, int(a < b)
                elif fn == F["AND"]:
                    wd = a & b
                elif fn == F["OR"]:
                    wd = a | b
                elif fn == F["XOR"]:
                    wd = a ^ b
                elif fn == F["SHLC"]:
                    wd, c_n = ((a << 1) | self.c) & MASK16, (a >> 15) & 1
                elif fn == F["SHRC"]:
                    wd, c_n = (a >> 1) | (self.c << 15), a & 1
                else:  # MOV
                    wd = a
            elif op == O["ADDI"]:
                s = a + (isa.sext(imm9, 9) & MASK16)
                we, wa, set_z = True, rd, True
                wd, c_n = s & MASK16, s >> 16
            elif op == O["CMPI"]:
                z_n, c_n = int(((a - imm8) & MASK16) == 0), int(a < imm8)
            elif op == O["BR"]:
                C = isa.BR_COND
                cond = {
                    C["AL"]: True, C["EQ"]: bool(self.z), C["NE"]: not self.z, C["CS"]: bool(self.c),
                    C["CC"]: not self.c, C["INE"]: len(self.ififo) == 0,
                    C["OUTF"]: len(self.ofifo) >= self.fifo_depth, C["TICK"]: bool(self.tick),
                }[sub]
                if cond:
                    pc_n, branch = target, True
            elif op == O["DJNZ"]:
                nv = (a - 1) & MASK16
                we, wa, wd = True, rd, nv
                if nv != 0:
                    pc_n, branch = target, True
            elif op == O["OUT"]:
                S = isa.OUT_SUB
                if sub in (S["OUT0"], S["OUT1"], S["OUTC"], S["OUTR"]):
                    v = {S["OUT0"]: 0, S["OUT1"]: 1, S["OUTC"]: self.c, S["OUTR"]: a & 1}[sub]
                    pout_n = (self.pout & ~(1 << pin)) | (v << pin)
                elif pin >= 8:
                    v = {S["OE0"]: 0, S["OE1"]: 1, S["OEC"]: self.c, S["OENC"]: self.c ^ 1}[sub]
                    poe_n = (self.poe & ~(1 << (pin - 8))) | (v << (pin - 8))
            elif op == O["IN"]:
                S = isa.IN_SUB
                if sub == S["INC"]:
                    c_n = pin_bit
                elif sub == S["INR"]:
                    we, wa, wd, set_z = True, rs, pin_bit, True
                else:  # INALL
                    we, wa, wd, set_z = True, rs, sync, True
            elif op == O["WAIT"]:
                S = isa.WAIT_SUB
                cond = {
                    S["WAITP0"]: pin_bit == 0, S["WAITP1"]: pin_bit == 1,
                    S["WAITR"]: pin_bit == 1 and prev_bit == 0, S["WAITF"]: pin_bit == 0 and prev_bit == 1,
                    S["WAITT"]: bool(self.tick),
                }[sub]
                stall = not cond
                if cond and sub == S["WAITT"]:
                    consume = True
            elif op == O["DELAY"]:
                if self.dly == imm12:
                    dly_n = 0
                else:
                    stall = True
                    dly_n = self.dly + 1
            elif op == O["TIMER"]:
                S = isa.TIMER_SUB
                if sub == S["TSET"]:
                    tset, period_in = True, a
                elif sub == S["TSTOP"]:
                    tstop = True
                elif sub == S["RDCYC"]:
                    we, wa, wd, set_z = True, rs, self.cyc, True
                else:  # RDT
                    we, wa, wd, set_z = True, rs, self.tmr_cnt, True
            elif op == O["LOGI"]:
                we, wa, set_z = True, rd, True
                wd = (a & imm8) if b8 == isa.LOGI_SUB["ANDI"] else (a | imm8)
            elif op == O["FIFO"]:
                if sub == isa.FIFO_SUB["PUSH"]:
                    stall = len(self.ofifo) >= self.fifo_depth
                    if not stall:
                        push_val = a
                else:  # PULL
                    stall = len(self.ififo) == 0
                    if not stall:
                        we, wa, wd, set_z, pull = True, rs, self.ififo[0], True, True
            elif op == O["CRC"]:
                S = isa.CRC_SUB
                if sub == S["CRCPOLY"]:
                    poly_n = a
                elif sub == S["CRCINIT"]:
                    crc_n = a
                elif sub == S["CRCIN"]:
                    fb = ((self.crc >> 15) & 1) ^ self.c
                    crc_n = ((self.crc << 1) & MASK16) ^ (self.poly if fb else 0)
                elif sub == S["CRCINR"]:
                    fb = (self.crc & 1) ^ self.c
                    crc_n = (self.crc >> 1) ^ (self.poly if fb else 0)
                else:  # CRCRD
                    we, wa, wd, set_z = True, rs, self.crc, True
            elif op == O["CALL"]:
                lr_n = (self.pc + 1) % depth
                pc_n, branch = target, True

            fired = not stall
            if stall:
                # Nothing but the delay counter moves on a stall cycle.
                we = False
                pout_n, poe_n = self.pout, self.poe
                c_n, z_n = self.c, self.z
                crc_n, poly_n = self.crc, self.poly
                running_n, halted_n, ill_n = self.running, self.halted, self.ill
                lr_n = self.lr
            else:
                if not branch and not ill_n:
                    pc_n = (self.pc + 1) % depth
                if we and set_z:
                    z_n = int(wd == 0)

        # Timer: advances only while the core is enabled (so STOP freezes it and STEP moves it
        # one cycle); overridden by TSET/TSTOP executing this cycle.
        new_tick = bool(self.tmr_run) and en and self.tmr_cnt == 0
        period_n, cnt_n, trun_n = self.tmr_period, self.tmr_cnt, self.tmr_run
        if tset:
            period_n, cnt_n, trun_n, tick_n = period_in, (period_in - 1) & MASK16, 1, 0
        elif tstop:
            trun_n, tick_n = 0, 0
        else:
            if self.tmr_run and en:
                cnt_n = (self.tmr_period - 1) & MASK16 if self.tmr_cnt == 0 else self.tmr_cnt - 1
            tick_n = int((self.tick and not consume) or new_tick)

        # Commit.
        if we:
            regs[wa] = wd & MASK16
        if push_val is not None:
            self.ofifo.append(push_val)
        if pull:
            self.ififo.popleft()
        self.pc, self.lr, self.z, self.c = pc_n, lr_n, z_n, c_n
        self.running, self.halted, self.ill = running_n, halted_n, ill_n
        self.pout, self.poe = pout_n, poe_n
        self.dly, self.crc, self.poly = dly_n, crc_n, poly_n
        self.tmr_period, self.tmr_cnt, self.tmr_run, self.tick = period_n, cnt_n, trun_n, tick_n
        if en:
            self.cyc = (self.cyc + 1) & MASK16
        self.sync3, self.sync2, self.sync1 = self.sync2, self.sync1, self.pad
        if self.trace is not None:
            self.trace.append(Trace(self.cycle, self.pc, word, fired, self.pout, self.poe))
        self.cycle += 1
        return fired

    # ------------------------------------------------------------- helpers
    def run_cycles(self, n: int, pad_fn=None) -> list[tuple[int, int, int]]:
        """Run n cycles. pad_fn(cycle, sim) -> pad_in. Returns (pout, poe, pad) per cycle."""
        out = []
        for _ in range(n):
            pad = pad_fn(self.cycle, self) if pad_fn else None
            self.step(pad)
            out.append((self.pout, self.poe, self.pad))
            if not self.running:
                break
        return out


def bus_level(pout: int, poe: int, pin: int, external_low: bool = False) -> int:
    """Level on a bidirectional pin (8..15) with an external pull-up and optional other driver."""
    k = pin - 8
    driven = (poe >> k) & 1
    level = ((pout >> pin) & 1) if driven else 1
    return 0 if external_low else level
