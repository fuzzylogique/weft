/* Two-flop input synchronizer with a third stage for edge detection.
 * SPDX-License-Identifier: Apache-2.0 */
`default_nettype none

module weft_sync #(
    parameter W = 16
) (
    input  wire         clk,
    input  wire         rst,
    input  wire [W-1:0] d,
    output reg  [W-1:0] q,       // what instructions read this cycle
    output reg  [W-1:0] q_prev   // q one cycle earlier
);
  reg [W-1:0] s1;
  always @(posedge clk) begin
    if (rst) begin
      s1     <= {W{1'b0}};
      q      <= {W{1'b0}};
      q_prev <= {W{1'b0}};
    end else begin
      s1     <= d;
      q      <= s1;
      q_prev <= q;
    end
  end
endmodule
