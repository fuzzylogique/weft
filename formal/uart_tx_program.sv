// Harness for the program-level UART proof. The program ROM is generated from
// sw/programs/uart_tx.asm by formal/gen_roms.py with BIT=4. The byte to send is
// an arbitrary constant delivered through the host FIFO interface exactly once.
`default_nettype none
module uart_tx_program (
    input wire clk,
    input wire rst
);
  localparam BIT = 4;  // the per-bit loop is 3 instructions plus WAITT, so 4 cycles is the smallest legal period
  localparam AW  = 4;

  wire [AW-1:0] pc;
  reg  [15:0]   instr;
  always @(*) begin
    case (pc)
`include "uart_tx_rom.vh"
      default: instr = 16'h0000;
    endcase
  end

  (* anyconst *) reg [7:0] data;
  reg  delivered;
  wire ififo_re;
  wire [15:0] pout, ofifo_wd, dbg_word;
  wire [7:0]  poe;
  wire ofifo_we, running, halted, ill, tick;

  reg init = 1'b1;
  always @(posedge clk) init <= 1'b0;
  always @(*) if (init) assume(rst);
  reg started;
  always @(posedge clk) if (rst) started <= 1'b0; else started <= 1'b1;
  wire host_run = !rst && !started;  // RUN in the first cycle after reset

  weft_core #(.PMEM_AW(AW)) u_core (
      .clk(clk), .rst(rst), .host_run(host_run), .host_stop(1'b0), .host_step(1'b0),
      .instr(instr), .pc_out(pc), .pin_in(16'd0), .pin_prev(16'd0), .pout(pout), .poe(poe),
      .ofifo_we(ofifo_we), .ofifo_wd(ofifo_wd), .ofifo_full(1'b0),
      .ififo_re(ififo_re), .ififo_rd({8'd0, data}), .ififo_empty(delivered),
      .running(running), .halted(halted), .ill(ill), .tick_out(tick),
      .dbg_sel(4'd0), .dbg_word(dbg_word)
  );
  always @(posedge clk) if (rst) delivered <= 1'b0; else if (ififo_re) delivered <= 1'b1;

  // Observer on the TX pin (output pin 0).
  wire tx = pout[0];
  reg  tx_q, seen_high, active, done;
  reg  [3:0] bit_idx;
  reg  [7:0] cnt;
  wire [2:0] data_idx = bit_idx[2:0] - 3'd1;  // bit_idx 1..8 -> data[0..7]; 3 bits wide so the select is never out of range (no x bits for the AIGER model)
  wire expected = (bit_idx == 4'd0) ? 1'b0 : (bit_idx <= 4'd8) ? data[data_idx] : 1'b1;
  always @(posedge clk) begin
    if (rst) begin
      tx_q <= 1'b1; seen_high <= 1'b0; active <= 1'b0; done <= 1'b0; bit_idx <= 4'd0; cnt <= 8'd0;
    end else begin
      tx_q <= tx;
      if (tx) seen_high <= 1'b1;
      if (!active) begin
        if (seen_high && tx_q && !tx) begin  // start bit edge
          active <= 1'b1; bit_idx <= 4'd0; cnt <= 8'd1;
        end
      end else if (cnt == BIT - 1) begin
        cnt <= 8'd0;
        bit_idx <= bit_idx + 4'd1;
        if (bit_idx == 4'd9) begin active <= 1'b0; done <= 1'b1; end
      end else begin
        cnt <= cnt + 8'd1;
      end
    end
  end
  always @(posedge clk) if (!init && !rst) begin
    if (active) assert(tx == expected);   // every cycle of every bit carries the right level
    if (done) assert(tx);                 // line idles high afterwards (PULL waits forever)
    assert(!ill);
  end
  // Gated like the asserts so the arbitrary pre-reset state cannot satisfy them;
  // reaching these takes the whole frame, about 62 cycles.
  always @(posedge clk) if (!init && !rst) cover(done);
  always @(posedge clk) if (!init && !rst) cover(done && data == 8'hA5);
endmodule
