/* Weft program memory: 2**AW x 16-bit words built from flip-flops.
 * Written by the host port. The read port is registered: the core presents the
 * address of the instruction it executes next (pc_next) and the word arrives
 * at the following edge, so the 2**AW:1 read mux is not in series with the
 * decoder and ALU. A write and a read of the same word at the same edge return
 * the old word; the host loads programs while the core is held in reset.
 * Not reset: the host loader must write every word that will be executed
 * (the reference loader zero-fills, and 0x0000 is NOP).
 * SPDX-License-Identifier: Apache-2.0 */
`default_nettype none

module weft_pmem #(
    parameter AW = 7
) (
    input  wire          clk,
    input  wire          we,
    input  wire [AW-1:0] wa,
    input  wire [15:0]   wd,
    input  wire [AW-1:0] ra,
    output reg  [15:0]   rd
);
  reg [15:0] mem [0:(1 << AW) - 1];
  always @(posedge clk) begin
    if (we) mem[wa] <= wd;
    rd <= mem[ra];
  end
endmodule
