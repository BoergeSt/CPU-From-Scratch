// Cocotb top-level wrapper: interface ports on the real sim top level
// aren't supported by Verilator, so this owns the bus_if instances instead.
// clk_i stays a plain port so cocotb can drive it directly. No rst_i --
// bram has none, see machines/hydrogen/docs/bram.md. Test infrastructure
// only, not part of the synthesizable design.
module bram_tb_top (
    input logic clk_i
);

  bus_if bus_I ();
  bus_if bus_D ();

  // Debug-only: current cocotb test phase, decoded by name in the
  // waveform (Verilator emits an FST enum table for typed signals --
  // Surfer decodes it natively, GTKWave via its enum translate filter).
  // All cocotb tests share one simulation run and one continuous waveform
  // dump; this makes a given test's slice of that timeline identifiable
  // directly in the wave instead of cross-referenced from the sim log.
  // Set by test_bram.py's phased_test decorator; order here must match
  // PHASE_NAMES there (index + 1, since PHASE_IDLE is 0). Not part of the
  // synthesizable design.
  typedef enum logic [7:0] {
    PHASE_IDLE,
    PHASE_TEST_WRITE_READ_BACK_VIA_BUS_D,
    PHASE_TEST_BUS_I_SEES_WRITES_MADE_VIA_BUS_D,
    PHASE_TEST_BUS_I_WE_IS_IGNORED,
    PHASE_TEST_DISABLED_PORT_RETURNS_ZERO_RDATA_AND_ACK,
    PHASE_TEST_ACK_BOUNDARY_AT_SIZE,
    PHASE_TEST_OUT_OF_RANGE_READ_RETURNS_ZERO,
    PHASE_TEST_OUT_OF_RANGE_WRITE_HAS_NO_EFFECT,
    PHASE_TEST_BUS_I_AND_BUS_D_INDEPENDENT_SAME_CYCLE,
    PHASE_TEST_WRITE_PULSE_PERSISTS,
    PHASE_TEST_READ_DURING_WRITE_SAME_PORT_SAME_ADDRESS,
    PHASE_TEST_BUS_I_READ_DURING_BUS_D_WRITE_SAME_ADDRESS
  } test_phase_e;

  test_phase_e dbg_test_phase = PHASE_IDLE;

  bram dut (
      .clk_i(clk_i),
      .bus_I(bus_I),
      .bus_D(bus_D)
  );

endmodule
