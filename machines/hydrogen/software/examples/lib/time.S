#pragma once
#include "../include/calling_convention.h"

.org
WaitCycles:
/* waits for N CPU cycles
 * Args:
 *   R0: N cycles
 * Returns: None
*/
	rshift R0, R0, 1;
	imm_set R1, 0
WaitCycles_Loop:
	add R1, R1, 1
	l [WaitCycles_Loop], R1, R0
	RETURN


