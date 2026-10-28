/*
 * Weft host port: an SPI target (mode 0, MSB first, active-low CSn) that
 * loads program memory, controls the core (reset / run / stop / single-step),
 * moves words through the two FIFOs and peeks at architectural state.
 * See docs/host-interface.md. Inputs must already be synchronized; SCK must be
 * at most clk/8. Transactions may be any length (no byte counter: a LOAD of the
 * whole memory is 258 bytes).
 *
 * SPDX-License-Identifier: Apache-2.0
 */
`default_nettype none

module weft_host_spi #(
    parameter PMEM_AW = 7
) (
    input  wire               clk,
    input  wire               rst,
    input  wire               sck,
    input  wire               mosi,
    input  wire               csn,
    output wire               miso,
    // program memory write port
    output reg                pmem_we,
    output reg  [PMEM_AW-1:0] pmem_wa,
    output reg  [15:0]        pmem_wd,
    // core control, one-cycle pulses
    output reg                core_rst,
    output reg                core_run,
    output reg                core_stop,
    output reg                core_step,
    // host -> core FIFO
    output reg                ififo_we,
    output reg  [15:0]        ififo_wd,
    // core -> host FIFO
    output reg                ofifo_re,
    input  wire [15:0]        ofifo_rd,
    // status
    input  wire               running,
    input  wire               halted,
    input  wire               ill,
    input  wire [PMEM_AW-1:0] pc,
    input  wire [2:0]         icount,
    input  wire [2:0]         ocount,
    input  wire               ififo_empty,
    input  wire               ofifo_full,
    // debug read
    output reg  [3:0]         dbg_sel,
    input  wire [15:0]        dbg_word
);
  localparam [7:0] CMD_STATUS = 8'h00;
  localparam [7:0] CMD_LOAD   = 8'h01;
  localparam [7:0] CMD_RESET  = 8'h02;
  localparam [7:0] CMD_RUN    = 8'h03;
  localparam [7:0] CMD_STOP   = 8'h04;
  localparam [7:0] CMD_STEP   = 8'h05;
  localparam [7:0] CMD_PUSH   = 8'h06;
  localparam [7:0] CMD_PULL   = 8'h07;
  localparam [7:0] CMD_PEEK   = 8'h08;
  localparam [7:0] VERSION    = 8'h01;

  reg       sck_q, csn_q;
  reg [2:0] bitcnt;
  reg [6:0] rx_sr;
  reg [7:0] tx_sr, cmd;
  reg        have_cmd;   // the command byte of this transaction has arrived
  reg        need_arg;   // LOAD: next byte is the address; PEEK: next byte is the selector
  reg        phase;      // data bytes come in pairs: 0 = high byte next, 1 = low byte next
  reg [1:0]  stat_idx;   // STATUS byte rotation
  reg [15:0] word;
  reg        pend_peek;

  wire sck_rise = sck & ~sck_q;
  wire sck_fall = ~sck & sck_q;
  wire csn_fall = ~csn & csn_q;
  wire [7:0] rxb = {rx_sr, mosi};  // the byte being completed on this rising edge

  wire [7:0] status0 = {ofifo_full, ififo_empty, 2'b00, ill, halted, running, 1'b1};
  wire [15:0] pc_ext = {{(16 - PMEM_AW){1'b0}}, pc};
  wire [7:0] status1 = pc_ext[7:0];
  wire [7:0] status2 = {1'b0, ocount, 1'b0, icount};
  reg  [7:0] status_sel;
  always @(*) begin
    case (stat_idx)
      2'd1:    status_sel = status1;
      2'd2:    status_sel = status2;
      2'd3:    status_sel = VERSION;
      default: status_sel = status0;
    endcase
  end

  assign miso = tx_sr[7];

  wire _unused = &{1'b0, pc_ext[15:8]};

  always @(posedge clk) begin
    if (rst) begin
      sck_q <= 1'b0; csn_q <= 1'b1;
      bitcnt <= 3'd0; rx_sr <= 7'd0; tx_sr <= 8'd0; cmd <= 8'd0; word <= 16'd0;
      have_cmd <= 1'b0; need_arg <= 1'b0; phase <= 1'b0; stat_idx <= 2'd0;
      pend_peek <= 1'b0;
      pmem_we <= 1'b0; pmem_wa <= {PMEM_AW{1'b0}}; pmem_wd <= 16'd0;
      core_rst <= 1'b0; core_run <= 1'b0; core_stop <= 1'b0; core_step <= 1'b0;
      ififo_we <= 1'b0; ififo_wd <= 16'd0; ofifo_re <= 1'b0; dbg_sel <= 4'd0;
    end else begin
      sck_q <= sck;
      csn_q <= csn;
      // Default: all pulses low; address advances after a write.
      core_rst <= 1'b0; core_run <= 1'b0; core_stop <= 1'b0; core_step <= 1'b0;
      ififo_we <= 1'b0; ofifo_re <= 1'b0;
      if (pmem_we) pmem_wa <= pmem_wa + 1'b1;
      pmem_we <= 1'b0;
      if (pend_peek) begin
        pend_peek <= 1'b0;
        word      <= dbg_word;
        tx_sr     <= dbg_word[15:8];
      end

      if (csn) begin
        bitcnt   <= 3'd0;
        have_cmd <= 1'b0;
      end
      if (csn_fall) begin
        tx_sr    <= status0;
        bitcnt   <= 3'd0;
        have_cmd <= 1'b0;
        need_arg <= 1'b0;
        phase    <= 1'b0;
        stat_idx <= 2'd1;
      end else if (~csn & sck_rise) begin
        rx_sr  <= rxb[6:0];
        bitcnt <= bitcnt + 3'd1;
        if (bitcnt == 3'd7) begin
          tx_sr <= status0;
          if (!have_cmd) begin
            have_cmd <= 1'b1;
            cmd      <= rxb;
            phase    <= 1'b0;
            case (rxb)
              CMD_RESET: core_rst  <= 1'b1;
              CMD_RUN:   core_run  <= 1'b1;
              CMD_STOP:  core_stop <= 1'b1;
              CMD_STEP:  core_step <= 1'b1;
              CMD_LOAD:  need_arg  <= 1'b1;
              CMD_PEEK:  need_arg  <= 1'b1;
              CMD_PULL: begin
                ofifo_re <= 1'b1;
                word     <= ofifo_rd;
                tx_sr    <= ofifo_rd[15:8];
              end
              default: ;
            endcase
          end else begin
            case (cmd)
              CMD_STATUS: begin
                tx_sr    <= status_sel;
                stat_idx <= stat_idx + 2'd1;
              end
              CMD_LOAD: begin
                if (need_arg) begin
                  pmem_wa  <= rxb[PMEM_AW-1:0];
                  need_arg <= 1'b0;
                end else if (!phase) begin
                  word[15:8] <= rxb;
                  phase      <= 1'b1;
                end else begin
                  pmem_we <= 1'b1;
                  pmem_wd <= {word[15:8], rxb};
                  phase   <= 1'b0;
                end
              end
              CMD_PUSH: begin
                if (!phase) begin
                  word[15:8] <= rxb;
                  phase      <= 1'b1;
                end else begin
                  ififo_we <= 1'b1;
                  ififo_wd <= {word[15:8], rxb};
                  phase    <= 1'b0;
                end
              end
              CMD_PULL: begin
                if (!phase) begin
                  tx_sr <= word[7:0];
                  phase <= 1'b1;
                end else begin
                  ofifo_re <= 1'b1;
                  word     <= ofifo_rd;
                  tx_sr    <= ofifo_rd[15:8];
                  phase    <= 1'b0;
                end
              end
              CMD_PEEK: begin
                if (need_arg) begin
                  dbg_sel   <= rxb[3:0];
                  pend_peek <= 1'b1;
                  need_arg  <= 1'b0;
                end else if (!phase) begin
                  tx_sr <= word[7:0];
                  phase <= 1'b1;
                end else begin
                  pend_peek <= 1'b1;
                  phase     <= 1'b0;
                end
              end
              default: ;
            endcase
          end
        end
      end else if (~csn & sck_fall & (bitcnt != 3'd0)) begin
        tx_sr <= {tx_sr[6:0], 1'b0};
      end
    end
  end
endmodule
