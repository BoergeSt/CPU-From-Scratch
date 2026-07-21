module core_glue (
    regfile_read_if.requester  read_1,
    regfile_read_if.requester  read_2,
    regfile_read_if.requester  read_3,
    regfile_write_if.requester write,
    alu_if.requester           alu,
    alu_status_if.requester    alu_status,
    flow_ctl_if.requester      flow_ctl,
    bus_if.master              bus_I,
    bus_if.master              bus_D
);
  import isa_pkg::*;

  instr_t instruction;
  logic   unknown_opcode;
  logic   address_over_under_flow;

  assign instruction          = instr_t'(bus_I.rdata);

  assign bus_I.addr           = flow_ctl.pc;
  assign bus_I.we             = '0;
  assign bus_I.enable         = '1;
  assign bus_I.wdata          = '0;

  assign read_1.addr          = instruction.generic.src1_addr;
  assign read_2.addr          = instruction.generic.src2_addr;
  assign read_3.addr          = instruction.generic.src3_addr;

  assign flow_ctl.instruction = instruction;
  assign flow_ctl.value1      = read_1.value;
  assign flow_ctl.value2      = read_2.value;
  assign flow_ctl.goto_val    = read_3.value;
  assign flow_ctl.overflow    = alu_status.latched_overflow;

  always_comb begin
    flow_ctl.error = !bus_I.ack;
    flow_ctl.error |= unknown_opcode;
    flow_ctl.error |= address_over_under_flow;
    flow_ctl.error |= bus_D.enable & !bus_D.ack;
    if (instruction.generic.ic == IC_ALU) flow_ctl.error |= alu.error;
  end

  assign alu_status.instruction = instruction;
  assign alu_status.overflow    = alu.overflow;

  assign alu.instruction        = instruction;
  assign alu.value1             = read_1.value;
  assign alu.value2             = read_2.value;


  always_comb begin
    unknown_opcode          = '0;
    address_over_under_flow = '0;

    write.enable            = '0;
    write.value             = '0;
    write.addr              = instruction.generic.dest;

    bus_D.addr              = '0;
    bus_D.enable            = '0;
    bus_D.we                = '0;
    bus_D.wdata             = '0;

    unique0 case (instruction.generic.ic)
      IC_ALU: begin
        write.enable = !alu.error;
        write.value  = alu.result;
      end
      IC_IMM_SET: begin
        write.enable = '1;
        write.value  = 32'(instruction.imm_set.imm);
      end
      IC_FLOW_CTL: ;  // Legal, but do not write
      default: begin
        unknown_opcode = '1;
      end
      IC_LOAD_IMM: begin
        bus_D.enable = '1;
        bus_D.addr   = 32'(instruction.load_imm.imm);
        write.enable = '1;
        write.value  = bus_D.rdata;
      end
      IC_STORE_IMM: begin
        bus_D.enable = '1;
        bus_D.addr = 32'(instruction.store_imm.imm);
        bus_D.we = '1;
        bus_D.wdata = read_1.value;
      end
      IC_LOAD: begin
        automatic logic signed [33:0] signed_combined_address;
        signed_combined_address = 34'($signed(instruction.load.offset)) +
            $signed(34'(read_1.value));
        address_over_under_flow = |signed_combined_address[33:32];
        if (!address_over_under_flow) begin
          bus_D.enable = '1;
          bus_D.addr   = signed_combined_address[31:0];
          write.enable = '1;
          write.value  = bus_D.rdata;
        end
      end
      IC_STORE: begin
        automatic logic signed [33:0] signed_combined_address;
        signed_combined_address = 34'($signed(instruction.store.offset)) +
            $signed(34'(read_1.value));
        address_over_under_flow = |signed_combined_address[33:32];
        if (!address_over_under_flow) begin
          bus_D.enable = '1;
          bus_D.addr = signed_combined_address[31:0];
          bus_D.we = '1;
          bus_D.wdata = read_2.value;
        end
      end
    endcase
  end

endmodule
