#define CLOCK_SPEED 10000000 // simulation locked to 10MHz (max with current design about 13MHz)

#define UART_DIV 5 // 10MHz / 16 oversampling / 115200 target baud = 5.4 -- does not matter for simulation as receiver uses the same div.
