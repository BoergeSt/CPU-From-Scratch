#define UART0_BASE 			0x10100

#define UART_CONTROL			0x0
#define UART_SETTINGS			0x1
#define UART_DATA			0x3
#define UART_TX_FILL			0x4
#define UART_RX_FILL			0x5

#define UART_CONTROL_ENABLE		0x2
#define UART_SETTINGS_PARITY_TYPE	0x1
#define UART_SETTINGS_PARITY_EN		0x2
#define UART_SETTINGS_STOP_BITS		0x4

#define UART_SETTINGS_DIVISOR_SHIFT	0x3
#define UART_FIFO_SIZE			128

#define UART0_DIV 54 // 100MHz / 16 / 115200 Hz = 54.253


/* Conventions for this File:
 *
 * R7 is return Address for functions
 * R4, R5, R6 are to be restored before function return
 * R0-R3 can be freely overwritten by functions / are used for return values or arguments
 *
 * */

.org 0x0
	always [0x0] // Halt
.org 0x10
	always [Uart0Setup]
	always [Main]

Uart0Setup:
	imm_set R0, UART0_BASE
	imm_set R1, UART0_DIV
	lshift R1, R1, UART_SETTINGS_DIVISOR_SHIFT
	store [R0 + UART_SETTINGS], R1
	imm_set R1, UART_CONTROL_ENABLE
	store [R0 + UART_CONTROL], R1

GetCharacter:
// reads 1 character from uart. Blocking waits until there is one.
// Args: None
// Returns: 
// 	R0: character read from uart
	imm_set R0, UART0_BASE
	imm_set R2, 0
	GetCharacter_TestRxEmpty: load R1, [R0 + UART_RX_FILL]
	g [GetCharacter_TestRxEmpty], R1, R2 // wait for non-empty rx fifo
	load R0, [R0 + UART_DATA]
	always [R7]

WriteCharacter:
// Writes one Character to the uart, blocking waits until it can.
// Args:
// 	R0: character to be written
// Return: None
	imm_set R1, UART0_BASE
	imm_set R2, UART_FIFO_SIZE
	WriteCharacter_TestTxFull: load R3, [R0 + UART_TX_FILL]
	ge [WriteCharacter_TestTxFull], R3, R2 // wait for non-full tx fifo
	store [R1 + UART_DATA], R0
	always [R7]

Main:
	imm_set R3, Main
	add R7, R3, 3
	always [GetCharacter]
	add R7, R3, 5
	always [WriteCharacter]
	always [Main]
