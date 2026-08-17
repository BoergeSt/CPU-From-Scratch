module hydrogen (
    input  logic clk_i,
    input  logic rst_i,
    input  logic uart0_rx_i,
    output logic uart0_tx_o
);
  alu_if alu_if ();
  alu_status_if alu_status_if ();
  bus_if bus_I ();
  bus_if bus_D_core ();
  bus_if bus_D_bram ();
  bus_if bus_D_uart0 ();
  flow_ctl_if flow_ctl_if ();
  regfile_read_if read_1 ();
  regfile_read_if read_2 ();
  regfile_read_if read_3 ();
  regfile_write_if write ();

  alu alu (.bus(alu_if));

  alu_status alu_status (
      .clk_i(clk_i),
      .rst_i(rst_i),
      .bus  (alu_status_if)
  );

  bram #(
      .Size(32'h1000)
  ) bram (
      .clk_i(clk_i),
      .bus_I(bus_I),
      .bus_D(bus_D_bram)
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
      .bus_D     (bus_D_core)
  );

  d_bus_interconnect d_bus_interconnect (
      .core_if (bus_D_core),
      .bram_if (bus_D_bram),
      .uart0_if(bus_D_uart0)
  );

  flow_ctl flow_ctl (
      .clk_i(clk_i),
      .rst_i(rst_i),
      .bus  (flow_ctl_if.flow_ctl)
  );

  regfile regfile (
      .clk_i(clk_i),
      .rst_i(rst_i),
      .read1(read_1),
      .read2(read_2),
      .read3(read_3),
      .write(write)
  );

  uart uart0 (
      .clk_i(clk_i),
      .rst_i(rst_i),
      .rx_i (uart0_rx_i),
      .tx_o (uart0_tx_o),
      .bus  (bus_D_uart0)
  );

endmodule
