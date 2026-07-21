// Elaboration-only top for `just elaborate`: unlike every other module in
// this directory, hydrogen has no interface ports at all -- clk_i/rst_i
// are its only ports, every bus/regfile interface is declared and wired
// internally -- so the usual "give the dut's own ports flat wrappers"
// pattern (see regfile_elab_top.sv) doesn't apply. Instead this taps
// hydrogen's internal interface instances via hierarchical reference and
// exposes the machine's true externally-observable side effects as flat
// output ports: PC/error (flow_ctl_if), register writeback (write), and
// D-bus memory writes (bus_D) -- everything else in the design is in the
// fan-in cone of one of those, so opt's dead-code elimination has real
// sinks to keep the whole machine alive. Not a cocotb testbench, not part
// of the synthesizable design.
module hydrogen_elab_top (
    input  logic        clk_i,
    input  logic        rst_i,
    output logic [31:0] pc_o,
    output logic        error_o,
    output logic [ 2:0] write_addr_o,
    output logic [31:0] write_value_o,
    output logic        write_enable_o,
    output logic [31:0] bus_d_addr_o,
    output logic [31:0] bus_d_wdata_o,
    output logic        bus_d_enable_o,
    output logic        bus_d_we_o
);
  hydrogen dut (
      .clk_i(clk_i),
      .rst_i(rst_i)
  );

  assign pc_o           = dut.flow_ctl_if.pc;
  assign error_o        = dut.flow_ctl_if.error;

  assign write_addr_o   = dut.write.addr;
  assign write_value_o  = dut.write.value;
  assign write_enable_o = dut.write.enable;

  assign bus_d_addr_o   = dut.bus_D.addr;
  assign bus_d_wdata_o  = dut.bus_D.wdata;
  assign bus_d_enable_o = dut.bus_D.enable;
  assign bus_d_we_o     = dut.bus_D.we;
endmodule
