#pragma once

#include "calling_convention.h"

#define CLOCK_SPEED 10000000 // simulation locked to 10MHz (max with current design about 13MHz)

#define UART0_BASE 			0x10100

#define UART_CONTROL			0x0
#define UART_SETTINGS			0x1
#define UART_DATA			0x3
#define UART_TX_FILL			0x4
#define UART_RX_FILL			0x5

#define UART_CONTROL_ENABLE		0x1
#define UART_CONTROL_RESET		0x2
#define UART_SETTINGS_PARITY_TYPE	0x1
#define UART_SETTINGS_PARITY_EN		0x2
#define UART_SETTINGS_STOP_BITS		0x4

#define UART_SETTINGS_DIVISOR_SHIFT	0x3
#define UART_FIFO_SIZE			128

#define UART_DIV 5 // 10MHz / 16 oversampling / 115200 target baud = 5.4 -- does not matter for simulation as receiver uses the same div.

