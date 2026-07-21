// Elaboration-only top for `just elaborate`: exposes core_glue's 9
// interface ports as flat ports so Yosys's `opt` pass has real outputs to
// keep alive -- see regfile_elab_top.sv for the general rationale. core_glue
// is purely combinational, so unlike alu/flow_ctl/regfile's elab tops there
// is no clk_i/rst_i to carry through. Not a cocotb testbench, not part of
// the synthesizable design.
module core_glue_elab_top (
    output logic [2:0]  read_1_addr_o,
    input  logic [31:0] read_1_value_i,
    output logic [2:0]  read_2_addr_o,
    input  logic [31:0] read_2_value_i,
    output logic [2:0]  read_3_addr_o,
    input  logic [31:0] read_3_value_i,

    output logic [2:0]  write_addr_o,
    output logic [31:0] write_value_o,
    output logic        write_enable_o,

    output logic [31:0] alu_instruction_o,
    output logic [31:0] alu_value1_o,
    output logic [31:0] alu_value2_o,
    input  logic [31:0] alu_result_i,
    input  logic        alu_overflow_i,
    input  logic        alu_error_i,

    output logic [31:0] alu_status_instruction_o,
    output logic        alu_status_overflow_o,
    input  logic        alu_status_latched_overflow_i,

    output logic [31:0] flow_ctl_instruction_o,
    output logic [31:0] flow_ctl_value1_o,
    output logic [31:0] flow_ctl_value2_o,
    output logic [31:0] flow_ctl_goto_val_o,
    output logic        flow_ctl_overflow_o,
    output logic        flow_ctl_error_o,
    input  logic [31:0] flow_ctl_pc_i,

    output logic [31:0] bus_I_addr_o,
    output logic [31:0] bus_I_wdata_o,
    output logic        bus_I_enable_o,
    output logic        bus_I_we_o,
    input  logic [31:0] bus_I_rdata_i,
    input  logic        bus_I_ack_i,

    output logic [31:0] bus_D_addr_o,
    output logic [31:0] bus_D_wdata_o,
    output logic        bus_D_enable_o,
    output logic        bus_D_we_o,
    input  logic [31:0] bus_D_rdata_i,
    input  logic        bus_D_ack_i
);
  regfile_read_if  read_1 ();
  regfile_read_if  read_2 ();
  regfile_read_if  read_3 ();
  regfile_write_if write ();
  alu_if           alu ();
  alu_status_if    alu_status ();
  flow_ctl_if      flow_ctl ();
  bus_if           bus_I ();
  bus_if           bus_D ();

  assign read_1_addr_o = read_1.addr;
  assign read_1.value = read_1_value_i;
  assign read_2_addr_o = read_2.addr;
  assign read_2.value = read_2_value_i;
  assign read_3_addr_o = read_3.addr;
  assign read_3.value = read_3_value_i;

  assign write_addr_o = write.addr;
  assign write_value_o = write.value;
  assign write_enable_o = write.enable;

  assign alu_instruction_o = alu.instruction;
  assign alu_value1_o = alu.value1;
  assign alu_value2_o = alu.value2;
  assign alu.result = alu_result_i;
  assign alu.overflow = alu_overflow_i;
  assign alu.error = alu_error_i;

  assign alu_status_instruction_o = alu_status.instruction;
  assign alu_status_overflow_o = alu_status.overflow;
  assign alu_status.latched_overflow = alu_status_latched_overflow_i;

  assign flow_ctl_instruction_o = flow_ctl.instruction;
  assign flow_ctl_value1_o = flow_ctl.value1;
  assign flow_ctl_value2_o = flow_ctl.value2;
  assign flow_ctl_goto_val_o = flow_ctl.goto_val;
  assign flow_ctl_overflow_o = flow_ctl.overflow;
  assign flow_ctl_error_o = flow_ctl.error;
  assign flow_ctl.pc = flow_ctl_pc_i;

  assign bus_I_addr_o = bus_I.addr;
  assign bus_I_wdata_o = bus_I.wdata;
  assign bus_I_enable_o = bus_I.enable;
  assign bus_I_we_o = bus_I.we;
  assign bus_I.rdata = bus_I_rdata_i;
  assign bus_I.ack = bus_I_ack_i;

  assign bus_D_addr_o = bus_D.addr;
  assign bus_D_wdata_o = bus_D.wdata;
  assign bus_D_enable_o = bus_D.enable;
  assign bus_D_we_o = bus_D.we;
  assign bus_D.rdata = bus_D_rdata_i;
  assign bus_D.ack = bus_D_ack_i;

  core_glue dut (
      .read_1(read_1),
      .read_2(read_2),
      .read_3(read_3),
      .write(write),
      .alu(alu),
      .alu_status(alu_status),
      .flow_ctl(flow_ctl),
      .bus_I(bus_I),
      .bus_D(bus_D)
  );
endmodule
