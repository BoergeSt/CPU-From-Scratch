package isa_pkg;
  localparam logic [31:0] ResetVector = 32'h10;
  localparam logic [31:0] ErrorVector = 32'h0;

  typedef enum logic [3:0] {
    IC_ALU       = 4'h0,
    IC_IMM_SET   = 4'h1,
    IC_FLOW_CTL  = 4'h2,
    IC_LOAD_IMM  = 4'h3,
    IC_STORE_IMM = 4'h4,
    IC_LOAD      = 4'h5,
    IC_STORE     = 4'h6
  } instr_class_e;

  typedef enum logic [2:0] {
    REG_R0 = 3'h0,
    REG_R1 = 3'h1,
    REG_R2 = 3'h2,
    REG_R3 = 3'h3,
    REG_R4 = 3'h4,
    REG_R5 = 3'h5,
    REG_R6 = 3'h6,
    REG_R7 = 3'h7
  } reg_addr_e;

  typedef enum logic [3:0] {
    ALU_OP_ADD    = 4'h0,
    ALU_OP_SUB    = 4'h1,
    ALU_OP_MUL    = 4'h2,
    ALU_OP_MULH   = 4'h3,
    ALU_OP_LSHIFT = 4'h4,
    ALU_OP_RSHIFT = 4'h5,
    ALU_OP_AND    = 4'h6,
    ALU_OP_OR     = 4'h7,
    ALU_OP_XOR    = 4'h8,
    ALU_OP_NOT    = 4'h9,
    ALU_OP_NAND   = 4'hA,
    ALU_OP_NOR    = 4'hB
  } alu_op_e;

  typedef enum logic [3:0] {
    FLOW_CTL_OP_NOP = 4'h0,
    FLOW_CTL_OP_LESS = 4'h1,
    FLOW_CTL_OP_LESS_EQUAL = 4'h2,
    FLOW_CTL_OP_GREATER = 4'h3,
    FLOW_CTL_OP_GREATER_EQUAL = 4'h4,
    FLOW_CTL_OP_ZERO = 4'h5,
    FLOW_CTL_OP_NOT_ZERO = 4'h6,
    FLOW_CTL_OP_EQUAL = 4'h7,
    FLOW_CTL_OP_NOT_EQUAL = 4'h8,
    FLOW_CTL_OP_ALWAYS = 4'h9,
    FLOW_CTL_OP_OVERFLOW = 4'hA,
    FLOW_CTL_OP_NOT_OVERFLOW = 4'hB
  } flow_op_e;

  typedef struct packed {
    instr_class_e ic;         // [31:28]
    reg_addr_e    dest;       // [27:25]
    logic [15:0]  reserved;   // [24:9]
    reg_addr_e    src3_addr;  // [8:6]
    reg_addr_e    src2_addr;  // [5:3]
    reg_addr_e    src1_addr;  // [2:0]
  } generic_instr_t;

  typedef struct packed {
    instr_class_e ic;           // [31:28]
    reg_addr_e    dest;         // [27:25]
    alu_op_e      op;           // [24:21]
    logic         is_imm_src1;  // [20]
    logic         is_imm_src2;  // [19]
    logic [12:0]  imm;          // [18:6]
    reg_addr_e    src2_addr;    // [5:3]
    reg_addr_e    src1_addr;    // [2:0]
  } alu_instr_t;

  typedef struct packed {
    logic [12:0] reserved;
    reg_addr_e   jump_to_addr;
  } flow_ctl_target_reg_t;

  typedef struct packed {logic [15:0] imm;} flow_ctl_target_imm_t;

  typedef union packed {
    flow_ctl_target_reg_t is_reg;
    flow_ctl_target_imm_t is_imm;
  } flow_ctl_target_t;

  typedef struct packed {
    instr_class_e     ic;           // [31:28]
    logic             is_relative;  // [27]
    logic             is_imm;       // [26]
    flow_op_e         op;           // [25:22]
    flow_ctl_target_t target;       // [21:6]
    reg_addr_e        src2_addr;    // [5:3]
    reg_addr_e        src1_addr;    // [2:0]
  } flow_ctl_instr_t;

  typedef union packed {
    logic [31:0]     raw;
    generic_instr_t  generic;
    alu_instr_t      alu;
    flow_ctl_instr_t flow_ctl;
  } instr_t;

endpackage
