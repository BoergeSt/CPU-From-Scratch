// Hydrogen machine ALU (v1) -- purely combinational, stateless. No
// clock/reset port (see "ALU: purely combinational for Phase 1" in
// CLAUDE.md). Full opcode table, flag semantics, and design rationale:
// docs/machines/hydrogen/alu.md. Bus field widths/directions: alu_if.sv.
module alu (
    alu_if.alu bus
);

  always_comb begin
    bus.result   = '0;
    bus.overflow = '0;
    unique case (bus.operation)
      4'h0: begin  // ADD
        {bus.overflow, bus.result} = bus.value1 + bus.value2;
      end
      4'h1: begin  // SUB
        bus.overflow = bus.value2 > bus.value1;
        bus.result   = bus.value1 - bus.value2;
      end
      4'h2: begin  // MUL
        automatic logic [63:0] product;
        product = bus.value1 * bus.value2;
        bus.overflow = |product[63:32];
        bus.result = product[31:0];
      end
      4'h3: begin  // MULH
        automatic logic [63:0] product;
        product = bus.value1 * bus.value2;
        bus.result = product[63:32];
      end
      4'h4: begin  // LSHIFT
        bus.result   = bus.value1 << bus.value2;
        bus.overflow = (bus.result >> bus.value2) != bus.value1;
      end
      4'h5: begin  // RSHIFT
        bus.result = bus.value1 >> bus.value2;
      end
      4'h6: begin  // AND
        bus.result = bus.value1 & bus.value2;
      end
      4'h7: begin  // OR
        bus.result = bus.value1 | bus.value2;
      end
      4'h8: begin  // XOR
        bus.result = bus.value1 ^ bus.value2;
      end
      4'h9: begin  // NOT
        bus.result = ~bus.value1;
      end
      4'hA: begin  // NAND
        bus.result = ~(bus.value1 & bus.value2);
      end
      4'hB: begin  // NOR
        bus.result = ~(bus.value1 | bus.value2);
      end
      default: begin
        bus.result   = '0;
        bus.overflow = '0;
      end
    endcase
  end

endmodule
