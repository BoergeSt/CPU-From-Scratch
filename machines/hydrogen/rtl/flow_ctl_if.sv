interface flow_ctl_if;
  import isa_pkg::instr_t;
  instr_t        instruction;
  logic   [31:0] value1;
  logic   [31:0] value2;
  logic   [31:0] goto_val;
  logic   [31:0] pc;
  logic          overflow;
  logic          error;

  modport flow_ctl(input instruction, value1, value2, goto_val, overflow, error, output pc);
  modport requester(output instruction, value1, value2, goto_val, overflow, error, input pc);
endinterface

