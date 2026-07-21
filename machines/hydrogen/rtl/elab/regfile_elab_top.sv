// Elaboration-only top for `just elaborate`: exposes regfile's read/write
// interface fields as flat ports so Yosys's `opt` pass has real outputs to
// keep alive. tb_top (tb/regfile_tb_top.sv) has none -- cocotb drives/reads
// it hierarchically instead -- so opt would otherwise delete the entire
// register file as unused. Not a cocotb testbench, not part of the
// synthesizable design.
module regfile_elab_top (
    input  logic        clk_i,
    input  logic        rst_i,
    input  logic [2:0]  read1_addr_i,
    input  logic [2:0]  read2_addr_i,
    input  logic [2:0]  read3_addr_i,
    output logic [31:0] read1_value_o,
    output logic [31:0] read2_value_o,
    output logic [31:0] read3_value_o,
    input  logic [2:0]  write_addr_i,
    input  logic [31:0] write_value_i,
    input  logic        write_enable_i
);
  import isa_pkg::reg_addr_e;

  regfile_read_if read1 ();
  regfile_read_if read2 ();
  regfile_read_if read3 ();
  regfile_write_if write ();

  assign read1.addr = reg_addr_e'(read1_addr_i);
  assign read2.addr = reg_addr_e'(read2_addr_i);
  assign read3.addr = reg_addr_e'(read3_addr_i);
  assign read1_value_o = read1.value;
  assign read2_value_o = read2.value;
  assign read3_value_o = read3.value;

  assign write.addr = reg_addr_e'(write_addr_i);
  assign write.value = write_value_i;
  assign write.enable = write_enable_i;

  regfile dut (
      .clk_i(clk_i),
      .rst_i(rst_i),
      .read1(read1),
      .read2(read2),
      .read3(read3),
      .write(write)
  );
endmodule
