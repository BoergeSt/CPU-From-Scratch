"""cocotb testbench for the Hydrogen ALU (see docs/machines/hydrogen/alu.md).

The ALU is purely combinational (no clock/reset), so each test just drives
operation_i/value1_i/value2_i and awaits a small delay for the combinational
logic to settle before checking result_o/overflow_o.
"""

import cocotb
from cocotb.triggers import Timer

ADD = 0x0
SUB = 0x1
MUL = 0x2
MULH = 0x3
LSHIFT = 0x4
RSHIFT = 0x5
AND = 0x6
OR = 0x7
XOR = 0x8
NOT = 0x9
NAND = 0xA
NOR = 0xB

MASK32 = 0xFFFF_FFFF

SETTLE_TIME = Timer(1, unit="ns")


async def apply(dut, operation, value1, value2):
    dut.operation_i.value = operation
    dut.value1_i.value = value1
    dut.value2_i.value = value2
    await SETTLE_TIME


def check(dut, expected_result, expected_overflow, description):
    actual_result = int(dut.result_o.value)
    actual_overflow = int(dut.overflow_o.value)
    assert actual_result == expected_result, (
        f"{description}: result_o = {actual_result:#010x}, "
        f"expected {expected_result:#010x}"
    )
    assert actual_overflow == expected_overflow, (
        f"{description}: overflow_o = {actual_overflow}, "
        f"expected {expected_overflow}"
    )


# (value1, value2, expected_result, expected_overflow, description)
ADD_CASES = [
    (5, 10, 15, 0, "simple add, no overflow"),
    (0, 0, 0, 0, "zero + zero"),
    (0x1234_5678, 0, 0x1234_5678, 0, "add zero is identity"),
    (0xFFFF_FFFF, 0x1, 0x0000_0000, 1, "wraps to zero at the 2**32 boundary"),
    (0xFFFF_FFFE, 0x1, 0xFFFF_FFFF, 0, "largest sum that still fits, just below overflow"),
    (0xFFFF_FFFF, 0xFFFF_FFFF, 0xFFFF_FFFE, 1, "max + max"),
]

SUB_CASES = [
    (10, 5, 5, 0, "simple sub, no underflow"),
    (5, 5, 0, 0, "equal operands, boundary of the overflow condition"),
    (0, 1, 0xFFFF_FFFF, 1, "underflow by one"),
    (0, 0xFFFF_FFFF, 0x0000_0001, 1, "underflow, max value2_i"),
    (0xFFFF_FFFF, 0xFFFF_FFFF, 0, 0, "max - max"),
    (0xFFFF_FFFF, 0, 0xFFFF_FFFF, 0, "subtract zero is identity"),
]

MUL_CASES = [
    (3, 4, 12, 0, "simple mul, no overflow"),
    (0, 0xFFFF_FFFF, 0, 0, "multiply by zero"),
    (0xFFFF_FFFF, 1, 0xFFFF_FFFF, 0, "multiply by one is identity"),
    (0xFFFF, 0x1_0000, 0xFFFF_0000, 0, "largest product that still fits in 32 bits"),
    (0x1_0000, 0x1_0000, 0, 1, "smallest product that overflows, exactly 2**32"),
    (0xFFFF_FFFF, 0xFFFF_FFFF, 0x0000_0001, 1, "max * max"),
]

# MULH never sets overflow_o -- it's the part MUL would otherwise drop.
MULH_CASES = [
    (3, 4, 0, 0, "small product fits entirely in the low word"),
    (0, 0xFFFF_FFFF, 0, 0, "multiply by zero"),
    (0xFFFF_FFFF, 1, 0, 0, "multiply by one is identity, high word still zero"),
    (0x1_0000, 0x1_0000, 1, 0, "smallest product that spills into the high word"),
    (0xFFFF_FFFF, 0xFFFF_FFFF, 0xFFFF_FFFE, 0, "max * max"),
    (0x1234_5678, 0x8765_4321, 0x09A0_CD05, 0, "arbitrary values, both words nonzero"),
]

# LSHIFT overflow: for shift amount n<32, overflow iff the top n bits of
# value1_i are nonzero; for n>=32, overflow iff value1_i != 0.
LSHIFT_CASES = [
    (0x1, 4, 0x10, 0, "simple shift, no overflow"),
    (0x1234_5678, 0, 0x1234_5678, 0, "shift by zero is identity, never overflows"),
    (0x8000_0000, 1, 0, 1, "top bit shifted out"),
    (0x5, 32, 0, 1, "shift amount exactly 32, nonzero operand"),
    (0x0, 32, 0, 0, "shift amount exactly 32, zero operand"),
    (0x1, 31, 0x8000_0000, 0, "largest in-range shift that still fits"),
    (0x5, 1000, 0, 1, "shift amount far beyond 32, nonzero operand"),
]

# RSHIFT never sets overflow_o -- truncating a value via right shift isn't
# data loss in the same sense as the other ops.
RSHIFT_CASES = [
    (0x80, 4, 0x8, 0, "simple shift, no overflow"),
    (0x1234_5678, 0, 0x1234_5678, 0, "shift by zero is identity"),
    (0xFFFF_FFFF, 32, 0, 0, "shift amount exactly 32"),
    (0x1234_5678, 1000, 0, 0, "shift amount far beyond 32"),
    (0x1, 1, 0, 0, "only set bit shifted out"),
    (0x8000_0000, 31, 0x1, 0, "top bit shifted all the way down"),
]

AND_CASES = [
    (0xFF00, 0x0FF0, 0x0F00, 0, "simple and"),
    (0xFFFF_FFFF, 0x1234_5678, 0x1234_5678, 0, "all-ones is identity"),
    (0x1234_5678, 0, 0, 0, "and zero is zero"),
    (0xABCD_EF01, 0xABCD_EF01, 0xABCD_EF01, 0, "and with itself is itself"),
    (0xAAAA_AAAA, 0x5555_5555, 0, 0, "complementary bit patterns"),
]

OR_CASES = [
    (0xFF00, 0x00FF, 0xFFFF, 0, "simple or"),
    (0x1234_5678, 0, 0x1234_5678, 0, "or zero is identity"),
    (0x1234_5678, 0xFFFF_FFFF, 0xFFFF_FFFF, 0, "or all-ones is all-ones"),
    (0xAAAA_AAAA, 0x5555_5555, 0xFFFF_FFFF, 0, "complementary bit patterns"),
    (0xABCD_EF01, 0xABCD_EF01, 0xABCD_EF01, 0, "or with itself is itself"),
]

XOR_CASES = [
    (0xFF00, 0x0FF0, 0xF0F0, 0, "simple xor"),
    (0x1234_5678, 0, 0x1234_5678, 0, "xor zero is identity"),
    (0x1234_5678, 0x1234_5678, 0, 0, "xor with itself is zero"),
    (0x1234_5678, 0xFFFF_FFFF, 0xEDCB_A987, 0, "xor all-ones is complement"),
    (0xAAAA_AAAA, 0x5555_5555, 0xFFFF_FFFF, 0, "complementary bit patterns"),
]

# NOT is unary -- value2_i is ignored, so the last two cases share value1_i
# with different value2_i to confirm it has no effect on the result.
NOT_CASES = [
    (0x0, 0x0, 0xFFFF_FFFF, 0, "not zero is all-ones"),
    (0xFFFF_FFFF, 0x0, 0, 0, "not all-ones is zero"),
    (0x1234_5678, 0x0, 0xEDCB_A987, 0, "arbitrary value"),
    (0xAAAA_AAAA, 0x0, 0x5555_5555, 0, "value2_i = 0 is ignored"),
    (0xAAAA_AAAA, 0xFFFF_FFFF, 0x5555_5555, 0, "value2_i = all-ones is still ignored"),
]

NAND_CASES = [
    (0xFF00, 0x0FF0, 0xFFFF_F0FF, 0, "simple nand"),
    (0x1234_5678, 0, 0xFFFF_FFFF, 0, "nand zero is all-ones"),
    (0x1234_5678, 0xFFFF_FFFF, 0xEDCB_A987, 0, "nand all-ones is complement"),
    (0xABCD_EF01, 0xABCD_EF01, 0x5432_10FE, 0, "nand with itself is complement of itself"),
    (0xAAAA_AAAA, 0x5555_5555, 0xFFFF_FFFF, 0, "complementary bit patterns"),
]

NOR_CASES = [
    (0xFF00, 0x00FF, 0xFFFF_0000, 0, "simple nor"),
    (0x1234_5678, 0, 0xEDCB_A987, 0, "nor zero is complement"),
    (0x1234_5678, 0xFFFF_FFFF, 0, 0, "nor all-ones is zero"),
    (0xAAAA_AAAA, 0x5555_5555, 0, 0, "complementary bit patterns"),
    (0xABCD_EF01, 0xABCD_EF01, 0x5432_10FE, 0, "nor with itself is complement of itself"),
]


@cocotb.test()
async def test_add(dut):
    for value1, value2, expected_result, expected_overflow, description in ADD_CASES:
        await apply(dut, ADD, value1, value2)
        check(dut, expected_result, expected_overflow, f"ADD({description})")


@cocotb.test()
async def test_sub(dut):
    for value1, value2, expected_result, expected_overflow, description in SUB_CASES:
        await apply(dut, SUB, value1, value2)
        check(dut, expected_result, expected_overflow, f"SUB({description})")


@cocotb.test()
async def test_mul(dut):
    for value1, value2, expected_result, expected_overflow, description in MUL_CASES:
        await apply(dut, MUL, value1, value2)
        check(dut, expected_result, expected_overflow, f"MUL({description})")


@cocotb.test()
async def test_mulh(dut):
    for value1, value2, expected_result, expected_overflow, description in MULH_CASES:
        await apply(dut, MULH, value1, value2)
        check(dut, expected_result, expected_overflow, f"MULH({description})")


@cocotb.test()
async def test_lshift(dut):
    for value1, value2, expected_result, expected_overflow, description in LSHIFT_CASES:
        await apply(dut, LSHIFT, value1, value2)
        check(dut, expected_result, expected_overflow, f"LSHIFT({description})")


@cocotb.test()
async def test_rshift(dut):
    for value1, value2, expected_result, expected_overflow, description in RSHIFT_CASES:
        await apply(dut, RSHIFT, value1, value2)
        check(dut, expected_result, expected_overflow, f"RSHIFT({description})")


@cocotb.test()
async def test_and(dut):
    for value1, value2, expected_result, expected_overflow, description in AND_CASES:
        await apply(dut, AND, value1, value2)
        check(dut, expected_result, expected_overflow, f"AND({description})")


@cocotb.test()
async def test_or(dut):
    for value1, value2, expected_result, expected_overflow, description in OR_CASES:
        await apply(dut, OR, value1, value2)
        check(dut, expected_result, expected_overflow, f"OR({description})")


@cocotb.test()
async def test_xor(dut):
    for value1, value2, expected_result, expected_overflow, description in XOR_CASES:
        await apply(dut, XOR, value1, value2)
        check(dut, expected_result, expected_overflow, f"XOR({description})")


@cocotb.test()
async def test_not(dut):
    for value1, value2, expected_result, expected_overflow, description in NOT_CASES:
        await apply(dut, NOT, value1, value2)
        check(dut, expected_result, expected_overflow, f"NOT({description})")


@cocotb.test()
async def test_nand(dut):
    for value1, value2, expected_result, expected_overflow, description in NAND_CASES:
        await apply(dut, NAND, value1, value2)
        check(dut, expected_result, expected_overflow, f"NAND({description})")


@cocotb.test()
async def test_nor(dut):
    for value1, value2, expected_result, expected_overflow, description in NOR_CASES:
        await apply(dut, NOR, value1, value2)
        check(dut, expected_result, expected_overflow, f"NOR({description})")
