// Cocotb top-level wrapper for interactive sessions (`just run-interactive`,
// see tb/interactive.py): wraps the real hydrogen DUT plus two "virtual"
// UART phys mirrored off uart.sv's own uart_phy_rx/uart_phy_tx -- one
// decoding uart0's TX line, one serializing bytes onto uart0's RX line --
// so all bit-level oversampling/framing happens natively in Verilator
// instead of being bit-banged cycle-by-cycle from Python. cocotb then only
// synchronizes once per decoded/transmitted byte instead of once per
// simulated clock edge. Both virtual phys track uart0's live settings_q
// directly via hierarchical reference into the DUT -- fine here since this
// is testbench-only wiring with no synthesizable counterpart, unlike
// core_glue/uart's own port-based wiring. Test infrastructure only, not
// part of the synthesizable design.
module hydrogen_interactive_tb_top (
    input  logic       clk_i,
    input  logic       rst_i,
    // Decoded byte + one-cycle strobe from the virtual RX phy, mirroring
    // uart0's TX line.
    output logic [7:0] rx_byte_o,
    output logic       rx_byte_valid_o,
    output logic       rx_frame_error_o,
    output logic       rx_parity_error_o,
    // Byte + one-cycle push strobe into the virtual TX phy's FIFO, which
    // then serializes it onto uart0's RX line at uart0's live bit timing.
    input  logic [7:0] tx_byte_i,
    input  logic       tx_byte_push_i,
    output logic       tx_fifo_full_o
);

  logic uart0_tx_from_dut;
  logic uart0_rx_to_dut;

  // Named "core" rather than "dut" -- cocotb's own `dut` handle is this
  // wrapper module itself, so an inner instance also named "dut" would
  // force confusing dut.dut.* hierarchical paths from interactive.py.
  hydrogen core (
      .clk_i     (clk_i),
      .rst_i     (rst_i),
      .uart0_rx_i(uart0_rx_to_dut),
      .uart0_tx_o(uart0_tx_from_dut)
  );

  // Mirrors core.uart0's own uart_phy_rx instance in uart.sv.
  uart_phy_rx virtual_rx (
      .clk_i         (clk_i),
      .rst_i         (rst_i),
      .enable_i      (1'b1),
      .parity_en_i   (core.uart0.settings_q.parity_en),
      .parity_type_i (core.uart0.settings_q.parity_type),
      .stop_bit_i    (core.uart0.settings_q.stop_bits),
      .divisor_i     (core.uart0.settings_q.divisor),
      .rx_i          (uart0_tx_from_dut),
      .data_o        (rx_byte_o),
      .push_data_o   (rx_byte_valid_o),
      .frame_error_o (rx_frame_error_o),
      .parity_error_o(rx_parity_error_o)
  );

  fifo_read_if #(
      .DataWidth(8),
      .FillWidth(8)
  ) virtual_tx_fifo_read ();

  fifo_write_if #(
      .DataWidth(8),
      .FillWidth(8)
  ) virtual_tx_fifo_write ();

  fifo #(
      .DataWidth(8),
      .FillWidth(8)
  ) virtual_tx_fifo (
      .clk_i(clk_i),
      .rst_i(rst_i),
      .read (virtual_tx_fifo_read),
      .write(virtual_tx_fifo_write)
  );

  assign virtual_tx_fifo_write.enable = tx_byte_push_i;
  assign virtual_tx_fifo_write.data   = tx_byte_i;
  assign tx_fifo_full_o               = virtual_tx_fifo_write.full;

  // Mirrors core.uart0's own uart_phy_tx instance in uart.sv. enable_i
  // tracks FIFO occupancy directly (no separate control-register enable
  // on this side -- the virtual phy has nothing to be disabled from).
  uart_phy_tx virtual_tx (
      .clk_i        (clk_i),
      .rst_i        (rst_i),
      .enable_i     (!virtual_tx_fifo_read.empty),
      .parity_en_i  (core.uart0.settings_q.parity_en),
      .parity_type_i(core.uart0.settings_q.parity_type),
      .stop_bit_i   (core.uart0.settings_q.stop_bits),
      .data_i       (virtual_tx_fifo_read.data),
      .divisor_i    (core.uart0.settings_q.divisor),
      .tx_o         (uart0_rx_to_dut),
      .pull_data_o  (virtual_tx_fifo_read.enable)
  );

endmodule
