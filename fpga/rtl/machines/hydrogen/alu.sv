// Hydrogen machine ALU (v1) -- purely combinational, stateless. No
// clock/reset port (see "ALU: purely combinational for Phase 1" in
// CLAUDE.md). Full opcode table, flag semantics, and design rationale:
// docs/machines/hydrogen/alu.md. Bus field widths/directions: alu_if.sv.
module alu (
    alu_if.alu bus
);

  always_comb begin
    automatic logic is_imm_src1;
    automatic logic is_imm_src2;
    automatic logic [12:0] imm_value;
    automatic logic [31:0] value1;
    automatic logic [31:0] value2;

    bus.result = '0;
    bus.overflow = '0;

    is_imm_src1 = bus.opcode[20];
    is_imm_src2 = bus.opcode[19];

    bus.error = is_imm_src1 & is_imm_src2;

    imm_value = bus.opcode[18:6];

    value1 = is_imm_src1 ? 32'(imm_value) : bus.value1;
    value2 = is_imm_src2 ? 32'(imm_value) : bus.value2;

    unique case (bus.opcode[24:21])
      4'h0: begin  // ADD
        {bus.overflow, bus.result} = value1 + value2;
      end
      4'h1: begin  // SUB
        bus.overflow = value2 > value1;
        bus.result   = value1 - value2;
      end
      4'h2: begin  // MUL
        automatic logic [63:0] product;
        product = value1 * value2;
        bus.overflow = |product[63:32];
        bus.result = product[31:0];
      end
      4'h3: begin  // MULH
        automatic logic [63:0] product;
        product = value1 * value2;
        bus.result = product[63:32];
      end
      4'h4: begin  // LSHIFT
        bus.result   = value1 << value2;
        bus.overflow = (bus.result >> value2) != value1;
      end
      4'h5: begin  // RSHIFT
        bus.result = value1 >> value2;
      end
      4'h6: begin  // AND
        bus.result = value1 & value2;
      end
      4'h7: begin  // OR
        bus.result = value1 | value2;
      end
      4'h8: begin  // XOR
        bus.result = value1 ^ value2;
      end
      4'h9: begin  // NOT
        bus.result = ~value1;
      end
      4'hA: begin  // NAND
        bus.result = ~(value1 & value2);
      end
      4'hB: begin  // NOR
        bus.result = ~(value1 | value2);
      end
      default: begin
        bus.error = '1;
      end
    endcase
  end

endmodule
