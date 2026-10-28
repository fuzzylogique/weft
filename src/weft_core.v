/*
 * Weft protocol engine: the core.
 *
 * One instruction per clock, no pipeline. Fetch (pmem[pc]), decode, execute
 * and write back all happen inside one cycle; see docs/isa.md for the cycle
 * contract. WAIT-class instructions hold the PC (stall) until their condition
 * is true; DELAY stalls imm12 extra cycles. Nothing else ever stalls.
 *
 * SPDX-License-Identifier: Apache-2.0
 * Copyright (c) 2026 Fayez Haque
 */
`default_nettype none

module weft_core #(
    parameter PMEM_AW = 7            // program memory address width (depth = 2**PMEM_AW, max 8)
) (
    input  wire               clk,
    input  wire               rst,       // synchronous, active high
    input  wire               host_run,  // one-cycle pulses from the host port
    input  wire               host_stop,
    input  wire               host_step,
    input  wire [15:0]        instr,     // pmem[pc]
    output wire [PMEM_AW-1:0] pc_out,
    input  wire [15:0]        pin_in,    // synchronized input pins {uio_in, ui_in}
    input  wire [15:0]        pin_prev,  // pin_in one cycle earlier (edge detection)
    output reg  [15:0]        pout,      // output pin registers {uio_out, uo_out}
    output reg  [7:0]         poe,       // output enables for uio
    output wire               ofifo_we,  // core -> host FIFO
    output wire [15:0]        ofifo_wd,
    input  wire               ofifo_full,
    output wire               ififo_re,  // host -> core FIFO
    input  wire [15:0]        ififo_rd,
    input  wire               ififo_empty,
    output reg                running,
    output reg                halted,
    output reg                ill,
    output wire               tick_out,
    input  wire [3:0]         dbg_sel,   // host PEEK selector (registers valid only while stopped)
    output reg  [15:0]        dbg_word
);

  // BEGIN GENERATED ISA (python -m weft.gen; do not edit by hand)
  /* verilator lint_off UNUSEDPARAM */
  localparam [3:0] OP_SYS = 4'd0;
  localparam [3:0] OP_LDI = 4'd1;
  localparam [3:0] OP_ALU = 4'd2;
  localparam [3:0] OP_ADDI = 4'd3;
  localparam [3:0] OP_CMPI = 4'd4;
  localparam [3:0] OP_BR = 4'd5;
  localparam [3:0] OP_DJNZ = 4'd6;
  localparam [3:0] OP_OUT = 4'd7;
  localparam [3:0] OP_IN = 4'd8;
  localparam [3:0] OP_WAIT = 4'd9;
  localparam [3:0] OP_DELAY = 4'd10;
  localparam [3:0] OP_TIMER = 4'd11;
  localparam [3:0] OP_LOGI = 4'd12;
  localparam [3:0] OP_FIFO = 4'd13;
  localparam [3:0] OP_CRC = 4'd14;
  localparam [3:0] OP_CALL = 4'd15;

  localparam [2:0] SYS_NOP = 3'd0;
  localparam [2:0] SYS_HALT = 3'd1;
  localparam [2:0] SYS_RET = 3'd2;

  localparam [2:0] ALU_ADD = 3'd0;
  localparam [2:0] ALU_SUB = 3'd1;
  localparam [2:0] ALU_AND = 3'd2;
  localparam [2:0] ALU_OR = 3'd3;
  localparam [2:0] ALU_XOR = 3'd4;
  localparam [2:0] ALU_SHLC = 3'd5;
  localparam [2:0] ALU_SHRC = 3'd6;
  localparam [2:0] ALU_MOV = 3'd7;

  localparam [2:0] BR_AL = 3'd0;
  localparam [2:0] BR_EQ = 3'd1;
  localparam [2:0] BR_NE = 3'd2;
  localparam [2:0] BR_CS = 3'd3;
  localparam [2:0] BR_CC = 3'd4;
  localparam [2:0] BR_INE = 3'd5;
  localparam [2:0] BR_OUTF = 3'd6;
  localparam [2:0] BR_TICK = 3'd7;

  localparam [2:0] OUT_OUT0 = 3'd0;
  localparam [2:0] OUT_OUT1 = 3'd1;
  localparam [2:0] OUT_OUTC = 3'd2;
  localparam [2:0] OUT_OUTR = 3'd3;
  localparam [2:0] OUT_OE0 = 3'd4;
  localparam [2:0] OUT_OE1 = 3'd5;
  localparam [2:0] OUT_OEC = 3'd6;
  localparam [2:0] OUT_OENC = 3'd7;

  localparam [2:0] IN_INC = 3'd0;
  localparam [2:0] IN_INR = 3'd1;
  localparam [2:0] IN_INALL = 3'd2;

  localparam [2:0] WAIT_WAITP0 = 3'd0;
  localparam [2:0] WAIT_WAITP1 = 3'd1;
  localparam [2:0] WAIT_WAITR = 3'd2;
  localparam [2:0] WAIT_WAITF = 3'd3;
  localparam [2:0] WAIT_WAITT = 3'd4;

  localparam [2:0] TMR_TSET = 3'd0;
  localparam [2:0] TMR_TSTOP = 3'd1;
  localparam [2:0] TMR_RDCYC = 3'd2;
  localparam [2:0] TMR_RDT = 3'd3;

  localparam [0:0] LOGI_ANDI = 1'd0;
  localparam [0:0] LOGI_ORI = 1'd1;

  localparam [2:0] FIFO_PUSH = 3'd0;
  localparam [2:0] FIFO_PULL = 3'd1;

  localparam [2:0] CRC_CRCPOLY = 3'd0;
  localparam [2:0] CRC_CRCINIT = 3'd1;
  localparam [2:0] CRC_CRCIN = 3'd2;
  localparam [2:0] CRC_CRCINR = 3'd3;
  localparam [2:0] CRC_CRCRD = 3'd4;

  localparam [3:0] DBG_R0 = 4'd0;
  localparam [3:0] DBG_R1 = 4'd1;
  localparam [3:0] DBG_R2 = 4'd2;
  localparam [3:0] DBG_R3 = 4'd3;
  localparam [3:0] DBG_R4 = 4'd4;
  localparam [3:0] DBG_R5 = 4'd5;
  localparam [3:0] DBG_R6 = 4'd6;
  localparam [3:0] DBG_R7 = 4'd7;
  localparam [3:0] DBG_PC = 4'd8;
  localparam [3:0] DBG_FLAGS = 4'd9;
  localparam [3:0] DBG_CYC = 4'd10;
  localparam [3:0] DBG_TCNT = 4'd11;
  localparam [3:0] DBG_CRC = 4'd12;
  localparam [3:0] DBG_POUT = 4'd13;
  localparam [3:0] DBG_POE = 4'd14;
  localparam [3:0] DBG_LR = 4'd15;

  localparam [3:0] FLAG_Z = 4'd0;
  localparam [3:0] FLAG_C = 4'd1;
  localparam [3:0] FLAG_TICK = 4'd2;
  localparam [3:0] FLAG_RUNNING = 4'd3;
  localparam [3:0] FLAG_HALTED = 4'd4;
  localparam [3:0] FLAG_ILL = 4'd5;
  localparam [3:0] FLAG_TRUN = 4'd6;

  localparam [7:0] HOST_STATUS = 8'd0;
  localparam [7:0] HOST_LOAD = 8'd1;
  localparam [7:0] HOST_RESET = 8'd2;
  localparam [7:0] HOST_RUN = 8'd3;
  localparam [7:0] HOST_STOP = 8'd4;
  localparam [7:0] HOST_STEP = 8'd5;
  localparam [7:0] HOST_PUSH = 8'd6;
  localparam [7:0] HOST_PULL = 8'd7;
  localparam [7:0] HOST_PEEK = 8'd8;
  localparam [7:0] HOST_VERSION = 8'd1;
  /* verilator lint_on UNUSEDPARAM */
  // END GENERATED ISA

  // ------------------------------------------------------------------ decode
  wire [3:0]  op      = instr[15:12];
  wire [2:0]  f_sub   = instr[11:9];
  wire [2:0]  f_rd    = instr[11:9];
  wire [2:0]  f_rs    = instr[8:6];
  wire [2:0]  f_rt    = instr[5:3];
  wire [2:0]  f_fn    = instr[2:0];
  wire        f_b8    = instr[8];
  wire [7:0]  f_imm8  = instr[7:0];
  wire [8:0]  f_imm9  = instr[8:0];
  wire [11:0] f_imm12 = instr[11:0];
  wire [3:0]  f_pin   = instr[3:0];
  wire [PMEM_AW-1:0] f_target = instr[PMEM_AW-1:0];  // branch targets wrap modulo depth

  wire en = running | host_step;
  reg  stall;
  wire fire = en & ~stall;

  // Register file: port A is rs for ALU/OUT/TIMER/FIFO/CRC, rd otherwise; the
  // host borrows it for PEEK while the core is stopped.
  wire use_rs = (op == OP_ALU) | (op == OP_OUT) | (op == OP_TIMER) | (op == OP_FIFO) | (op == OP_CRC);
  wire [2:0]  rf_ra = en ? (use_rs ? f_rs : f_rd) : dbg_sel[2:0];
  wire [15:0] a, b;
  reg         rf_we_i;
  reg  [2:0]  rf_wa;
  reg  [15:0] rf_wd;
  reg         set_z;

  weft_regfile u_rf (
      .clk(clk), .rst(rst), .we(rf_we_i & fire), .wa(rf_wa), .wd(rf_wd),
      .ra(rf_ra), .rb(f_rt), .da(a), .db(b)
  );

  // Architectural state besides the register file.
  reg [PMEM_AW-1:0] pc, lr;
  reg               z, c;
  reg [15:0]        cyc;
  reg [11:0]        dly;

  assign pc_out = pc;

  // Timer and CRC units.
  reg         tset, tstop, consume;
  wire        tick;
  wire [15:0] tcnt, tperiod;
  wire        trun;
  weft_timer u_tmr (
      .clk(clk), .rst(rst), .enable(en), .tset(tset & fire), .tstop(tstop & fire), .consume(consume & fire),
      .period_in(a), .tick(tick), .cnt(tcnt), .run(trun), .period(tperiod)
  );
  assign tick_out = tick;

  reg         crc_set_poly, crc_set_init, crc_shift_msb, crc_shift_lsb;
  wire [15:0] crc;
  weft_crc u_crc (
      .clk(clk), .rst(rst), .set_poly(crc_set_poly & fire), .set_init(crc_set_init & fire),
      .shift_msb(crc_shift_msb & fire), .shift_lsb(crc_shift_lsb & fire), .din(a), .bit_in(c), .crc(crc)
  );

  // Illegal encodings: undefined sub-field values or reserved bits set.
  wire illegal =
      ((op == OP_SYS)   & (f_sub > SYS_RET))   |
      ((op == OP_IN)    & (f_sub > IN_INALL))  |
      ((op == OP_WAIT)  & (f_sub > WAIT_WAITT)) |
      ((op == OP_TIMER) & (f_sub > TMR_RDT))   |
      ((op == OP_FIFO)  & (f_sub > FIFO_PULL)) |
      ((op == OP_CRC)   & (f_sub > CRC_CRCRD)) |
      (((op == OP_CMPI) | (op == OP_BR) | (op == OP_DJNZ)) & f_b8) |
      ((op == OP_CALL)  & ((f_sub != 3'd0) | f_b8));

  // Arithmetic.
  wire [16:0] add_r  = {1'b0, a} + {1'b0, b};
  wire [16:0] sub_r  = {1'b0, a} - {1'b0, b};
  wire [15:0] sext9  = {{7{f_imm9[8]}}, f_imm9};
  wire [16:0] addi_r = {1'b0, a} + {1'b0, sext9};
  wire [16:0] cmpi_r = {1'b0, a} - {9'b0, f_imm8};
  wire        pin_bit  = pin_in[f_pin];
  wire        prev_bit = pin_prev[f_pin];

  reg br_cond;
  always @(*) begin
    case (f_sub)
      BR_AL:   br_cond = 1'b1;
      BR_EQ:   br_cond = z;
      BR_NE:   br_cond = ~z;
      BR_CS:   br_cond = c;
      BR_CC:   br_cond = ~c;
      BR_INE:  br_cond = ififo_empty;
      BR_OUTF: br_cond = ofifo_full;
      default: br_cond = tick;  // BR_TICK
    endcase
  end

  reg wait_cond;
  always @(*) begin
    case (f_sub)
      WAIT_WAITP0: wait_cond = ~pin_bit;
      WAIT_WAITP1: wait_cond = pin_bit;
      WAIT_WAITR:  wait_cond = pin_bit & ~prev_bit;
      WAIT_WAITF:  wait_cond = ~pin_bit & prev_bit;
      default:     wait_cond = tick;  // WAIT_WAITT
    endcase
  end

  // --------------------------------------------------------------- execute
  reg [PMEM_AW-1:0] pc_n, lr_n;
  reg               z_n, c_n;
  reg               running_n, halted_n, ill_n;
  reg [15:0]        pout_n;
  reg [7:0]         poe_n;
  reg [11:0]        dly_n;
  reg               branch;
  reg               push, pull;

  always @(*) begin
    stall      = 1'b0;
    branch     = 1'b0;
    pc_n       = pc + 1'b1;
    lr_n       = lr;
    z_n        = z;
    c_n        = c;
    running_n  = running;
    halted_n   = halted;
    ill_n      = ill;
    pout_n     = pout;
    poe_n      = poe;
    dly_n      = dly;
    rf_we_i    = 1'b0;
    rf_wa      = f_rd;
    rf_wd      = 16'd0;
    set_z      = 1'b0;
    tset       = 1'b0;
    tstop      = 1'b0;
    consume    = 1'b0;
    crc_set_poly  = 1'b0;
    crc_set_init  = 1'b0;
    crc_shift_msb = 1'b0;
    crc_shift_lsb = 1'b0;
    push       = 1'b0;
    pull       = 1'b0;

    if (illegal) begin
      running_n = 1'b0;
      halted_n  = 1'b1;
      ill_n     = 1'b1;
      pc_n      = pc;
    end else begin
      case (op)
        OP_SYS: begin
          if (f_sub == SYS_HALT) begin
            running_n = 1'b0;
            halted_n  = 1'b1;
          end else if (f_sub == SYS_RET) begin
            pc_n   = lr;
            branch = 1'b1;
          end
        end
        OP_LDI: begin
          rf_we_i = 1'b1;
          set_z   = 1'b1;
          rf_wd   = f_b8 ? {f_imm8, a[7:0]} : {8'd0, f_imm8};
        end
        OP_ALU: begin
          rf_we_i = 1'b1;
          set_z   = 1'b1;
          case (f_fn)
            ALU_ADD:  begin rf_wd = add_r[15:0]; c_n = add_r[16]; end
            ALU_SUB:  begin rf_wd = sub_r[15:0]; c_n = sub_r[16]; end
            ALU_AND:  rf_wd = a & b;
            ALU_OR:   rf_wd = a | b;
            ALU_XOR:  rf_wd = a ^ b;
            ALU_SHLC: begin rf_wd = {a[14:0], c}; c_n = a[15]; end
            ALU_SHRC: begin rf_wd = {c, a[15:1]}; c_n = a[0]; end
            default:  rf_wd = a;  // ALU_MOV
          endcase
        end
        OP_ADDI: begin
          rf_we_i = 1'b1;
          set_z   = 1'b1;
          rf_wd   = addi_r[15:0];
          c_n     = addi_r[16];
        end
        OP_CMPI: begin
          z_n = (cmpi_r[15:0] == 16'd0);
          c_n = cmpi_r[16];
        end
        OP_BR: begin
          if (br_cond) begin
            pc_n   = f_target;
            branch = 1'b1;
          end
        end
        OP_DJNZ: begin
          rf_we_i = 1'b1;
          rf_wd   = a - 16'd1;
          if (rf_wd != 16'd0) begin
            pc_n   = f_target;
            branch = 1'b1;
          end
        end
        OP_OUT: begin
          case (f_sub)
            OUT_OUT0: pout_n[f_pin] = 1'b0;
            OUT_OUT1: pout_n[f_pin] = 1'b1;
            OUT_OUTC: pout_n[f_pin] = c;
            OUT_OUTR: pout_n[f_pin] = a[0];
            default: begin  // OE0, OE1, OEC, OENC: only bidirectional pins 8..15 have an enable
              if (f_pin[3]) begin
                case (f_sub)
                  OUT_OE0: poe_n[f_pin[2:0]] = 1'b0;
                  OUT_OE1: poe_n[f_pin[2:0]] = 1'b1;
                  OUT_OEC: poe_n[f_pin[2:0]] = c;
                  default: poe_n[f_pin[2:0]] = ~c;  // OUT_OENC
                endcase
              end
            end
          endcase
        end
        OP_IN: begin
          case (f_sub)
            IN_INC: c_n = pin_bit;
            IN_INR: begin rf_we_i = 1'b1; set_z = 1'b1; rf_wa = f_rs; rf_wd = {15'd0, pin_bit}; end
            default: begin rf_we_i = 1'b1; set_z = 1'b1; rf_wa = f_rs; rf_wd = pin_in; end  // IN_INALL
          endcase
        end
        OP_WAIT: begin
          stall   = ~wait_cond;
          consume = wait_cond & (f_sub == WAIT_WAITT);
        end
        OP_DELAY: begin
          if (dly == f_imm12) begin
            dly_n = 12'd0;
          end else begin
            stall = 1'b1;
            dly_n = dly + 12'd1;
          end
        end
        OP_TIMER: begin
          case (f_sub)
            TMR_TSET:  tset  = 1'b1;
            TMR_TSTOP: tstop = 1'b1;
            TMR_RDCYC: begin rf_we_i = 1'b1; set_z = 1'b1; rf_wa = f_rs; rf_wd = cyc; end
            default:   begin rf_we_i = 1'b1; set_z = 1'b1; rf_wa = f_rs; rf_wd = tcnt; end  // TMR_RDT
          endcase
        end
        OP_LOGI: begin
          rf_we_i = 1'b1;
          set_z   = 1'b1;
          rf_wd   = (f_b8 == LOGI_ANDI) ? (a & {8'd0, f_imm8}) : (a | {8'd0, f_imm8});
        end
        OP_FIFO: begin
          if (f_sub == FIFO_PUSH) begin
            stall = ofifo_full;
            push  = ~ofifo_full;
          end else begin
            stall   = ififo_empty;
            pull    = ~ififo_empty;
            rf_we_i = 1'b1;
            set_z   = 1'b1;
            rf_wa   = f_rs;
            rf_wd   = ififo_rd;
          end
        end
        OP_CRC: begin
          case (f_sub)
            CRC_CRCPOLY: crc_set_poly  = 1'b1;
            CRC_CRCINIT: crc_set_init  = 1'b1;
            CRC_CRCIN:   crc_shift_msb = 1'b1;
            CRC_CRCINR:  crc_shift_lsb = 1'b1;
            default:     begin rf_we_i = 1'b1; set_z = 1'b1; rf_wa = f_rs; rf_wd = crc; end  // CRC_CRCRD
          endcase
        end
        default: begin  // OP_CALL
          lr_n   = pc + 1'b1;
          pc_n   = f_target;
          branch = 1'b1;
        end
      endcase
      if (rf_we_i & set_z) z_n = (rf_wd == 16'd0);
    end
  end

  assign ofifo_we = push & fire;
  assign ofifo_wd = a;
  assign ififo_re = pull & fire;

  // ------------------------------------------------------------ commit
  always @(posedge clk) begin
    if (rst) begin
      pc      <= {PMEM_AW{1'b0}};
      lr      <= {PMEM_AW{1'b0}};
      z       <= 1'b0;
      c       <= 1'b0;
      running <= 1'b0;
      halted  <= 1'b0;
      ill     <= 1'b0;
      pout    <= 16'd0;
      poe     <= 8'd0;
      cyc     <= 16'd0;
      dly     <= 12'd0;
    end else begin
      if (host_run) begin
        running <= 1'b1;
        halted  <= 1'b0;
      end else if (host_stop) begin
        running <= 1'b0;
      end else if (fire) begin
        running <= running_n;
        halted  <= halted_n;
        ill     <= ill_n;
      end
      if (fire) begin
        pc   <= pc_n;
        lr   <= lr_n;
        z    <= z_n;
        c    <= c_n;
        pout <= pout_n;
        poe  <= poe_n;
      end
      if (en) begin
        cyc <= cyc + 16'd1;
        dly <= dly_n;
      end
    end
  end

  // ------------------------------------------------------------- debug
  wire [15:0] pc_ext = {{(16 - PMEM_AW){1'b0}}, pc};
  wire [15:0] lr_ext = {{(16 - PMEM_AW){1'b0}}, lr};
  always @(*) begin
    case (dbg_sel)
      DBG_PC:    dbg_word = pc_ext;
      DBG_FLAGS: dbg_word = {9'd0, trun, ill, halted, running, tick, c, z};
      DBG_CYC:   dbg_word = cyc;
      DBG_TCNT:  dbg_word = tcnt;
      DBG_CRC:   dbg_word = crc;
      DBG_POUT:  dbg_word = pout;
      DBG_POE:   dbg_word = {8'd0, poe};
      DBG_LR:    dbg_word = lr_ext;
      default:   dbg_word = a;  // DBG_R0..R7 via the register file's port A
    endcase
  end

  wire _unused = &{1'b0, branch, f_imm12, cmpi_r[16], tperiod};

`ifdef FORMAL
  // Properties checked by SymbiYosys (formal/weft_core.sby). Immediate-assertion
  // style, as Yosys supports it. f_past_valid guards the first cycle.
  reg f_past_valid;
  initial f_past_valid = 1'b0;
  always @(posedge clk) f_past_valid <= 1'b1;

  always @(posedge clk) if (f_past_valid && !$past(rst)) begin
    // Running and halted are never both set.
    assert(!(running && halted));
    // Pins change only when an instruction fired.
    if (!$past(fire)) begin
      assert(pout == $past(pout));
      assert(poe == $past(poe));
    end
    // Pins 0..7 never acquire an output enable; OE touches uio only.
    // (poe is 8 bits wide by construction.)
    // A non-wait, non-delay instruction never stalls: PC moves or the core halts.
    if ($past(en) && $past(op) != OP_WAIT && $past(op) != OP_DELAY && $past(op) != OP_FIFO)
      assert($past(fire));
    // DJNZ writes no flags.
    if ($past(fire) && $past(op) == OP_DJNZ) begin
      assert(z == $past(z));
      assert(c == $past(c));
    end
    // A consumed tick is cleared unless a new one arrived the same cycle.
    if ($past(fire) && $past(op) == OP_WAIT && $past(f_sub) == WAIT_WAITT && !($past(trun) && $past(en) && $past(tcnt) == 16'd0))
      assert(!tick);
  end
  // Reachability: a WAITT completes, a branch is taken, a pin write happens.
  always @(posedge clk) begin
    cover(fire && op == OP_WAIT && f_sub == WAIT_WAITT);
    cover(fire && op == OP_BR && br_cond);
    cover(fire && op == OP_OUT);
    cover(halted && ill);
  end
`endif

endmodule
