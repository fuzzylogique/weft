# ADR-002: 128 x 16 flip-flop program memory, host loaded

Date: 2026-10-28 / Status: accepted
Owner: ARCH

Context: Storage, not logic, sets the die size. The numbers tab costs a
256x16 program memory at about 60% of the usable area in flops, 35% in latches
and about 5% as an IHP SRAM macro, but the macro is not proven on CMOS5L and
needs power-grid and placement work the team has not done.

Options:
- A. 64 x 16 flops: about 83K µm² hand count (15%). Holds two or three
  protocol programs at once.
- B. 128 x 16 flops: about 166K µm² (30%). Holds three or four programs.
- C. 128 x 16 latches: about 96K µm², but needs a clean write pulse, latch
  timing in OpenSTA, and has no reset.
- D. 256 x 16 SRAM macro: densest, highest integration risk.

Decision: B, flops, as a `PMEM_AW` parameter in the top module so a 64-word
variant is a one-line change. Flops are fully supported by synthesis, timing
and gate-level simulation, which keeps Gate A and C risk low. The memory is
not reset (a reset mux on 2048 flops costs about 18K µm² and the loader
zero-fills instead); the host writes it over SPI.

Consequences: The whole design is budgeted around 215K µm² after the 1.3
planning factor, about 40% of the 549,700 µm² budget at 60% density, leaving
room for the real flow to come in larger. The largest demo program (I2C) uses
66 words. A 128:1 read mux is on the fetch path: about 1.7 ns, acceptable.

Revisit if: the first GDS run reports utilization above 75% (drop to 64 words)
or the organizers confirm SRAM macros work on CMOS5L and a program needs more
than 128 words (consider a 256x16 macro).
