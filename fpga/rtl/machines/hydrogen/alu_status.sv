

module alu_status
  import isa_pkg::*;
(
    input  logic   clk_i,
    input  logic   rst_i,
    input  instr_t instruction,
    input  logic   overflow_i,
    output logic   overflow_o
);

  always_ff @(posedge clk_i) begin
    if (rst_i) begin
      overflow_o <= '0;
    end else if (instruction.generic.ic == IC_ALU) begin
      overflow_o <= overflow_i;
    end
  end
endmodule

