// Hydrogen machine register file (v1) -- plain 8x32-bit R0-R7 storage only;
// no PC, no immediate-flag decode, no ALU/bus routing (see module-boundary
// rationale in machines/hydrogen/docs/regfile.md). Combinational reads,
// synchronous active-high reset to 0; reset takes unconditional priority
// over a simultaneous write. Read/write port field widths/directions:
// regfile_read_if.sv, regfile_write_if.sv.
module regfile (
    input logic clk_i,
    input logic rst_i,
    regfile_read_if.regfile read1,
    regfile_read_if.regfile read2,
    regfile_read_if.regfile read3,
    regfile_write_if.regfile write
);
  logic [31:0] registers[8];

  always_comb begin
    read1.value = registers[read1.addr];
    read2.value = registers[read2.addr];
    read3.value = registers[read3.addr];
  end

  always_ff @(posedge clk_i) begin
    if (rst_i) begin
      registers <= '{default: '0};
    end else if (write.enable) begin
      registers[write.addr] <= write.value;
    end
  end

endmodule
