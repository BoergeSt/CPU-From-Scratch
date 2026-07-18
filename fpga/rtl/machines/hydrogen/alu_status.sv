

module alu_status (
    input logic clk_i,
    input logic rst_i,
    input logic [31:0] opcode_i,
    input logic overflow_i,
    output logic overflow_o
);

  always_ff @(posedge clk_i) begin
    if (rst_i) begin
      overflow_o <= '0;
    end else if (opcode_i[31:28] == 4'h0) begin
      overflow_o <= overflow_i;
    end
  end
endmodule

