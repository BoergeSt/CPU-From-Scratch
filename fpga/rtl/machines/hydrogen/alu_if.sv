interface alu_if;
  logic [ 3:0] operation;
  logic [31:0] value1;
  logic [31:0] value2;
  logic [31:0] result;
  logic        overflow;

  modport alu(input operation, value1, value2, output result, overflow);
  modport requester(output operation, value1, value2, input result, overflow);
endinterface
