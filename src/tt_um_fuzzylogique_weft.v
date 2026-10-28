/*
 * Weft: a tiny programmable protocol engine. Tiny Tapeout top level.
 *
 * Pins:
 *   ui_in[4:0]   input pins 0..4 for firmware (UART RX on 0, SPI MISO on 1)
 *   ui_in[5]     host SPI SCK      ui_in[6] host SPI MOSI     ui_in[7] host SPI CSn
 *   uo_out[6:0]  output pins 0..6 for firmware (UART TX 0, SPI SCLK/MOSI/CSn 1..3, LED 4)
 *   uo_out[7]    host SPI MISO
 *   uio[7:0]     bidirectional pins 8..15 for firmware (I2C SCL/SDA on 8/9), open drain capable
 *
 * SPDX-License-Identifier: Apache-2.0
 * Copyright (c) 2026 Fayez Haque
 */
`default_nettype none

module tt_um_fuzzylogique_weft (
    input  wire [7:0] ui_in,    // Dedicated inputs
    output wire [7:0] uo_out,   // Dedicated outputs
    input  wire [7:0] uio_in,   // IOs: Input path
    output wire [7:0] uio_out,  // IOs: Output path
    output wire [7:0] uio_oe,   // IOs: Enable path (active high: 0=input, 1=output)
    input  wire       ena,      // always 1 when the design is powered, so you can ignore it
    input  wire       clk,      // clock
    input  wire       rst_n     // reset_n - low to reset
);
  localparam PMEM_AW = 7;  // 128 words of program memory

  wire rst = ~rst_n;

  // Synchronize every input once; the host port and the core share the flops.
  wire [15:0] pin_s, pin_prev;
  weft_sync #(.W(16)) u_sync (
      .clk(clk), .rst(rst), .d({uio_in, ui_in}), .q(pin_s), .q_prev(pin_prev)
  );

  // Host port.
  wire                host_miso;
  wire                pmem_we;
  wire [PMEM_AW-1:0]  pmem_wa;
  wire [15:0]         pmem_wd;
  wire                core_rst_req, core_run, core_stop, core_step;
  wire                ififo_we, ofifo_re;
  wire [15:0]         ififo_wd, ofifo_rd;
  wire                running, halted, ill, tick;
  wire [PMEM_AW-1:0]  pc;
  wire [2:0]          icount, ocount;
  wire                ififo_empty, ififo_full, ofifo_empty, ofifo_full;
  wire [3:0]          dbg_sel;
  wire [15:0]         dbg_word;

  weft_host_spi #(.PMEM_AW(PMEM_AW)) u_host (
      .clk(clk), .rst(rst),
      .sck(pin_s[5]), .mosi(pin_s[6]), .csn(pin_s[7]), .miso(host_miso),
      .pmem_we(pmem_we), .pmem_wa(pmem_wa), .pmem_wd(pmem_wd),
      .core_rst(core_rst_req), .core_run(core_run), .core_stop(core_stop), .core_step(core_step),
      .ififo_we(ififo_we), .ififo_wd(ififo_wd),
      .ofifo_re(ofifo_re), .ofifo_rd(ofifo_rd),
      .running(running), .halted(halted), .ill(ill), .pc(pc),
      .icount(icount), .ocount(ocount), .ififo_empty(ififo_empty), .ofifo_full(ofifo_full),
      .dbg_sel(dbg_sel), .dbg_word(dbg_word)
  );

  wire core_rst = rst | core_rst_req;

  // Program memory.
  wire [15:0] instr;
  weft_pmem #(.AW(PMEM_AW)) u_pmem (
      .clk(clk), .we(pmem_we), .wa(pmem_wa), .wd(pmem_wd), .ra(pc), .rd(instr)
  );

  // FIFOs: host -> core (IN) and core -> host (OUT).
  wire        ififo_re, ofifo_we;
  wire [15:0] ififo_rd, ofifo_wd;
  weft_fifo #(.DEPTH(4), .W(16)) u_ififo (
      .clk(clk), .rst(core_rst), .we(ififo_we), .wd(ififo_wd), .re(ififo_re), .rd(ififo_rd),
      .full(ififo_full), .empty(ififo_empty), .count(icount)
  );
  weft_fifo #(.DEPTH(4), .W(16)) u_ofifo (
      .clk(clk), .rst(core_rst), .we(ofifo_we), .wd(ofifo_wd), .re(ofifo_re), .rd(ofifo_rd),
      .full(ofifo_full), .empty(ofifo_empty), .count(ocount)
  );

  // The core.
  wire [15:0] pout;
  wire [7:0]  poe;
  weft_core #(.PMEM_AW(PMEM_AW)) u_core (
      .clk(clk), .rst(core_rst),
      .host_run(core_run), .host_stop(core_stop), .host_step(core_step),
      .instr(instr), .pc_out(pc),
      .pin_in(pin_s), .pin_prev(pin_prev), .pout(pout), .poe(poe),
      .ofifo_we(ofifo_we), .ofifo_wd(ofifo_wd), .ofifo_full(ofifo_full),
      .ififo_re(ififo_re), .ififo_rd(ififo_rd), .ififo_empty(ififo_empty),
      .running(running), .halted(halted), .ill(ill), .tick_out(tick),
      .dbg_sel(dbg_sel), .dbg_word(dbg_word)
  );

  assign uo_out  = {host_miso, pout[6:0]};  // uo_out[7] is the host MISO
  assign uio_out = pout[15:8];
  assign uio_oe  = poe;

  wire _unused = &{ena, ififo_full, ofifo_empty, tick, pout[7], 1'b0};
endmodule
