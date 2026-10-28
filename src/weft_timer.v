/* Weft bit timer: a 16-bit period register and down-counter. After TSET P the
 * tick flag rises every P cycles (P = 0 means 65536). WAITT consumes a tick.
 * Ticks do not queue. The timer only advances while `enable` is high (the core's
 * run/step enable), so STOP freezes it and STEP advances it one cycle.
 * SPDX-License-Identifier: Apache-2.0 */
`default_nettype none

module weft_timer (
    input  wire        clk,
    input  wire        rst,
    input  wire        enable,
    input  wire        tset,
    input  wire        tstop,
    input  wire        consume,
    input  wire [15:0] period_in,
    output reg         tick,
    output reg  [15:0] cnt,
    output reg         run,
    output reg  [15:0] period      // observable for the formal proof; unused by the core
);
  wire new_tick = run & enable & (cnt == 16'd0);
  always @(posedge clk) begin
    if (rst) begin
      period <= 16'd0;
      cnt    <= 16'd0;
      run    <= 1'b0;
      tick   <= 1'b0;
    end else if (tset) begin
      period <= period_in;
      cnt    <= period_in - 16'd1;
      run    <= 1'b1;
      tick   <= 1'b0;
    end else if (tstop) begin
      run  <= 1'b0;
      tick <= 1'b0;
    end else begin
      if (run & enable) cnt <= (cnt == 16'd0) ? (period - 16'd1) : (cnt - 16'd1);
      tick <= (tick & ~consume) | new_tick;
    end
  end
endmodule
