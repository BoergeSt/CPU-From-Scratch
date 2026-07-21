"""cocotb testbench for the Hydrogen ALU (see machines/hydrogen/docs/alu.md).

Purely combinational (no clock/reset): each test drives bus.instruction (the
entire 32-bit fetched instruction word, see isa.md's ALU encoding)/
bus.value1/bus.value2, awaits a small settle delay, then checks
bus.result/bus.overflow/bus.error.
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

ALU_MAJOR_OPCODE = 0x7
IMM_MASK = 0x1FFF  # 13 bits

SETTLE_TIME = Timer(1, unit="ns")


def make_opcode(alu_op, is_imm_src1=0, is_imm_src2=0, imm=0):
    """Assemble the 32-bit ALU instruction word (isa.md): major opcode
    [31:28]=ALU, alu_op [24:21], is_imm_src1 [20], is_imm_src2 [19],
    imm [18:6]. dest/src1_addr/src2_addr [27:25]/[5:3]/[2:0] are left 0 --
    the ALU module itself doesn't consume them, only regfile address
    routing (outside this module) does."""
    return (
        (ALU_MAJOR_OPCODE & 0xF) << 28
        | (alu_op & 0xF) << 21
        | (is_imm_src1 & 0x1) << 20
        | (is_imm_src2 & 0x1) << 19
        | (imm & IMM_MASK) << 6
    )


async def apply(dut, operation, value1, value2, is_imm_src1=0, is_imm_src2=0, imm=0):
    dut.bus.instruction.value = make_opcode(operation, is_imm_src1, is_imm_src2, imm)
    dut.bus.value1.value = value1
    dut.bus.value2.value = value2
    await SETTLE_TIME


def check(dut, expected_result, expected_overflow, description, expected_error=0):
    actual_result = int(dut.bus.result.value)
    actual_overflow = int(dut.bus.overflow.value)
    actual_error = int(dut.bus.error.value)
    assert actual_result == expected_result, (
        f"{description}: bus.result = {actual_result:#010x}, "
        f"expected {expected_result:#010x}"
    )
    assert actual_overflow == expected_overflow, (
        f"{description}: bus.overflow = {actual_overflow}, "
        f"expected {expected_overflow}"
    )
    assert actual_error == expected_error, (
        f"{description}: bus.error = {actual_error}, expected {expected_error}"
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
    (0, 0xFFFF_FFFF, 0x0000_0001, 1, "underflow, max value2"),
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

# MULH never sets bus.overflow -- it's the part MUL would otherwise drop.
MULH_CASES = [
    (3, 4, 0, 0, "small product fits entirely in the low word"),
    (0, 0xFFFF_FFFF, 0, 0, "multiply by zero"),
    (0xFFFF_FFFF, 1, 0, 0, "multiply by one is identity, high word still zero"),
    (0x1_0000, 0x1_0000, 1, 0, "smallest product that spills into the high word"),
    (0xFFFF_FFFF, 0xFFFF_FFFF, 0xFFFF_FFFE, 0, "max * max"),
    (0x1234_5678, 0x8765_4321, 0x09A0_CD05, 0, "arbitrary values, both words nonzero"),
]

# LSHIFT overflow: for shift amount n<32, overflow iff the top n bits of
# value1 are nonzero; for n>=32, overflow iff value1 != 0.
LSHIFT_CASES = [
    (0x1, 4, 0x10, 0, "simple shift, no overflow"),
    (0x1234_5678, 0, 0x1234_5678, 0, "shift by zero is identity, never overflows"),
    (0x8000_0000, 1, 0, 1, "top bit shifted out"),
    (0x5, 32, 0, 1, "shift amount exactly 32, nonzero operand"),
    (0x0, 32, 0, 0, "shift amount exactly 32, zero operand"),
    (0x1, 31, 0x8000_0000, 0, "largest in-range shift that still fits"),
    (0x5, 1000, 0, 1, "shift amount far beyond 32, nonzero operand"),
]

# RSHIFT never sets bus.overflow -- truncating a value via right shift isn't
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

# NOT is unary -- value2 is ignored, so the last two cases share value1
# with different value2 to confirm it has no effect on the result.
NOT_CASES = [
    (0x0, 0x0, 0xFFFF_FFFF, 0, "not zero is all-ones"),
    (0xFFFF_FFFF, 0x0, 0, 0, "not all-ones is zero"),
    (0x1234_5678, 0x0, 0xEDCB_A987, 0, "arbitrary value"),
    (0xAAAA_AAAA, 0x0, 0x5555_5555, 0, "value2 = 0 is ignored"),
    (0xAAAA_AAAA, 0xFFFF_FFFF, 0x5555_5555, 0, "value2 = all-ones is still ignored"),
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


# (name, opcode, cases) -- drives the dynamic test generation below.
OPS = [
    ("add", ADD, ADD_CASES),
    ("sub", SUB, SUB_CASES),
    ("mul", MUL, MUL_CASES),
    ("mulh", MULH, MULH_CASES),
    ("lshift", LSHIFT, LSHIFT_CASES),
    ("rshift", RSHIFT, RSHIFT_CASES),
    ("and", AND, AND_CASES),
    ("or", OR, OR_CASES),
    ("xor", XOR, XOR_CASES),
    ("not", NOT, NOT_CASES),
    ("nand", NAND, NAND_CASES),
    ("nor", NOR, NOR_CASES),
]


def _make_test(operation, cases, name):
    async def _test(dut):
        for value1, value2, expected_result, expected_overflow, description in cases:
            await apply(dut, operation, value1, value2)
            check(dut, expected_result, expected_overflow,
                  f"{name.upper()}({description})")
    _test.__name__ = f"test_{name}"
    _test.__qualname__ = f"test_{name}"
    return _test


for _name, _opcode, _cases in OPS:
    globals()[f"test_{_name}"] = cocotb.test()(_make_test(_opcode, _cases, _name))


RESERVED_OPCODES = [0xC, 0xD, 0xE, 0xF]

RESERVED_OPERAND_CASES = [
    (0, 0, "all-zero operands"),
    (0xFFFF_FFFF, 0xFFFF_FFFF, "all-ones operands"),
    (0x1234_5678, 0x8765_4321, "arbitrary operands"),
]


@cocotb.test()
async def test_reserved_opcodes_flag_error(dut):
    """Every reserved opcode (0xC-0xF) drives bus.result=0, bus.overflow=0,
    bus.error=1 regardless of operands -- see alu.md's Errors section and
    CLAUDE.md's illegal-instruction-exception item."""
    for opcode in RESERVED_OPCODES:
        for value1, value2, description in RESERVED_OPERAND_CASES:
            await apply(dut, opcode, value1, value2)
            check(
                dut, 0, 0,
                f"reserved opcode {opcode:#x} ({description})",
                expected_error=1,
            )


# (imm, other_operand, expected_result, description)
IMM_SRC1_CASES = [
    (0, 50, 50, "imm=0 as src1"),
    (100, 50, 150, "arbitrary imm as src1"),
    (0x1FFF, 1, 0x2000, "max 13-bit imm (8191) as src1, zero-extended"),
]

IMM_SRC2_CASES = [
    (50, 0, 50, "imm=0 as src2"),
    (50, 100, 150, "arbitrary imm as src2"),
    (1, 0x1FFF, 0x2000, "max 13-bit imm (8191) as src2, zero-extended"),
]


@cocotb.test()
async def test_imm_as_src1(dut):
    """is_imm_src1=1 substitutes `imm` for value1 -- bus.value1 (the raw
    register read) is ignored/don't-care in this case."""
    for imm, value2, expected_result, description in IMM_SRC1_CASES:
        await apply(dut, ADD, 0xDEAD_BEEF, value2, is_imm_src1=1, imm=imm)
        check(dut, expected_result, 0, f"ADD(imm src1, {description})")


@cocotb.test()
async def test_imm_as_src2(dut):
    """is_imm_src2=1 substitutes `imm` for value2 -- bus.value2 (the raw
    register read) is ignored/don't-care in this case."""
    for value1, imm, expected_result, description in IMM_SRC2_CASES:
        await apply(dut, ADD, value1, 0xDEAD_BEEF, is_imm_src2=1, imm=imm)
        check(dut, expected_result, 0, f"ADD(imm src2, {description})")


@cocotb.test()
async def test_imm_operand_order_preserved_for_sub(dut):
    """SUB is order-sensitive -- confirms an immediate substituted for src1
    vs src2 lands on the correct side of the subtraction, not just that
    *some* substitution happened (ADD alone can't catch a swapped operand
    order, since it's commutative)."""
    await apply(dut, SUB, 0xDEAD_BEEF, 30, is_imm_src1=1, imm=100)
    check(dut, 70, 0, "SUB(imm src1=100, value2=30), expect 100-30")

    await apply(dut, SUB, 100, 0xDEAD_BEEF, is_imm_src2=1, imm=30)
    check(dut, 70, 0, "SUB(value1=100, imm src2=30), expect 100-30")
