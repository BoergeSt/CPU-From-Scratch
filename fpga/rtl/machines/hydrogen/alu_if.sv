

interface alu_if;
  import isa_pkg::instr_t;
  instr_t        instruction;
  logic   [31:0] value1;
  logic   [31:0] value2;
  logic   [31:0] result;
  logic          overflow;
  logic          error;

  modport alu(input instruction, value1, value2, output result, overflow, error);
  modport requester(output instruction, value1, value2, input result, overflow, error);
endinterface
