"""cocotb driver for the Weft host SPI port (see docs/host-interface.md).

The host lines live on ui_in[7]=CSn, ui_in[6]=MOSI, ui_in[5]=SCK and the
response on uo_out[7]=MISO. SCK runs at clk/(2*HALF).
"""

from cocotb.triggers import ClockCycles, FallingEdge, RisingEdge

from weft import isa

CSN, MOSI, SCK = 7, 6, 5
HALF = 5  # clock cycles per SCK half period


class SpiHost:
    def __init__(self, dut):
        self.dut = dut
        self.other = 0  # ui_in[4:0] pad values owned by the test
        self.lines = (1, 0, 0)  # (csn, mosi, sck) as currently driven

    def _drive(self, csn, mosi, sck):
        self.lines = (csn, mosi, sck)
        self.dut.ui_in.value = (csn << CSN) | (mosi << MOSI) | (sck << SCK) | (self.other & 0x1F)

    def idle(self):
        self._drive(1, 0, 0)

    def refresh(self):
        """Re-drive ui_in after `other` changed, keeping the host lines as they are."""
        self._drive(*self.lines)

    async def xfer(self, tx, hold=False):
        """One transaction. With hold=True, return right after the last clock edge, leaving CSn low,
        so the caller can watch the chip's reaction from a known cycle (see lockstep in test.py)."""
        rx = []
        await FallingEdge(self.dut.clk)
        self._drive(0, 0, 0)
        await ClockCycles(self.dut.clk, HALF)
        for b in tx:
            r = 0
            for i in range(7, -1, -1):
                self._drive(0, (b >> i) & 1, 0)
                await ClockCycles(self.dut.clk, HALF)
                self._drive(0, (b >> i) & 1, 1)
                r = (r << 1) | ((int(self.dut.uo_out.value) >> 7) & 1)
                if hold and b is tx[-1] and i == 0:
                    rx.append(r)
                    return rx
                await ClockCycles(self.dut.clk, HALF)
            rx.append(r)
        self._drive(0, 0, 0)
        await ClockCycles(self.dut.clk, HALF)
        self.idle()
        await ClockCycles(self.dut.clk, 2 * HALF)
        return rx

    async def status(self):
        rx = await self.xfer([isa.HOST_CMD["STATUS"], 0, 0, 0, 0])
        return {"alive": rx[1] & 1, "running": (rx[1] >> 1) & 1, "halted": (rx[1] >> 2) & 1, "ill": (rx[1] >> 3) & 1,
                "ififo_empty": (rx[1] >> 6) & 1, "ofifo_full": (rx[1] >> 7) & 1, "pc": rx[2],
                "icount": rx[3] & 0xF, "ocount": (rx[3] >> 4) & 0xF, "version": rx[4], "raw": rx}

    async def load(self, words, base=0):
        payload = []
        for w in words:
            payload += [(w >> 8) & 0xFF, w & 0xFF]
        await self.xfer([isa.HOST_CMD["LOAD"], base] + payload)

    async def load_full(self, words, depth=isa.PMEM_DEPTH_DEFAULT):
        """Zero-fill the whole program memory, then the program: no X anywhere in gate-level sim."""
        await self.load(list(words) + [0] * (depth - len(words)))

    async def reset(self):
        await self.xfer([isa.HOST_CMD["RESET"]])

    async def run(self):
        await self.xfer([isa.HOST_CMD["RUN"]])

    async def run_hold(self):
        """Send RUN and return at its final clock edge; the core starts a few cycles later."""
        await self.xfer([isa.HOST_CMD["RUN"]], hold=True)

    async def stop(self):
        await self.xfer([isa.HOST_CMD["STOP"]])

    async def step(self):
        await self.xfer([isa.HOST_CMD["STEP"]])

    async def push(self, words):
        payload = []
        for w in words:
            payload += [(w >> 8) & 0xFF, w & 0xFF]
        if payload:
            await self.xfer([isa.HOST_CMD["PUSH"]] + payload)

    async def pull(self, n):
        rx = await self.xfer([isa.HOST_CMD["PULL"]] + [0] * (2 * n))
        return [(rx[1 + 2 * i] << 8) | rx[2 + 2 * i] for i in range(n)]

    async def peek(self, sel):
        rx = await self.xfer([isa.HOST_CMD["PEEK"], sel, 0, 0])
        return (rx[2] << 8) | rx[3]

    async def peek_all(self):
        return {name: await self.peek(sel) for name, sel in isa.DBG.items()}
