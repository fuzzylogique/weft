"""Cycle-sampled protocol decoders and bus models.

Each class consumes one sample per clock cycle, so the same code checks a
program on the ISS (layer 2 of the verification plan) and on the RTL under
cocotb (layer 3).  They are deliberately independent of the firmware: they
implement the protocol as the spec describes it, not as the program does it.
"""

from __future__ import annotations

from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# UART
# ---------------------------------------------------------------------------

@dataclass
class UartFrame:
    start_cycle: int
    byte: int
    framing_ok: bool
    bit_lengths: list[int]  # measured length in cycles of each of the 10 bits where an edge bounded it


class UartDecoder:
    """8N1 receiver sampling at the centre of each bit.

    Also records the cycle of every level change so a test can check that the
    transmitter's bit boundaries are exactly ``cycles_per_bit`` apart.
    """

    def __init__(self, cycles_per_bit: int):
        self.cpb = cycles_per_bit
        self.prev = 0  # the line must be seen idle-high before a start bit counts
        self.cycle = 0
        self.in_frame = False
        self.frames: list[UartFrame] = []
        self.edges: list[int] = []  # cycles at which the line changed
        self._samples: list[int] = []
        self._next_sample = 0
        self._start = 0

    def feed(self, level: int) -> None:
        level &= 1
        if level != self.prev:
            self.edges.append(self.cycle)
        if not self.in_frame:
            if self.prev == 1 and level == 0:
                self.in_frame = True
                self._start = self.cycle
                self._samples = []
                self._next_sample = self.cycle + self.cpb // 2
        if self.in_frame and self.cycle == self._next_sample:
            self._samples.append(level)
            self._next_sample += self.cpb
            if len(self._samples) == 10:
                start, data, stop = self._samples[0], self._samples[1:9], self._samples[9]
                byte = sum(b << i for i, b in enumerate(data))
                frame_edges = [e for e in self.edges if self._start <= e <= self.cycle]
                lengths = [b - a for a, b in zip(frame_edges, frame_edges[1:])]
                self.frames.append(UartFrame(self._start, byte, start == 0 and stop == 1, lengths))
                self.in_frame = False
        self.prev = level
        self.cycle += 1

    @property
    def bytes(self) -> list[int]:
        return [f.byte for f in self.frames]


def uart_frame_levels(byte: int, cycles_per_bit: int) -> list[int]:
    """Expected TX line, one entry per cycle, for an 8N1 frame (start, 8 data LSB first, stop)."""
    bits = [0] + [(byte >> i) & 1 for i in range(8)] + [1]
    out = []
    for b in bits:
        out.extend([b] * cycles_per_bit)
    return out


# ---------------------------------------------------------------------------
# SPI
# ---------------------------------------------------------------------------

class SpiSlaveModel:
    """Mode 0 (CPOL=0, CPHA=0) SPI target, MSB first, active-low chip select.

    Samples MOSI on the rising SCLK edge.  Presents the MSB of the next
    response byte when CS falls and after every eighth rising edge, and shifts
    on falling edges, so the master samples valid data on each rising edge.
    """

    def __init__(self, response: list[int] | None = None):
        self.response = list(response or [])
        self.received: list[int] = []
        self.transactions: list[list[int]] = []
        self.sclk_prev = 0
        self.cs_prev = 1
        self.bitcnt = 0
        self.rx = 0
        self.tx = 0
        self.miso = 0
        self.idx = 0  # next response byte; advances only once a byte has been clocked out
        self._cur: list[int] = []

    def _load_next(self) -> None:
        self.tx = self.response[self.idx] if self.idx < len(self.response) else 0xFF
        self.miso = (self.tx >> 7) & 1

    def feed(self, sclk: int, mosi: int, cs: int) -> int:
        """Feed this cycle's pad levels; return the MISO level the target drives from now on."""
        if self.cs_prev == 1 and cs == 0:  # select
            self.bitcnt = 0
            self.rx = 0
            self._cur = []
            self._load_next()
        elif self.cs_prev == 0 and cs == 1:  # deselect
            if self._cur:
                self.transactions.append(self._cur)
        if cs == 0:
            if self.sclk_prev == 0 and sclk == 1:  # rising: sample
                self.rx = ((self.rx << 1) | (mosi & 1)) & 0xFF
                self.bitcnt += 1
                if self.bitcnt == 8:
                    self.received.append(self.rx)
                    self._cur.append(self.rx)
                    self.bitcnt = 0
                    self.idx += 1
                    self._load_next()
            elif self.sclk_prev == 1 and sclk == 0 and self.bitcnt != 0:  # falling: shift
                self.tx = (self.tx << 1) & 0xFF
                self.miso = (self.tx >> 7) & 1
        self.sclk_prev, self.cs_prev = sclk, cs
        return self.miso


class SpiMonitor:
    """Decodes a mode-0 SPI bus from (sclk, mosi, miso, cs) samples; also measures SCLK half periods."""

    def __init__(self):
        self.mosi_bytes: list[int] = []
        self.miso_bytes: list[int] = []
        self.sclk_edges: list[list[int]] = []  # SCLK edge cycles, one list per chip-select window
        self.cycle = 0
        self.sclk_prev = 0
        self.cs_prev = 1
        self.n = 0
        self.a = self.b = 0

    def feed(self, sclk: int, mosi: int, miso: int, cs: int) -> None:
        if self.cs_prev == 1 and cs == 0:
            self.n = self.a = self.b = 0
            self.sclk_edges.append([])
        if cs == 0 and sclk != self.sclk_prev:
            self.sclk_edges[-1].append(self.cycle)
            if sclk == 1:
                self.a = ((self.a << 1) | (mosi & 1)) & 0xFF
                self.b = ((self.b << 1) | (miso & 1)) & 0xFF
                self.n += 1
                if self.n == 8:
                    self.mosi_bytes.append(self.a)
                    self.miso_bytes.append(self.b)
                    self.n = 0
        self.sclk_prev, self.cs_prev = sclk, cs
        self.cycle += 1

    def half_periods(self) -> list[int]:
        """SCLK half periods measured within each chip-select window (not across the gaps)."""
        out = []
        for group in self.sclk_edges:
            out += [b - a for a, b in zip(group, group[1:])]
        return out


# ---------------------------------------------------------------------------
# I2C
# ---------------------------------------------------------------------------

@dataclass
class I2cEvent:
    kind: str  # START, STOP, BYTE (written to target), ACK, NACK, READ (byte sent by target)
    value: int = 0
    cycle: int = 0


class I2cTargetModel:
    """A 7-bit-address I2C target with a small register file.

    Write transfers: first data byte is the register pointer, following bytes
    are stored at pointer++.  Read transfers return memory[pointer++].  The
    model pulls SDA low to ACK its address and every written byte.  Call
    :meth:`feed` with the *bus* levels every cycle; it returns True while the
    target is pulling SDA low, so the caller can resolve the open-drain bus.
    """

    def __init__(self, address: int = 0x50, memory: dict[int, int] | None = None, ack: bool = True):
        self.address = address
        self.memory = dict(memory or {})
        self.ack_enabled = ack
        self.events: list[I2cEvent] = []
        self.scl_prev = 1
        self.sda_prev = 1
        self.cycle = 0
        self.active = False
        self.bitcnt = 0
        self.shift = 0
        self.byte_index = 0  # 0 = address byte
        self.reading = False
        self.pointer = 0
        self.pull_low = False
        self.tx_byte = 0
        self.phase = "bits"  # bits | ack
        self.selected = False

    def _log(self, kind, value=0):
        self.events.append(I2cEvent(kind, value, self.cycle))

    def feed(self, scl: int, sda: int) -> bool:
        if self.scl_prev == 1 and scl == 1:
            if self.sda_prev == 1 and sda == 0:
                self._log("START")
                self.active, self.bitcnt, self.shift, self.byte_index = True, 0, 0, 0
                self.phase, self.reading, self.selected, self.pull_low = "bits", False, False, False
            elif self.sda_prev == 0 and sda == 1:
                self._log("STOP")
                self.active, self.pull_low, self.selected = False, False, False
        if self.active:
            if self.scl_prev == 0 and scl == 1:  # rising edge: sample
                if self.phase == "bits":
                    if not (self.reading and self.byte_index > 0):
                        self.shift = ((self.shift << 1) | (sda & 1)) & 0xFF
                    self.bitcnt += 1
                else:  # ack bit
                    if self.reading and self.byte_index > 0:
                        self._log("ACK" if sda == 0 else "NACK", self.tx_byte)
                        if sda == 0:
                            pass
                        else:
                            self.selected = False
            elif self.scl_prev == 1 and scl == 0:  # falling edge: change drivers
                if self.phase == "bits" and self.bitcnt == 8:
                    self.phase = "ack"
                    if self.byte_index == 0:
                        addr, rw = self.shift >> 1, self.shift & 1
                        self.selected = addr == self.address and self.ack_enabled
                        self.reading = bool(rw)
                        self._log("BYTE", self.shift)
                        self.pull_low = self.selected
                    elif not self.reading:
                        self._log("BYTE", self.shift)
                        if self.selected:
                            if self.byte_index == 1:
                                self.pointer = self.shift
                            else:
                                self.memory[self.pointer] = self.shift
                                self.pointer = (self.pointer + 1) & 0xFF
                        self.pull_low = self.selected
                    else:
                        self.pull_low = False  # master acks reads
                elif self.phase == "ack":
                    self.phase, self.bitcnt, self.shift = "bits", 0, 0
                    self.byte_index += 1
                    if self.reading and self.selected:
                        self.tx_byte = self.memory.get(self.pointer, 0xFF)
                        self.pointer = (self.pointer + 1) & 0xFF
                        self._log("READ", self.tx_byte)
                        self.pull_low = not ((self.tx_byte >> 7) & 1)
                    else:
                        self.pull_low = False
                elif self.phase == "bits" and self.reading and self.selected and self.byte_index > 0:
                    bit = (self.tx_byte >> (7 - self.bitcnt)) & 1
                    self.pull_low = not bit
        self.scl_prev, self.sda_prev = scl, sda
        self.cycle += 1
        return self.pull_low

    def written_bytes(self) -> list[int]:
        return [e.value for e in self.events if e.kind == "BYTE"]


class I2cMonitor:
    """Pure decoder of an I2C bus: START/STOP/bytes with the ACK bit as seen on the wire."""

    def __init__(self):
        self.events: list[I2cEvent] = []
        self.scl_prev = self.sda_prev = 1
        self.cycle = 0
        self.active = False
        self.bitcnt = 0
        self.shift = 0

    def feed(self, scl: int, sda: int) -> None:
        if self.scl_prev == 1 and scl == 1:
            if self.sda_prev == 1 and sda == 0:
                self.events.append(I2cEvent("START", 0, self.cycle))
                self.active, self.bitcnt, self.shift = True, 0, 0
            elif self.sda_prev == 0 and sda == 1:
                self.events.append(I2cEvent("STOP", 0, self.cycle))
                self.active = False
        if self.active and self.scl_prev == 0 and scl == 1:
            self.shift = ((self.shift << 1) | (sda & 1)) & 0x1FF
            self.bitcnt += 1
            if self.bitcnt == 9:
                self.events.append(I2cEvent("BYTE", self.shift >> 1, self.cycle))
                self.events.append(I2cEvent("ACK" if (self.shift & 1) == 0 else "NACK", self.shift >> 1, self.cycle))
                self.bitcnt, self.shift = 0, 0
        self.scl_prev, self.sda_prev = scl, sda
        self.cycle += 1

    def summary(self) -> list[str]:
        return [f"{e.kind}" + (f" 0x{e.value:02x}" if e.kind in ("BYTE",) else "") for e in self.events if e.kind != "ACK" and e.kind != "NACK"] 
