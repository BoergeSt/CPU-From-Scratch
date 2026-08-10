"""cocotb testbench for the Hydrogen register file (see
machines/hydrogen/docs/regfile.md).

Synchronous, active-high reset; combinational reads; synchronous writes.
Each test starts its own clock and drives its own reset to a known state,
since DUT register contents persist across tests within one simulation run.
"""

import functools

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer

# Mirrors regfile_tb_top.sv's test_phase_e -- order must match the SV
# declaration (index + 1, since PHASE_IDLE is 0). phased_test() below uses
# this to drive dut.dbg_test_phase, which shows the currently-running test
# by name in the waveform (Surfer/GTKWave enum decode) -- all tests below
# share one simulation run and one continuous waveform dump, so this is
# what makes a given test's slice of the timeline identifiable at all.
PHASE_NAMES = [
    "test_reset_clears_all_registers",
    "test_reset_overrides_writes_and_simultaneous_write",
    "test_write_read_back_all_registers_via_read1",
    "test_write_read_back_all_registers_via_read2",
    "test_write_read_back_all_registers_via_read3",
    "test_read_ports_independent_different_addresses",
    "test_read_ports_agree_same_address",
    "test_write_does_not_disturb_other_registers",
    "test_enable_low_has_no_effect",
    "test_write_pulse_persists",
    "test_read_during_write_same_address",
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

NUM_REGS = 8


def make_value(addr, salt):
    """A value that's unique per `addr` (top nibble = addr) so crosstalk
    between registers is unmistakable, distinguishable per-test via `salt`.
    Stays within 32 bits by construction."""
    return ((addr & 0xF) << 28) | ((salt + addr) & 0x0FFF_FFFF)


async def start(dut):
    """Start the clock and drive one synchronous reset cycle (POR)."""
    cocotb.start_soon(Clock(dut.clk_i, CLOCK_PERIOD_NS, unit="ns").start())
    dut.rst_i.value = 1
    dut.write.enable.value = 0
    dut.write.addr.value = 0
    dut.write.value.value = 0
    dut.read1.addr.value = 0
    dut.read2.addr.value = 0
    dut.read3.addr.value = 0
    await RisingEdge(dut.clk_i)
    dut.rst_i.value = 0
    await SETTLE


async def write_reg(dut, addr, value):
    """Write `value` into register `addr` on the next rising edge."""
    dut.write.addr.value = addr
    dut.write.value.value = value
    dut.write.enable.value = 1
    await RisingEdge(dut.clk_i)
    dut.write.enable.value = 0
    await SETTLE


async def read1(dut, addr):
    dut.read1.addr.value = addr
    await SETTLE
    return int(dut.read1.value.value)


async def read2(dut, addr):
    dut.read2.addr.value = addr
    await SETTLE
    return int(dut.read2.value.value)


async def read3(dut, addr):
    dut.read3.addr.value = addr
    await SETTLE
    return int(dut.read3.value.value)


@cocotb.test()
@phased_test
async def test_reset_clears_all_registers(dut):
    """After POR, every register R0-R7 reads back as 0."""
    await start(dut)
    for addr in range(NUM_REGS):
        value = await read1(dut, addr)
        assert value == 0, f"R{addr} = {value:#010x} after reset, expected 0"


@cocotb.test()
@phased_test
async def test_reset_overrides_writes_and_simultaneous_write(dut):
    """Reset unconditionally wins: it clears prior writes AND discards a
    write attempted on the same edge reset is asserted."""
    await start(dut)
    for addr in range(NUM_REGS):
        await write_reg(dut, addr, make_value(addr, 0x1000))

    # Assert rst_i together with a live write attempt on the same edge.
    dut.rst_i.value = 1
    dut.write.addr.value = 3
    dut.write.value.value = 0x0DEA_DBEE
    dut.write.enable.value = 1
    await RisingEdge(dut.clk_i)
    dut.rst_i.value = 0
    dut.write.enable.value = 0
    await SETTLE

    for addr in range(NUM_REGS):
        value = await read1(dut, addr)
        assert value == 0, (
            f"R{addr} = {value:#010x} after reset+write collision, expected 0"
        )


@cocotb.test()
@phased_test
async def test_write_read_back_all_registers_via_read1(dut):
    await start(dut)
    values = {addr: make_value(addr, 0xBEEF) for addr in range(NUM_REGS)}
    for addr, value in values.items():
        await write_reg(dut, addr, value)
    for addr, value in values.items():
        actual = await read1(dut, addr)
        assert actual == value, (
            f"R{addr} via read1 = {actual:#010x}, expected {value:#010x}"
        )


@cocotb.test()
@phased_test
async def test_write_read_back_all_registers_via_read2(dut):
    await start(dut)
    values = {addr: make_value(addr, 0xC0DE) for addr in range(NUM_REGS)}
    for addr, value in values.items():
        await write_reg(dut, addr, value)
    for addr, value in values.items():
        actual = await read2(dut, addr)
        assert actual == value, (
            f"R{addr} via read2 = {actual:#010x}, expected {value:#010x}"
        )


@cocotb.test()
@phased_test
async def test_write_read_back_all_registers_via_read3(dut):
    await start(dut)
    values = {addr: make_value(addr, 0x7E57) for addr in range(NUM_REGS)}
    for addr, value in values.items():
        await write_reg(dut, addr, value)
    for addr, value in values.items():
        actual = await read3(dut, addr)
        assert actual == value, (
            f"R{addr} via read3 = {actual:#010x}, expected {value:#010x}"
        )


@cocotb.test()
@phased_test
async def test_read_ports_independent_different_addresses(dut):
    """read1/read2/read3 addressed at three different registers don't
    interfere with each other."""
    await start(dut)
    values = {addr: make_value(addr, 0x5A5A) for addr in range(NUM_REGS)}
    for addr, value in values.items():
        await write_reg(dut, addr, value)

    for addr1 in range(NUM_REGS):
        addr2 = (addr1 + 1) % NUM_REGS
        addr3 = (addr1 + 2) % NUM_REGS
        dut.read1.addr.value = addr1
        dut.read2.addr.value = addr2
        dut.read3.addr.value = addr3
        await SETTLE
        actual1 = int(dut.read1.value.value)
        actual2 = int(dut.read2.value.value)
        actual3 = int(dut.read3.value.value)
        assert actual1 == values[addr1], (
            f"read1(R{addr1}) = {actual1:#010x}, expected {values[addr1]:#010x}"
        )
        assert actual2 == values[addr2], (
            f"read2(R{addr2}) = {actual2:#010x}, expected {values[addr2]:#010x}"
        )
        assert actual3 == values[addr3], (
            f"read3(R{addr3}) = {actual3:#010x}, expected {values[addr3]:#010x}"
        )


@cocotb.test()
@phased_test
async def test_read_ports_agree_same_address(dut):
    """read1/read2/read3 addressed at the same register return identical
    data."""
    await start(dut)
    values = {addr: make_value(addr, 0x1234) for addr in range(NUM_REGS)}
    for addr, value in values.items():
        await write_reg(dut, addr, value)

    for addr in range(NUM_REGS):
        dut.read1.addr.value = addr
        dut.read2.addr.value = addr
        dut.read3.addr.value = addr
        await SETTLE
        actual1 = int(dut.read1.value.value)
        actual2 = int(dut.read2.value.value)
        actual3 = int(dut.read3.value.value)
        assert actual1 == actual2 == actual3 == values[addr], (
            f"R{addr}: read1={actual1:#010x} read2={actual2:#010x} "
            f"read3={actual3:#010x} expected {values[addr]:#010x}"
        )


@cocotb.test()
@phased_test
async def test_write_does_not_disturb_other_registers(dut):
    """Writing register N never changes any other register's value --
    checked after each of the 8 writes in sequence, not just once."""
    await start(dut)
    expected = [0] * NUM_REGS
    for addr in range(NUM_REGS):
        value = make_value(addr, 0x9999)
        await write_reg(dut, addr, value)
        expected[addr] = value
        for check_addr in range(NUM_REGS):
            actual = await read1(dut, check_addr)
            assert actual == expected[check_addr], (
                f"after writing R{addr}, R{check_addr} = {actual:#010x}, "
                f"expected {expected[check_addr]:#010x}"
            )


@cocotb.test()
@phased_test
async def test_enable_low_has_no_effect(dut):
    await start(dut)
    await write_reg(dut, 4, 0x1234_5678)

    dut.write.addr.value = 4
    dut.write.value.value = 0xFFFF_FFFF
    dut.write.enable.value = 0
    await RisingEdge(dut.clk_i)
    await SETTLE

    actual = await read1(dut, 4)
    assert actual == 0x1234_5678, (
        f"R4 = {actual:#010x} after enable=0, expected unchanged 0x12345678"
    )


@cocotb.test()
@phased_test
async def test_write_pulse_persists(dut):
    """A single-cycle enable pulse's value survives further idle cycles,
    even while addr/value keep changing (enable stays low)."""
    await start(dut)
    await write_reg(dut, 2, 0xCAFE_BABE)

    for i in range(5):
        dut.write.addr.value = (2 + i + 1) % NUM_REGS
        dut.write.value.value = (0x1111_1111 * (i + 1)) & 0xFFFF_FFFF
        dut.write.enable.value = 0
        await RisingEdge(dut.clk_i)
        await SETTLE
        actual = await read1(dut, 2)
        assert actual == 0xCAFE_BABE, (
            f"R2 = {actual:#010x} after {i + 1} idle cycles, expected unchanged"
        )


@cocotb.test()
@phased_test
async def test_read_during_write_same_address(dut):
    """Reading the register currently being written (e.g. `ADD R1,R1,...`):
    the combinational read shows the old value right up to the clock edge,
    and the new value only once the edge has passed."""
    await start(dut)
    old, new = 0x1111_2222, 0x3333_4444
    await write_reg(dut, 5, old)

    dut.read1.addr.value = 5
    dut.write.addr.value = 5
    dut.write.value.value = new
    dut.write.enable.value = 1
    await SETTLE
    before_edge = int(dut.read1.value.value)
    assert before_edge == old, (
        f"R5 read before the write's edge = {before_edge:#010x}, "
        f"expected old value {old:#010x}"
    )

    await RisingEdge(dut.clk_i)
    dut.write.enable.value = 0
    await SETTLE
    after_edge = int(dut.read1.value.value)
    assert after_edge == new, (
        f"R5 read after the write's edge = {after_edge:#010x}, "
        f"expected new value {new:#010x}"
    )
