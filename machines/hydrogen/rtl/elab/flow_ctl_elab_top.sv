// Elaboration-only top for `just elaborate`: exposes flow_ctl_if's fields
// as flat ports so Yosys's opt pass has real outputs to keep alive (see
// regfile_elab_top.sv for why). Not a cocotb testbench, not part of the
// synthesizable design.
module flow_ctl_elab_top (
    input  logic        clk_i,
    input  logic        rst_i,
    input  logic [31:0] instruction_i,
    input  logic [31:0] value1_i,
    input  logic [31:0] value2_i,
    input  logic [31:0] goto_val_i,
    input  logic        overflow_i,
    input  logic        error_i,
    output logic [31:0] pc_o
);
  import isa_pkg::instr_t;

  flow_ctl_if bus ();

  assign bus.instruction = instr_t'(instruction_i);
  assign bus.value1 = value1_i;
  assign bus.value2 = value2_i;
  assign bus.goto_val = goto_val_i;
  assign bus.overflow = overflow_i;
  assign bus.error = error_i;
  assign pc_o = bus.pc;

  flow_ctl dut (
      .clk_i(clk_i),
      .rst_i(rst_i),
      .bus  (bus)
  );
endmodule
