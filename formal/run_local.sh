#!/bin/sh
# Run the formal jobs with Yosys's built-in SAT engine (no SymbiYosys needed).
# `cover` statements are stripped (sat cannot model them); CI's sby run keeps them.
# Usage: formal/run_local.sh [yosys-binary]   (default: yowasp-yosys)
set -u
YOSYS=${1:-yowasp-yosys}
cd "$(dirname "$0")" && mkdir -p out
SRC=../src
status=0
run() {
  name=$1; shift
  printf '%-10s ' "$name"
  if $YOSYS -q -l "out/$name.log" -p "$*" > "out/$name.run" 2>&1; then
    grep -E "SUCCESS" "out/$name.log" | tail -n 1
  else
    status=1
    grep -E "FAIL|Reached maximum|ERROR" "out/$name.log" | tail -n 1
  fi
}
PRE="flatten; memory_map; async2sync; chformal -cover -remove;"
run timer    "read_verilog -formal -sv $SRC/weft_timer.v weft_timer_formal.sv; chparam -set PERIOD 3 weft_timer_formal; prep -top weft_timer_formal; $PRE sat -tempinduct -prove-asserts -set-assumes -seq 1 -maxsteps 12 -verify"
run fifo     "read_verilog -formal -sv $SRC/weft_fifo.v weft_fifo_formal.sv; prep -top weft_fifo_formal; $PRE sat -tempinduct -prove-asserts -set-assumes -seq 1 -maxsteps 10 -verify"
run core_bmc "read_verilog -formal -sv $SRC/weft_regfile.v $SRC/weft_timer.v $SRC/weft_crc.v $SRC/weft_core.v weft_core_formal.sv; prep -top weft_core_formal; $PRE sat -prove-asserts -set-assumes -seq 8 -verify"
run uart_bmc "read_verilog -formal -sv $SRC/weft_regfile.v $SRC/weft_timer.v $SRC/weft_crc.v $SRC/weft_core.v uart_tx_program.sv; prep -top uart_tx_program; $PRE sat -prove-asserts -set-assumes -seq 62 -verify"
exit $status
