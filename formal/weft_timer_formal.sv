// Proves: after TSET with period PERIOD (and no further TSET/TSTOP/consume),
// the count output walks PERIOD-1 .. 0 and the tick flag rises exactly PERIOD
// cycles after TSET and stays set (ticks are level flags; WAITT consumes them).
// The harness keeps the phase modulo PERIOD and an elapsed count that saturates
// at PERIOD+1, so every property is a finite inductive invariant (an earlier
// version counted cycles in a saturating 16-bit register, which made the
// relation false after 65535 cycles and left k-induction and PDR inconclusive).
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
  reg [15:0] phase;    // (cycles since TSET - 1) mod PERIOD: 0 in the cycle after TSET
  reg [15:0] elapsed;  // cycles since TSET, saturating at PERIOD+1 (the tick cycle)
  always @(posedge clk) begin
    if (rst) begin
      armed   <= 1'b0;
      phase   <= 16'd0;
      elapsed <= 16'd0;
    end else if (tset) begin
      armed   <= 1'b1;
      phase   <= 16'd0;
      elapsed <= 16'd1;
    end else if (armed) begin
      phase   <= (phase == PERIOD - 1) ? 16'd0 : phase + 16'd1;
      if (elapsed != PERIOD + 1) elapsed <= elapsed + 16'd1;
    end
  end
  always @(*) begin
    if (armed) assume(!tset);
    assume(!tstop);
    assume(!consume);
  end

  always @(posedge clk) if (!init && !rst && armed) begin
    assert(run);
    assert(period == PERIOD[15:0]);
    assert(phase < PERIOD);
    // Count output is PERIOD-1 one cycle after TSET and wraps every PERIOD cycles.
    assert(cnt == (PERIOD - 1) - phase);
    // The tick appears exactly PERIOD+1 cycles after TSET fired and stays.
    assert(tick == (elapsed == PERIOD + 1));
  end
  always @(posedge clk) if (!init && !rst) cover(armed && tick && elapsed == PERIOD + 1);
endmodule
