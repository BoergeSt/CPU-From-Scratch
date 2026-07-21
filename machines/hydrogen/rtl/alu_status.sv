

module alu_status (
    input logic                    clk_i,
    input logic                    rst_i,
          alu_status_if.alu_status bus
);

  import isa_pkg::IC_ALU;

  always_ff @(posedge clk_i) begin
    if (rst_i) begin
      bus.latched_overflow <= '0;
    end else if (bus.instruction.generic.ic == IC_ALU) begin
      bus.latched_overflow <= bus.overflow;
    end
  end
endmodule

