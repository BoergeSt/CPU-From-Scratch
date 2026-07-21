// Cocotb top-level wrapper: an interface port on the real sim top level
// isn't supported by Verilator, so this owns the alu_status_if instance
// instead. clk_i/rst_i stay plain ports here so cocotb can drive them
// directly. Test infrastructure only, not part of the synthesizable design.
module alu_status_tb_top (
    input logic clk_i,
    input logic rst_i
);

  alu_status_if bus ();

  alu_status dut (
      .clk_i(clk_i),
      .rst_i(rst_i),
      .bus  (bus)
  );

endmodule
