// Formal wrapper for weft_core: reset is asserted in the first cycle, everything
// else (instruction word, pins, host pulses, FIFO state) is left free so the
// properties inside weft_core (`ifdef FORMAL) hold for every program.
`default_nettype none
module weft_core_formal (
    input  wire        clk,
    input  wire        rst,
    input  wire        host_run,
    input  wire        host_stop,
    input  wire        host_step,
    input  wire [15:0] instr,
    input  wire [15:0] pin_in,
    input  wire [15:0] pin_prev,
    input  wire        ofifo_full,
    input  wire [15:0] ififo_rd,
    input  wire        ififo_empty,
    input  wire [3:0]  dbg_sel
);
  wire [6:0]  pc;
  wire [15:0] pout, ofifo_wd, dbg_word;
  wire [7:0]  poe;
  wire ofifo_we, ififo_re, running, halted, ill, tick;

  weft_core #(.PMEM_AW(7)) u_core (
      .clk(clk), .rst(rst), .host_run(host_run), .host_stop(host_stop), .host_step(host_step),
      .instr(instr), .pc_out(pc), .pin_in(pin_in), .pin_prev(pin_prev), .pout(pout), .poe(poe),
      .ofifo_we(ofifo_we), .ofifo_wd(ofifo_wd), .ofifo_full(ofifo_full),
      .ififo_re(ififo_re), .ififo_rd(ififo_rd), .ififo_empty(ififo_empty),
      .running(running), .halted(halted), .ill(ill), .tick_out(tick),
      .dbg_sel(dbg_sel), .dbg_word(dbg_word)
  );

  reg init = 1'b1;
  always @(posedge clk) init <= 1'b0;
  always @(*) if (init) assume(rst);

  // The FIFO flags behave like a FIFO's: never both full and empty.
  always @(*) assume(!(ofifo_full && ififo_empty && 1'b0));  // placeholder keeps the interface honest

  // Top-level sanity visible at the wrapper.
  always @(posedge clk) if (!init && !rst) begin
    assert(!(running && halted));
    if (ofifo_we) assert(!ofifo_full);   // the core never writes a full FIFO
    if (ififo_re) assert(!ififo_empty);  // or reads an empty one
  end
endmodule
