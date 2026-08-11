// Cocotb top-level wrapper: an interface port on the real sim top level
// isn't supported by Verilator, so this owns the bus_if instance instead.
// clk_i/rst_i/rx_i/tx_o stay plain ports so cocotb can drive/observe them
// directly. Test infrastructure only, not part of the synthesizable design.
module uart_tb_top (
    input  logic clk_i,
    input  logic rst_i,
    input  logic rx_i,
    output logic tx_o
);

  bus_if bus ();

  // Debug-only: current cocotb test phase, decoded by name in the
  // waveform (Verilator emits an FST enum table for typed signals --
  // Surfer decodes it natively, GTKWave via its enum translate filter).
  // All cocotb tests share one simulation run and one continuous waveform
  // dump; this makes a given test's slice of that timeline identifiable
  // directly in the wave instead of cross-referenced from the sim log.
  // Set by test_uart.py's phased_test decorator; order here must match
  // PHASE_NAMES there (index + 1, since PHASE_IDLE is 0). Not part of the
  // synthesizable design.
  typedef enum logic [7:0] {
    PHASE_IDLE,
    PHASE_TEST_ENABLE_REJECTED_WHEN_DIVISOR_ZERO,
    PHASE_TEST_DISABLE_ALWAYS_SUCCEEDS,
    PHASE_TEST_CONTROL_RESET_BIT_RAZ,
    PHASE_TEST_CONTROL_RESERVED_BITS_RAZ_WI,
    PHASE_TEST_SETTINGS_WRITABLE_WHILE_DISABLED,
    PHASE_TEST_SETTINGS_WRITES_IGNORED_WHILE_ENABLED,
    PHASE_TEST_SETTINGS_RESERVED_BITS_RAZ_WI,
    PHASE_TEST_ERRORS_RESERVED_BITS_RAZ_WI,
    PHASE_TEST_ERRORS_W1C_SEMANTICS,
    PHASE_TEST_FILL_REGISTERS_ARE_READ_ONLY,
    PHASE_TEST_RESERVED_ADDRESSES_BUS_ERROR,
    PHASE_TEST_DATA_READ_WHILE_RX_EMPTY,
    PHASE_TEST_TX_PUSH_WHILE_DISABLED_THEN_DRAINS_ON_ENABLE,
    PHASE_TEST_RX_IGNORED_WHILE_DISABLED,
    PHASE_TEST_TX_FIFO_FULL_IGNORE_NEW,
    PHASE_TEST_RX_FIFO_FULL_IGNORE_NEW,
    PHASE_TEST_TX_FIFO_ORDERING,
    PHASE_TEST_RX_FIFO_ORDERING,
    PHASE_TEST_RST_I_CLEARS_EVERYTHING,
    PHASE_TEST_CONTROL_RESET_PRESERVES_SETTINGS,
    PHASE_TEST_TX_BYTE_8N1,
    PHASE_TEST_TX_BYTE_WITH_PARITY,
    PHASE_TEST_TX_BYTE_TWO_STOP_BITS,
    PHASE_TEST_RX_BYTE_8N1,
    PHASE_TEST_RX_BYTE_WITH_PARITY_AND_TWO_STOP_BITS,
    PHASE_TEST_FULL_DUPLEX,
    PHASE_TEST_RX_GLITCH_REJECTED,
    PHASE_TEST_RX_FRAMING_ERROR,
    PHASE_TEST_RX_PARITY_ERROR,
    PHASE_TEST_RX_BACK_TO_BACK_FRAMES_NO_GAP,
    PHASE_TEST_LOOPBACK_100MHZ_DIVISOR_54,
    PHASE_TEST_LOOPBACK_100MHZ_DIVISOR_651
  } test_phase_e;

  test_phase_e dbg_test_phase = PHASE_IDLE;

  uart dut (
      .clk_i(clk_i),
      .rst_i(rst_i),
      .bus  (bus),
      .rx_i (rx_i),
      .tx_o (tx_o)
  );

endmodule
