# Toolchain setup

Everything runs locally except the physical flow (Tiny Tapeout's GitHub
action) and SymbiYosys (the `formal` workflow). On macOS/arm64 Icarus, Yosys
and SymbiYosys are not on conda-forge, so the local simulator is Verilator and
synthesis estimates use the WebAssembly build of Yosys.

```bash
conda create -n jsasic -c conda-forge --override-channels python=3.12 verilator gh make
conda activate jsasic
pip install cocotb==2.0.1 pytest==8.4.2 hypothesis yowasp-yosys cocotb-coverage pyyaml
pip install -e sw
```

Then from the repo root:

| Command | What it does |
| --- | --- |
| `make gen` | regenerate the Verilog ISA constants and `docs/isa.md` from `sw/weft/isa.py` |
| `make asm` | assemble every program in `sw/programs` to `.hex` |
| `make test-sw` | 53 pytest tests: encoding round trips (Hypothesis), ISS semantics, firmware on the ISS with snapshots |
| `make lint` | Verilator `-Wall` lint of the RTL |
| `make sim` | cocotb RTL tests under Verilator (CI uses Icarus like the Tiny Tapeout template) |
| `make synth` | Yosys with the IHP CMOS5L liberty, writes `docs/budget.md` numbers |
| `make formal` | SymbiYosys jobs (needs `sby`; CI runs them) |

cocotb's and Verilator's Makefiles cannot cope with spaces in paths. If the
checkout lives in a folder with spaces (as the original did), run `make sim`
through a symlink and point the build directory somewhere without spaces:

```bash
ln -s "/path/with spaces/weft" ~/weft
cd ~/weft/test && make SIM=verilator SIM_BUILD=/tmp/weft_sim/rtl
```

Zed: open the folder; `.zed/settings.json` installs the Verilog extension and
points basedpyright at the conda env; `.zed/tasks.json` has one task per
command above (cmd-shift-p, "task: spawn").
