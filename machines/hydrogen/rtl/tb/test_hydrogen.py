"""cocotb testbench for the Hydrogen machine top-level (see
machines/hydrogen/docs/hydrogen.md).

Not opcode coverage -- every IC_* case already has directed tests in
test_core_glue.py/test_alu.py/test_flow_ctl.py/test_regfile.py. This is a
wiring sanity check: hand-assembled instruction words preloaded directly
into the real BRAM array (hierarchically -- there's no external path to
load a program otherwise, since only the core itself drives the I-bus),
clocked through the real fetch/decode/writeback loop, with results read
back from the real register file / BRAM contents, also hierarchically.
"""

import functools

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer

# Mirrors hydrogen_tb_top.sv's test_phase_e -- order must match the SV
# declaration (index + 1, since PHASE_IDLE is 0). phased_test() below uses
# this to drive dut.dbg_test_phase, which shows the currently-running test
# by name in the waveform (Surfer/GTKWave enum decode) -- all tests below
# share one simulation run and one continuous waveform dump, so this is
# what makes a given test's slice of the timeline identifiable at all.
PHASE_NAMES = [
    "test_reset_vector_and_registers",
    "test_fetch_decode_writeback_round_trip",
    "test_store_load_round_trip_through_d_bus",
    "test_branch_redirects_real_pc",
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

RESET_VECTOR = 0x10
NUM_REGS = 8

IC_IMM_SET = 0x1
IC_FLOW_CTL = 0x2
IC_LOAD_IMM = 0x3
IC_STORE_IMM = 0x4

FLOW_CTL_OP_EQUAL = 0x7


def make_imm_set(dest=0, imm=0):
    """isa.md: IMM_SET -- ic[31:28], dest[27:25], imm[24:0]."""
    return (IC_IMM_SET & 0xF) << 28 | (dest & 0x7) << 25 | (imm & 0x1FF_FFFF)


def make_load_imm(dest=0, imm=0):
    """isa.md: LOAD_IMM -- ic[31:28], dest[27:25], imm[24:0]."""
    return (IC_LOAD_IMM & 0xF) << 28 | (dest & 0x7) << 25 | (imm & 0x1FF_FFFF)


def make_store_imm(imm=0, src=0):
    """isa.md: STORE_IMM -- ic[31:28], imm[27:3], src[2:0]. `src` sits at the
    universal [2:0] read position."""
    return (IC_STORE_IMM & 0xF) << 28 | (imm & 0x1FF_FFFF) << 3 | (src & 0x7)


def make_flow_ctl(op=0, r=0, i=0, imm=0, jump_to_addr=0, src1=0, src2=0):
    """isa.md: FLOW_CTL -- ic[31:28], is_relative(r)[27], is_imm(i)[26],
    op[25:22], target[21:6], src2_addr[5:3], src1_addr[2:0]."""
    target = (imm & 0xFFFF) if i else (jump_to_addr & 0x7)
    return (
        (IC_FLOW_CTL & 0xF) << 28
        | (r & 0x1) << 27
        | (i & 0x1) << 26
        | (op & 0xF) << 22
        | (target & 0xFFFF) << 6
        | (src2 & 0x7) << 3
        | (src1 & 0x7) << 0
    )


def load_program(dut, words, base=RESET_VECTOR):
    """Preload `words` into BRAM starting at word address `base`. Only path
    to get a program in: nothing external can drive the I-bus, the core
    itself owns it."""
    for offset, word in enumerate(words):
        dut.dut.bram.bram[base + offset].value = word


async def start(dut):
    """Start the clock and drive one synchronous reset cycle (POR)."""
    cocotb.start_soon(Clock(dut.clk_i, CLOCK_PERIOD_NS, unit="ns").start())
    dut.rst_i.value = 1
    await RisingEdge(dut.clk_i)
    dut.rst_i.value = 0
    await SETTLE


def read_reg(dut, addr):
    return int(dut.dut.regfile.registers[addr].value)


def read_mem(dut, addr):
    return int(dut.dut.bram.bram[addr].value)


@cocotb.test()
@phased_test
async def test_reset_vector_and_registers(dut):
    """After POR, PC sits at ResetVector and every register reads 0."""
    await start(dut)
    assert int(dut.dut.flow_ctl_if.pc.value) == RESET_VECTOR
    for addr in range(NUM_REGS):
        assert read_reg(dut, addr) == 0, f"R{addr} nonzero after reset"


@cocotb.test()
@phased_test
async def test_fetch_decode_writeback_round_trip(dut):
    """A single hand-assembled IMM_SET, fetched from real BRAM at the real
    PC and decoded by the real core_glue, lands in the real register file,
    and PC advances by one word."""
    load_program(dut, [make_imm_set(dest=3, imm=0x1234)])
    await start(dut)
    await RisingEdge(dut.clk_i)
    await SETTLE
    assert read_reg(dut, 3) == 0x1234
    assert int(dut.dut.flow_ctl_if.pc.value) == RESET_VECTOR + 1


@cocotb.test()
@phased_test
async def test_store_load_round_trip_through_d_bus(dut):
    """IMM_SET a value into R2, STORE_IMM it out to memory, LOAD_IMM it back
    into R5 -- proves the D-bus write path (core_glue -> real BRAM) and
    read path (real BRAM -> core_glue -> regfile) both actually connect,
    not just each in isolation against a driven bus."""
    value = 0x0004D2
    mem_addr = 0x100
    load_program(
        dut,
        [
            make_imm_set(dest=2, imm=value),
            make_store_imm(imm=mem_addr, src=2),
            make_load_imm(dest=5, imm=mem_addr),
        ],
    )
    await start(dut)
    for _ in range(3):
        await RisingEdge(dut.clk_i)
    await SETTLE
    assert read_mem(dut, mem_addr) == value
    assert read_reg(dut, 5) == value
    assert int(dut.dut.flow_ctl_if.pc.value) == RESET_VECTOR + 3


@cocotb.test()
@phased_test
async def test_branch_redirects_real_pc(dut):
    """Two IMM_SETs feed equal values into a flow_ctl EQUAL branch --
    proves a branch decision fed by real register values actually
    redirects the real PC driving the real next fetch."""
    target = 0x50
    load_program(
        dut,
        [
            make_imm_set(dest=0, imm=1),
            make_imm_set(dest=1, imm=1),
            make_flow_ctl(op=FLOW_CTL_OP_EQUAL, r=0, i=1, imm=target, src1=0, src2=1),
        ],
    )
    await start(dut)
    for _ in range(3):
        await RisingEdge(dut.clk_i)
    await SETTLE
    assert int(dut.dut.flow_ctl_if.pc.value) == target
