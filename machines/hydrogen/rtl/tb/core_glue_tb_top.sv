// Cocotb top-level wrapper: interface ports on the real sim top level
// aren't supported by Verilator, so this owns every interface instance
// instead. core_glue is purely combinational -- no clk_i/rst_i to pass
// through. Test infrastructure only, not part of the synthesizable design.
module core_glue_tb_top;

  regfile_read_if  read_1 ();
  regfile_read_if  read_2 ();
  regfile_read_if  read_3 ();
  regfile_write_if write ();
  alu_if           alu ();
  alu_status_if    alu_status ();
  flow_ctl_if      flow_ctl ();
  bus_if           bus_I ();
  bus_if           bus_D ();

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
