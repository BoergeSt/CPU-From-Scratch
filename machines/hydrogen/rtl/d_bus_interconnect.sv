module d_bus_interconnect (
    bus_if.slave  core_if,
    bus_if.master bram_if,
    bus_if.master uart0_if
);

  localparam int unsigned BramHighAddr = 'hFFFF;

  localparam int unsigned Uart0LowAddr = 'h10100;
  localparam int unsigned Uart0Mask = 'b111;
  localparam int unsigned Uart0HighAddr = Uart0LowAddr + Uart0Mask;

  logic [31:0] addr;
  logic [31:0] wdata;
  logic [31:0] rdata;
  logic we;
  logic enable;
  logic ack;

  assign addr = core_if.addr;
  assign wdata = core_if.wdata;
  assign we = core_if.we;
  assign enable = core_if.enable;
  assign core_if.rdata = rdata;
  assign core_if.ack = ack;

  assign bram_if.addr = addr;
  assign bram_if.wdata = wdata;
  assign bram_if.we = we;
  assign bram_if.enable = enable && addr <= BramHighAddr;

  assign uart0_if.addr = addr & Uart0Mask;
  assign uart0_if.wdata = wdata;
  assign uart0_if.we = we;
  assign uart0_if.enable = enable && addr >= Uart0LowAddr && addr <= Uart0HighAddr;

  always_comb begin
    ack   = 'h0;
    rdata = 'h0;
    if (bram_if.enable) begin
      ack   = bram_if.ack;
      rdata = bram_if.rdata;
    end else if (uart0_if.enable) begin
      ack   = uart0_if.ack;
      rdata = uart0_if.rdata;
    end
  end

endmodule
