"""Weft: a tiny programmable protocol engine for Tiny Tapeout (IHP CMOS5L).

This package is the software side of the chip:

- :mod:`weft.isa`  the single-source instruction set table (also generates the
  Verilog decode constants and the ISA reference document),
- :mod:`weft.asm`  a two-pass assembler and a disassembler,
- :mod:`weft.iss`  a cycle-accurate instruction-set simulator (the golden model),
- :mod:`weft.protocols`  Python decoders/models for UART, SPI and I2C used to
  check firmware on the ISS and on the RTL,
- :mod:`weft.waves`  an ASCII waveform renderer for snapshot tests.
"""

__version__ = "0.1.0"
