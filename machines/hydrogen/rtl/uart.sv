typedef struct packed {
  logic [29:0] reserved;
  logic        reset;
  logic        enable;
} uart_control_t;

typedef enum logic {
  UART_PARITY_EVEN = 1'h0,
  UART_PARITY_ODD  = 1'h1
} uart_parity_e;

typedef enum logic {
  UART_ONE_STOPBIT  = 1'h0,
  UART_TWO_STOPBITS = 1'h1
} uart_stopbit_e;

typedef struct packed {
  logic [16:0]   reserved;
  logic [11:0]   divisor;
  uart_stopbit_e stop_bits;
  logic          parity_en;
  uart_parity_e  parity_type;
} uart_settings_t;

typedef struct packed {
  logic [27:0] reserved;
  logic        parity_err;
  logic        framing_err;
  logic        rx_overflow;
  logic        tx_overflow;
} uart_errors_t;

typedef struct packed {
  logic [23:0] reserved;
  logic [7:0]  value;
} uart_data_t;

typedef struct packed {
  logic [23:0] reserved;
  logic [7:0]  fill;
} uart_fill_t;

typedef union packed {
  uart_control_t  control;
  uart_settings_t settings;
  uart_errors_t   errors;
  uart_data_t     data;
  uart_fill_t     fill;
  logic [31:0]    raw;
} uart_register_t;

typedef enum logic [2:0] {
  UART_CONTROL  = 3'h0,
  UART_SETTINGS = 3'h1,
  UART_ERRORS   = 3'h2,
  UART_DATA     = 3'h3,
  UART_TX_FILL  = 3'h4,
  UART_RX_FILL  = 3'h5
} uart_registers_e;


typedef enum logic [2:0] {
  UART_TX_STATE_IDLE     = 3'h0,
  UART_TX_STATE_START    = 3'h1,
  UART_TX_STATE_BYTE_OUT = 3'h2,
  UART_TX_STATE_PARITY   = 3'h3,
  UART_TX_STATE_STOP     = 3'h4
} uart_tx_state_e;

module uart_phy_tx (
    input logic clk_i,
    input logic rst_i,
    input logic enable_i,
    input logic parity_en_i,
    input uart_parity_e parity_type_i,
    input uart_stopbit_e stop_bit_i,
    input logic [7:0] data_i,
    input logic [11:0] divisor_i,
    output logic tx_o,
    output logic pull_data_o
);

  logic [ 2:0] bit_counter;
  logic [15:0] count_to;
  assign count_to = (16'(divisor_i) << 4) - 1;

  logic [15:0] supersample_counter;

  logic [7:0] data_q;

  uart_tx_state_e state;

  always_comb begin
    tx_o = 1'b0;
    unique case (state)
      UART_TX_STATE_IDLE:     tx_o = 1'b1;
      UART_TX_STATE_START:    tx_o = 1'b0;
      UART_TX_STATE_BYTE_OUT: tx_o = 1'(data_q >> bit_counter);
      UART_TX_STATE_PARITY:   tx_o = parity_type_i ? ~^data_q : ^data_q;
      UART_TX_STATE_STOP:     tx_o = 1'b1;
    endcase
  end

  assign pull_data_o = state == UART_TX_STATE_START && supersample_counter == 'h0;

  always_ff @(posedge clk_i) begin
    if (rst_i) begin
      bit_counter <= 'h0;
      supersample_counter <= 'h0;
      state <= UART_TX_STATE_IDLE;
    end else begin
      unique case (state)
        UART_TX_STATE_IDLE:
        if (enable_i) begin
          state <= UART_TX_STATE_START;
          supersample_counter <= 'h0;
        end
        UART_TX_STATE_START: begin
          if (supersample_counter == 0) data_q <= data_i;
          if (supersample_counter == count_to) begin
            state <= UART_TX_STATE_BYTE_OUT;
            supersample_counter <= 'h0;
            bit_counter <= 'h0;
          end else supersample_counter <= supersample_counter + 'b1;
        end
        UART_TX_STATE_BYTE_OUT: begin
          if (supersample_counter == count_to) begin
            supersample_counter <= 'h0;
            bit_counter <= bit_counter + 'b1;  // overflow handles resetting this nicely
            if (bit_counter == 'h7)
              state <= parity_en_i ? UART_TX_STATE_PARITY : UART_TX_STATE_STOP;
          end else supersample_counter <= supersample_counter + 'b1;
        end
        UART_TX_STATE_PARITY: begin
          if (supersample_counter == count_to) begin
            supersample_counter <= 'h0;
            state <= UART_TX_STATE_STOP;
          end else supersample_counter <= supersample_counter + 'b1;
        end
        UART_TX_STATE_STOP: begin
          if (supersample_counter == count_to) begin
            supersample_counter <= 'h0;
            if (stop_bit_i == UART_ONE_STOPBIT || bit_counter == 'h1)
              state <= enable_i ? UART_TX_STATE_START : UART_TX_STATE_IDLE;
            else bit_counter <= bit_counter + 'b1;
          end else supersample_counter <= supersample_counter + 'b1;
        end
      endcase
    end
  end
endmodule

typedef enum logic [2:0] {
  UART_RX_STATE_ERROR   = 3'h0,
  UART_RX_STATE_IDLE    = 3'h1,
  UART_RX_STATE_START   = 3'h2,
  UART_RX_STATE_BYTE_IN = 3'h3,
  UART_RX_STATE_PARITY  = 3'h4,
  UART_RX_STATE_STOP    = 3'h5,
  UART_RX_STATE_PUSH    = 3'h6
} uart_rx_state_e;

module uart_phy_rx (
    input logic clk_i,
    input logic rst_i,
    input logic enable_i,
    input logic parity_en_i,
    input uart_parity_e parity_type_i,
    input uart_stopbit_e stop_bit_i,
    input logic [11:0] divisor_i,
    input logic rx_i,
    output logic [7:0] data_o,
    output logic push_data_o,
    output logic frame_error_o,
    output logic parity_error_o
);

  uart_rx_state_e state;
  logic rx_synced;

  logic [15:0] supersample_counter;
  logic [2:0] bit_count;
  logic [7:0] read_byte;

  logic parity;
  logic had_parity_error;

  assign push_data_o = state == UART_RX_STATE_PUSH && !had_parity_error;
  assign parity = parity_type_i ? ~^read_byte : ^read_byte;
  assign data_o = read_byte;

  always_comb begin
    parity_error_o = '0;
    frame_error_o  = '0;

    if (state == UART_RX_STATE_PARITY && supersample_counter == (16'(divisor_i) << 'h4) - 'h1)
      parity_error_o = parity != rx_synced;
    if (state == UART_RX_STATE_STOP && supersample_counter == (16'(divisor_i) << 'h4) - 'h1)
      frame_error_o = !rx_synced;
  end

  always_ff @(posedge clk_i) begin
    static logic rx_tmp;
    rx_tmp <= rst_i ? '0 : rx_i;
    rx_synced <= rst_i ? '0 : rx_tmp;
  end

  always_ff @(posedge clk_i) begin
    if (rst_i || !enable_i) state <= UART_RX_STATE_ERROR;
    else begin
      unique case (state)
        UART_RX_STATE_ERROR: if (rx_synced) state <= UART_RX_STATE_IDLE;
        UART_RX_STATE_IDLE:
        if (!rx_synced) begin
          state <= UART_RX_STATE_START;
          supersample_counter <= 'h1;  // first cycle is still in idle state
        end
        UART_RX_STATE_START:
        if (supersample_counter == (16'(divisor_i) << 'h3) - 'h1) begin
          state <= rx_synced ? UART_RX_STATE_IDLE : UART_RX_STATE_BYTE_IN;
          read_byte <= '0;
          bit_count <= '0;
          had_parity_error <= '0;
          supersample_counter <= '0;
        end else supersample_counter <= supersample_counter + 1;
        UART_RX_STATE_BYTE_IN:
        if (supersample_counter == (16'(divisor_i) << 'h4) - 'h1) begin
          bit_count <= bit_count + 1;
          read_byte <= read_byte | (8'(rx_synced) << bit_count);
          supersample_counter <= '0;
          if (bit_count == 7) state <= parity_en_i ? UART_RX_STATE_PARITY : UART_RX_STATE_STOP;
        end else supersample_counter <= supersample_counter + 1;
        UART_RX_STATE_PARITY:
        if (supersample_counter == (16'(divisor_i) << 'h4) - 'h1) begin
          had_parity_error <= parity_error_o;
          state <= UART_RX_STATE_STOP;
          supersample_counter <= '0;
        end else supersample_counter <= supersample_counter + 1;
        UART_RX_STATE_STOP:
        if (supersample_counter == (16'(divisor_i) << 'h4) - 'h1) begin
          bit_count <= bit_count + 1;
          supersample_counter <= '0;
          if (frame_error_o) state <= UART_RX_STATE_ERROR;
          else if (stop_bit_i == UART_ONE_STOPBIT || bit_count == 'h1) begin
            state <= UART_RX_STATE_PUSH;
          end
        end else supersample_counter <= supersample_counter + 1;
        UART_RX_STATE_PUSH:  state <= UART_RX_STATE_IDLE;
      endcase
    end
  end
endmodule

module uart (
    input   logic   clk_i,
    input   logic   rst_i,
    input   logic   rx_i,
    output  logic   tx_o,
    bus_if.slave    bus
);

  logic soft_reset;
  logic frame_error;
  logic parity_error;

  uart_control_t control_q, control_d;
  uart_settings_t settings_q, settings_d;
  uart_errors_t errors_q, errors_d;

  uart_phy_tx uart_phy_tx (
      .clk_i        (clk_i),
      .rst_i        (rst_i || soft_reset),
      .enable_i     (control_q.enable && !tx_fifo_read.empty),
      .parity_en_i  (settings_q.parity_en),
      .parity_type_i(settings_q.parity_type),
      .stop_bit_i   (settings_q.stop_bits),
      .data_i       (tx_fifo_read.data),
      .divisor_i    (settings_q.divisor),
      .tx_o         (tx_o),
      .pull_data_o  (tx_fifo_read.enable)
  );

  uart_phy_rx uart_phy_rx (
      .clk_i         (clk_i),
      .rst_i         (rst_i || soft_reset),
      .enable_i      (control_q.enable),
      .parity_en_i   (settings_q.parity_en),
      .parity_type_i (settings_q.parity_type),
      .stop_bit_i    (settings_q.stop_bits),
      .divisor_i     (settings_q.divisor),
      .rx_i          (rx_i),
      .data_o        (rx_fifo_write.data),
      .push_data_o   (rx_fifo_write.enable),
      .frame_error_o (frame_error),
      .parity_error_o(parity_error)
  );

  uart_register_t rdata;
  assign bus.rdata = rdata;

  uart_register_t wdata;
  assign wdata = bus.wdata;

  fifo_read_if #(
      .DataWidth(8),
      .FillWidth(8)
  ) rx_fifo_read ();

  fifo_write_if #(
      .DataWidth(8),
      .FillWidth(8)
  ) rx_fifo_write ();

  fifo #(
      .DataWidth(8),
      .FillWidth(8)
  ) rx_fifo (
      .clk_i(clk_i),
      .rst_i(rst_i || soft_reset),
      .read (rx_fifo_read),
      .write(rx_fifo_write)
  );

  fifo_read_if #(
      .DataWidth(8),
      .FillWidth(8)
  ) tx_fifo_read ();

  fifo_write_if #(
      .DataWidth(8),
      .FillWidth(8)
  ) tx_fifo_write ();

  fifo #(
      .DataWidth(8),
      .FillWidth(8)
  ) tx_fifo (
      .clk_i(clk_i),
      .rst_i(rst_i || soft_reset),
      .read (tx_fifo_read),
      .write(tx_fifo_write)
  );

  assign tx_fifo_write.data = wdata.data.value;


  always_comb begin
    bus.ack = 1'b1;
    rdata.raw = 32'h0;
    control_d = control_q;
    settings_d = settings_q;
    errors_d = errors_q;
    soft_reset = 1'b0;
    tx_fifo_write.enable = 1'b0;
    rx_fifo_read.enable = 1'b0;
    if (bus.enable) begin
      unique0 case (uart_registers_e'(bus.addr[2:0]))

        UART_CONTROL: begin
          rdata.control = control_q;
          if (bus.we) begin
            if (settings_q.divisor != '0 || !wdata.control.enable) begin
              control_d.enable = wdata.control.enable;
            end
            if (wdata.control.reset) soft_reset = 1'b1;
          end
        end

        UART_SETTINGS: begin
          rdata.settings = settings_q;
          if (bus.we && !control_q.enable) begin
            settings_d.parity_type = wdata.settings.parity_type;
            settings_d.parity_en = wdata.settings.parity_en;
            settings_d.divisor = wdata.settings.divisor;
            settings_d.stop_bits = wdata.settings.stop_bits;
          end
        end

        UART_ERRORS: begin
          rdata.errors = errors_q;
          if (bus.we) begin
            if (wdata.errors.rx_overflow) errors_d.rx_overflow = 1'b0;
            if (wdata.errors.tx_overflow) errors_d.tx_overflow = 1'b0;
            if (wdata.errors.framing_err) errors_d.framing_err = 1'b0;
            if (wdata.errors.parity_err) errors_d.parity_err = 1'b0;
          end
        end

        UART_DATA: begin
          if (bus.we) begin
            tx_fifo_write.enable = 1'b1;
            if (tx_fifo_write.overflow) errors_d.tx_overflow = 1'b1;
          end else begin
            rx_fifo_read.enable = 1'b1;
            rdata.data.value = rx_fifo_read.data;
          end
        end

        UART_TX_FILL: begin
          rdata.fill.fill = tx_fifo_write.fill;
        end

        UART_RX_FILL: begin
          rdata.fill.fill = rx_fifo_write.fill;
        end

        default: begin
          bus.ack = 1'h0;
        end
      endcase
    end
    errors_d.parity_err |= parity_error && control_q.enable;
    errors_d.framing_err |= frame_error && control_q.enable;
    errors_d.rx_overflow |= rx_fifo_write.overflow;
  end

  always_ff @(posedge clk_i) begin
    control_q  <= rst_i ? '0 : control_d;
    settings_q <= rst_i ? '0 : settings_d;
    errors_q   <= rst_i || soft_reset ? '0 : errors_d;
  end


endmodule
