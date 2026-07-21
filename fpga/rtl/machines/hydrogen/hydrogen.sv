module hydrogen (
    input logic clk_i,
    input logic rst_i
);
  flow_ctl_if flow_ctl_if ();
  flow_ctl flow_ctl (
      .clk_i(clk_i),
      .rst_i(rst_i),
      .bus  (flow_ctl_if.flow_ctl)
  );

  alu_if alu_if ();
  alu alu (.bus(alu_if));

  alu_status_if alu_status_if ();
  alu_status alu_status (
      .clk_i(clk_i),
      .rst_i(rst_i),
      .bus  (alu_status_if)
  );

  bus_if bus_I ();
  bus_if bus_D ();

  bram #(
      .Size(32'h1000)
  ) bram (
      .clk_i(clk_i),
      .bus_I(bus_I),
      .bus_D(bus_D)
  );


  regfile_read_if read_1 ();
  regfile_read_if read_2 ();
  regfile_read_if read_3 ();
  regfile_write_if write ();

  regfile regfile (
      .clk_i(clk_i),
      .rst_i(rst_i),
      .read1(read_1),
      .read2(read_2),
      .read3(read_3),
      .write(write)
  );

  core_glue core_glue (
      .read_1    (read_1),
      .read_2    (read_2),
      .read_3    (read_3),
      .write     (write),
      .alu       (alu_if),
      .alu_status(alu_status_if),
      .flow_ctl  (flow_ctl_if),
      .bus_I     (bus_I),
      .bus_D     (bus_D)
  );

endmodule
