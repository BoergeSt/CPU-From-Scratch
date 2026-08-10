"""cocotb testbench for the generic FIFO (see common/fifo/docs/fifo.md).

fifo.sv's ports are fifo_write_if.fifo write / fifo_read_if.fifo read, not
flat signals -- interface ports aren't supported on a cocotb sim toplevel
under Verilator, so tb/fifo_tb_top.sv owns one instance of each and this
testbench drives/reads them through dut.write.<field>/dut.read.<field>.
Both interfaces name their enable field plainly `enable` (not `we_i`/`re_i`)
-- being write-only/read-only, respectively, already disambiguates which
direction it drives without needing the prefix.

SIZE/DATA_WIDTH below must track fifo.sv's DataWidth/FillWidth parameter
defaults (32/8, i.e. 128 entries) -- same convention as test_regfile.py's
NUM_REGS. The helper functions below use short `we`/`re` kwarg names for
"value to drive write.enable/read.enable with" purely as local shorthand;
the actual DUT fields are dut.write.enable/dut.read.enable.

Synchronous, active-high reset. write.full/read.empty/write.fill/read.fill
reflect pre-cycle occupancy; write.enable/read.enable are evaluated against
that same pre-cycle state, independently of each other -- no same-cycle
write-to-read bypass. write.fill and read.fill are two interface fields fed
by the same internal occupancy count, so snapshot() below asserts they
always agree -- an implicit consistency check that runs on every call.
Each test starts its own clock and drives its own reset to a known state,
since DUT state persists across tests within one simulation run.
"""

import functools
import random
from collections import deque

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer

# Mirrors fifo_tb_top.sv's test_phase_e -- order must match the SV
# declaration (index + 1, since PHASE_IDLE is 0). phased_test() below uses
# this to drive dut.dbg_test_phase, which shows the currently-running test
# by name in the waveform (Surfer/GTKWave enum decode) -- all tests below
# share one simulation run and one continuous waveform dump, so this is
# what makes a given test's slice of the timeline identifiable at all.
PHASE_NAMES = [
    "test_reset_state",
    "test_data_o_zero_when_idle",
    "test_single_write_then_read",
    "test_fifo_ordering",
    "test_fill_to_full",
    "test_drain_to_empty",
    "test_overflow_write_while_full",
    "test_underflow_read_while_empty",
    "test_simultaneous_we_re_on_empty",
    "test_simultaneous_we_re_on_full",
    "test_simultaneous_we_re_midrange",
    "test_overflow_underflow_are_combinational_not_sticky",
    "test_reset_mid_operation",
    "test_wraparound",
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

DATA_WIDTH = 32
SIZE = 128
MASK = (1 << DATA_WIDTH) - 1


def make_value(salt):
    return (salt * 0x1000_0001 + 0xA5A5_A5A5) & MASK


async def start(dut):
    """Start the clock and drive one synchronous reset cycle (POR)."""
    cocotb.start_soon(Clock(dut.clk_i, CLOCK_PERIOD_NS, unit="ns").start())
    dut.rst_i.value = 1
    dut.write.enable.value = 0
    dut.write.data.value = 0
    dut.read.enable.value = 0
    await RisingEdge(dut.clk_i)
    dut.rst_i.value = 0
    await SETTLE


async def drive(dut, we=0, re=0, data=0):
    """Drive write.enable/read.enable/write.data and let combinational
    outputs settle. Caller inspects read.data/write.overflow/
    read.underflow here -- they reflect what *would* happen if this
    cycle's edge commits, evaluated against pre-edge state."""
    dut.write.enable.value = we
    dut.write.data.value = data
    dut.read.enable.value = re
    await SETTLE


async def commit(dut):
    """Advance one clock edge, applying whatever drive() last set, then
    settle so write.fill/write.full/read.empty reflect the new post-edge
    state."""
    await RisingEdge(dut.clk_i)
    await SETTLE


def snapshot(dut):
    wr_fill = int(dut.write.fill.value)
    rd_fill = int(dut.read.fill.value)
    assert wr_fill == rd_fill, (
        f"write.fill ({wr_fill}) and read.fill ({rd_fill}) disagree -- "
        "both interfaces must reflect the same occupancy"
    )
    return {
        "data_o": int(dut.read.data.value),
        "fill_o": wr_fill,
        "full_o": int(dut.write.full.value),
        "empty_o": int(dut.read.empty.value),
        "overflow_o": int(dut.write.overflow.value),
        "underflow_o": int(dut.read.underflow.value),
    }


async def write_elem(dut, value):
    """Enqueue one value (assumes not full) and idle the ports afterward."""
    await drive(dut, we=1, data=value)
    assert int(dut.write.overflow.value) == 0, "unexpected overflow on a plain write"
    await commit(dut)
    await drive(dut)


async def read_elem(dut):
    """Dequeue one value (assumes not empty), return it, idle afterward."""
    await drive(dut, re=1)
    assert int(dut.read.underflow.value) == 0, "unexpected underflow on a plain read"
    value = int(dut.read.data.value)
    await commit(dut)
    await drive(dut)
    return value


@cocotb.test()
@phased_test
async def test_reset_state(dut):
    """After POR: empty, fill=0, full=0, data=0 with read.enable low."""
    await start(dut)
    s = snapshot(dut)
    assert s["fill_o"] == 0, f"fill = {s['fill_o']}, expected 0"
    assert s["empty_o"] == 1, "empty not set after reset"
    assert s["full_o"] == 0, "full set after reset"
    assert s["data_o"] == 0, f"read.data = {s['data_o']:#x}, expected 0"


@cocotb.test()
@phased_test
async def test_data_o_zero_when_idle(dut):
    """read.data stays 0 whenever read.enable is low, even with elements
    queued."""
    await start(dut)
    await write_elem(dut, make_value(1))
    await write_elem(dut, make_value(2))
    for _ in range(5):
        await drive(dut)
        assert int(dut.read.data.value) == 0, "read.data nonzero while read.enable low"
        await commit(dut)


@cocotb.test()
@phased_test
async def test_single_write_then_read(dut):
    await start(dut)
    value = make_value(0xBEEF)
    await write_elem(dut, value)
    s = snapshot(dut)
    assert s["fill_o"] == 1, f"fill = {s['fill_o']}, expected 1"
    assert s["empty_o"] == 0
    actual = await read_elem(dut)
    assert actual == value, f"read back {actual:#010x}, expected {value:#010x}"
    s = snapshot(dut)
    assert s["fill_o"] == 0
    assert s["empty_o"] == 1


@cocotb.test()
@phased_test
async def test_fifo_ordering(dut):
    """Values dequeue in the same order they were enqueued."""
    await start(dut)
    values = [make_value(i) for i in range(10)]
    for v in values:
        await write_elem(dut, v)
    for expected in values:
        actual = await read_elem(dut)
        assert actual == expected, (
            f"dequeued {actual:#010x}, expected {expected:#010x} (FIFO order violated)"
        )


@cocotb.test()
@phased_test
async def test_fill_to_full(dut):
    """Writing SIZE elements sequentially fills the queue exactly, with
    fill/full/empty correct at every step."""
    await start(dut)
    for i in range(SIZE):
        s = snapshot(dut)
        assert s["full_o"] == 0, f"full set early, after {i} writes"
        await write_elem(dut, make_value(i))
        s = snapshot(dut)
        assert s["fill_o"] == i + 1, f"fill = {s['fill_o']}, expected {i + 1}"
        assert s["empty_o"] == 0
    s = snapshot(dut)
    assert s["full_o"] == 1, "full not set after SIZE writes"
    assert s["fill_o"] == SIZE


@cocotb.test()
@phased_test
async def test_drain_to_empty(dut):
    """After filling to SIZE, reading SIZE elements drains it exactly, in
    order, with fill/full/empty correct at every step."""
    await start(dut)
    values = [make_value(i) for i in range(SIZE)]
    for v in values:
        await write_elem(dut, v)

    for i, expected in enumerate(values):
        s = snapshot(dut)
        assert s["empty_o"] == 0, f"empty set early, after {i} reads"
        actual = await read_elem(dut)
        assert actual == expected, f"dequeued {actual:#010x}, expected {expected:#010x}"
        s = snapshot(dut)
        assert s["fill_o"] == SIZE - (i + 1)
        assert s["full_o"] == 0
    s = snapshot(dut)
    assert s["empty_o"] == 1, "empty not set after draining SIZE elements"


@cocotb.test()
@phased_test
async def test_overflow_write_while_full(dut):
    """A write attempted while full is dropped: overflow is set exactly
    while write.enable is held against a full queue, state/data are
    unaffected, and it clears the moment write.enable is deasserted."""
    await start(dut)
    values = [make_value(i) for i in range(SIZE)]
    for v in values:
        await write_elem(dut, v)

    dropped = make_value(0xDEAD)
    await drive(dut, we=1, data=dropped)
    assert int(dut.write.overflow.value) == 1, "overflow not set on write-while-full"
    assert int(dut.read.underflow.value) == 0
    await commit(dut)
    s = snapshot(dut)
    assert s["fill_o"] == SIZE, "fill changed on a dropped write"
    assert s["overflow_o"] == 1, (
        "overflow is combinational -- must stay high while write.enable is held"
    )
    await drive(dut)  # deassert write.enable
    assert int(dut.write.overflow.value) == 0, "overflow must clear once write.enable is deasserted"
    await commit(dut)

    for expected in values:
        actual = await read_elem(dut)
        assert actual == expected, (
            f"dequeued {actual:#010x}, expected {expected:#010x} -- "
            "dropped write must not have altered queue contents"
        )


@cocotb.test()
@phased_test
async def test_underflow_read_while_empty(dut):
    """A read attempted while empty returns 0 and sets underflow for
    exactly as long as read.enable is held, with no state change."""
    await start(dut)
    await drive(dut, re=1)
    assert int(dut.read.underflow.value) == 1, "underflow not set on read-while-empty"
    assert int(dut.write.overflow.value) == 0
    assert int(dut.read.data.value) == 0, "read.data nonzero on underflow"
    await commit(dut)
    s = snapshot(dut)
    assert s["fill_o"] == 0
    assert s["underflow_o"] == 1, (
        "underflow is combinational -- must stay high while read.enable is held"
    )
    await drive(dut)  # deassert read.enable
    assert int(dut.read.underflow.value) == 0, "underflow must clear once read.enable is deasserted"


@cocotb.test()
@phased_test
async def test_simultaneous_we_re_on_empty(dut):
    """write.enable and read.enable together on an empty queue: the write
    is accepted, but read.enable still sees pre-cycle empty=1 and
    underflows -- no bypass. The written value only becomes readable on a
    later, separate read.enable pulse."""
    await start(dut)
    value = make_value(0xF00D)
    await drive(dut, we=1, re=1, data=value)
    assert int(dut.read.underflow.value) == 1, "expected underflow on empty+write+read"
    assert int(dut.write.overflow.value) == 0
    assert int(dut.read.data.value) == 0, "read.data must not bypass write.data to the same cycle"
    await commit(dut)
    await drive(dut)
    s = snapshot(dut)
    assert s["fill_o"] == 1, "the write must still have landed"
    assert s["empty_o"] == 0

    actual = await read_elem(dut)
    assert actual == value, f"read back {actual:#010x}, expected {value:#010x}"


@cocotb.test()
@phased_test
async def test_simultaneous_we_re_on_full(dut):
    """write.enable and read.enable together on a full queue: the read is
    accepted (dequeues the oldest value), but write.enable still sees
    pre-cycle full=1 and overflows -- the write is dropped even though a
    slot just freed up."""
    await start(dut)
    values = [make_value(i) for i in range(SIZE)]
    for v in values:
        await write_elem(dut, v)

    dropped = make_value(0xCAFE)
    await drive(dut, we=1, re=1, data=dropped)
    assert int(dut.write.overflow.value) == 1, "expected overflow on full+write+read"
    assert int(dut.read.underflow.value) == 0
    actual = int(dut.read.data.value)
    assert actual == values[0], f"dequeued {actual:#010x}, expected {values[0]:#010x}"
    await commit(dut)
    await drive(dut)
    s = snapshot(dut)
    assert s["fill_o"] == SIZE - 1, "net fill change must be -1 (read only)"
    assert s["full_o"] == 0

    for expected in values[1:]:
        got = await read_elem(dut)
        assert got == expected, (
            f"dequeued {got:#010x}, expected {expected:#010x} -- "
            "dropped write must not have entered the queue"
        )


@cocotb.test()
@phased_test
async def test_simultaneous_we_re_midrange(dut):
    """write.enable and read.enable together when neither full nor empty:
    both succeed, net fill is unchanged, no error flags set."""
    await start(dut)
    preload = [make_value(i) for i in range(10)]
    for v in preload:
        await write_elem(dut, v)

    pushed = make_value(0x1234)
    await drive(dut, we=1, re=1, data=pushed)
    assert int(dut.write.overflow.value) == 0
    assert int(dut.read.underflow.value) == 0
    actual = int(dut.read.data.value)
    assert actual == preload[0], f"dequeued {actual:#010x}, expected {preload[0]:#010x}"
    await commit(dut)
    await drive(dut)
    s = snapshot(dut)
    assert s["fill_o"] == len(preload), "net fill must be unchanged"

    expected_remaining = preload[1:] + [pushed]
    for expected in expected_remaining:
        got = await read_elem(dut)
        assert got == expected, f"dequeued {got:#010x}, expected {expected:#010x}"


@cocotb.test()
@phased_test
async def test_overflow_underflow_are_combinational_not_sticky(dut):
    """write.overflow/read.underflow track write.enable/read.enable &&
    full/empty combinationally, not as an edge-triggered pulse or a latch:
    each stays set for as long as its triggering condition is held (even
    across a clock edge), and clears the moment the triggering enable is
    deasserted -- no clear/ack needed."""
    await start(dut)

    # underflow: held across an edge while read.enable stays asserted on an
    # empty queue, clears only once read.enable itself is deasserted.
    await drive(dut, re=1)
    assert int(dut.read.underflow.value) == 1
    await commit(dut)
    assert int(dut.read.underflow.value) == 1, "must still be high while read.enable is held"
    await drive(dut)
    assert int(dut.read.underflow.value) == 0, "must clear once read.enable is deasserted"
    await commit(dut)
    assert int(dut.read.underflow.value) == 0

    # overflow: same shape, on a full queue.
    for i in range(SIZE):
        await write_elem(dut, make_value(i))
    await drive(dut, we=1, data=make_value(0xFFFF))
    assert int(dut.write.overflow.value) == 1
    await commit(dut)
    assert int(dut.write.overflow.value) == 1, "must still be high while write.enable is held"
    await drive(dut)
    assert int(dut.write.overflow.value) == 0, "must clear once write.enable is deasserted"
    await commit(dut)
    assert int(dut.write.overflow.value) == 0


@cocotb.test()
@phased_test
async def test_reset_mid_operation(dut):
    """Asserting rst_i while elements are queued clears fill/empty/full
    immediately, and previously queued elements are not dequeuable
    afterward."""
    await start(dut)
    for i in range(20):
        await write_elem(dut, make_value(i))

    dut.rst_i.value = 1
    dut.write.enable.value = 0
    dut.read.enable.value = 0
    await RisingEdge(dut.clk_i)
    dut.rst_i.value = 0
    await SETTLE

    s = snapshot(dut)
    assert s["fill_o"] == 0, f"fill = {s['fill_o']} after reset, expected 0"
    assert s["empty_o"] == 1
    assert s["full_o"] == 0

    # Queue behaves like a fresh one: write-then-read round-trips correctly,
    # with no leftover pre-reset data surfacing.
    value = make_value(0x5EED)
    await write_elem(dut, value)
    actual = await read_elem(dut)
    assert actual == value, f"post-reset read back {actual:#010x}, expected {value:#010x}"


@cocotb.test()
@phased_test
async def test_wraparound(dut):
    """Sustained write/read traffic that pushes cumulative operations well
    past SIZE, oscillating occupancy so the queue never goes full or empty,
    checked against a Python deque reference. Exercises internal wraparound
    without assuming any particular implementation of it."""
    await start(dut)
    random.seed(0xFEED)
    reference = deque()

    # Preload to a mid-range occupancy so both write-only and read-only
    # imbalance stays possible without hitting either boundary.
    half = SIZE // 2
    for i in range(half):
        v = make_value(i)
        await write_elem(dut, v)
        reference.append(v)

    salt = 1000
    for _ in range(4 * SIZE):
        do_write = random.random() < 0.5
        if do_write and len(reference) < SIZE - 1:
            v = make_value(salt)
            salt += 1
            await write_elem(dut, v)
            reference.append(v)
        elif reference:
            expected = reference.popleft()
            actual = await read_elem(dut)
            assert actual == expected, (
                f"dequeued {actual:#010x}, expected {expected:#010x} (wraparound stress)"
            )

    s = snapshot(dut)
    assert s["fill_o"] == len(reference), (
        f"fill = {s['fill_o']}, expected {len(reference)} to match reference model"
    )

    while reference:
        expected = reference.popleft()
        actual = await read_elem(dut)
        assert actual == expected, f"dequeued {actual:#010x}, expected {expected:#010x}"
