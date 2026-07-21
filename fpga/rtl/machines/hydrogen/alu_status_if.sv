interface alu_status_if;
  import isa_pkg::instr_t;
  instr_t instruction;
  logic   overflow;
  logic   latched_overflow;

  modport alu_status(input instruction, overflow, output latched_overflow);
  modport requester(output instruction, overflow, input latched_overflow);
endinterface


