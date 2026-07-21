interface bus_if;
  logic [31:0] addr;
  logic [31:0] wdata;
  logic [31:0] rdata;
  logic        enable;
  logic        we;
  logic        ack;

  modport master(output addr, wdata, enable, we, input rdata, ack);
  modport slave(input addr, wdata, enable, we, output rdata, ack);
endinterface

