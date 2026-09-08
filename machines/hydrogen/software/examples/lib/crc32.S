#pragma once
#include "../include/calling_convention.h"

.org

CRC32Polynomial:
.word 0xEDB88320

CRC32Word:
/* Folds one 32-bit word into a running CRC-32 accumulator, reflected
 * (bit-reversed) algorithm, polynomial 0xEDB88320, bytes processed
 * low-to-high (matches the assembler's little-endian string layout).
 * Args:
 *   R0: CRC Initial Value
 *   R1: Word
 * Returns:
 *   R0: CRC Value
 * Reg Map:
 *   R2: Byte Count (4...1)
 *   R3: Inner Count (8...1)
 *   R4: CRC Polynomial
 *   R5: Byte, Temporary If Condition
 * Pseudo Code:
 *   for byte_count in 4..1:
 *     byte = word AND 0xFF
 *     word = word >> 8
 *     crc = crc XOR byte
 *     for inner_count in 8..1:
 *       if crc AND 1:
 *         crc = (crc >> 1) XOR polynomial
 *       else:
 *         crc = crc >> 1
 *   return crc
 */
	PUSH(R2)
	PUSH(R3)
	PUSH(R4)
	PUSH(R5)
	load R4, [CRC32Polynomial]
	imm_set R2, 4
CRC32Word_ByteLoop:
	and R5, R1, 0xFF
	rshift R1, R1, 8
	xor R0, R0, R5
	imm_set R3, 8
CRC32Word_InnerLoop:
	and R5, R0, 1
	rshift R0, R0, 1
	z [CRC32Word_If_END], R5
	xor R0, R0, R4
CRC32Word_If_END:
	sub R3, R3, 1
	nz [CRC32Word_InnerLoop], R3
	sub R2, R2, 1
	nz [CRC32Word_ByteLoop], R2
CRC32Word_Cleanup:
	POP(R5)
	POP(R4)
	POP(R3)
	POP(R2)
	RETURN


CRC32:
/* Computes the standard CRC-32 (reflected, polynomial 0xEDB88320, init and
 * final XOR 0xFFFFFFFF) over a run of consecutive 32-bit words in memory,
 * folding each word in via CRC32Word.
 * Args:
 *   R0: Memory Address
 *   R1: Count in Words
 * Returns:
 *   R0: CRC32 sum
 * Reg Map:
 *   R0: CRC
 *   R1: loaded Word
 *   R2: Memory Address
 *   R3: Count (to zero)
 * Pseudo Code:
 *   crc = 0xFFFFFFFF
 *   if count == 0:
 *     return crc XOR 0xFFFFFFFF
 *   for i in 0..count-1:
 *     word = MEM[address + i]
 *     crc = CRC32Word(crc, word)
 *   return crc XOR 0xFFFFFFFF
 */
	PUSH(R2)
	PUSH(R3)
	PUSH(RET_REG)
	or R2, R0, 0
	or R3, R1, 0
	not R0, 0 // R0 = 0xFFFFFFFF
	z [CRC32_Cleanup], R1
CRC32_Loop:
	load R1, [R2]
	CALL(CRC32Word)
	add R2, R2, 1
	sub R3, R3, 1
	nz [CRC32_Loop], R3
CRC32_Cleanup:
	not R0, R0
	POP(RET_REG)
	POP(R3)
	POP(R2)
	RETURN
	
