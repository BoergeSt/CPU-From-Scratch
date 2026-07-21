"""cocotb testbench for the Hydrogen flow-control unit (see
machines/hydrogen/docs/flow_ctl.md).

Synchronous, active-high reset; `bus.pc` is registered. Each test starts its
own clock and drives its own reset to a known state (pc = ResetVector),
since the DUT's pc persists across tests within one simulation run.
Register-operand *addressing* ([2:0]/[5:3]/[8:6] of bus.instruction) is outside
this module's own scope (CLAUDE.md's fixed-register-position decision --
regfile reads are resolved system-wide, not by this module) so tests drive
bus.value1/bus.value2/bus.goto directly, as if already resolved, and leave
those bit positions in bus.instruction as don't-care (0).
"""

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer

CLOCK_PERIOD_NS = 10
SETTLE = Timer(1, unit="ns")

FLOW_CTL_MAJOR_OPCODE = 0x2
OTHER_MAJOR_OPCODE = 0x0  # ALU -- anything != FLOW_CTL works for self-detection tests

NOP = 0x0
L = 0x1
LE = 0x2
G = 0x3
GE = 0x4
Z = 0x5
NZ = 0x6
EQ = 0x7
NEQ = 0x8
ALWAYS = 0x9
OVERFLOW = 0xA
NOT_OVERFLOW = 0xB

RESET_VECTOR = 0x10
ERROR_VECTOR = 0x0

MASK32 = 0xFFFF_FFFF


def make_opcode(op, r=0, i=0, imm=0, major_opcode=FLOW_CTL_MAJOR_OPCODE):
    """Assemble the 32-bit instruction word (isa.md): major opcode [31:28],
    r [27], i [26], op [25:22], imm [21:6] (only meaningful when i=1).
    [8:0] (val1_addr/val2_addr/jump_to_addr) are register-*addressing* bits
    this module never looks at itself -- see module docstring -- so they're
    left 0 here."""
    return (
        (major_opcode & 0xF) << 28
        | (r & 0x1) << 27
        | (i & 0x1) << 26
        | (op & 0xF) << 22
        | (imm & 0xFFFF) << 6
    )


async def start(dut):
    """Start the clock and drive one synchronous reset cycle (POR)."""
    cocotb.start_soon(Clock(dut.clk_i, CLOCK_PERIOD_NS, unit="ns").start())
    dut.rst_i.value = 1
    dut.bus.instruction.value = 0
    dut.bus.value1.value = 0
    dut.bus.value2.value = 0
    dut.bus.goto_val.value = 0
    dut.bus.overflow.value = 0
    dut.bus.error.value = 0
    await RisingEdge(dut.clk_i)
    dut.rst_i.value = 0
    await SETTLE


async def step(dut, opcode, value1=0, value2=0, goto=0, overflow=0, error=0):
    """Drive one cycle's inputs, advance past the rising edge, return the
    resulting bus.pc."""
    dut.bus.instruction.value = opcode
    dut.bus.value1.value = value1
    dut.bus.value2.value = value2
    dut.bus.goto_val.value = goto
    dut.bus.overflow.value = overflow
    dut.bus.error.value = error
    await RisingEdge(dut.clk_i)
    await SETTLE
    return int(dut.bus.pc.value)


@cocotb.test()
async def test_reset_sets_reset_vector(dut):
    """After POR, bus.pc reads back as ResetVector (0x10), not 0 --
    flow_ctl.md's rationale for reserving 0x0-0xF as a fixed error-handler
    region."""
    await start(dut)
    actual = int(dut.bus.pc.value)
    assert actual == RESET_VECTOR, (
        f"bus.pc = {actual:#010x} after reset, expected {RESET_VECTOR:#010x}"
    )


@cocotb.test()
async def test_non_flow_ctl_major_opcode_is_nop_regardless_of_other_bits(dut):
    """Self-detection: any major opcode other than FLOW_CTL forces the
    never-taken path internally, even when the sub-bits happen to encode
    what would otherwise be a taken 'always' jump."""
    await start(dut)
    pc_before = int(dut.bus.pc.value)
    fake_jump = make_opcode(ALWAYS, r=0, i=0, major_opcode=OTHER_MAJOR_OPCODE)
    pc_after = await step(dut, fake_jump, goto=0xDEAD_0000)
    assert pc_after == pc_before + 1, (
        f"bus.pc = {pc_after:#010x} for a non-FLOW_CTL major opcode, "
        f"expected fall-through {pc_before + 1:#010x}"
    )


@cocotb.test()
async def test_flow_ctl_nop_ignores_everything(dut):
    """op=NOP (0x0) is never-taken regardless of r/i/imm/operands -- same
    encoding self-detection forces for non-FLOW_CTL instructions."""
    await start(dut)
    pc_before = int(dut.bus.pc.value)
    opcode = make_opcode(NOP, r=1, i=1, imm=0x1234)
    pc_after = await step(
        dut, opcode, value1=1, value2=1, goto=0xBEEF_0000, overflow=1
    )
    assert pc_after == pc_before + 1, (
        f"bus.pc = {pc_after:#010x} for FLOW_CTL nop, "
        f"expected fall-through {pc_before + 1:#010x}"
    )


# (op, val1, val2, overflow, taken, description)
CONDITION_CASES = [
    (L, 5, 10, 0, True, "l: 5 < 10"),
    (L, 10, 5, 0, False, "l: 10 < 5"),
    (L, 5, 5, 0, False, "l: 5 < 5 (equal)"),
    (LE, 5, 10, 0, True, "le: 5 <= 10"),
    (LE, 5, 5, 0, True, "le: 5 <= 5 (equal)"),
    (LE, 10, 5, 0, False, "le: 10 <= 5"),
    (G, 10, 5, 0, True, "g: 10 > 5"),
    (G, 5, 10, 0, False, "g: 5 > 10"),
    (G, 5, 5, 0, False, "g: 5 > 5 (equal)"),
    (GE, 10, 5, 0, True, "ge: 10 >= 5"),
    (GE, 5, 5, 0, True, "ge: 5 >= 5 (equal)"),
    (GE, 5, 10, 0, False, "ge: 5 >= 10"),
    (Z, 0, 0xFFFF_FFFF, 0, True, "z: val1=0"),
    (Z, 1, 0, 0, False, "z: val1=1"),
    (NZ, 1, 0, 0, True, "nz: val1=1"),
    (NZ, 0, 0xFFFF_FFFF, 0, False, "nz: val1=0"),
    (EQ, 7, 7, 0, True, "eq: 7 == 7"),
    (EQ, 7, 8, 0, False, "eq: 7 == 8"),
    (NEQ, 7, 8, 0, True, "neq: 7 != 8"),
    (NEQ, 7, 7, 0, False, "neq: 7 != 7"),
    (ALWAYS, 0, 0, 0, True, "always: taken regardless of operands"),
    (OVERFLOW, 0, 0, 1, True, "overflow: overflow_i=1"),
    (OVERFLOW, 0, 0, 0, False, "overflow: overflow_i=0"),
    (NOT_OVERFLOW, 0, 0, 0, True, "not_overflow: overflow_i=0"),
    (NOT_OVERFLOW, 0, 0, 1, False, "not_overflow: overflow_i=1"),
]

# l/le/g/ge use large-magnitude operands to catch a signed-comparison bug
# (a value with the MSB set would compare as negative if treated signed).
UNSIGNED_COMPARISON_CASES = [
    (L, 0x7FFF_FFFF, 0x8000_0000, 0, True, "l: unsigned 0x7FFFFFFF < 0x80000000"),
    (G, 0x8000_0000, 0x7FFF_FFFF, 0, True, "g: unsigned 0x80000000 > 0x7FFFFFFF"),
]


@cocotb.test()
async def test_conditions(dut):
    """Each op's condition, taken and not-taken. Uses absolute
    register-indirect targeting (r=0, i=0) to isolate condition evaluation
    from target computation (covered separately below)."""
    target = 0x0000_1234
    for op, val1, val2, overflow, taken, description in (
        CONDITION_CASES + UNSIGNED_COMPARISON_CASES
    ):
        await start(dut)
        pc_before = int(dut.bus.pc.value)
        opcode = make_opcode(op, r=0, i=0)
        pc_after = await step(
            dut, opcode, value1=val1, value2=val2, goto=target, overflow=overflow
        )
        if taken:
            assert pc_after == target, (
                f"{description}: expected taken (pc={target:#010x}), "
                f"got pc={pc_after:#010x}"
            )
        else:
            expected = pc_before + 1
            assert pc_after == expected, (
                f"{description}: expected not-taken (pc={expected:#010x}), "
                f"got pc={pc_after:#010x}"
            )


@cocotb.test()
async def test_val2_ignored_where_documented(dut):
    """z/nz/always don't depend on val2 -- confirm varying it doesn't change
    the taken outcome (isa.md/flow_ctl.md's 'ignored' column)."""
    target = 0x0000_0100
    for op, val1, description in [(Z, 0, "z"), (NZ, 5, "nz"), (ALWAYS, 0, "always")]:
        for val2 in (0x0000_0000, 0xFFFF_FFFF):
            await start(dut)
            opcode = make_opcode(op, r=0, i=0)
            pc_after = await step(dut, opcode, value1=val1, value2=val2, goto=target)
            assert pc_after == target, (
                f"{description} with val2={val2:#010x}: expected taken "
                f"(pc={target:#010x}), got pc={pc_after:#010x}"
            )


@cocotb.test()
async def test_target_absolute_register_indirect(dut):
    """i=0, r=0: target = goto, used directly (unsigned)."""
    await start(dut)
    opcode = make_opcode(ALWAYS, r=0, i=0)
    pc_after = await step(dut, opcode, goto=0x0002_0000)
    assert pc_after == 0x0002_0000, (
        f"bus.pc = {pc_after:#010x}, expected 0x00020000 (absolute, register)"
    )


@cocotb.test()
async def test_target_relative_register_indirect(dut):
    """i=0, r=1: target = pc + goto, goto interpreted as signed."""
    await start(dut)
    pc_before = int(dut.bus.pc.value)
    opcode = make_opcode(ALWAYS, r=1, i=0)
    pc_after = await step(dut, opcode, goto=5)
    expected = (pc_before + 5) & MASK32
    assert pc_after == expected, (
        f"bus.pc = {pc_after:#010x}, expected {expected:#010x} "
        f"(relative, register, +5)"
    )

    await start(dut)
    pc_before = int(dut.bus.pc.value)
    opcode = make_opcode(ALWAYS, r=1, i=0)
    pc_after = await step(dut, opcode, goto=0xFFFF_FFFF)  # -1, two's complement
    expected = (pc_before - 1) & MASK32
    assert pc_after == expected, (
        f"bus.pc = {pc_after:#010x}, expected {expected:#010x} "
        f"(relative, register, -1)"
    )


@cocotb.test()
async def test_relative_target_underflow_forces_error_vector(dut):
    """r=1: if the *true* (unbounded) pc + target sum is negative, that's
    treated as an error rather than silently wrapping -- flow_ctl.md's
    Design rationale on out-of-range relative targets."""
    await start(dut)  # bus.pc = ResetVector = 0x10 (16)
    opcode = make_opcode(ALWAYS, r=1, i=0)
    pc_after = await step(dut, opcode, goto=(-256) & MASK32)  # 16 + (-256) < 0
    assert pc_after == ERROR_VECTOR, (
        f"bus.pc = {pc_after:#010x}, expected ErrorVector {ERROR_VECTOR:#010x} "
        f"for an out-of-range (negative) relative target"
    )


@cocotb.test()
async def test_relative_target_overflow_forces_error_vector(dut):
    """r=1: if the true sum exceeds 2**32-1, same treatment as the
    underflow case above."""
    await start(dut)
    near_top = 0xFFFF_FFF0
    opcode = make_opcode(ALWAYS, r=0, i=0)
    pc_after = await step(dut, opcode, goto=near_top)
    assert pc_after == near_top, (
        f"setup: bus.pc = {pc_after:#010x}, expected {near_top:#010x}"
    )

    opcode = make_opcode(ALWAYS, r=1, i=0)
    pc_after = await step(dut, opcode, goto=0x21)
    assert pc_after == ERROR_VECTOR, (
        f"bus.pc = {pc_after:#010x}, expected ErrorVector {ERROR_VECTOR:#010x} "
        f"for an out-of-range (>2**32-1) relative target"
    )


@cocotb.test()
async def test_target_absolute_immediate(dut):
    """i=1, r=0: target = imm, zero-extended (unsigned)."""
    await start(dut)
    opcode = make_opcode(ALWAYS, r=0, i=1, imm=0x1234)
    pc_after = await step(dut, opcode)
    assert pc_after == 0x0000_1234, (
        f"bus.pc = {pc_after:#010x}, expected 0x00001234 (absolute, immediate)"
    )


@cocotb.test()
async def test_target_relative_immediate(dut):
    """i=1, r=1: target = pc + imm, imm sign-extended (two's complement)."""
    await start(dut)
    pc_before = int(dut.bus.pc.value)
    opcode = make_opcode(ALWAYS, r=1, i=1, imm=100)
    pc_after = await step(dut, opcode)
    expected = (pc_before + 100) & MASK32
    assert pc_after == expected, (
        f"bus.pc = {pc_after:#010x}, expected {expected:#010x} "
        f"(relative, immediate, +100)"
    )

    await start(dut)
    pc_before = int(dut.bus.pc.value)
    opcode = make_opcode(ALWAYS, r=1, i=1, imm=0xFFFF)  # -1, 16b two's complement
    pc_after = await step(dut, opcode)
    expected = (pc_before - 1) & MASK32
    assert pc_after == expected, (
        f"bus.pc = {pc_after:#010x}, expected {expected:#010x} "
        f"(relative, immediate, -1)"
    )


@cocotb.test()
async def test_error_forces_error_vector(dut):
    """error_i overrides a taken jump unconditionally."""
    await start(dut)
    opcode = make_opcode(ALWAYS, r=0, i=1, imm=0x1234)  # would jump to 0x1234
    pc_after = await step(dut, opcode, error=1)
    assert pc_after == ERROR_VECTOR, (
        f"bus.pc = {pc_after:#010x} with error_i=1, expected "
        f"ErrorVector {ERROR_VECTOR:#010x}"
    )


@cocotb.test()
async def test_error_forces_error_vector_even_for_non_flow_ctl_major_opcode(dut):
    """error_i overrides self-detection too -- flow_ctl.md's priority order
    puts error_i above the condition/fall-through step, and major-opcode
    self-detection is part of that step, not a separate bypass."""
    await start(dut)
    opcode = make_opcode(ALWAYS, r=0, i=0, major_opcode=OTHER_MAJOR_OPCODE)
    pc_after = await step(dut, opcode, error=1)
    assert pc_after == ERROR_VECTOR, (
        f"bus.pc = {pc_after:#010x} with error_i=1 during a non-FLOW_CTL "
        f"major opcode, expected ErrorVector {ERROR_VECTOR:#010x}"
    )


RESERVED_OPS = [0xC, 0xD, 0xE, 0xF]


@cocotb.test()
async def test_reserved_op_forces_error_vector(dut):
    """Reserved op values (0xC-0xF) on a real FLOW_CTL instruction are
    illegal, not a no-op -- flow_ctl.md's Design rationale: they land in the
    case statement's default: arm, which resolves to ErrorVector, distinct
    from NOP's defined fall-through. Operands are set as if they'd otherwise
    produce a taken jump, to confirm the reserved op overrides them."""
    for op in RESERVED_OPS:
        await start(dut)
        opcode = make_opcode(op, r=1, i=1, imm=0x1234)
        pc_after = await step(
            dut, opcode, value1=1, value2=1, goto=0xBEEF_0000, overflow=1
        )
        assert pc_after == ERROR_VECTOR, (
            f"bus.pc = {pc_after:#010x} for reserved op={op:#x}, expected "
            f"ErrorVector {ERROR_VECTOR:#010x}"
        )


@cocotb.test()
async def test_reset_overrides_error_and_condition(dut):
    """rst_i wins even over a simultaneous error_i + taken jump."""
    await start(dut)
    dut.rst_i.value = 1
    dut.bus.instruction.value = make_opcode(ALWAYS, r=0, i=1, imm=0x1234)
    dut.bus.error.value = 1
    await RisingEdge(dut.clk_i)
    dut.rst_i.value = 0
    dut.bus.error.value = 0
    await SETTLE
    actual = int(dut.bus.pc.value)
    assert actual == RESET_VECTOR, (
        f"bus.pc = {actual:#010x} with rst_i=1 (and error_i=1, taken jump "
        f"also asserted), expected ResetVector {RESET_VECTOR:#010x}"
    )
