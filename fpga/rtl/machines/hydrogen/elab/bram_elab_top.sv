// Elaboration-only top for `just elaborate`: exposes both bus_if ports'
// fields as flat ports so Yosys's opt pass has real outputs to keep alive
// (see regfile_elab_top.sv for why). Not a cocotb testbench, not part of
// the synthesizable design.
module bram_elab_top (
    input  logic        clk_i,
    input  logic [31:0] bus_I_addr_i,
    input  logic [31:0] bus_I_wdata_i,
    input  logic        bus_I_enable_i,
    input  logic        bus_I_we_i,
    output logic [31:0] bus_I_rdata_o,
    output logic        bus_I_ack_o,
    input  logic [31:0] bus_D_addr_i,
    input  logic [31:0] bus_D_wdata_i,
    input  logic        bus_D_enable_i,
    input  logic        bus_D_we_i,
    output logic [31:0] bus_D_rdata_o,
    output logic        bus_D_ack_o
);

  bus_if bus_I ();
  bus_if bus_D ();

  assign bus_I.addr = bus_I_addr_i;
  assign bus_I.wdata = bus_I_wdata_i;
  assign bus_I.enable = bus_I_enable_i;
  assign bus_I.we = bus_I_we_i;
  assign bus_I_rdata_o = bus_I.rdata;
  assign bus_I_ack_o = bus_I.ack;

  assign bus_D.addr = bus_D_addr_i;
  assign bus_D.wdata = bus_D_wdata_i;
  assign bus_D.enable = bus_D_enable_i;
  assign bus_D.we = bus_D_we_i;
  assign bus_D_rdata_o = bus_D.rdata;
  assign bus_D_ack_o = bus_D.ack;

  bram dut (
      .clk_i(clk_i),
      .bus_I(bus_I),
      .bus_D(bus_D)
  );
endmodule
