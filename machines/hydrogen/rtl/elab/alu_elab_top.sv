// Elaboration-only top for `just elaborate`: exposes alu_if's fields as
// flat ports so Yosys's opt pass has real outputs to keep alive (see
// regfile_elab_top.sv for why). Not a cocotb testbench, not part of the
// synthesizable design.
module alu_elab_top (
    input  logic [31:0] instruction_i,
    input  logic [31:0] value1_i,
    input  logic [31:0] value2_i,
    output logic [31:0] result_o,
    output logic        overflow_o,
    output logic        error_o
);
  import isa_pkg::instr_t;

  alu_if bus ();

  assign bus.instruction = instr_t'(instruction_i);
  assign bus.value1 = value1_i;
  assign bus.value2 = value2_i;
  assign result_o = bus.result;
  assign overflow_o = bus.overflow;
  assign error_o = bus.error;

  alu dut (
      .bus(bus)
  );
endmodule
