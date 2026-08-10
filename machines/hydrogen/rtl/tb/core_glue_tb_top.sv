// Cocotb top-level wrapper: interface ports on the real sim top level
// aren't supported by Verilator, so this owns every interface instance
// instead. core_glue is purely combinational -- no clk_i/rst_i to pass
// through. Test infrastructure only, not part of the synthesizable design.
module core_glue_tb_top;

  regfile_read_if  read_1 ();
  regfile_read_if  read_2 ();
  regfile_read_if  read_3 ();
  regfile_write_if write ();
  alu_if           alu ();
  alu_status_if    alu_status ();
  flow_ctl_if      flow_ctl ();
  bus_if           bus_I ();
  bus_if           bus_D ();

  // Debug-only: current cocotb test phase, decoded by name in the
  // waveform (Verilator emits an FST enum table for typed signals --
  // Surfer decodes it natively, GTKWave via its enum translate filter).
  // All cocotb tests share one simulation run and one continuous waveform
  // dump; this makes a given test's slice of that timeline identifiable
  // directly in the wave instead of cross-referenced from the sim log.
  // Set by test_core_glue.py's phased_test decorator; order here must match
  // PHASE_NAMES there (index + 1, since PHASE_IDLE is 0). Not part of the
  // synthesizable design.
  typedef enum logic [7:0] {
    PHASE_IDLE,
    PHASE_TEST_REGISTER_READ_ADDRESSES_ALWAYS_TAP_FIXED_POSITIONS,
    PHASE_TEST_INSTRUCTION_BROADCAST_TO_EVERY_FUNCTIONAL_UNIT,
    PHASE_TEST_ALU_AND_FLOW_CTL_SHARE_READ1_READ2_VALUE,
    PHASE_TEST_FLOW_CTL_GOTO_VAL_FROM_READ3,
    PHASE_TEST_ALU_STATUS_RECEIVES_LIVE_ALU_OVERFLOW,
    PHASE_TEST_FLOW_CTL_RECEIVES_LATCHED_OVERFLOW,
    PHASE_TEST_I_BUS_FETCHES_AT_PC_EVERY_CYCLE,
    PHASE_TEST_BUS_D_DISABLED_FOR_NON_D_BUS_OPCODES,
    PHASE_TEST_ALU_WRITEBACK,
    PHASE_TEST_ALU_WRITEBACK_SUPPRESSED_ON_ERROR,
    PHASE_TEST_IMM_SET_WRITEBACK,
    PHASE_TEST_FLOW_CTL_AND_RESERVED_NEVER_WRITE,
    PHASE_TEST_ERROR_ON_RESERVED_MAJOR_OPCODE,
    PHASE_TEST_ERROR_ON_ALU_ILLEGAL_ENCODING,
    PHASE_TEST_ALU_ERROR_IGNORED_WHEN_NOT_ALU_INSTRUCTION,
    PHASE_TEST_NO_ERROR_ON_LEGAL_INSTRUCTIONS,
    PHASE_TEST_ERROR_ON_I_BUS_ACK_FAILURE,
    PHASE_TEST_ERROR_ON_D_BUS_ACK_FAILURE,
    PHASE_TEST_LOAD_IMM,
    PHASE_TEST_STORE_IMM,
    PHASE_TEST_LOAD_EFFECTIVE_ADDRESS_AND_WRITEBACK,
    PHASE_TEST_STORE_EFFECTIVE_ADDRESS_AND_NO_WRITEBACK,
    PHASE_TEST_LOAD_EFFECTIVE_ADDRESS_UNDERFLOW_FORCES_ERROR,
    PHASE_TEST_LOAD_EFFECTIVE_ADDRESS_OVERFLOW_FORCES_ERROR,
    PHASE_TEST_STORE_EFFECTIVE_ADDRESS_UNDERFLOW_FORCES_ERROR,
    PHASE_TEST_STORE_EFFECTIVE_ADDRESS_OVERFLOW_FORCES_ERROR
  } test_phase_e;

  test_phase_e dbg_test_phase = PHASE_IDLE;

  core_glue dut (
      .read_1(read_1),
      .read_2(read_2),
      .read_3(read_3),
      .write(write),
      .alu(alu),
      .alu_status(alu_status),
      .flow_ctl(flow_ctl),
      .bus_I(bus_I),
      .bus_D(bus_D)
  );

endmodule
