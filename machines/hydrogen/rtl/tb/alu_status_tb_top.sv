// Cocotb top-level wrapper: an interface port on the real sim top level
// isn't supported by Verilator, so this owns the alu_status_if instance
// instead. clk_i/rst_i stay plain ports here so cocotb can drive them
// directly. Test infrastructure only, not part of the synthesizable design.
module alu_status_tb_top (
    input logic clk_i,
    input logic rst_i
);

  alu_status_if bus ();

  // Debug-only: current cocotb test phase, decoded by name in the
  // waveform (Verilator emits an FST enum table for typed signals --
  // Surfer decodes it natively, GTKWave via its enum translate filter).
  // All cocotb tests share one simulation run and one continuous waveform
  // dump; this makes a given test's slice of that timeline identifiable
  // directly in the wave instead of cross-referenced from the sim log.
  // Set by test_alu_status.py's phased_test decorator; order here must match
  // PHASE_NAMES there (index + 1, since PHASE_IDLE is 0). Not part of the
  // synthesizable design.
  typedef enum logic [7:0] {
    PHASE_IDLE,
    PHASE_TEST_RESET_CLEARS_OVERFLOW,
    PHASE_TEST_ALU_CYCLE_CAPTURES_OVERFLOW_I,
    PHASE_TEST_NON_ALU_CYCLE_HOLDS_PREVIOUS_VALUE,
    PHASE_TEST_NON_ALU_MAJOR_OPCODE_IGNORES_OVERFLOW_I_REGARDLESS_OF_VALUE,
    PHASE_TEST_CONSECUTIVE_ALU_CYCLES_TRACK_LIVE_VALUE,
    PHASE_TEST_RESET_OVERRIDES_CAPTURE
  } test_phase_e;

  test_phase_e dbg_test_phase = PHASE_IDLE;

  alu_status dut (
      .clk_i(clk_i),
      .rst_i(rst_i),
      .bus  (bus)
  );

endmodule
