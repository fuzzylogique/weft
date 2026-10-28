`default_nettype none
module weft_fifo_formal (
    input wire        clk,
    input wire        rst,
    input wire        we,
    input wire [15:0] wd,
    input wire        re
);
  wire [15:0] rd;
  wire        full, empty;
  wire [2:0]  count;
  weft_fifo #(.DEPTH(4), .W(16)) u (
      .clk(clk), .rst(rst), .we(we), .wd(wd), .re(re), .rd(rd), .full(full), .empty(empty), .count(count)
  );

  reg init = 1'b1;
  always @(posedge clk) init <= 1'b0;
  always @(*) if (init) assume(rst);

  // Occupancy model: count writes accepted minus reads accepted.
  reg [2:0] model;
  always @(posedge clk) begin
    if (rst) model <= 3'd0;
    else model <= model + {2'd0, (we & ~full)} - {2'd0, (re & ~empty)};
  end
  always @(posedge clk) if (!init && !rst) begin
    assert(count == model);
    assert(count <= 3'd4);
    assert(empty == (count == 3'd0));
    assert(full == (count == 3'd4));
  end

  // Data integrity: a tagged word written when the FIFO holds `model` words is read
  // out exactly `model` reads later.
  (* anyconst *) reg [15:0] tag;
  reg        tag_in;
  reg [2:0]  ahead;  // words ahead of the tag still to be read
  always @(posedge clk) begin
    if (rst) begin
      tag_in <= 1'b0;
    end else begin
      if (!tag_in && we && !full && wd == tag) begin
        tag_in <= 1'b1;
        ahead  <= model - {2'd0, (re & ~empty)};
      end else if (tag_in && re && !empty) begin
        if (ahead == 3'd0) tag_in <= 1'b0;
        else ahead <= ahead - 3'd1;
      end
    end
  end
  always @(posedge clk) if (!init && !rst && tag_in && ahead == 3'd0 && !empty) assert(rd == tag);
  always @(posedge clk) cover(tag_in && ahead == 3'd0 && re && !empty);
endmodule
