interface fifo_read_if #(
    parameter int unsigned DataWidth = 32,
    parameter int unsigned FillWidth = 8
);
  logic                 enable;
  logic [DataWidth-1:0] data;
  logic                 empty;
  logic                 underflow;
  logic [FillWidth-1:0] fill;

  modport fifo(input enable, output data, empty, underflow, fill);
  modport requester(output enable, input data, empty, underflow, fill);
endinterface
