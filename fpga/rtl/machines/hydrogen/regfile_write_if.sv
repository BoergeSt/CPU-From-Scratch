interface regfile_write_if;
  import isa_pkg::reg_addr_e;
  reg_addr_e        addr;
  logic      [31:0] data;
  logic             write_en;

  modport regfile(input addr, data, write_en);
  modport requester(output addr, data, write_en);
endinterface

