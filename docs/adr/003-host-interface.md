# ADR-003: SPI target host port on four pins

Date: 2026-10-28 / Status: accepted
Owner: ARCH

Context: Something must load programs and move data through 24 pins. The
demo board's microcontroller is wired to every project pin and can act as the
host. UART (2 pins, slow), SPI target (4 pins, 780 kB/s at clk/8), parallel
(10 pins) and a 2-pin shift chain (load only) were compared in the numbers tab.

Decision: SPI target, mode 0, on `ui_in[7:5]` and `uo_out[7]`, at up to clk/8.
A 128-word program loads in about 0.4 ms. The command set is deliberately
small (status, load, reset, run, stop, step, push, pull, peek) and each
transaction is a single CSn window, so a host needs about 30 lines of code.
STEP and PEEK give full observability from the host, which is both a debug
feature and a demo: a judge can single-step the engine through the pins.

Consequences: Firmware has 5 inputs, 7 outputs and 8 bidirectional pins. The
host lines are readable as input pins 5-7 by firmware but should not be used.
The FIFOs are 4 words deep in each direction; long transfers need host polling.

Revisit if: a protocol needs more than 7 dedicated outputs at once (move the
host port to `uio` pins), or streaming data needs more than about 1 MB/s.
