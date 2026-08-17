// Register roles and stack layout: docs/assembler.md, "Calling convention".
#pragma once

#define CONCAT2(a,b) a##b
#define CONCAT(a,b) CONCAT2(a,b) // indirection so ## sees __COUNTER__'s expansion, not the literal token.

#define RET_REG R7
#define STACK_REG R6

#define PUSH(reg) sub STACK_REG, STACK_REG, 1; store [STACK_REG], reg;
#define POP(reg) load reg, [STACK_REG]; add STACK_REG, STACK_REG, 1;

// Nested CALLs: saving RET_REG before the inner call is on the caller, same as any callee-saved register.
#define CALL_IMPL(func,return_label) imm_set RET_REG, return_label ;always [func]; return_label:
#define CALL(func) CALL_IMPL(func,CONCAT(ret_,__COUNTER__))

#define RETURN always [RET_REG]

