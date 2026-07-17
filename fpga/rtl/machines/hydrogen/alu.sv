module alu (
    input  logic [ 3:0] operation_i,
    input  logic [31:0] value1_i,
    input  logic [31:0] value2_i,
    output logic [31:0] result_o,
    output logic        overflow_o
);

  always_comb begin
    result_o   = '0;
    overflow_o = '0;
    unique case (operation_i)
      4'h0: begin  // ADD
        {overflow_o, result_o} = value1_i + value2_i;
      end
      4'h1: begin  // SUB
        overflow_o = value2_i > value1_i;
        result_o   = value1_i - value2_i;
      end
      4'h2: begin  // MUL
        automatic logic [63:0] product;
        product = value1_i * value2_i;
        overflow_o = |product[63:32];
        result_o = product[31:0];
      end
      4'h3: begin  // MULH
        automatic logic [63:0] product;
        product  = value1_i * value2_i;
        result_o = product[63:32];
      end
      4'h4: begin  // LSHIFT
        result_o   = value1_i << value2_i;
        overflow_o = (result_o >> value2_i) != value1_i;
      end
      4'h5: begin  // RSHIFT
        result_o = value1_i >> value2_i;
      end
      4'h6: begin  // AND
        result_o = value1_i & value2_i;
      end
      4'h7: begin  // OR
        result_o = value1_i | value2_i;
      end
      4'h8: begin  // XOR
        result_o = value1_i ^ value2_i;
      end
      4'h9: begin  // NOT
        result_o = ~value1_i;
      end
      4'hA: begin  // NAND
        result_o = ~(value1_i & value2_i);
      end
      4'hB: begin  // NOR
        result_o = ~(value1_i | value2_i);
      end
      default: begin
        result_o   = '0;
        overflow_o = '0;
      end
    endcase
  end

endmodule
