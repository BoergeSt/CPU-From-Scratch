#pragma once

#include "hydrogen.h"

.org
UartSetup:
	imm_set R0, UART0_BASE
	imm_set R1, UART_DIV
	lshift R1, R1, UART_SETTINGS_DIVISOR_SHIFT
	store [R0 + UART_SETTINGS], R1
	imm_set	R1, UART_CONTROL_RESET
	or R1, R1, UART_CONTROL_ENABLE
	store [R0 + UART_CONTROL], R1
	RETURN

GetCharacter:
// reads 1 character from uart. Blocking waits until there is one.
// Args: None
// Returns: 
// 	R0: character read from uart
	imm_set R0, UART0_BASE
GetCharacter_TestRxEmpty: load R1, [R0 + UART_RX_FILL]
	z [GetCharacter_TestRxEmpty], R1 // wait for non-empty rx fifo
	load R0, [R0 + UART_DATA]
	RETURN

PrintCharacter:
// Writes one Character to the uart, blocking waits until it can.
// Args:
// 	R0: character to be written
// Return: None
	PUSH(R2)
	PUSH(R3)
	imm_set R1, UART0_BASE
	imm_set R2, UART_FIFO_SIZE
PrintCharacter_TestTxFull: load R3, [R1 + UART_TX_FILL]
	ge [PrintCharacter_TestTxFull], R3, R2 // wait for non-full tx fifo
	store [R1 + UART_DATA], R0
	POP(R3)
	POP(R2)
	RETURN

Print:
/* Writes a Zero terminated string from Memory to Uart. The string needs to be stored
 * in little endian and must go to increasing word addresses
 * May blocking wait if the UART fifo is full. Be sure to enable it previously or
 * this function might wait endlessly for the fifo to clear.
 * Args:
 * R0: Pointer to String
 * Return: None
 */
 	PUSH(RET_REG)
	PUSH(R2)
	PUSH(R3)
	PUSH(R4)
	or R2, R0, 0 			// save input pointer
	imm_set R4, 24			// last value offset counter
Print_Word_Loop:
	imm_set R3, 0 			// set offset counter (0/8/16/24)
Print_Char_Loop:
	load R0, [R2]			// load Word from ram
	rshift R0, R0, R3		// shift to active char
	and R0, R0, 0xFF 		// only keep lowest byte
	z [Print_Cleanup], R0		// Finished if current Char is 0x0
	CALL(PrintCharacter)		// display current Char
	eq [Print_Next_Word], R3, R4 	// if Last Char in Word go to next word
	add R3, R3, 8			// next offset
	always [Print_Char_Loop]
Print_Next_Word:
	add R2, R2, 1
	always [Print_Word_Loop]	
Print_Cleanup:
	POP(R4)
	POP(R3)
	POP(R2)
	POP(RET_REG)
	RETURN





