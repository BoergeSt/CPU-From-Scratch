interface regfile_write_if;
  logic [ 2:0] addr;
  logic [31:0] data;
  logic        write_en;

  modport regfile(input addr, data, write_en);
  modport requester(output addr, data, write_en);
endinterface

