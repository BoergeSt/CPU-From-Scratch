module bram #(
    parameter logic [31:0] Size = 32'h1000
) (
    input logic clk_i,
    bus_if.slave bus_I,
    bus_if.slave bus_D
);

  logic [31:0] bram[Size];

  function automatic void bram_read(input logic [31:0] addr, input logic enable, output logic ack,
                                    output logic [31:0] rdata);
    ack   = '0;
    rdata = '0;
    if (enable && addr < Size) begin
      ack   = '1;
      rdata = bram[addr];
    end
  endfunction

  always_comb bram_read(bus_I.addr, bus_I.enable, bus_I.ack, bus_I.rdata);
  always_comb bram_read(bus_D.addr, bus_D.enable, bus_D.ack, bus_D.rdata);

  always_ff @(posedge clk_i) begin
    if (bus_D.enable && bus_D.we && bus_D.addr < Size) begin
      bram[bus_D.addr] <= bus_D.wdata;
    end
  end

endmodule
