// Hydrogen machine ALU (v1) -- purely combinational, stateless. No
// clock/reset port (see "ALU: purely combinational for Phase 1" in
// CLAUDE.md). Full opcode table, flag semantics, and design rationale:
// machines/hydrogen/docs/alu.md. Bus field widths/directions: alu_if.sv.
module alu (
    alu_if.alu bus
);
  import isa_pkg::*;

  always_comb begin
    automatic logic [31:0] value1;
    automatic logic [31:0] value2;

    bus.result = '0;
    bus.overflow = '0;

    bus.error = bus.instruction.alu.is_imm_src1 & bus.instruction.alu.is_imm_src2;

    value1 = bus.instruction.alu.is_imm_src1 ? 32'(bus.instruction.alu.imm) : bus.value1;
    value2 = bus.instruction.alu.is_imm_src2 ? 32'(bus.instruction.alu.imm) : bus.value2;

    unique0 case (bus.instruction.alu.op)
      ALU_OP_ADD: begin
        {bus.overflow, bus.result} = value1 + value2;
      end
      ALU_OP_SUB: begin
        bus.overflow = value2 > value1;
        bus.result   = value1 - value2;
      end
      ALU_OP_MUL: begin
        automatic logic [63:0] product;
        product = value1 * value2;
        bus.overflow = |product[63:32];
        bus.result = product[31:0];
      end
      ALU_OP_MULH: begin
        automatic logic [63:0] product;
        product = value1 * value2;
        bus.result = product[63:32];
      end
      ALU_OP_LSHIFT: begin
        bus.result   = value1 << value2;
        bus.overflow = (bus.result >> value2) != value1;
      end
      ALU_OP_RSHIFT: begin
        bus.result = value1 >> value2;
      end
      ALU_OP_AND: begin
        bus.result = value1 & value2;
      end
      ALU_OP_OR: begin
        bus.result = value1 | value2;
      end
      ALU_OP_XOR: begin
        bus.result = value1 ^ value2;
      end
      ALU_OP_NOT: begin
        bus.result = ~value1;
      end
      ALU_OP_NAND: begin
        bus.result = ~(value1 & value2);
      end
      ALU_OP_NOR: begin
        bus.result = ~(value1 | value2);
      end
      default: begin
        bus.error = '1;
      end
    endcase
  end

endmodule
