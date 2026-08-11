// Elaboration-only top for `just elaborate`: exposes bus's fields as
// flat ports so Yosys's opt pass has real outputs to keep alive (see
// regfile_elab_top.sv for why). Not a cocotb testbench, not part of the
// synthesizable design.
module uart_elab_top (
    input  logic        clk_i,
    input  logic        rst_i,
    input  logic [31:0] bus_addr_i,
    input  logic [31:0] bus_wdata_i,
    input  logic        bus_enable_i,
    input  logic        bus_we_i,
    output logic [31:0] bus_rdata_o,
    output logic        bus_ack_o,
    input  logic        rx_i,
    output logic        tx_o
);

  bus_if bus ();

  assign bus.addr = bus_addr_i;
  assign bus.wdata = bus_wdata_i;
  assign bus.enable = bus_enable_i;
  assign bus.we = bus_we_i;
  assign bus_rdata_o = bus.rdata;
  assign bus_ack_o = bus.ack;

  uart dut (
      .clk_i(clk_i),
      .rst_i(rst_i),
      .bus  (bus),
      .rx_i (rx_i),
      .tx_o (tx_o)
  );
endmodule
