interface regfile_read_if;
  import isa_pkg::reg_addr_e;
  reg_addr_e addr;
  logic [31:0] value;

  modport regfile(input addr, output value);
  modport requester(output addr, input value);
endinterface
