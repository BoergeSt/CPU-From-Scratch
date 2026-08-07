interface fifo_write_if #(
    parameter int unsigned DataWidth = 32,
    parameter int unsigned FillWidth = 8
);
  logic                 enable;
  logic [DataWidth-1:0] data;
  logic                 full;
  logic                 overflow;
  logic [FillWidth-1:0] fill;

  modport fifo(input enable, data, output full, overflow, fill);
  modport requester(output enable, data, input full, overflow, fill);
endinterface
