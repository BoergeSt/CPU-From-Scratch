"""cocotb testbench for the Hydrogen ALU status latch (see
machines/hydrogen/docs/alu_status.md).

Synchronous, active-high reset; `bus.latched_overflow` is registered. Each
test starts its own clock and drives its own reset to a known state, since
the DUT's latched_overflow persists across tests within one simulation run.
"""

import functools

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer

# Mirrors alu_status_tb_top.sv's test_phase_e -- order must match the SV
# declaration (index + 1, since PHASE_IDLE is 0). phased_test() below uses
# this to drive dut.dbg_test_phase, which shows the currently-running test
# by name in the waveform (Surfer/GTKWave enum decode) -- all tests below
# share one simulation run and one continuous waveform dump, so this is
# what makes a given test's slice of the timeline identifiable at all.
PHASE_NAMES = [
    "test_reset_clears_overflow",
    "test_alu_cycle_captures_overflow_i",
    "test_non_alu_cycle_holds_previous_value",
    "test_non_alu_major_opcode_ignores_overflow_i_regardless_of_value",
    "test_consecutive_alu_cycles_track_live_value",
    "test_reset_overrides_capture",
]


def phased_test(func):
    """Drive dut.dbg_test_phase to func's matching test_phase_e value for
    the duration of the test, back to PHASE_IDLE afterward."""

    phase = PHASE_NAMES.index(func.__name__) + 1

    @functools.wraps(func)
    async def wrapper(dut, *args, **kwargs):
        dut.dbg_test_phase.value = phase
        try:
            await func(dut, *args, **kwargs)
        finally:
            dut.dbg_test_phase.value = 0

    return wrapper


CLOCK_PERIOD_NS = 10
SETTLE = Timer(1, unit="ns")

ALU_MAJOR_OPCODE = 0x7
OTHER_MAJOR_OPCODE = 0x2  # FLOW_CTL -- anything != ALU works for self-detection tests


def make_opcode(major_opcode):
    """Assemble a 32-bit instruction word with only the major opcode field
    ([31:28]) set -- this module only ever looks at that field."""
    return (major_opcode & 0xF) << 28


async def start(dut):
    """Start the clock and drive one synchronous reset cycle (POR)."""
    cocotb.start_soon(Clock(dut.clk_i, CLOCK_PERIOD_NS, unit="ns").start())
    dut.rst_i.value = 1
    dut.bus.instruction.value = 0
    dut.bus.overflow.value = 0
    await RisingEdge(dut.clk_i)
    dut.rst_i.value = 0
    await SETTLE


async def step(dut, opcode, overflow_i):
    """Drive one cycle's inputs, advance past the rising edge, return the
    resulting latched_overflow."""
    dut.bus.instruction.value = opcode
    dut.bus.overflow.value = overflow_i
    await RisingEdge(dut.clk_i)
    await SETTLE
    return int(dut.bus.latched_overflow.value)


@cocotb.test()
@phased_test
async def test_reset_clears_overflow(dut):
    """After POR, overflow_o reads back as 0."""
    await start(dut)
    actual = int(dut.bus.latched_overflow.value)
    assert actual == 0, f"overflow_o = {actual} after reset, expected 0"


@cocotb.test()
@phased_test
async def test_alu_cycle_captures_overflow_i(dut):
    """An ALU-major-opcode cycle captures the live overflow_i, both
    directions (0->1 and 1->0)."""
    await start(dut)
    opcode = make_opcode(ALU_MAJOR_OPCODE)

    actual = await step(dut, opcode, overflow_i=1)
    assert actual == 1, f"overflow_o = {actual} after ALU cycle, overflow_i=1"

    actual = await step(dut, opcode, overflow_i=0)
    assert actual == 0, f"overflow_o = {actual} after ALU cycle, overflow_i=0"


@cocotb.test()
@phased_test
async def test_non_alu_cycle_holds_previous_value(dut):
    """A non-ALU-major-opcode cycle leaves overflow_o unchanged, even while
    overflow_i (meaningless that cycle) varies -- the latched value must
    survive an arbitrary number of unrelated instructions in between."""
    await start(dut)
    alu_opcode = make_opcode(ALU_MAJOR_OPCODE)
    other_opcode = make_opcode(OTHER_MAJOR_OPCODE)

    actual = await step(dut, alu_opcode, overflow_i=1)
    assert actual == 1, f"setup: overflow_o = {actual}, expected 1"

    for overflow_i in (0, 1, 0):
        actual = await step(dut, other_opcode, overflow_i=overflow_i)
        assert actual == 1, (
            f"overflow_o = {actual} after non-ALU cycle (overflow_i={overflow_i}), "
            f"expected held value 1"
        )


@cocotb.test()
@phased_test
async def test_non_alu_major_opcode_ignores_overflow_i_regardless_of_value(dut):
    """Self-detection: any major opcode other than ALU forces the hold path
    internally, even when overflow_i happens to equal the currently-latched
    value's opposite."""
    await start(dut)
    alu_opcode = make_opcode(ALU_MAJOR_OPCODE)
    other_opcode = make_opcode(OTHER_MAJOR_OPCODE)

    actual = await step(dut, alu_opcode, overflow_i=0)
    assert actual == 0, f"setup: overflow_o = {actual}, expected 0"

    actual = await step(dut, other_opcode, overflow_i=1)
    assert actual == 0, (
        f"overflow_o = {actual} after non-ALU cycle with overflow_i=1, "
        f"expected held value 0 (self-detection must ignore overflow_i)"
    )


@cocotb.test()
@phased_test
async def test_consecutive_alu_cycles_track_live_value(dut):
    """Back-to-back ALU cycles each capture that cycle's own overflow_i --
    not just the first or last of a run."""
    await start(dut)
    opcode = make_opcode(ALU_MAJOR_OPCODE)

    for overflow_i in (1, 0, 1, 1, 0):
        actual = await step(dut, opcode, overflow_i=overflow_i)
        assert actual == overflow_i, (
            f"overflow_o = {actual} after ALU cycle with overflow_i={overflow_i}, "
            f"expected {overflow_i}"
        )


@cocotb.test()
@phased_test
async def test_reset_overrides_capture(dut):
    """rst_i wins even over a simultaneous ALU cycle with overflow_i=1."""
    await start(dut)
    dut.rst_i.value = 1
    dut.bus.instruction.value = make_opcode(ALU_MAJOR_OPCODE)
    dut.bus.overflow.value = 1
    await RisingEdge(dut.clk_i)
    dut.rst_i.value = 0
    dut.bus.overflow.value = 0
    await SETTLE
    actual = int(dut.bus.latched_overflow.value)
    assert actual == 0, (
        f"overflow_o = {actual} with rst_i=1 (and a simultaneous ALU cycle, "
        f"overflow_i=1), expected 0"
    )
