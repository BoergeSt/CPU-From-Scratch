// Elaboration-only top for `just elaborate`: exposes fifo's write/read
// interface fields as flat ports so Yosys's `opt` pass has real outputs to
// keep alive. tb_top (tb/fifo_tb_top.sv) has none -- cocotb drives/reads it
// hierarchically instead -- so opt would otherwise delete the entire FIFO
// as unused. Hardcodes fifo's default DataWidth/FillWidth (32/8, i.e. 128
// entries), matching regfile_elab_top's fixed-width approach -- this
// target only ever elaborates with defaults, so exposing them as this
// module's own parameters would be dead configurability. write.fill and
// read.fill are two separate output ports here (wr_fill_o/rd_fill_o) since
// they're two distinct interface fields fed by the same internal count --
// see fifo.md's Design rationale for why both interfaces carry it. Not a
// cocotb testbench, not part of the synthesizable design.
module fifo_elab_top (
    input  logic        clk_i,
    input  logic        rst_i,
    input  logic        we_i,
    input  logic [31:0] data_i,
    output logic        full_o,
    output logic        overflow_o,
    output logic [ 7:0] wr_fill_o,
    input  logic        re_i,
    output logic [31:0] data_o,
    output logic        empty_o,
    output logic        underflow_o,
    output logic [ 7:0] rd_fill_o
);

  fifo_write_if write ();
  fifo_read_if read ();

  assign write.enable = we_i;
  assign write.data = data_i;
  assign full_o = write.full;
  assign overflow_o = write.overflow;
  assign wr_fill_o = write.fill;

  assign read.enable = re_i;
  assign data_o = read.data;
  assign empty_o = read.empty;
  assign underflow_o = read.underflow;
  assign rd_fill_o = read.fill;

  fifo dut (
      .clk_i(clk_i),
      .rst_i(rst_i),
      .read (read),
      .write(write)
  );

endmodule
