# Synthesis estimates

`make synth` (from the repo root) runs Yosys with the IHP CMOS5L standard-cell
liberty and writes `synth/out/stat_hier.txt` (per module) and
`synth/out/stat_flat.txt` (whole design), then `report.py` turns them into
`docs/budget.md`. The liberty file is downloaded on first use and is not
committed. These are pre-layout numbers from Yosys+ABC; LibreLane's result in
the Tiny Tapeout `gds` action will be 20% to 50% larger after buffering, clock
tree and hold fixing (see the "numbers" research tab).
