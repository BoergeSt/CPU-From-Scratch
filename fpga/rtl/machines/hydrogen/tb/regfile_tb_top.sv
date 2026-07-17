// Cocotb top-level wrapper: an interface port on the real sim top level
// isn't supported by Verilator, so this owns the regfile_read_if/
// regfile_write_if instances instead. clk_i/rst_i stay plain ports here so
// cocotb can drive them directly. Test infrastructure only, not part of the
// synthesizable design.
module regfile_tb_top (
    input logic clk_i,
    input logic rst_i
);

  regfile_read_if read1 ();
  regfile_read_if read2 ();
  regfile_write_if write ();

  regfile dut (
      .clk_i(clk_i),
      .rst_i(rst_i),
      .read1(read1),
      .read2(read2),
      .write(write)
  );

endmodule
