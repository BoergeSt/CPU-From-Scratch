interface regfile_write_if;
  import isa_pkg::reg_addr_e;
  reg_addr_e        addr;
  logic      [31:0] value;
  logic             enable;

  modport regfile(input addr, value, enable);
  modport requester(output addr, value, enable);
endinterface
