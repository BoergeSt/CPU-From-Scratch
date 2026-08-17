#include "uart_include.h"
#include "timing.h"

.org 0x0
	always [0x0] // Halt
.org 0x10
Uart_Setup:
	imm_set R0, UART0_BASE
	imm_set R1, UART_DIV
	lshift R1, R1, UART_SETTINGS_DIVISOR_SHIFT
	store [R0 + UART_SETTINGS], R1
	imm_set	R1, UART_CONTROL_RESET
	or R1, R1, UART_CONTROL_ENABLE
	store [R0 + UART_CONTROL], R1

Main:
	imm_set R1, 0x48 //H
	store [R0 + UART_DATA], R1
	imm_set R1, 0x65 //e
	store [R0 + UART_DATA], R1
	imm_set R1, 0x6c //l
	store [R0 + UART_DATA], R1
	imm_set R1, 0x6c //l
	store [R0 + UART_DATA], R1
	imm_set R1, 0x6f //o
	store [R0 + UART_DATA], R1
	imm_set R1, 0x20 //<space>
	store [R0 + UART_DATA], R1
	imm_set R1, 0x57 //W
	store [R0 + UART_DATA], R1
	imm_set R1, 0x6f //o
	store [R0 + UART_DATA], R1
	imm_set R1, 0x72 //r
	store [R0 + UART_DATA], R1
	imm_set R1, 0x6c //l
	store [R0 + UART_DATA], R1
	imm_set R1, 0x64 //d
	store [R0 + UART_DATA], R1
	imm_set R1, 0x0d //<^M>
	store [R0 + UART_DATA], R1
	imm_set R1, 0x0a //<enter>
	store [R0 + UART_DATA], R1

	imm_set R6, 0 // Wait one second then repeat
	load R7, [WaitTime]
Wait:
	add R6, R6, 1
	le [Wait], R6, R7
	always [Main]
	
WaitTime: .word 5000000 // clockspeed // 2 cycles per loop




