#include "lib/uart_printf.S"
#include "lib/time.S"

.org // constants
WaitTime: .word CLOCK_SPEED // == 1 second
Message: .asciz "Hello %s!\r\nPrinting Percent signs (%%) also works, and if i do an unknown substitution like %f it is printed out without change!\r\nDisplaying numbers in hex (0x%x, 0x%x, 0x%x) is now also working.\r\n"
World_Substitution: .asciz "World"
Number: .word 0xdeadbeef

.org 0x0
	always [0x0] // Halt
.org 0x10
Main:
	imm_set STACK_REG, 0x1000 // end of bram
	CALL(UartSetup)

Main_Loop:
	imm_set R0, 0x0
	PUSH(R0)
	imm_set R0, 0x42
	PUSH(R0)
	load R0, [Number]
	PUSH(R0)
	imm_set R0, World_Substitution
	PUSH(R0)
	imm_set R0, Message
	CALL(Printf)
	STACK_FREE(2)

	load R0, [WaitTime]
	CALL(WaitCycles)
	always [Main_Loop]

