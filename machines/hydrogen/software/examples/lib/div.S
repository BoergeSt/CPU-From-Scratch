#pragma once
#include "../include/calling_convention.h"

.org
Division:
/* Do a restoring division N/D = Q mod R
 * Args:
 *   R0: N (Numerator)
 *   R1: D (Denominator)
 * Results:
 *   R0: Q (integer Quotient)
 *   R1: R (modulus/Reminder)
 *
 * The implementation uses the following pseudo code:
 * R := 0
 * for i := n − 1 .. 0 do
 *   c := R[n−1]                -- top bit of R, about to be shifted off
 *   R := (R << 1) | N[i]       -- shift remainder left, bring in next dividend bit
 *   if c = 1 or R >= D then
 *     R := R − D                -- n-bit wraparound subtract; still correct when c = 1
 *     q(i) := 1
 *   else
 *     q(i) := 0
 *   end
 * end
 * For the implementation we use:
 * - R0: N
 * - R1: D
 * - R2: i
 * - R3: R
 * - R4: Q
 * - R5: temp (N[i])
 */ 
	PUSH(R2)
	PUSH(R3)
	PUSH(R4)
	PUSH(R5)
	imm_set R3, 0			// R := 0
	imm_set R4, 0			// Q := 0
	imm_set R2, 32			// i := 32
Division_For:
	sub R2, R2, 1			// i := i-1
	rshift R5, R0, R2		// temp := N << i
	and R5, R5, 0x1			// N[i] := temp && 0x1
	lshift R3, R3, 1		// R := R << 1
	overflow [Division_Error_Bit]
	or R3, R3, R5			// R := R | N[i]
	l [Division_For_End], R3, R1	// if R < D => q[i] = 0 (by initialization already given)
Division_Reminder_Update:
	sub R3, R3, R1			// R := R - D
	lshift R5, 1, R2		// temp := 1 << i
	or R4, R4, R5			// Q := Q || temp => Q[i] = 1
Division_For_End:
	z [Division_Cleanup], R2	// if i == 0: stop
	always [Division_For]
Division_Error_Bit: 			// c == 1
	or R3, R3, R5			// R := R | N[i]
	always [Division_Reminder_Update]
Division_Cleanup:
	or R1, R3, 0
	or R0, R4, 0
	POP(R5)
	POP(R4)
	POP(R3)
	POP(R2)
	RETURN

