"""Firmware on the ISS, checked by independent protocol models (layer 2), with ASCII snapshots."""

import os

import pytest

from weft import bench, isa, protocols, waves
from weft.bench import load_program, run_iss

HERE = os.path.dirname(__file__)
SNAP = os.path.join(HERE, "snapshots")


def check_snapshot(name: str, text: str):
    path = os.path.join(SNAP, name + ".txt")
    if os.environ.get("UPDATE_SNAPSHOTS") or not os.path.exists(path):
        with open(path, "w") as f:
            f.write(text)
    with open(path) as f:
        expected = f.read()
    assert text == expected, f"snapshot {name} changed; run with UPDATE_SNAPSHOTS=1 to accept"


def test_selftest_passes():
    res = run_iss(load_program("selftest").words, cycles=2000, drain=True)
    assert res.pulled == [0xC0DE], f"selftest failed at check {res.pulled}"
    assert res.sim.halted


def test_blink_period_exact():
    res = run_iss(load_program("blink").words, cycles=2000, drain=True)
    led = res.pin_levels(4)
    edges = [i for i in range(1, len(led)) if led[i] != led[i - 1]]
    gaps = [b - a for a, b in zip(edges, edges[1:])]
    assert gaps and all(g == 100 for g in gaps), gaps
    assert all(b - a == 100 for a, b in zip(res.pulled, res.pulled[1:]))
    check_snapshot("blink", waves.ascii({"LED": led[:800]}, cycles_per_col=10))


@pytest.mark.parametrize("data", [[0x55], [0x00, 0xFF, 0xA5, 0x3C]])
def test_uart_tx_frames_exact(data):
    res = run_iss(load_program("uart_tx").words, cycles=434 * 11 * len(data) + 500, prefill=data)
    dec = protocols.UartDecoder(434)
    for lvl in res.pin_levels(0):
        dec.feed(lvl)
    assert dec.bytes == data
    for f in dec.frames:
        assert f.framing_ok
        assert all(l % 434 == 0 for l in f.bit_lengths), f.bit_lengths  # every edge on a bit boundary
    if data == [0x55]:
        check_snapshot("uart_tx_0x55", waves.ascii({"TX": res.pin_levels(0)[:434 * 11]}, cycles_per_col=31) +
                       "runs: " + waves.runs(res.pin_levels(0)[:434 * 11]) + "\n")


@pytest.mark.parametrize("data", [[0x55], [0x00, 0xFF, 0xA5, 0x3C]])
def test_uart_rx_decodes(data):
    stim = bench.UartRxStim(data, 434, start=60, gap=300)
    res = run_iss(load_program("uart_rx").words, stim, cycles=len(stim.levels) + 2000, drain=True)
    assert res.pulled == data


def test_uart_rx_framing_error():
    stim = bench.UartRxStim([0x5A, 0x33], 434, corrupt_stop=True)
    res = run_iss(load_program("uart_rx").words, stim, cycles=len(stim.levels) + 2000, drain=True)
    assert res.pulled == [0x5A, 0x01FF]


def test_spi_master_mode0():
    tx = [0x9F, 0x00, 0xA5, 0x3C]
    stim = bench.SpiSlaveStim(response=[0xEF, 0x40, 0x18, 0x01])
    res = run_iss(load_program("spi_master").words, stim, cycles=6000, prefill=tx)
    assert stim.model.received == tx
    assert list(res.sim.ofifo) == [0xEF, 0x40, 0x18, 0x01]
    assert stim.monitor.mosi_bytes == tx and stim.monitor.miso_bytes == [0xEF, 0x40, 0x18, 0x01]
    assert all(h == 10 for h in stim.monitor.half_periods()), stim.monitor.half_periods()
    sig = {"CSn": res.pin_levels(3)[:600], "SCLK": res.pin_levels(1)[:600], "MOSI": res.pin_levels(2)[:600],
           "MISO": res.pad_levels(1)[:600]}
    check_snapshot("spi_master_first_byte", waves.ascii(sig, cycles_per_col=5))


def test_i2c_master_write_and_ack():
    cmds = [0x0100, 0xA0, 0x10, 0x42, 0x0200]  # START, addr 0x50 write, reg 0x10, data 0x42, STOP
    stim = bench.I2cTargetStim(address=0x50)
    # The FIFO holds 4 words: run in two halves, draining ACKs, like a host would.
    res = run_iss(load_program("i2c_master").words, stim, cycles=40000, prefill=cmds[:4], drain=True)
    assert res.pulled == [0, 0, 0]  # three ACKs
    assert stim.model.memory[0x10] == 0x42
    kinds = [e.kind for e in stim.monitor.events]
    assert kinds[:7] == ["START", "BYTE", "ACK", "BYTE", "ACK", "BYTE", "ACK"]
    assert [e.value for e in stim.monitor.events if e.kind == "BYTE"] == [0xA0, 0x10, 0x42]
    scl = [(p >> 8) & 1 for p in res.pad]
    sda = [(p >> 9) & 1 for p in res.pad]
    check_snapshot("i2c_start_and_address", waves.ascii({"SCL": scl[:5200], "SDA": sda[:5200]}, cycles_per_col=40))


def test_i2c_master_nack_and_stop():
    cmds = [0x0100, 0xA2, 0x0200]  # address 0x51: nobody home -> NACK
    stim = bench.I2cTargetStim(address=0x50)
    res = run_iss(load_program("i2c_master").words, stim, cycles=20000, prefill=cmds, drain=True)
    assert res.pulled == [1]
    kinds = [e.kind for e in stim.monitor.events]
    assert kinds == ["START", "BYTE", "NACK", "STOP"]


def test_i2c_master_clock_stretching():
    cmds = [0x0100, 0xA0, 0x10, 0x42]
    stim = bench.I2cTargetStim(address=0x50, stretch=300)
    res = run_iss(load_program("i2c_master").words, stim, cycles=60000, prefill=cmds, drain=True)
    assert res.pulled == [0, 0, 0]
    assert stim.model.memory[0x10] == 0x42


def test_random_programs_run_deterministically():
    for seed in range(20):
        words, _ = bench.random_program(seed)
        a = run_iss(words, bench.RandomPinStim(seed), cycles=500, prefill=[1, 2, 3, 4], stop_on_halt=False)
        b = run_iss(words, bench.RandomPinStim(seed), cycles=500, prefill=[1, 2, 3, 4], stop_on_halt=False)
        assert a.pout == b.pout and a.poe == b.poe
