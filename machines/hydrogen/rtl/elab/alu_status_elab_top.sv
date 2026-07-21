// Elaboration-only top for `just elaborate`: exposes alu_status_if's fields
// as flat ports so Yosys's `opt` pass has real outputs to keep alive -- see
// regfile_elab_top.sv for the general rationale. Not a cocotb testbench,
// not part of the synthesizable design.
module alu_status_elab_top (
    input  logic        clk_i,
    input  logic        rst_i,
    input  logic [31:0] instruction_i,
    input  logic        overflow_i,
    output logic        latched_overflow_o
);
  import isa_pkg::instr_t;

  alu_status_if bus ();

  assign bus.instruction = instr_t'(instruction_i);
  assign bus.overflow = overflow_i;
  assign latched_overflow_o = bus.latched_overflow;

  alu_status dut (
      .clk_i(clk_i),
      .rst_i(rst_i),
      .bus  (bus)
  );
endmodule
