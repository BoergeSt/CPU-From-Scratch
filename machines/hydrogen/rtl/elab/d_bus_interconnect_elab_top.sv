// Elaboration-only top for `just elaborate`: exposes each bus_if's fields
// as flat ports so Yosys's opt pass has real outputs to keep alive (see
// regfile_elab_top.sv for why). Not a cocotb testbench, not part of the
// synthesizable design.
module d_bus_interconnect_elab_top (
    input  logic [31:0] core_addr_i,
    input  logic [31:0] core_wdata_i,
    input  logic        core_enable_i,
    input  logic        core_we_i,
    output logic [31:0] core_rdata_o,
    output logic        core_ack_o,

    input  logic [31:0] bram_rdata_i,
    input  logic        bram_ack_i,
    output logic [31:0] bram_addr_o,
    output logic [31:0] bram_wdata_o,
    output logic        bram_enable_o,
    output logic        bram_we_o,

    input  logic [31:0] uart0_rdata_i,
    input  logic        uart0_ack_i,
    output logic [31:0] uart0_addr_o,
    output logic [31:0] uart0_wdata_o,
    output logic        uart0_enable_o,
    output logic        uart0_we_o
);
  bus_if core_if ();
  bus_if bram_if ();
  bus_if uart0_if ();

  assign core_if.addr = core_addr_i;
  assign core_if.wdata = core_wdata_i;
  assign core_if.enable = core_enable_i;
  assign core_if.we = core_we_i;
  assign core_rdata_o = core_if.rdata;
  assign core_ack_o = core_if.ack;

  assign bram_if.rdata = bram_rdata_i;
  assign bram_if.ack = bram_ack_i;
  assign bram_addr_o = bram_if.addr;
  assign bram_wdata_o = bram_if.wdata;
  assign bram_enable_o = bram_if.enable;
  assign bram_we_o = bram_if.we;

  assign uart0_if.rdata = uart0_rdata_i;
  assign uart0_if.ack = uart0_ack_i;
  assign uart0_addr_o = uart0_if.addr;
  assign uart0_wdata_o = uart0_if.wdata;
  assign uart0_enable_o = uart0_if.enable;
  assign uart0_we_o = uart0_if.we;

  d_bus_interconnect dut (
      .core_if  (core_if),
      .bram_if  (bram_if),
      .uart0_if (uart0_if)
  );
endmodule
