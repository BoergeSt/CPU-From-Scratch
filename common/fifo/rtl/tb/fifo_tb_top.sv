// Cocotb top-level wrapper: interface ports on the real sim top level
// aren't supported by Verilator, so this owns the fifo_write_if/fifo_read_if
// instances instead. clk_i/rst_i stay plain ports so cocotb can drive them
// directly. Uses all three declarations' default DataWidth/FillWidth
// (32/8, i.e. 128 entries) -- fifo.sv now takes FillWidth directly (not a
// separate Size), the same parameter name/value fifo_write_if/fifo_read_if
// already use, so instantiating all three with matching values is just
// "use the shared default everywhere" rather than translating one
// parameter into another; nothing but Verilator's own width checking
// enforces the three declarations actually agree. Test infrastructure
// only, not part of the synthesizable design.
module fifo_tb_top (
    input logic clk_i,
    input logic rst_i
);

  fifo_write_if write ();
  fifo_read_if read ();

  // Debug-only: current cocotb test phase, decoded by name in the
  // waveform (Verilator emits an FST enum table for typed signals --
  // Surfer decodes it natively, GTKWave via its enum translate filter).
  // All cocotb tests share one simulation run and one continuous waveform
  // dump; this makes a given test's slice of that timeline identifiable
  // directly in the wave instead of cross-referenced from the sim log.
  // Set by test_fifo.py's phased_test decorator; order here must match
  // PHASE_NAMES there (index + 1, since PHASE_IDLE is 0). Not part of the
  // synthesizable design.
  typedef enum logic [7:0] {
    PHASE_IDLE,
    PHASE_TEST_RESET_STATE,
    PHASE_TEST_DATA_O_ZERO_WHEN_IDLE,
    PHASE_TEST_SINGLE_WRITE_THEN_READ,
    PHASE_TEST_FIFO_ORDERING,
    PHASE_TEST_FILL_TO_FULL,
    PHASE_TEST_DRAIN_TO_EMPTY,
    PHASE_TEST_OVERFLOW_WRITE_WHILE_FULL,
    PHASE_TEST_UNDERFLOW_READ_WHILE_EMPTY,
    PHASE_TEST_SIMULTANEOUS_WE_RE_ON_EMPTY,
    PHASE_TEST_SIMULTANEOUS_WE_RE_ON_FULL,
    PHASE_TEST_SIMULTANEOUS_WE_RE_MIDRANGE,
    PHASE_TEST_OVERFLOW_UNDERFLOW_ARE_COMBINATIONAL_NOT_STICKY,
    PHASE_TEST_RESET_MID_OPERATION,
    PHASE_TEST_WRAPAROUND
  } test_phase_e;

  test_phase_e dbg_test_phase = PHASE_IDLE;

  fifo dut (
      .clk_i(clk_i),
      .rst_i(rst_i),
      .read (read),
      .write(write)
  );

endmodule
