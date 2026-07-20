// Cocotb top-level wrapper: interface ports on the real sim top level
// aren't supported by Verilator, so this owns the bus_if instances instead.
// clk_i stays a plain port so cocotb can drive it directly. No rst_i --
// bram has none, see docs/machines/hydrogen/bram.md. Test infrastructure
// only, not part of the synthesizable design.
module bram_tb_top (
    input logic clk_i
);

  bus_if bus_I ();
  bus_if bus_D ();

  bram dut (
      .clk_i(clk_i),
      .bus_I(bus_I),
      .bus_D(bus_D)
  );

endmodule
