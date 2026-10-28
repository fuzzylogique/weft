/* Weft FIFO: small synchronous FIFO with a count output.
 * SPDX-License-Identifier: Apache-2.0 */
`default_nettype none

module weft_fifo #(
    parameter DEPTH = 4,
    parameter W = 16
) (
    input  wire         clk,
    input  wire         rst,
    input  wire         we,
    input  wire [W-1:0] wd,
    input  wire         re,
    output wire [W-1:0] rd,
    output wire         full,
    output wire         empty,
    output wire [2:0]   count
);
  localparam AW = $clog2(DEPTH);
  reg [W-1:0] mem [0:DEPTH-1];
  reg [AW:0] wp, rp;
  wire [AW:0] diff = wp - rp;
  assign empty = (wp == rp);
  assign full  = (diff == DEPTH[AW:0]);
  assign count = diff[2:0];
  assign rd    = mem[rp[AW-1:0]];
  always @(posedge clk) begin
    if (rst) begin
      wp <= {(AW + 1){1'b0}};
      rp <= {(AW + 1){1'b0}};
    end else begin
      if (we & ~full) begin
        mem[wp[AW-1:0]] <= wd;
        wp <= wp + 1'b1;
      end
      if (re & ~empty) rp <= rp + 1'b1;
    end
  end
endmodule
