interface flow_ctl_if;
  logic [31:0] opcode;
  logic [31:0] value1;
  logic [31:0] value2;
  logic [31:0] goto_val;
  logic [31:0] pc;
  logic        overflow;
  logic        error;

  modport flow_ctl(input opcode, value1, value2, goto_val, overflow, error, output pc);
  modport requester(output opcode, value1, value2, goto_val, overflow, error, input pc);
endinterface

