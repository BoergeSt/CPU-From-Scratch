// Cocotb top-level wrapper: interface ports on the real sim top level
// aren't supported by Verilator, so this owns every interface instance
// instead. d_bus_interconnect is purely combinational -- no clk_i/rst_i to
// pass through. Test infrastructure only, not part of the synthesizable
// design.
module d_bus_interconnect_tb_top;

  bus_if core_if ();
  bus_if bram_if ();
  bus_if uart0_if ();

  // Debug-only: current cocotb test phase, decoded by name in the
  // waveform (Verilator emits an FST enum table for typed signals --
  // Surfer decodes it natively, GTKWave via its enum translate filter).
  // All cocotb tests share one simulation run and one continuous waveform
  // dump; this makes a given test's slice of that timeline identifiable
  // directly in the wave instead of cross-referenced from the sim log.
  // Set by test_d_bus_interconnect.py's phased_test decorator; order here
  // must match PHASE_NAMES there (index + 1, since PHASE_IDLE is 0). Not
  // part of the synthesizable design.
  typedef enum logic [7:0] {
    PHASE_IDLE,
    PHASE_TEST_BRAM_RANGE_ENABLES_BRAM_ONLY,
    PHASE_TEST_UART_RANGE_ENABLES_UART_ONLY,
    PHASE_TEST_RESERVED_GAP_IS_UNMAPPED,
    PHASE_TEST_PAST_UART_RANGE_IS_UNMAPPED,
    PHASE_TEST_BRAM_ADDRESS_TRANSLATION_IS_IDENTITY,
    PHASE_TEST_UART_ADDRESS_TRANSLATION_IS_LOCAL_3_BIT,
    PHASE_TEST_RESPONSE_MUX_REFLECTS_SELECTED_SLAVE,
    PHASE_TEST_UNMAPPED_RESPONSE_IGNORES_SLAVE_OUTPUTS,
    PHASE_TEST_ENABLE_LOW_SELECTS_NO_SLAVE,
    PHASE_TEST_WDATA_AND_WE_FAN_OUT_TO_EVERY_SLAVE,
    PHASE_TEST_BRAM_UART_BOUNDARY,
    PHASE_TEST_RESERVED_GAP_BOUNDARIES,
    PHASE_TEST_DECODE_INDEPENDENT_OF_WE
  } test_phase_e;

  test_phase_e dbg_test_phase = PHASE_IDLE;

  d_bus_interconnect dut (
      .core_if  (core_if),
      .bram_if  (bram_if),
      .uart0_if (uart0_if)
  );

endmodule
