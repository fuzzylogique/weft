# SPDX-FileCopyrightText: © 2026 Fayez Haque
# SPDX-License-Identifier: Apache-2.0
"""cocotb tests for the Weft protocol engine.

Layers (see docs/verification-plan.md):
  * host port: status, load, peek, single-step
  * lockstep: every output pin compared against the Python ISS on every cycle,
    for the demo firmware and for constrained-random programs, then every
    architectural register compared through PEEK when the run stops
  * program level: the RTL's UART/SPI/I2C waveforms decoded by independent
    protocol models

Set GATES=yes (the Tiny Tapeout gate-level job does) to shorten the runs.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "sw"))

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, FallingEdge, ReadOnly, RisingEdge

from host import SpiHost
from weft import asm, bench, isa, protocols
from weft.bench import HOST_IDLE, MARKER_PIN, load_program, random_program, with_marker
from weft.iss import Weft

GL = os.environ.get("GATES") == "yes"
DEPTH = isa.PMEM_DEPTH_DEFAULT


async def start(dut):
    cocotb.start_soon(Clock(dut.clk, 20, unit="ns").start())
    host = SpiHost(dut)
    dut.ena.value = 1
    dut.uio_in.value = 0
    host.idle()
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 5)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 5)
    return host


def rtl_outputs(dut):
    return int(dut.uo_out.value) & 0x7F, int(dut.uio_out.value), int(dut.uio_oe.value)


async def lockstep(dut, host, words, stim=None, cycles=2000, prefill=(), check_state=True):
    """Load `words` (behind a marker instruction) into the RTL and the ISS, run them in lockstep."""
    stim = stim or bench.Stimulus()
    prog = with_marker(words)
    sim = Weft(DEPTH)
    sim.load(prog)
    await host.reset()
    await host.load_full(prog)
    await host.reset()
    for w in prefill:
        assert sim.host_push(w)
    await host.push(list(prefill))
    # RUN takes effect a few cycles after the command's last clock edge; return right there so the
    # marker's rising edge (output pin 6, cycle 1 of the program) is seen by the loop below.
    await host.run_hold()
    sim.run()
    for _ in range(50):
        await RisingEdge(dut.clk)
        await ReadOnly()
        if (int(dut.uo_out.value) >> MARKER_PIN) & 1:
            break
    else:
        raise AssertionError("marker never appeared: core did not start")
    sim.step(HOST_IDLE)  # cycle 0 in the ISS
    pad = HOST_IDLE
    trace = bench.RunResult(sim)
    k = 1
    while True:
        rtl = rtl_outputs(dut)
        exp = (sim.uo_out & 0x7F, sim.uio_out, sim.uio_oe)
        if rtl != exp:
            w = sim.pmem[sim.pc]
            raise AssertionError(
                f"lockstep mismatch at cycle {k}: rtl uo/uio/oe={rtl} iss={exp}; iss pc={sim.pc} "
                f"next instr {asm.disassemble(w)} regs={[hex(r) for r in sim.regs]}")
        trace.pout.append(sim.pout)
        trace.poe.append(sim.poe)
        trace.pad.append(pad)
        if k >= cycles or not sim.running:
            break
        await FallingEdge(dut.clk)
        pad = stim.pad(k, sim.pout, sim.poe)
        host.other = pad & 0x1F
        host.idle()  # also ends the held RUN transaction (CSn high); harmless to the core
        dut.uio_in.value = (pad >> 8) & 0xFF
        sim.step(pad)
        await RisingEdge(dut.clk)
        await ReadOnly()
        k += 1
    await FallingEdge(dut.clk)
    if check_state:
        await host.stop()
        cyc = await host.peek(isa.DBG["CYC"])
        extra = (cyc - sim.cyc) & 0xFFFF
        assert extra < 5000, f"RTL ran {extra} cycles more than expected"
        for _ in range(extra):
            sim.step(pad)
        sim.stop()
        for name, sel in isa.DBG.items():
            got = await host.peek(sel)
            assert got == sim.peek(sel), f"{name}: rtl=0x{got:04x} iss=0x{sim.peek(sel):04x} after {k} cycles"
    return trace


# ----------------------------------------------------------------- host port

@cocotb.test()
async def test_host_status_and_version(dut):
    host = await start(dut)
    st = await host.status()
    assert st["alive"] == 1 and st["running"] == 0 and st["version"] == isa.HOST_VERSION, st


@cocotb.test()
async def test_load_run_halt_peek(dut):
    host = await start(dut)
    prog = asm.assemble("LDI r1, 0x5A\nLDIH r1, 0xA5\nLDI r2, 3\nOUT 4, 1\nOE 9, 1\nCALL f\nHALT\nf: RET").words
    await host.load_full(prog)
    await host.reset()
    await host.run()
    await ClockCycles(dut.clk, 40)
    st = await host.status()
    assert st["halted"] == 1 and st["running"] == 0 and st["pc"] == 7, st
    assert await host.peek(isa.DBG["R1"]) == 0xA55A
    assert await host.peek(isa.DBG["R2"]) == 3
    assert await host.peek(isa.DBG["POUT"]) == 1 << 4
    assert await host.peek(isa.DBG["POE"]) == 1 << 1
    assert await host.peek(isa.DBG["LR"]) == 6
    assert (int(dut.uo_out.value) >> 4) & 1 == 1 and int(dut.uio_oe.value) == 2


@cocotb.test()
async def test_single_step(dut):
    host = await start(dut)
    prog = asm.assemble("LDI r1, 1\nADDI r1, 1\nADDI r1, 1\nDELAY 2\nADDI r1, 1\nHALT").words
    await host.load_full(prog)
    await host.reset()
    expect_pc = [1, 2, 3, 3, 3, 4, 5]  # DELAY 2 occupies three cycles
    for pc in expect_pc:
        await host.step()
        assert await host.peek(isa.DBG["PC"]) == pc
    assert await host.peek(isa.DBG["R1"]) == 4
    assert await host.peek(isa.DBG["CYC"]) == len(expect_pc)


@cocotb.test()
async def test_fifo_round_trip(dut):
    host = await start(dut)
    prog = asm.assemble("loop: PULL r1\nADDI r1, 1\nPUSH r1\nJMP loop").words
    await host.load_full(prog)
    await host.reset()
    await host.push([0x1000, 0x2000, 0xFFFF])
    await host.run()
    await ClockCycles(dut.clk, 50)
    st = await host.status()
    assert st["ocount"] == 3 and st["icount"] == 0, st
    assert await host.pull(3) == [0x1001, 0x2001, 0x0000]


@cocotb.test()
async def test_illegal_instruction_halts(dut):
    host = await start(dut)
    await host.load_full([asm.assemble("LDI r1, 1").words[0], 0xFE00, asm.assemble("LDI r1, 2").words[0]])
    await host.reset()
    await host.run()
    await ClockCycles(dut.clk, 20)
    st = await host.status()
    assert st["ill"] == 1 and st["halted"] == 1 and st["pc"] == 1
    assert await host.peek(isa.DBG["R1"]) == 1


# -------------------------------------------------------------- lockstep

@cocotb.test()
async def test_lockstep_selftest(dut):
    host = await start(dut)
    await lockstep(dut, host, load_program("selftest").words, cycles=3000)
    assert await host.pull(1) == [0xC0DE]


@cocotb.test()
async def test_lockstep_blink(dut):
    host = await start(dut)
    await lockstep(dut, host, load_program("blink").words, cycles=1200)


@cocotb.test()
async def test_lockstep_uart_tx_and_decode(dut):
    host = await start(dut)
    data = [0x55] if GL else [0x55, 0x00, 0xFF, 0xA3]
    trace = await lockstep(dut, host, load_program("uart_tx").words, cycles=434 * 11 * len(data) + 400, prefill=data)
    dec = protocols.UartDecoder(434)
    for lvl in trace.pin_levels(0):
        dec.feed(lvl)
    assert dec.bytes == data, dec.bytes
    for f in dec.frames:
        assert f.framing_ok and all(l % 434 == 0 for l in f.bit_lengths), f


@cocotb.test()
async def test_lockstep_uart_rx(dut):
    host = await start(dut)
    data = [0xA5] if GL else [0xA5, 0x00, 0x7E]
    stim = bench.UartRxStim(data, 434, start=60, gap=300)
    await lockstep(dut, host, load_program("uart_rx").words, stim, cycles=len(stim.levels) + 1500)
    assert await host.pull(len(data)) == data


@cocotb.test()
async def test_lockstep_spi_master(dut):
    host = await start(dut)
    tx = [0x9F, 0x00] if GL else [0x9F, 0x00, 0xA5, 0x3C]
    resp = [0xEF, 0x40, 0x18, 0x01][: len(tx)]
    stim = bench.SpiSlaveStim(response=list(resp))
    await lockstep(dut, host, load_program("spi_master").words, stim, cycles=1500 * len(tx), prefill=tx)
    assert stim.model.received == tx
    assert all(h == 10 for h in stim.monitor.half_periods())
    assert await host.pull(len(tx)) == resp


@cocotb.test()
async def test_lockstep_i2c_master(dut):
    host = await start(dut)
    cmds = [0x0100, 0xA0] if GL else [0x0100, 0xA0, 0x10, 0x42]
    stim = bench.I2cTargetStim(address=0x50)
    await lockstep(dut, host, load_program("i2c_master").words, stim, cycles=5200 * (len(cmds) - 1) + 1500, prefill=cmds)
    acks = await host.pull(len(cmds) - 1)
    assert acks == [0] * (len(cmds) - 1), acks
    kinds = [e.kind for e in stim.monitor.events]
    assert kinds[:3] == ["START", "BYTE", "ACK"]
    if not GL:
        assert stim.model.memory[0x10] == 0x42


@cocotb.test()
async def test_lockstep_random_programs(dut):
    host = await start(dut)
    n = 2 if GL else 12
    for seed in range(n):
        words, lines = random_program(seed)
        dut._log.info(f"random program seed={seed}: {len(words)} words")
        try:
            await lockstep(dut, host, words, bench.RandomPinStim(seed), cycles=600, prefill=[1, 2, 3, 4])
        except AssertionError as e:
            raise AssertionError(f"seed {seed}: {e}\n" + "\n".join(lines)) from e
