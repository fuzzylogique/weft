/* Weft register file: 8 x 16 bits, three read ports (rd, rs, rt fields read
 * in parallel so no decode sits in front of the read mux), one write port.
 * SPDX-License-Identifier: Apache-2.0 */
`default_nettype none

module weft_regfile (
    input  wire        clk,
    input  wire        rst,
    input  wire        we,
    input  wire [2:0]  wa,
    input  wire [15:0] wd,
    input  wire [2:0]  ra,
    input  wire [2:0]  rs,
    input  wire [2:0]  rb,
    output wire [15:0] da,
    output wire [15:0] ds,
    output wire [15:0] db
);
  reg [15:0] r [0:7];
  integer i;
  always @(posedge clk) begin
    if (rst) begin
      for (i = 0; i < 8; i = i + 1) r[i] <= 16'd0;
    end else if (we) begin
      r[wa] <= wd;
    end
  end
  assign da = r[ra];
  assign ds = r[rs];
  assign db = r[rb];
endmodule
