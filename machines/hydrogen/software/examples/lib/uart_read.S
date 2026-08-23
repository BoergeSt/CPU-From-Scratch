#pragma once
#include "uart.S"

ReadWord:
/* Reads 4 characters from uart and packs them into one word, low byte first
 * (the first character read ends up in bits [7:0]), matching the byte order
 * Print expects when writing a word back out. Blocking waits for each
 * character; see GetCharacter.
 * Args: None
 * Returns:
 *   R0: word of 4 read chars
 * Reg-Map:
 *   R2: chars left to read
 *   R3: word under construction
 */
	PUSH(RET_REG)
	PUSH(R2)
	PUSH(R3)
	imm_set R2, 4
	imm_set R3, 0
ReadWord_Loop:
	rshift R3, R3, 8 	// make room: shift already-read bytes down
	CALL(GetCharacter)
	lshift R0, R0, 24 	// move new byte to the top byte
	or R3, R3, R0		// append new byte (add/or are equivalent)
	sub R2, R2, 1
	nz [ReadWord_Loop], R2
ReadWord_Cleanup:
	or R0, R3, 0
	POP(R3)
	POP(R2)
	POP(RET_REG)
	RETURN

ReadWords:
/* Reads a fixed count of words from uart into memory via repeated ReadWord
 * calls, storing to increasing word addresses starting at the given base.
 * Raw copy: no byte value is treated specially, so this is suited to
 * downloading binary data rather than reading a delimited line.
 * Args:
 *   R0 Memory Address
 *   R1 Word Count
 * Result: None
 * Reg-Map:
 *   R2: persistent Memory Address
 *   R3: persistent Word Counter
 */
	PUSH(RET_REG)
	PUSH(R2)
	PUSH(R3)
	or R2, R0, 0
	or R3, R1, 0
ReadWords_Next:
	z [ReadWords_Cleanup], R3
	CALL(ReadWord)
	store [R2], R0
	sub R3, R3, 1
	add R2, R2, 1
	always [ReadWords_Next]
ReadWords_Cleanup:
	POP(R3)
	POP(R2)
	POP(RET_REG)
	RETURN
