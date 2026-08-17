#include "lib/uart.S"
#include "lib/time.S"

.org // constants
WaitTime: .word CLOCK_SPEED // == 1 second
Message: .asciz "Hello World!\r\n"

.org 0x0
	always [0x0] // Halt
.org 0x10
Main:
	imm_set STACK_REG, 0x1000 // end of bram
	CALL(UartSetup)

Main_Loop:
	imm_set R0, Message
	CALL(Print)
	load R0, [WaitTime]
	CALL(WaitCycles)
	always [Main_Loop]

