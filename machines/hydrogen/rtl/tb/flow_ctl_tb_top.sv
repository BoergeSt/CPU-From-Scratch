// Cocotb top-level wrapper: an interface port on the real sim top level
// isn't supported by Verilator, so this owns the flow_ctl_if instance
// instead. clk_i/rst_i stay plain ports here so cocotb can drive them
// directly. Test infrastructure only, not part of the synthesizable design.
module flow_ctl_tb_top (
    input logic clk_i,
    input logic rst_i
);

  flow_ctl_if bus ();

  // Debug-only: current cocotb test phase, decoded by name in the
  // waveform (Verilator emits an FST enum table for typed signals --
  // Surfer decodes it natively, GTKWave via its enum translate filter).
  // All cocotb tests share one simulation run and one continuous waveform
  // dump; this makes a given test's slice of that timeline identifiable
  // directly in the wave instead of cross-referenced from the sim log.
  // Set by test_flow_ctl.py's phased_test decorator; order here must match
  // PHASE_NAMES there (index + 1, since PHASE_IDLE is 0). Not part of the
  // synthesizable design.
  typedef enum logic [7:0] {
    PHASE_IDLE,
    PHASE_TEST_RESET_SETS_RESET_VECTOR,
    PHASE_TEST_NON_FLOW_CTL_MAJOR_OPCODE_IS_NOP_REGARDLESS_OF_OTHER_BITS,
    PHASE_TEST_FLOW_CTL_NOP_IGNORES_EVERYTHING,
    PHASE_TEST_CONDITIONS,
    PHASE_TEST_VAL2_IGNORED_WHERE_DOCUMENTED,
    PHASE_TEST_TARGET_ABSOLUTE_REGISTER_INDIRECT,
    PHASE_TEST_TARGET_RELATIVE_REGISTER_INDIRECT,
    PHASE_TEST_RELATIVE_TARGET_UNDERFLOW_FORCES_ERROR_VECTOR,
    PHASE_TEST_RELATIVE_TARGET_OVERFLOW_FORCES_ERROR_VECTOR,
    PHASE_TEST_TARGET_ABSOLUTE_IMMEDIATE,
    PHASE_TEST_TARGET_RELATIVE_IMMEDIATE,
    PHASE_TEST_ERROR_FORCES_ERROR_VECTOR,
    PHASE_TEST_ERROR_FORCES_ERROR_VECTOR_EVEN_FOR_NON_FLOW_CTL_MAJOR_OPCODE,
    PHASE_TEST_RESERVED_OP_FORCES_ERROR_VECTOR,
    PHASE_TEST_RESET_OVERRIDES_ERROR_AND_CONDITION
  } test_phase_e;

  test_phase_e dbg_test_phase = PHASE_IDLE;

  flow_ctl dut (
      .clk_i(clk_i),
      .rst_i(rst_i),
      .bus  (bus)
  );

endmodule
