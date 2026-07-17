localparam logic [31:0] ResetVector = 32'h10;
localparam logic [31:0] ErrorVector = 32'h0;
localparam logic [3:0] FlowCtlOpcode = 4'h2;


module flow_ctl (
    input logic clk_i,
    input logic rst_i,
    flow_ctl_if.flow_ctl bus
);

  logic [31:0] pc;

  logic [ 3:0] major_opcode;
  logic        is_relative;
  logic        is_imm;
  logic [ 3:0] operation;
  logic [15:0] imm;
  logic [31:0] goto_val;

  assign major_opcode = bus.opcode[31:28];
  assign is_relative = bus.opcode[27];
  assign is_imm = bus.opcode[26];
  assign operation = bus.opcode[25:22];
  assign imm = bus.opcode[21:6];

  always_comb begin
    if (is_relative) begin
      automatic logic signed [33:0] signed_goto_val;
      signed_goto_val = 34'(pc) + (is_imm ? 34'($signed(imm)) : 34'($signed(bus.goto_val)));
      if (|signed_goto_val[33:32]) begin
        goto_val = ErrorVector;
      end else begin
        goto_val = signed_goto_val[31:0];
      end
    end else begin
      goto_val = is_imm ? {16'h0, imm} : bus.goto_val;
    end
  end

  always_comb begin
    bus.pc = pc;
  end

  always_ff @(posedge clk_i) begin
    if (rst_i) begin
      pc <= ResetVector;
    end else if (bus.error) begin
      pc <= ErrorVector;
    end else if (major_opcode != FlowCtlOpcode) begin
      pc <= pc + 1;
    end else begin
      unique case (operation)
        4'h0: begin  // NOP
          pc <= pc + 1;
        end
        4'h1: begin  // less
          pc <= bus.value1 < bus.value2 ? goto_val : pc + 1;
        end
        4'h2: begin  // less or equal
          pc <= bus.value1 <= bus.value2 ? goto_val : pc + 1;
        end
        4'h3: begin  // greater
          pc <= bus.value1 > bus.value2 ? goto_val : pc + 1;
        end
        4'h4: begin  // greater or equal
          pc <= bus.value1 >= bus.value2 ? goto_val : pc + 1;
        end
        4'h5: begin  // is zero
          pc <= bus.value1 == '0 ? goto_val : pc + 1;
        end
        4'h6: begin  // is not zero
          pc <= bus.value1 != 0 ? goto_val : pc + 1;
        end
        4'h7: begin  // equal
          pc <= bus.value1 == bus.value2 ? goto_val : pc + 1;
        end
        4'h8: begin  // not equal
          pc <= bus.value1 != bus.value2 ? goto_val : pc + 1;
        end
        4'h9: begin  // always
          pc <= goto_val;
        end
        4'ha: begin  // overflow
          pc <= bus.overflow ? goto_val : pc + 1;
        end
        4'hb: begin  // not overflow
          pc <= !bus.overflow ? goto_val : pc + 1;
        end
        default: begin
          pc <= ErrorVector;
        end
      endcase
    end
  end
endmodule
