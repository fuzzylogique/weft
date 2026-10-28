/* Weft program memory: 2**AW x 16-bit words built from flip-flops.
 * Written by the host port, read combinationally by the core every cycle.
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
    output wire [15:0]   rd
);
  reg [15:0] mem [0:(1 << AW) - 1];
  always @(posedge clk) begin
    if (we) mem[wa] <= wd;
  end
  assign rd = mem[ra];
endmodule
