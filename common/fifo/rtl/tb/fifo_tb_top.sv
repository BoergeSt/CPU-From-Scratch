// Cocotb top-level wrapper: interface ports on the real sim top level
// aren't supported by Verilator, so this owns the fifo_write_if/fifo_read_if
// instances instead. clk_i/rst_i stay plain ports so cocotb can drive them
// directly. Uses all three declarations' default DataWidth/FillWidth
// (32/8, i.e. 128 entries) -- fifo.sv now takes FillWidth directly (not a
// separate Size), the same parameter name/value fifo_write_if/fifo_read_if
// already use, so instantiating all three with matching values is just
// "use the shared default everywhere" rather than translating one
// parameter into another; nothing but Verilator's own width checking
// enforces the three declarations actually agree. Test infrastructure
// only, not part of the synthesizable design.
module fifo_tb_top (
    input logic clk_i,
    input logic rst_i
);

  fifo_write_if write ();
  fifo_read_if read ();

  fifo dut (
      .clk_i(clk_i),
      .rst_i(rst_i),
      .read (read),
      .write(write)
  );

endmodule
