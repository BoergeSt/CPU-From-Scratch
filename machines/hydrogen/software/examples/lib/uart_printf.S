#pragma once
#include "uart.S"

.org
IntegersHex_LUT:
.word '0'
.word '1'
.word '2'
.word '3'
.word '4'
.word '5'
.word '6'
.word '7'
.word '8'
.word '9'
.word 'a'
.word 'b'
.word 'c'
.word 'd'
.word 'e'
.word 'f'

// Advances the character-cursor state (R2: word pointer, R3: bit offset
// within that word) to the next character position, wrapping R2 to the
// next word and resetting R3 to 0 once the current offset was the word's
// last byte (24). PRINTF_ macros use R1 as a temporary.
#define PRINTF_ADVANCE_POINTERS(label) \
	imm_set R1, 24 ;\
	eq [CONCAT(label,_NEXT_CHARACTER)],R3, R1 ;\
	add R3, R3, 8 ;\
	always [CONCAT(label,_DONE)] ;\
	CONCAT(label,_NEXT_CHARACTER): \
	add R2, R2, 1 ;\
	imm_set R3, 0 ;\
	CONCAT(label,_DONE):

// Loads the character at the current R2/R3 cursor into R0, then advances
// the cursor to the next character via PRINTF_ADVANCE_POINTERS.
#define PRINTF_LOAD_NEXT_CHARACTER \
	load R0, [R2] ;\
	rshift R0, R0, R3 ;\
	and R0, R0, 0xFF ;\
	PRINTF_ADVANCE_POINTERS(CONCAT(Printf_Next_Character_,__COUNTER__))

PrintIntegerHex:
/* Writes R0 to the UART as 8 hex digits, most-significant nibble first.
 * Always fixed-width: no leading-zero suppression, no "0x" prefix.
 * Args:
 *   R0: value to print
 * Returns: None
 *
 * Regmap:
 * R2: temp (nibble value, then LUT address)
 * R3: persistent copy of the input value
 * R4: pointer to IntegersHex_LUT
 * R5: bit-shift amount, 28 down to 0 in steps of 4
 */
 	PUSH(R2)
	PUSH(R3)
	PUSH(R4)
	PUSH(R5)
	PUSH(RET_REG)
	or R3, R0, 0
	imm_set R5, 32
	imm_set R4, IntegersHex_LUT
PrintIntegerHex_Skip_Initial_Zeros:
	sub R5, R5, 4
	rshift R2, R3, R5
	and R2, R2, 0xF
	nz [PrintIntegerHex_Display], R2
	z [PrintIntegerHex_Display], R5
	always [PrintIntegerHex_Skip_Initial_Zeros]
PrintIntegerHex_Loop:
	sub R5, R5, 4
	rshift R2, R3, R5
	and R2, R2, 0xF
PrintIntegerHex_Display:
	add R2, R2, R4
	load R0, [R2]
	CALL(PrintCharacter)
	nz [PrintIntegerHex_Loop], R5
	POP(RET_REG)
	POP(R5)
	POP(R4)
	POP(R3)
	POP(R2)
	RETURN

Printf:
/* Writes a format string from memory to the UART, substituting each `%`
 * conversion with its corresponding stack argument. A `%` followed by an
 * unrecognized conversion character is echoed literally (both characters,
 * unchanged) rather than consuming an argument.
 * Formatters:
 * %% -> Emits a literal % character
 * %s -> Substitutes a zero-terminated string at the argument's address
 *       (no recursive substitution)
 * %x -> Substitutes the argument as 8 fixed-width hex digits (PrintIntegerHex)
 * Args:
 *   R0: pointer to the format string
 *   Stack: one entry per `%` conversion, pushed right-to-left (the format
 *     string's last conversion pushed first) so its first conversion ends
 *     up on top of the stack
 * Returns: None
 *
 * Register map:
 * R1: scratch (comparisons); also holds the caller's pre-call stack
 *     pointer briefly at entry, before argument access starts -- see
 *     PRINTF_ macros above for their own use of R1
 * R2: pointer to the word holding the next format-string character
 * R3: bit offset of that character within its word (0/8/16/24)
 * R4: pointer to the next stack argument to substitute
 */
 	or R1, STACK_REG, 0		// save the pre-function stack pointer to R1, which is caller saved
	PUSH(R2)
	PUSH(R3)
	PUSH(R4)
	PUSH(RET_REG)
	or R2, R0, 0 			// move the String Pointer to R2
	imm_set R3, 0			// Initialize Character Offset
	or R4, R1, 0			// move the Arguments Pointer to R4
	
Printf_Read_Next:
	PRINTF_LOAD_NEXT_CHARACTER	
	z [Printf_Cleanup],R0
	imm_set R1, '%'
	eq [Printf_Start_Substitution],R0,R1
	CALL(PrintCharacter)
	always [Printf_Read_Next]
	
Printf_Start_Substitution:
	PRINTF_LOAD_NEXT_CHARACTER	
	imm_set R1, '%'
	eq [Printf_Substitute_Percent], R0, R1
	imm_set R1, 's'
	eq [Printf_Substitute_String], R0, R1
	imm_set R1, 'x'
	eq [Printf_Substitute_Hex], R0, R1
	// Unknown substitution:
	PUSH(R0)
	imm_set R0, '%'
	CALL(PrintCharacter)
	POP(R0)
	CALL(PrintCharacter)
	always [Printf_Read_Next]

Printf_Substitute_Percent:
	CALL(PrintCharacter)
	always [Printf_Read_Next]

Printf_Substitute_String:
	load R0, [R4]			// Load Argument
	add R4, R4, 1			// advance Arguments Pointer
	CALL(Print)
	always [Printf_Read_Next]

Printf_Substitute_Hex:
	load R0, [R4]
	add R4, R4, 1
	CALL(PrintIntegerHex)
	always [Printf_Read_Next]

Printf_Cleanup:
	POP(RET_REG)
	POP(R4)
	POP(R3)
	POP(R2)
	RETURN

