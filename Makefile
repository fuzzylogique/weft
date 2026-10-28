# Weft: top-level convenience targets. Tools come from the `jsasic` conda env
# (see docs/setup.md); override PY/VERILATOR/YOSYS if yours live elsewhere.
PY        ?= python
VERILATOR ?= verilator
YOSYS     ?= yowasp-yosys
SIM       ?= verilator

PROGRAMS := $(wildcard sw/programs/*.asm)
HEXES    := $(PROGRAMS:.asm=.hex)

.PHONY: all gen asm test-sw lint sim sim-gl synth formal formal-local check clean

all: gen asm lint test-sw sim

gen:            ## regenerate Verilog ISA constants and docs/isa.md from sw/weft/isa.py
	$(PY) -m weft.gen

asm: $(HEXES)   ## assemble every program in sw/programs

sw/programs/%.hex: sw/programs/%.asm sw/weft/isa.py sw/weft/asm.py
	$(PY) -m weft.asm $< -o $@

test-sw:        ## assembler, ISS and firmware tests (pytest + hypothesis)
	cd sw && $(PY) -m pytest -q

lint:           ## Verilator lint of the RTL
	$(VERILATOR) --lint-only -Wall -Wno-DECLFILENAME --top-module tt_um_fuzzylogique_weft src/*.v

sim:            ## cocotb RTL tests (SIM=verilator locally, icarus in CI)
	cd test && $(MAKE) SIM=$(SIM) && $(PY) -m cocotb_tools.check_results results.xml

sim-gl:         ## cocotb on the gate-level netlist (needs PDK_ROOT and test/gate_level_netlist.v)
	cd test && $(MAKE) GATES=yes && $(PY) -m cocotb_tools.check_results results.xml

synth:          ## Yosys synthesis with the IHP liberty for cell counts and area (synth/README.md)
	$(MAKE) -C synth YOSYS=$(YOSYS)

formal:         ## SymbiYosys proofs (needs sby; CI runs them)
	cd formal && for f in *.sby; do sby -f $$f || exit 1; done

formal-local:   ## the same properties through Yosys's own SAT engine (works with yowasp-yosys)
	formal/run_local.sh $(YOSYS)

check: gen asm  ## fail if generated files were stale
	$(PY) -m weft.gen --check
	git diff --exit-code -- sw/programs/*.hex

clean:
	rm -rf test/sim_build test/results.xml test/tb.fst synth/out formal/*/ sw/.pytest_cache sw/.hypothesis
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
