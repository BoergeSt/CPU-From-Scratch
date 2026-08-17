
#include "lib/uart.S"
#include "lib/time.S"

.org // constants
Del_Sequence: .asciz "\b \b"

.org 0x0
	always [0x0] // Halt
.org 0x10
Main:
	imm_set STACK_REG, 0x1000 // end of bram
	CALL(UartSetup)

Main_Loop:
	CALL(GetCharacter)
	imm_set R1, '\x7F' 	// historical: uart sends del (0x7f) instead of backspace (\b)
	eq [Main_Delete], R0, R1
	CALL(PrintCharacter)
	imm_set R1, '\r'	// historical: uart sends \r instead of \n => check and do both
	eq [Main_NewLine], R0, R1
	always [Main_Loop]

Main_NewLine:
// already echoed \r above; also emit \n so the terminal gets a full CRLF
	imm_set R0, '\n'
	CALL(PrintCharacter)
	always [Main_Loop]

Main_Delete:
// destructive backspace: move back, overwrite with space, move back again
	imm_set R0, Del_Sequence
	CALL(Print)
	always [Main_Loop]
