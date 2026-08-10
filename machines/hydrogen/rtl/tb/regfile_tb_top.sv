// Cocotb top-level wrapper: an interface port on the real sim top level
// isn't supported by Verilator, so this owns the regfile_read_if/
// regfile_write_if instances instead. clk_i/rst_i stay plain ports here so
// cocotb can drive them directly. Test infrastructure only, not part of the
// synthesizable design.
module regfile_tb_top (
    input logic clk_i,
    input logic rst_i
);

  regfile_read_if read1 ();
  regfile_read_if read2 ();
  regfile_read_if read3 ();
  regfile_write_if write ();

  // Debug-only: current cocotb test phase, decoded by name in the
  // waveform (Verilator emits an FST enum table for typed signals --
  // Surfer decodes it natively, GTKWave via its enum translate filter).
  // All cocotb tests share one simulation run and one continuous waveform
  // dump; this makes a given test's slice of that timeline identifiable
  // directly in the wave instead of cross-referenced from the sim log.
  // Set by test_regfile.py's phased_test decorator; order here must match
  // PHASE_NAMES there (index + 1, since PHASE_IDLE is 0). Not part of the
  // synthesizable design.
  typedef enum logic [7:0] {
    PHASE_IDLE,
    PHASE_TEST_RESET_CLEARS_ALL_REGISTERS,
    PHASE_TEST_RESET_OVERRIDES_WRITES_AND_SIMULTANEOUS_WRITE,
    PHASE_TEST_WRITE_READ_BACK_ALL_REGISTERS_VIA_READ1,
    PHASE_TEST_WRITE_READ_BACK_ALL_REGISTERS_VIA_READ2,
    PHASE_TEST_WRITE_READ_BACK_ALL_REGISTERS_VIA_READ3,
    PHASE_TEST_READ_PORTS_INDEPENDENT_DIFFERENT_ADDRESSES,
    PHASE_TEST_READ_PORTS_AGREE_SAME_ADDRESS,
    PHASE_TEST_WRITE_DOES_NOT_DISTURB_OTHER_REGISTERS,
    PHASE_TEST_ENABLE_LOW_HAS_NO_EFFECT,
    PHASE_TEST_WRITE_PULSE_PERSISTS,
    PHASE_TEST_READ_DURING_WRITE_SAME_ADDRESS
  } test_phase_e;

  test_phase_e dbg_test_phase = PHASE_IDLE;

  regfile dut (
      .clk_i(clk_i),
      .rst_i(rst_i),
      .read1(read1),
      .read2(read2),
      .read3(read3),
      .write(write)
  );

endmodule
