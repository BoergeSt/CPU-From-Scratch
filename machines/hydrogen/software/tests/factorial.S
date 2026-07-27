/* This is a simple Test which calculates the factorial of
some value X, which can be set freely */

#define X 10
.org 0x0
	always [0x0] // Halt
.org 0x10
	imm_set R0, 1	// initialize x = 1
	imm_set R1, 1	// initialize y = 1
	load R2, [loop_end]	// initialize X
loop:
	mul R1, R1, R0	// y=x*y
	add R0, R0, 1	// x=x+1
	le loop, R0, R2	// while x < X
end:
	imm_set R0, 0 // reset counter
	always [0x0] // Go to Halt
.org 0x20
loop_end: .word X

