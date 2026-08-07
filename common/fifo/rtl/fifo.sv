module fifo #(
    parameter  int unsigned DataWidth = 32,
    parameter  int unsigned FillWidth = 8,
    localparam int unsigned AddrWidth = FillWidth - 1,
    localparam int unsigned Size      = 2 ** AddrWidth
) (
    input logic              clk_i,
    input logic              rst_i,
          fifo_read_if.fifo  read,
          fifo_write_if.fifo write
);

  logic [DataWidth-1:0] mem[Size];
  logic [AddrWidth-1:0] read_ptr, write_ptr;

  logic [FillWidth-1:0] fill;

  assign read.fill = fill;
  assign write.fill = fill;

  assign write_ptr = AddrWidth'(FillWidth'(read_ptr) + fill);

  assign write.full = fill == FillWidth'(Size);
  assign write.overflow = write.enable && write.full;

  assign read.empty = fill == '0;
  assign read.underflow = read.enable && read.empty;

  assign read.data = read.enable && !read.empty ? mem[read_ptr] : '0;

  always_ff @(posedge clk_i) begin
    if (rst_i) begin
      read_ptr <= '0;
      fill <= '0;
    end else begin
      automatic logic write_accept = write.enable && !write.full;
      automatic logic read_accept = read.enable && !read.empty;

      if (write_accept) mem[write_ptr] <= write.data;
      if (read_accept) read_ptr <= read_ptr + 1;

      if (write_accept && !read_accept) fill <= fill + 1'b1;
      if (read_accept && !write_accept) fill <= fill - 1'b1;
    end
  end


endmodule
