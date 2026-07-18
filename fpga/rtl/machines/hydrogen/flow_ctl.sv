module flow_ctl (
    input logic clk_i,
    input logic rst_i,
    flow_ctl_if.flow_ctl bus
);
  import isa_pkg::*;

  logic [31:0] pc;

  logic        is_imm;
  logic [15:0] imm;
  logic [31:0] goto_val;

  assign is_imm = bus.instruction.flow_ctl.is_imm;
  assign imm = bus.instruction.flow_ctl.target.is_imm.imm;

  always_comb begin
    if (bus.instruction.flow_ctl.is_relative) begin
      automatic logic signed [33:0] signed_goto_val;
      signed_goto_val = $signed(34'(pc)) +
          (is_imm ? 34'($signed(imm)) : 34'($signed(bus.goto_val)));
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
    end else if (bus.instruction.flow_ctl.ic != IC_FLOW_CTL) begin
      pc <= pc + 1;
    end else begin
      unique0 case (bus.instruction.flow_ctl.op)
        FLOW_CTL_OP_NOP: begin
          pc <= pc + 1;
        end
        FLOW_CTL_OP_LESS: begin
          pc <= bus.value1 < bus.value2 ? goto_val : pc + 1;
        end
        FLOW_CTL_OP_LESS_EQUAL: begin
          pc <= bus.value1 <= bus.value2 ? goto_val : pc + 1;
        end
        FLOW_CTL_OP_GREATER: begin
          pc <= bus.value1 > bus.value2 ? goto_val : pc + 1;
        end
        FLOW_CTL_OP_GREATER_EQUAL: begin
          pc <= bus.value1 >= bus.value2 ? goto_val : pc + 1;
        end
        FLOW_CTL_OP_ZERO: begin
          pc <= bus.value1 == '0 ? goto_val : pc + 1;
        end
        FLOW_CTL_OP_NOT_ZERO: begin
          pc <= bus.value1 != 0 ? goto_val : pc + 1;
        end
        FLOW_CTL_OP_EQUAL: begin
          pc <= bus.value1 == bus.value2 ? goto_val : pc + 1;
        end
        FLOW_CTL_OP_NOT_EQUAL: begin
          pc <= bus.value1 != bus.value2 ? goto_val : pc + 1;
        end
        FLOW_CTL_OP_ALWAYS: begin
          pc <= goto_val;
        end
        FLOW_CTL_OP_OVERFLOW: begin
          pc <= bus.overflow ? goto_val : pc + 1;
        end
        FLOW_CTL_OP_NOT_OVERFLOW: begin
          pc <= !bus.overflow ? goto_val : pc + 1;
        end
        default: begin
          pc <= ErrorVector;
        end
      endcase
    end
  end
endmodule
