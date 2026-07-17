interface regfile_read_if;
  logic [ 2:0] addr;
  logic [31:0] data;

  modport regfile(input addr, output data);
  modport requester(output addr, input data);
endinterface

