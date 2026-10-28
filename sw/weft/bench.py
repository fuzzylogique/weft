"""Shared test-bench pieces used by both the Python tests and the cocotb tests.

The point of this module is *parity*: the same stimulus objects drive the ISS
in ``sw/tests`` and the RTL in ``test/test.py``, cycle by cycle, so a lockstep
comparison is meaningful.

Pad word layout (16 bits): ``{uio_in[7:0], ui_in[7:0]}``.  Bits 5..7 of ui_in
are the host SPI lines; when the host is idle they read SCK=0, MOSI=0, CSn=1.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from . import asm, isa, protocols
from .iss import Weft

HOST_IDLE = 0x0080  # CSn high, SCK and MOSI low, all other pads low
MARKER_PIN = 6  # lockstep runs prepend "OUT 6, 1" so the RTL test can find cycle 1
MARKER_WORD = asm.encode_instruction("OUT", [str(MARKER_PIN), "1"], {})


def with_marker(words: list[int]) -> list[int]:
    return [MARKER_WORD] + list(words)


def load_program(name: str, depth: int = isa.PMEM_DEPTH_DEFAULT, marker: bool = True) -> asm.Program:
    """Assemble sw/programs/<name>.asm. With marker=True (the default, what run_iss and the
    cocotb lockstep expect) the program is assembled at base address 1, behind the marker word."""
    import os
    path = os.path.join(os.path.dirname(__file__), "..", "programs", name + ".asm")
    return asm.assemble_file(path, depth, base=1 if marker else 0)


# ---------------------------------------------------------------------------
# Stimulus models: pad(cycle, pout, poe) -> 16-bit pad value for this cycle
# ---------------------------------------------------------------------------

class Stimulus:
    def pad(self, cycle: int, pout: int, poe: int) -> int:
        return HOST_IDLE


class UartRxStim(Stimulus):
    """Drives 8N1 frames into input pin `pin` (default 0: ui_in[0])."""

    def __init__(self, data: list[int], cycles_per_bit: int, start: int = 50, gap: int = 100, pin: int = 0,
                 corrupt_stop: bool = False):
        levels = [1] * start
        for i, b in enumerate(data):
            frame = protocols.uart_frame_levels(b, cycles_per_bit)
            if corrupt_stop and i == len(data) - 1:
                frame[-cycles_per_bit:] = [0] * cycles_per_bit
            levels += frame + [1] * gap
        self.levels = levels
        self.pin = pin

    def pad(self, cycle, pout, poe):
        lvl = self.levels[cycle] if cycle < len(self.levels) else 1
        return HOST_IDLE | (lvl << self.pin)


class SpiSlaveStim(Stimulus):
    """An SPI mode-0 target on SCLK=pin 1, MOSI=pin 2, CSn=pin 3 (outputs) answering on input pin 1."""

    def __init__(self, response: list[int]):
        self.model = protocols.SpiSlaveModel(response)
        self.monitor = protocols.SpiMonitor()
        self.miso = 0

    def pad(self, cycle, pout, poe):
        sclk, mosi, cs = (pout >> 1) & 1, (pout >> 2) & 1, (pout >> 3) & 1
        self.monitor.feed(sclk, mosi, self.miso, cs)
        self.miso = self.model.feed(sclk, mosi, cs)
        return HOST_IDLE | (self.miso << 1)


class I2cTargetStim(Stimulus):
    """Open-drain bus with pull-ups on SCL=pin 8, SDA=pin 9 and one target device."""

    def __init__(self, address: int = 0x50, memory: dict | None = None, ack: bool = True, stretch: int = 0):
        self.model = protocols.I2cTargetModel(address, memory, ack)
        self.monitor = protocols.I2cMonitor()
        self.target_low = False
        self.stretch = stretch  # cycles the target holds SCL low after each falling edge (clock stretching)
        self._stretch_left = 0
        self._scl_prev = 1

    def pad(self, cycle, pout, poe):
        master_scl_low = bool((poe >> 0) & 1) and not ((pout >> 8) & 1)
        master_sda_low = bool((poe >> 1) & 1) and not ((pout >> 9) & 1)
        scl = 0 if master_scl_low else 1
        if self.stretch:
            if self._scl_prev == 1 and scl == 0:
                self._stretch_left = self.stretch
            elif self._stretch_left > 0:
                self._stretch_left -= 1
                scl = 0
            self._scl_prev = scl if not self._stretch_left else 0
        sda = 0 if (master_sda_low or self.target_low) else 1
        self.monitor.feed(scl, sda)
        self.target_low = self.model.feed(scl, sda)
        return HOST_IDLE | (scl << 8) | (sda << 9)


class RandomPinStim(Stimulus):
    """Seeded random activity on the firmware input pins (never on the host lines)."""

    PINS = [0, 1, 2, 3, 4, 8, 9, 10, 11, 12, 13, 14, 15]

    def __init__(self, seed: int, hold: int = 7):
        self.rng = random.Random(seed)
        self.hold = hold
        self.value = HOST_IDLE

    def pad(self, cycle, pout, poe):
        if cycle % self.hold == 0:
            pin = self.rng.choice(self.PINS)
            self.value ^= 1 << pin
        return self.value


# ---------------------------------------------------------------------------
# ISS runner
# ---------------------------------------------------------------------------

@dataclass
class RunResult:
    sim: Weft
    pout: list[int] = field(default_factory=list)  # per cycle, state during cycle k (k >= 1)
    poe: list[int] = field(default_factory=list)
    pad: list[int] = field(default_factory=list)
    pulled: list[int] = field(default_factory=list)

    def pin_levels(self, pin: int) -> list[int]:
        return [(p >> pin) & 1 for p in self.pout]

    def pad_levels(self, pin: int) -> list[int]:
        return [(p >> pin) & 1 for p in self.pad]


def run_iss(words: list[int], stim: Stimulus | None = None, cycles: int = 1000, prefill=(), drain: bool = False,
            depth: int = isa.PMEM_DEPTH_DEFAULT, marker: bool = True, stop_on_halt: bool = True) -> RunResult:
    """Run a program on the ISS exactly the way the cocotb lockstep test runs it on the RTL."""
    stim = stim or Stimulus()
    sim = Weft(depth)
    sim.load(with_marker(words) if marker else words)
    for w in prefill:
        assert sim.host_push(w)
    sim.run()
    res = RunResult(sim)
    sim.step(HOST_IDLE)  # cycle 0: marker (or first instruction)
    res.pout.append(sim.pout)
    res.poe.append(sim.poe)
    res.pad.append(HOST_IDLE)
    for k in range(1, cycles):
        pad = stim.pad(k, sim.pout, sim.poe)
        sim.step(pad)
        res.pout.append(sim.pout)
        res.poe.append(sim.poe)
        res.pad.append(pad)
        if drain:
            w = sim.host_pull()
            if w is not None:
                res.pulled.append(w)
        if stop_on_halt and not sim.running:
            break
    return res


# ---------------------------------------------------------------------------
# Constrained-random programs
# ---------------------------------------------------------------------------

_RANDOM_PINS = [0, 1, 2, 3, 4, 8, 9, 10, 11, 12, 13, 14, 15]
_WEIGHTS = {
    "LDI": 6, "LDIH": 2, "ADD": 4, "SUB": 4, "AND": 2, "OR": 2, "XOR": 3, "SHLC": 4, "SHRC": 4, "MOV": 2,
    "ADDI": 4, "CMPI": 3, "ANDI": 2, "ORI": 2, "JMP": 1, "BEQ": 2, "BNE": 2, "BCS": 2, "BCC": 2, "BINE": 1,
    "BOUTF": 1, "BTICK": 1, "DJNZ": 3, "CALL": 1, "RET": 1, "OUT0": 4, "OUT1": 4, "OUTC": 3, "OUTR": 2,
    "OE0": 2, "OE1": 2, "OEC": 1, "OENC": 1, "INC": 3, "INR": 2, "WAITP0": 1, "WAITP1": 1, "WAITR": 1,
    "WAITF": 1, "WAITT": 3, "DELAY": 2, "TSET": 1, "TSTOP": 0.3, "RDCYC": 2, "RDT": 1, "PUSH": 1, "PULL": 1,
    "CRCPOLY": 1, "CRCINIT": 1, "CRCIN": 2, "CRCINR": 2, "CRCRD": 1, "NOP": 1, "HALT": 0.2,
}


def random_program(seed: int, length: int = 40, illegal_rate: float = 0.01) -> tuple[list[int], list[str]]:
    """A random but legal-looking program. Returns (words, source lines)."""
    rng = random.Random(seed)
    names = list(_WEIGHTS)
    weights = [_WEIGHTS[n] for n in names]
    lines = [f"LDI r3, {rng.randint(3, 24)}", "TSET r3"]
    total = length + 1  # marker occupies address 0
    while len(lines) < length:
        if rng.random() < illegal_rate:
            lines.append(f".word 0x{0xFE00 | rng.randint(0, 0x1FF):04x}")
            continue
        ins = isa.BY_NAME[rng.choices(names, weights)[0]]
        ops = []
        for tmpl in ins.operands:
            if not tmpl.startswith("{"):
                ops.append(tmpl)
                continue
            kind = tmpl[1:-1]
            if kind in ("rd", "rs", "rt", "rx"):
                ops.append(f"r{rng.randint(0, 7)}")
            elif kind == "imm8":
                ops.append(str(rng.choice([0, 1, 0x7F, 0x80, 0xFF, rng.randint(0, 255)])))
            elif kind == "simm9":
                ops.append(str(rng.choice([-1, 1, -256, 255, rng.randint(-256, 255)])))
            elif kind == "imm12":
                ops.append(str(rng.randint(0, 12)))
            elif kind == "pin":
                ops.append(str(rng.choice(_RANDOM_PINS)))
            elif kind == "target":
                ops.append(str(rng.randint(1, total - 1)))
        lines.append(ins.mnemonic + (" " + ", ".join(ops) if ops else ""))
    prog = asm.assemble("\n".join(lines))
    return prog.words, lines
