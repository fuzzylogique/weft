YOSYS ?= yowasp-yosys
LIB    = pdk/sg13cmos5l_stdcell_typ_1p20V_25C.lib

.PHONY: all pdk clean
all: pdk out/stat_flat.txt docs

pdk: $(LIB)
$(LIB):
	mkdir -p pdk
	curl -sSL -o $@ https://raw.githubusercontent.com/IHP-GmbH/IHP-Open-PDK/dev/ihp-sg13cmos5l/libs.ref/sg13cmos5l_stdcell/lib/sg13cmos5l_stdcell_typ_1p20V_25C.lib

out/stat_flat.txt: synth.ys $(wildcard ../src/*.v) $(LIB)
	mkdir -p out
	$(YOSYS) -q -l out/yosys.log -s synth.ys

docs: out/stat_flat.txt
	python report.py

clean:
	rm -rf out
