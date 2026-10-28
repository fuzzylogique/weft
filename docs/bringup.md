# Silicon bring-up plan

The first program to run on silicon is `sw/programs/selftest.asm`. It exercises
the ALU, carry shifts, the CRC unit, the timer and CALL/RET, and pushes `0xC0DE`
to the host if every check passed, or the number of the first failing check.
It is the same program the cocotb suite runs in lockstep against the ISS, so a
pass on silicon means the chip matches the model on every unit it touches.

Steps on the Tiny Tapeout demo board (RP2350, MicroPython SDK):

1. Select the project, set the clock to 50 MHz, release reset.
2. Drive the host SPI lines from the demo board: SCK on `ui_in[5]`, MOSI on
   `ui_in[6]`, CSn on `ui_in[7]`, MISO read from `uo_out[7]`.
3. Send `STATUS`: byte 0 must read `0x01` (alive, stopped). Byte 3 is the host
   version `0x01`.
4. `LOAD` `selftest.hex`, `RESET`, `RUN`, wait 1 ms, `STATUS`: halted set,
   `PULL 1` returns `0xC0DE`. Any other value names the failing check.
5. `LOAD` `blink.hex`, `RUN`: `uo_out[4]` toggles every 100 cycles (2 µs at
   50 MHz, 250 kHz square wave); `PULL` returns cycle stamps 100 apart.
6. `LOAD` `uart_tx.hex`, `RUN`, `PUSH` `0x55`: a USB-UART adapter on `uo_out[0]`
   at 115200 8N1 shows `U`.
7. Loop `uo_out[0]` back to `ui_in[0]` with a jumper and load `uart_rx.hex`
   into a second session (or use the UART adapter) to receive.

Sketch of the host side in MicroPython (untested on hardware; the cocotb driver
in `test/host.py` is the reference implementation):

```python
from machine import Pin
SCK, MOSI, CSN, MISO = Pin(..), Pin(..), Pin(..), Pin(..)   # ui_in[5], ui_in[6], ui_in[7], uo_out[7]

def xfer(tx):
    rx = []
    CSN.value(0)
    for b in tx:
        r = 0
        for i in range(7, -1, -1):
            MOSI.value((b >> i) & 1); SCK.value(1); r = (r << 1) | MISO.value(); SCK.value(0)
        rx.append(r)
    CSN.value(1)
    return rx

def load(words):
    payload = []
    for w in words + [0] * (128 - len(words)):
        payload += [w >> 8, w & 0xFF]
    xfer([0x01, 0] + payload)
```
