// Proves: after TSET with period PERIOD (and no further TSET/TSTOP/consume),
// the count output walks PERIOD-1 .. 0 and the tick flag rises exactly PERIOD
// cycles after TSET and stays set (ticks are level flags; WAITT consumes them).
`default_nettype none
module weft_timer_formal #(
    parameter PERIOD = 3
) (
    input wire clk,
    input wire rst,
    input wire tset,
    input wire tstop,
    input wire consume
);
  wire        tick, run;
  wire [15:0] cnt, period;
  weft_timer u (
      .clk(clk), .rst(rst), .enable(1'b1), .tset(tset), .tstop(tstop), .consume(consume),
      .period_in(PERIOD[15:0]), .tick(tick), .cnt(cnt), .run(run), .period(period)
  );

  reg init = 1'b1;
  always @(posedge clk) init <= 1'b0;
  always @(*) if (init) assume(rst);

  // Scenario: exactly one TSET, then hands off.
  reg armed;
  reg [15:0] since;  // cycles since TSET fired (1 in the cycle after it), saturating
  always @(posedge clk) begin
    if (rst) begin
      armed <= 1'b0;
      since <= 16'd0;
    end else if (tset) begin
      armed <= 1'b1;
      since <= 16'd1;  // the cycle after TSET is "since 1": cnt reads PERIOD-1 there
    end else if (armed && since != 16'hFFFF) begin
      since <= since + 16'd1;
    end
  end
  always @(*) begin
    if (armed) assume(!tset);
    assume(!tstop);
    assume(!consume);
  end

  always @(posedge clk) if (!init && !rst && armed) begin
    assert(run);
    assert(period == PERIOD[15:0]);  // strengthening invariant for k-induction
    // Count output is PERIOD-1 one cycle after TSET and wraps every PERIOD cycles.
    assert(cnt == (PERIOD - 1) - ((since - 1) % PERIOD));
    // The tick appears exactly PERIOD+1 cycles after TSET fired and stays.
    assert(tick == (since >= PERIOD + 1));
  end
  always @(posedge clk) cover(armed && tick && since == PERIOD + 1);
endmodule
