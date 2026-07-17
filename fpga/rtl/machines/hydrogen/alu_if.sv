interface alu_if;
  logic [31:0] opcode;
  logic [31:0] value1;
  logic [31:0] value2;
  logic [31:0] result;
  logic        overflow;
  logic        error;

  modport alu(input opcode, value1, value2, output result, overflow, error);
  modport requester(output opcode, value1, value2, input result, overflow, error);
endinterface
