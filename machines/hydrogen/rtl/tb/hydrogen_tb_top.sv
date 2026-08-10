// Cocotb top-level wrapper: hydrogen has no interface ports of its own
// (only clk_i/rst_i, already plain -- see hydrogen.core's tb_cocotb
// fileset), so unlike every other module's tb_top.sv this isn't needed
// to flatten anything. It exists purely to host the debug-only test-phase
// signal below; every hierarchical reference in test_hydrogen.py (e.g.
// dut.regfile.registers, dut.flow_ctl_if.pc) now goes one level deeper
// through .dut. accordingly. Test infrastructure only, not part of the
// synthesizable design.
module hydrogen_tb_top (
    input logic clk_i,
    input logic rst_i
);

  // Debug-only: current cocotb test phase, decoded by name in the
  // waveform (Verilator emits an FST enum table for typed signals --
  // Surfer decodes it natively, GTKWave via its enum translate filter).
  // All cocotb tests share one simulation run and one continuous waveform
  // dump; this makes a given test's slice of that timeline identifiable
  // directly in the wave instead of cross-referenced from the sim log.
  // Set by test_hydrogen.py's phased_test decorator; order here must
  // match PHASE_NAMES there (index + 1, since PHASE_IDLE is 0). Not part
  // of the synthesizable design.
  typedef enum logic [7:0] {
    PHASE_IDLE,
    PHASE_TEST_RESET_VECTOR_AND_REGISTERS,
    PHASE_TEST_FETCH_DECODE_WRITEBACK_ROUND_TRIP,
    PHASE_TEST_STORE_LOAD_ROUND_TRIP_THROUGH_D_BUS,
    PHASE_TEST_BRANCH_REDIRECTS_REAL_PC
  } test_phase_e;

  test_phase_e dbg_test_phase = PHASE_IDLE;

  hydrogen dut (
      .clk_i(clk_i),
      .rst_i(rst_i)
  );

endmodule
