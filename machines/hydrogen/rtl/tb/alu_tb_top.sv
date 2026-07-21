// Cocotb top-level wrapper: an interface port on the real sim top level
// isn't supported by Verilator, so this owns the alu_if instance instead.
// Test infrastructure only, not part of the synthesizable design.
module alu_tb_top;

  alu_if bus ();

  alu dut (
      .bus(bus)
  );

endmodule
