/* Weft CRC/LFSR unit: 16-bit state, programmable polynomial, one bit per
 * shift, MSB-first (CRCIN) or reflected (CRCINR).
 * SPDX-License-Identifier: Apache-2.0 */
`default_nettype none

module weft_crc (
    input  wire        clk,
    input  wire        rst,
    input  wire        set_poly,
    input  wire        set_init,
    input  wire        shift_msb,
    input  wire        shift_lsb,
    input  wire [15:0] din,
    input  wire        bit_in,
    output reg  [15:0] crc
);
  reg [15:0] poly;
  wire fb_m = crc[15] ^ bit_in;
  wire fb_l = crc[0] ^ bit_in;
  always @(posedge clk) begin
    if (rst) begin
      poly <= 16'd0;
      crc  <= 16'd0;
    end else if (set_poly) begin
      poly <= din;
    end else if (set_init) begin
      crc <= din;
    end else if (shift_msb) begin
      crc <= {crc[14:0], 1'b0} ^ (fb_m ? poly : 16'd0);
    end else if (shift_lsb) begin
      crc <= {1'b0, crc[15:1]} ^ (fb_l ? poly : 16'd0);
    end
  end
endmodule
