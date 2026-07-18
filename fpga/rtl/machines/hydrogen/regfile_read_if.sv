interface regfile_read_if;
  import isa_pkg::reg_addr_e;
  reg_addr_e addr;
  logic [31:0] data;

  modport regfile(input addr, output data);
  modport requester(output addr, input data);
endinterface

