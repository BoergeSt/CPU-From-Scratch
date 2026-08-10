// Cocotb top-level wrapper: an interface port on the real sim top level
// isn't supported by Verilator, so this owns the alu_if instance instead.
// Test infrastructure only, not part of the synthesizable design.
module alu_tb_top;

  alu_if bus ();

  // Debug-only: current cocotb test phase, decoded by name in the
  // waveform (Verilator emits an FST enum table for typed signals --
  // Surfer decodes it natively, GTKWave via its enum translate filter).
  // All cocotb tests share one simulation run and one continuous waveform
  // dump; this makes a given test's slice of that timeline identifiable
  // directly in the wave instead of cross-referenced from the sim log.
  // Set by test_alu.py's phased_test decorator; order here must match
  // PHASE_NAMES there (index + 1, since PHASE_IDLE is 0). Not part of the
  // synthesizable design.
  typedef enum logic [7:0] {
    PHASE_IDLE,
    PHASE_TEST_ADD,
    PHASE_TEST_SUB,
    PHASE_TEST_MUL,
    PHASE_TEST_MULH,
    PHASE_TEST_LSHIFT,
    PHASE_TEST_RSHIFT,
    PHASE_TEST_AND,
    PHASE_TEST_OR,
    PHASE_TEST_XOR,
    PHASE_TEST_NOT,
    PHASE_TEST_NAND,
    PHASE_TEST_NOR,
    PHASE_TEST_RESERVED_OPCODES_FLAG_ERROR,
    PHASE_TEST_IMM_AS_SRC1,
    PHASE_TEST_IMM_AS_SRC2,
    PHASE_TEST_IMM_OPERAND_ORDER_PRESERVED_FOR_SUB
  } test_phase_e;

  test_phase_e dbg_test_phase = PHASE_IDLE;

  alu dut (
      .bus(bus)
  );

endmodule
