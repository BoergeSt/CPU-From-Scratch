"""cocotb testbench for the Hydrogen BRAM main memory (see
docs/machines/hydrogen/bram.md).

No reset -- storage contents are undefined at simulation start and persist
across tests within one simulation run, so every test explicitly writes
whatever it depends on reading. Combinational reads, synchronous writes
(bus_D only); bus_I is read-only.
"""

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer

CLOCK_PERIOD_NS = 10
SETTLE = Timer(1, unit="ns")

SIZE = 0x1000


def make_value(addr, salt):
    """A value that's unique per `addr` (top nibble = addr) so crosstalk
    between words is unmistakable, distinguishable per-test via `salt`.
    Stays within 32 bits by construction."""
    return ((addr & 0xF) << 28) | ((salt + addr) & 0x0FFF_FFFF)


async def start(dut):
    """Start the clock. No reset exists -- ports are only driven to a known
    idle state, storage contents are left exactly as they were."""
    cocotb.start_soon(Clock(dut.clk_i, CLOCK_PERIOD_NS, unit="ns").start())
    for port in (dut.bus_I, dut.bus_D):
        port.addr.value = 0
        port.wdata.value = 0
        port.enable.value = 0
        port.we.value = 0
    await RisingEdge(dut.clk_i)
    await SETTLE


async def write_word(dut, addr, data):
    """Write `data` to `addr` via bus_D on the next rising edge."""
    dut.bus_D.addr.value = addr
    dut.bus_D.wdata.value = data
    dut.bus_D.enable.value = 1
    dut.bus_D.we.value = 1
    await RisingEdge(dut.clk_i)
    dut.bus_D.enable.value = 0
    dut.bus_D.we.value = 0
    await SETTLE


async def read_port(port, addr, enable=1):
    port.addr.value = addr
    port.enable.value = enable
    port.we.value = 0
    await SETTLE
    return int(port.rdata.value), int(port.ack.value)


@cocotb.test()
async def test_write_read_back_via_bus_D(dut):
    """Words written via bus_D read back correctly via bus_D."""
    await start(dut)
    addrs = [0x000, 0x001, 0x0FF, 0x800, SIZE - 1]
    values = {addr: make_value(addr, 0xBEEF) for addr in addrs}
    for addr, value in values.items():
        await write_word(dut, addr, value)
    for addr, value in values.items():
        rdata, ack = await read_port(dut.bus_D, addr)
        assert ack == 1, f"bus_D addr={addr:#x} ack={ack}, expected 1"
        assert rdata == value, (
            f"bus_D addr={addr:#x} rdata={rdata:#010x}, expected {value:#010x}"
        )


@cocotb.test()
async def test_bus_I_sees_writes_made_via_bus_D(dut):
    """bus_I and bus_D address the same underlying storage -- a write
    through bus_D is visible through bus_I."""
    await start(dut)
    addrs = [0x000, 0x123, 0x0FF, SIZE - 1]
    values = {addr: make_value(addr, 0xC0DE) for addr in addrs}
    for addr, value in values.items():
        await write_word(dut, addr, value)
    for addr, value in values.items():
        rdata, ack = await read_port(dut.bus_I, addr)
        assert ack == 1, f"bus_I addr={addr:#x} ack={ack}, expected 1"
        assert rdata == value, (
            f"bus_I addr={addr:#x} rdata={rdata:#010x}, expected {value:#010x}"
        )


@cocotb.test()
async def test_bus_I_we_is_ignored(dut):
    """Driving bus_I.we high never modifies storage -- bus_I is read-only."""
    await start(dut)
    addr = 0x10
    original = make_value(addr, 0x1111)
    await write_word(dut, addr, original)

    dut.bus_I.addr.value = addr
    dut.bus_I.wdata.value = make_value(addr, 0xFFFF)
    dut.bus_I.enable.value = 1
    dut.bus_I.we.value = 1
    await RisingEdge(dut.clk_i)
    dut.bus_I.enable.value = 0
    dut.bus_I.we.value = 0
    await SETTLE

    rdata, ack = await read_port(dut.bus_D, addr)
    assert ack == 1, f"bus_D addr={addr:#x} ack={ack}, expected 1"
    assert rdata == original, (
        f"addr={addr:#x} rdata={rdata:#010x} after bus_I write attempt, "
        f"expected unchanged {original:#010x}"
    )


@cocotb.test()
async def test_disabled_port_returns_zero_rdata_and_ack(dut):
    """A port with enable=0 reads rdata=0, ack=0, regardless of what's
    actually stored at that address."""
    await start(dut)
    addr = 0x20
    await write_word(dut, addr, make_value(addr, 0x2222))

    for port in (dut.bus_I, dut.bus_D):
        rdata, ack = await read_port(port, addr, enable=0)
        assert ack == 0, f"{port._name} addr={addr:#x} enable=0 ack={ack}, expected 0"
        assert rdata == 0, (
            f"{port._name} addr={addr:#x} enable=0 rdata={rdata:#010x}, expected 0"
        )


@cocotb.test()
async def test_ack_boundary_at_size(dut):
    """ack is 1 for the last in-range address (Size-1) and 0 for the first
    out-of-range address (Size), for both ports."""
    await start(dut)
    await write_word(dut, SIZE - 1, make_value(SIZE - 1, 0x3333))

    for port in (dut.bus_I, dut.bus_D):
        rdata, ack = await read_port(port, SIZE - 1)
        assert ack == 1, f"{port._name} addr={SIZE - 1:#x} ack={ack}, expected 1"

        rdata, ack = await read_port(port, SIZE)
        assert ack == 0, f"{port._name} addr={SIZE:#x} ack={ack}, expected 0"
        assert rdata == 0, (
            f"{port._name} addr={SIZE:#x} rdata={rdata:#010x}, expected 0"
        )


@cocotb.test()
async def test_out_of_range_read_returns_zero(dut):
    """An enabled read past Size returns rdata=0, ack=0, on both ports."""
    await start(dut)
    for port in (dut.bus_I, dut.bus_D):
        rdata, ack = await read_port(port, SIZE + 0x100)
        assert ack == 0, f"{port._name} out-of-range ack={ack}, expected 0"
        assert rdata == 0, f"{port._name} out-of-range rdata={rdata:#010x}, expected 0"


@cocotb.test()
async def test_out_of_range_write_has_no_effect(dut):
    """A bus_D write attempt past Size doesn't corrupt neighboring in-range
    storage and doesn't itself become readable."""
    await start(dut)
    guard_addr = SIZE - 1
    guard_value = make_value(guard_addr, 0x4444)
    await write_word(dut, guard_addr, guard_value)

    await write_word(dut, SIZE + 4, 0xDEAD_BEEF)

    rdata, ack = await read_port(dut.bus_D, guard_addr)
    assert ack == 1, f"guard addr={guard_addr:#x} ack={ack}, expected 1"
    assert rdata == guard_value, (
        f"guard addr={guard_addr:#x} rdata={rdata:#010x} after an out-of-range "
        f"write attempt, expected unchanged {guard_value:#010x}"
    )


@cocotb.test()
async def test_bus_I_and_bus_D_independent_same_cycle(dut):
    """bus_I and bus_D addressed at different words in the same cycle don't
    interfere with each other."""
    await start(dut)
    addr_i, addr_d = 0x30, 0x31
    value_i = make_value(addr_i, 0x5555)
    value_d = make_value(addr_d, 0x6666)
    await write_word(dut, addr_i, value_i)
    await write_word(dut, addr_d, value_d)

    dut.bus_I.addr.value = addr_i
    dut.bus_I.enable.value = 1
    dut.bus_I.we.value = 0
    dut.bus_D.addr.value = addr_d
    dut.bus_D.enable.value = 1
    dut.bus_D.we.value = 0
    await SETTLE

    rdata_i = int(dut.bus_I.rdata.value)
    ack_i = int(dut.bus_I.ack.value)
    rdata_d = int(dut.bus_D.rdata.value)
    ack_d = int(dut.bus_D.ack.value)

    assert ack_i == 1 and rdata_i == value_i, (
        f"bus_I addr={addr_i:#x} rdata={rdata_i:#010x} ack={ack_i}, "
        f"expected {value_i:#010x}/1"
    )
    assert ack_d == 1 and rdata_d == value_d, (
        f"bus_D addr={addr_d:#x} rdata={rdata_d:#010x} ack={ack_d}, "
        f"expected {value_d:#010x}/1"
    )


@cocotb.test()
async def test_write_pulse_persists(dut):
    """A single-cycle write pulse's value survives further idle cycles on
    bus_D, even while addr/wdata keep changing (enable/we stay low)."""
    await start(dut)
    addr = 0x40
    value = make_value(addr, 0x7777)
    await write_word(dut, addr, value)

    for i in range(5):
        dut.bus_D.addr.value = addr + i + 1
        dut.bus_D.wdata.value = (0x1111_1111 * (i + 1)) & 0xFFFF_FFFF
        dut.bus_D.enable.value = 0
        dut.bus_D.we.value = 0
        await RisingEdge(dut.clk_i)
        await SETTLE
        rdata, ack = await read_port(dut.bus_D, addr)
        assert ack == 1 and rdata == value, (
            f"addr={addr:#x} rdata={rdata:#010x} ack={ack} after {i + 1} idle "
            f"cycles, expected unchanged {value:#010x}/1"
        )


@cocotb.test()
async def test_read_during_write_same_port_same_address(dut):
    """bus_D reading its own rdata while simultaneously writing the same
    address: rdata shows the old value right up to the clock edge, and the
    new value only once the edge has passed -- rdata is never gated by that
    same port's own write activity."""
    await start(dut)
    addr = 0x51
    old, new = 0x5555_6666, 0x7777_8888
    await write_word(dut, addr, old)

    dut.bus_D.addr.value = addr
    dut.bus_D.wdata.value = new
    dut.bus_D.enable.value = 1
    dut.bus_D.we.value = 1
    await SETTLE
    before_edge = int(dut.bus_D.rdata.value)
    assert before_edge == old, (
        f"addr={addr:#x} bus_D read before its own write edge = "
        f"{before_edge:#010x}, expected old value {old:#010x}"
    )

    await RisingEdge(dut.clk_i)
    dut.bus_D.we.value = 0
    await SETTLE
    after_edge = int(dut.bus_D.rdata.value)
    assert after_edge == new, (
        f"addr={addr:#x} bus_D read after its own write edge = "
        f"{after_edge:#010x}, expected new value {new:#010x}"
    )
    dut.bus_D.enable.value = 0
    await SETTLE


@cocotb.test()
async def test_bus_I_read_during_bus_D_write_same_address(dut):
    """bus_I reading the exact word bus_D is writing that cycle: the
    combinational read shows the old value right up to the clock edge, and
    the new value only once the edge has passed."""
    await start(dut)
    addr = 0x50
    old, new = 0x1111_2222, 0x3333_4444
    await write_word(dut, addr, old)

    dut.bus_I.addr.value = addr
    dut.bus_I.enable.value = 1
    dut.bus_I.we.value = 0
    dut.bus_D.addr.value = addr
    dut.bus_D.wdata.value = new
    dut.bus_D.enable.value = 1
    dut.bus_D.we.value = 1
    await SETTLE
    before_edge = int(dut.bus_I.rdata.value)
    assert before_edge == old, (
        f"addr={addr:#x} bus_I read before bus_D's write edge = "
        f"{before_edge:#010x}, expected old value {old:#010x}"
    )

    await RisingEdge(dut.clk_i)
    dut.bus_D.enable.value = 0
    dut.bus_D.we.value = 0
    await SETTLE
    after_edge = int(dut.bus_I.rdata.value)
    assert after_edge == new, (
        f"addr={addr:#x} bus_I read after bus_D's write edge = "
        f"{after_edge:#010x}, expected new value {new:#010x}"
    )
