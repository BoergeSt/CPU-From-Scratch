"""cocotb testbench for the Hydrogen virtual UART (see
machines/hydrogen/docs/uart.md).

Synchronous, active-high reset (rst_i). bus is this module's only bus
port, word-addressed via addr[2:0] (CONTROL/SETTINGS/ERRORS/DATA/TX_FILL/
RX_FILL/reserved x2), per the register map in uart.md. Every access
resolves the same cycle it's presented (bus.md's no-wait-state protocol) --
bus_txn() below both samples the combinational rdata/ack and advances one
clock edge to commit whatever synchronous side effect that access has (a
register write, or a `data`-read RX-FIFO pop); a plain status read has no
side effect, but paying the same one-cycle shape for every access keeps
the helper uniform.

Assumes LSB-first bit order on the wire (standard real-world UART
convention; not pinned down in uart.md itself, since it's an internal
implementation detail) -- if the RTL sends MSB-first instead, every
serial-timing test below will need bit order flipped to match.

Divisor 2 is used for all directed/edge-case tests (uart.md's "any
nontrivial divisor" -- kept small purely so waiting out full serial frames
in sim doesn't cost many cycles); the realistic-parameter tests at the
bottom use the actual 100 MHz/divisor pairs closest to real 115200/9600
baud.
"""

import functools

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, Edge, FallingEdge, RisingEdge, Timer

CLOCK_PERIOD_NS = 10  # 100 MHz
SETTLE = Timer(1, unit="ns")

# Shared, deliberately generous timeout for every test below -- cocotb 2.x
# has no global default (only per-test timeout_time/timeout_unit), so this
# stands in for one. Sized well above the slowest legitimate test
# (test_loopback_100mhz_divisor_651's ~1.15ms of sim time) so it never
# trips on real passes, but still turns a stuck await (e.g. FallingEdge on
# a tx_o that's never driven) into a clean per-test failure instead of
# hanging `just sim` forever.
TEST_TIMEOUT_NS = 5_000_000
uart_test = functools.partial(cocotb.test, timeout_time=TEST_TIMEOUT_NS, timeout_unit="ns")

# Mirrors uart_tb_top.sv's test_phase_e -- order must match the SV
# declaration (index + 1, since PHASE_IDLE is 0). phased_test() below uses
# this to drive dut.dbg_test_phase, which shows the currently-running test
# by name in the waveform (Surfer/GTKWave enum decode) -- all tests below
# share one simulation run and one continuous waveform dump, so this is
# what makes a given test's slice of the timeline identifiable at all.
PHASE_NAMES = [
    "test_enable_rejected_when_divisor_zero",
    "test_disable_always_succeeds",
    "test_control_reset_bit_raz",
    "test_control_reserved_bits_raz_wi",
    "test_settings_writable_while_disabled",
    "test_settings_writes_ignored_while_enabled",
    "test_settings_reserved_bits_raz_wi",
    "test_errors_reserved_bits_raz_wi",
    "test_errors_w1c_semantics",
    "test_fill_registers_are_read_only",
    "test_reserved_addresses_bus_error",
    "test_data_read_while_rx_empty",
    "test_tx_push_while_disabled_then_drains_on_enable",
    "test_rx_ignored_while_disabled",
    "test_tx_fifo_full_ignore_new",
    "test_rx_fifo_full_ignore_new",
    "test_tx_fifo_ordering",
    "test_rx_fifo_ordering",
    "test_rst_i_clears_everything",
    "test_control_reset_preserves_settings",
    "test_tx_byte_8n1",
    "test_tx_byte_with_parity",
    "test_tx_byte_two_stop_bits",
    "test_rx_byte_8n1",
    "test_rx_byte_with_parity_and_two_stop_bits",
    "test_full_duplex",
    "test_rx_glitch_rejected",
    "test_rx_framing_error",
    "test_rx_parity_error",
    "test_rx_back_to_back_frames_no_gap",
    "test_loopback_100mhz_divisor_54",
    "test_loopback_100mhz_divisor_651",
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


OVERSAMPLE = 16
FIFO_DEPTH = 128

# Register map (uart.md) -- local, word addresses on bus.
CONTROL = 0x0
SETTINGS = 0x1
ERRORS = 0x2
DATA = 0x3
TX_FILL = 0x4
RX_FILL = 0x5
RESERVED_ADDRS = (0x6, 0x7)

# control (0x0)
CTRL_ENABLE = 1 << 0
CTRL_RESET = 1 << 1
CTRL_RESERVED_MASK = 0xFFFF_FFFC

# settings (0x1)
SETTINGS_DEFINED_MASK = 0x7FFF
SETTINGS_RESERVED_MASK = 0xFFFF_8000

# errors (0x2, W1C)
ERR_TX_OVERFLOW = 1 << 0
ERR_RX_OVERFLOW = 1 << 1
ERR_FRAMING = 1 << 2
ERR_PARITY = 1 << 3
ERRORS_RESERVED_MASK = 0xFFFF_FFF0


def control_word(enable=0, reset=0):
    return ((reset & 1) << 1) | (enable & 1)


def settings_word(parity_type=0, parity_en=0, stop_bits=0, divisor=0):
    return (
        ((divisor & 0xFFF) << 3)
        | ((stop_bits & 1) << 2)
        | ((parity_en & 1) << 1)
        | (parity_type & 1)
    )


def expected_parity(data_byte, parity_type):
    """Parity bit value that makes data+parity even (parity_type=0)
    or odd (parity_type=1), per uart.md's `settings.parity_type`."""
    even_bit = bin(data_byte & 0xFF).count("1") & 1
    return (1 - even_bit) if parity_type else even_bit


# --- bus transaction helpers ------------------------------------------


async def start(dut):
    """Start the clock and drive one synchronous reset cycle (POR).
    rx_i idles high (uart.md: 'idles high')."""
    cocotb.start_soon(Clock(dut.clk_i, CLOCK_PERIOD_NS, unit="ns").start())
    dut.rst_i.value = 1
    dut.bus.addr.value = 0
    dut.bus.wdata.value = 0
    dut.bus.enable.value = 0
    dut.bus.we.value = 0
    dut.rx_i.value = 1
    await RisingEdge(dut.clk_i)
    dut.rst_i.value = 0
    await SETTLE


async def bus_txn(dut, addr, wdata=0, we=0):
    """Drive one bus transaction: assert addr/wdata/we/enable, sample
    rdata/ack combinationally (same cycle, per bus.md's no-wait-state
    protocol), then advance one clock edge to commit any synchronous side
    effect, then idle the bus again."""
    dut.bus.addr.value = addr
    dut.bus.wdata.value = wdata
    dut.bus.we.value = we
    dut.bus.enable.value = 1
    await SETTLE
    rdata = int(dut.bus.rdata.value)
    ack = int(dut.bus.ack.value)
    await RisingEdge(dut.clk_i)
    dut.bus.enable.value = 0
    dut.bus.we.value = 0
    await SETTLE
    return rdata, ack


async def write_reg(dut, addr, value):
    _, ack = await bus_txn(dut, addr, wdata=value, we=1)
    return ack


async def read_reg(dut, addr):
    return await bus_txn(dut, addr, we=0)


async def enable_uart(dut, divisor, parity_en=0, parity_type=0, stop_bits=0):
    """Configure settings (requires enable=0, already the case any time
    this is called after start()/a prior disable) then enable, asserting
    the enable write actually took."""
    await write_reg(
        dut, SETTINGS, settings_word(parity_type, parity_en, stop_bits, divisor)
    )
    await write_reg(dut, CONTROL, control_word(enable=1))
    ctrl, _ = await read_reg(dut, CONTROL)
    assert ctrl & CTRL_ENABLE, f"enable did not take with divisor={divisor}"


async def disable_uart(dut):
    await write_reg(dut, CONTROL, control_word(enable=0))


# --- serial helpers -------------------------------------------------------


async def capture_tx_frame(dut, divisor, parity_en, stop_bits_count):
    """Wait for the next start bit on tx_o, sample every subsequent bit at
    its center, and decode it. Returns (data_byte, parity_bit_or_None,
    [stop_bit, ...]). Bit order: LSB-first (see module docstring)."""
    bit_cycles = divisor * OVERSAMPLE
    await FallingEdge(dut.tx_o)
    await ClockCycles(dut.clk_i, bit_cycles // 2)
    assert dut.tx_o.value == 0, "start bit not low at its center"

    nbits = 8 + (1 if parity_en else 0) + stop_bits_count
    bits = []
    for _ in range(nbits):
        await ClockCycles(dut.clk_i, bit_cycles)
        bits.append(int(dut.tx_o.value))

    data_bits, idx = bits[:8], 8
    data_byte = sum(b << i for i, b in enumerate(data_bits))
    parity_bit = None
    if parity_en:
        parity_bit = bits[idx]
        idx += 1
    stop_bits = bits[idx : idx + stop_bits_count]
    return data_byte, parity_bit, stop_bits


async def drive_rx_frame(
    dut,
    divisor,
    data_byte,
    parity_en=0,
    parity_type=0,
    stop_bits_count=1,
    corrupt_stop=False,
    corrupt_parity=False,
    idle_cycles=0,
):
    """Drive one serial frame onto rx_i: start bit, 8 data bits LSB-first,
    optional parity, stop_bits_count stop bits, then back to idle-high.
    corrupt_stop/corrupt_parity inject a framing/parity error. idle_cycles
    of idle-high are held after the frame (0 for true back-to-back
    framing, since rx_i is already idle-high at the point this returns)."""
    bit_cycles = divisor * OVERSAMPLE

    dut.rx_i.value = 0  # start bit
    await ClockCycles(dut.clk_i, bit_cycles)

    for i in range(8):
        dut.rx_i.value = (data_byte >> i) & 1
        await ClockCycles(dut.clk_i, bit_cycles)

    if parity_en:
        parity_bit = expected_parity(data_byte, parity_type)
        if corrupt_parity:
            parity_bit ^= 1
        dut.rx_i.value = parity_bit
        await ClockCycles(dut.clk_i, bit_cycles)

    for i in range(stop_bits_count):
        last = i == stop_bits_count - 1
        dut.rx_i.value = 0 if (corrupt_stop and last) else 1
        await ClockCycles(dut.clk_i, bit_cycles)

    dut.rx_i.value = 1  # back to idle, regardless of corrupt_stop
    if idle_cycles:
        await ClockCycles(dut.clk_i, idle_cycles)


async def loopback_tx_to_rx(dut):
    """Continuously mirror tx_o onto rx_i -- used by the realistic-baud
    smoke tests to exercise the DUT's own generated bit timing end-to-end,
    rather than independently re-deriving it. Runs until killed."""
    dut.rx_i.value = int(dut.tx_o.value)
    while True:
        await Edge(dut.tx_o)
        dut.rx_i.value = int(dut.tx_o.value)


# =========================================================================
# Register-level
# =========================================================================


@uart_test()
@phased_test
async def test_enable_rejected_when_divisor_zero(dut):
    """control.enable 0->1 is ignored while settings.divisor == 0 (the
    reset default) -- see uart.md's control.enable / Design rationale."""
    await start(dut)
    await write_reg(dut, CONTROL, control_word(enable=1))
    ctrl, _ = await read_reg(dut, CONTROL)
    assert ctrl & CTRL_ENABLE == 0, "enable took with divisor=0"

    await write_reg(dut, SETTINGS, settings_word(divisor=5))
    await write_reg(dut, CONTROL, control_word(enable=1))
    ctrl2, _ = await read_reg(dut, CONTROL)
    assert ctrl2 & CTRL_ENABLE, "enable did not take once divisor was nonzero"


@uart_test()
@phased_test
async def test_disable_always_succeeds(dut):
    """control.enable 1->0 is never gated (unlike 0->1)."""
    await start(dut)
    await enable_uart(dut, divisor=2)
    await disable_uart(dut)
    ctrl, _ = await read_reg(dut, CONTROL)
    assert ctrl & CTRL_ENABLE == 0


@uart_test()
@phased_test
async def test_control_reset_bit_raz(dut):
    """control.reset triggers the internal reset combinationally on write
    (see test_control_reset_preserves_settings) but is itself RAZ/WI --
    there's no latched 'reset pending' state to read back, since the
    reset always completes in exactly one cycle (uart.md's Design
    rationale)."""
    await start(dut)
    await write_reg(dut, CONTROL, control_word(reset=1))
    ctrl1, _ = await read_reg(dut, CONTROL)
    assert ctrl1 & CTRL_RESET == 0, "reset bit should read 0 immediately after being written"
    ctrl2, _ = await read_reg(dut, CONTROL)
    assert ctrl2 & CTRL_RESET == 0, "reset bit should read 0 on subsequent reads too"


@uart_test()
@phased_test
async def test_control_reserved_bits_raz_wi(dut):
    await start(dut)
    await write_reg(dut, CONTROL, 0xFFFF_FFFD)  # every bit but enable
    ctrl, _ = await read_reg(dut, CONTROL)
    assert ctrl & CTRL_RESERVED_MASK == 0, f"control reserved bits not RAZ: {ctrl:#010x}"


@uart_test()
@phased_test
async def test_settings_writable_while_disabled(dut):
    await start(dut)
    word = settings_word(parity_type=1, parity_en=1, stop_bits=1, divisor=100)
    await write_reg(dut, SETTINGS, word)
    settings, _ = await read_reg(dut, SETTINGS)
    assert settings == word


@uart_test()
@phased_test
async def test_settings_writes_ignored_while_enabled(dut):
    await start(dut)
    await enable_uart(dut, divisor=7)
    before, _ = await read_reg(dut, SETTINGS)
    await write_reg(dut, SETTINGS, settings_word(divisor=99, parity_en=1))
    after, _ = await read_reg(dut, SETTINGS)
    assert after == before, "settings changed while enabled"


@uart_test()
@phased_test
async def test_settings_reserved_bits_raz_wi(dut):
    await start(dut)
    await write_reg(dut, SETTINGS, 0xFFFF_FFFF)
    settings, _ = await read_reg(dut, SETTINGS)
    assert settings & SETTINGS_RESERVED_MASK == 0, (
        f"settings reserved bits not RAZ: {settings:#010x}"
    )
    assert settings & SETTINGS_DEFINED_MASK == SETTINGS_DEFINED_MASK


@uart_test()
@phased_test
async def test_errors_reserved_bits_raz_wi(dut):
    await start(dut)
    await write_reg(dut, ERRORS, 0xFFFF_FFFF)
    errors, _ = await read_reg(dut, ERRORS)
    assert errors & ERRORS_RESERVED_MASK == 0, f"errors reserved bits not RAZ: {errors:#010x}"


@uart_test()
@phased_test
async def test_errors_w1c_semantics(dut):
    """W1C mechanism, exercised via tx_overflow (cheap to trigger, no
    serial timing needed) -- per-trigger coverage for each error bit lives
    in its own test below."""
    await start(dut)
    for i in range(FIFO_DEPTH + 1):
        await write_reg(dut, DATA, i & 0xFF)
    errors, _ = await read_reg(dut, ERRORS)
    assert errors & ERR_TX_OVERFLOW

    errors2, _ = await read_reg(dut, ERRORS)  # read must not clear
    assert errors2 & ERR_TX_OVERFLOW

    await write_reg(dut, ERRORS, 0)  # write-0 is a no-op
    errors3, _ = await read_reg(dut, ERRORS)
    assert errors3 & ERR_TX_OVERFLOW

    await write_reg(dut, ERRORS, ERR_TX_OVERFLOW)  # write-1 clears exactly that bit
    errors4, _ = await read_reg(dut, ERRORS)
    assert errors4 & ERR_TX_OVERFLOW == 0


@uart_test()
@phased_test
async def test_fill_registers_are_read_only(dut):
    await start(dut)
    await write_reg(dut, DATA, 0x55)
    before, _ = await read_reg(dut, TX_FILL)
    await write_reg(dut, TX_FILL, 0xFFFF_FFFF)
    after, _ = await read_reg(dut, TX_FILL)
    assert after == before == 1

    before_rx, _ = await read_reg(dut, RX_FILL)
    await write_reg(dut, RX_FILL, 0xFFFF_FFFF)
    after_rx, _ = await read_reg(dut, RX_FILL)
    assert after_rx == before_rx == 0


@uart_test()
@phased_test
async def test_reserved_addresses_bus_error(dut):
    await start(dut)
    for addr in RESERVED_ADDRS:
        _, ack = await read_reg(dut, addr)
        assert ack == 0, f"addr={addr:#x} read ack={ack}, expected 0"
        _, ack = await bus_txn(dut, addr, wdata=0x1234, we=1)
        assert ack == 0, f"addr={addr:#x} write ack={ack}, expected 0"


# =========================================================================
# FIFO / data-path
# =========================================================================


@uart_test()
@phased_test
async def test_data_read_while_rx_empty(dut):
    await start(dut)
    rdata, ack = await read_reg(dut, DATA)
    assert rdata == 0
    assert ack == 1, "empty RX read must not be a bus error"
    errors, _ = await read_reg(dut, ERRORS)
    assert errors == 0


@uart_test()
@phased_test
async def test_tx_push_while_disabled_then_drains_on_enable(dut):
    await start(dut)
    byte = 0x42
    await write_reg(dut, DATA, byte)
    tx_fill, _ = await read_reg(dut, TX_FILL)
    assert tx_fill == 1

    for _ in range(50):  # tx_o must stay idle-high the whole time disabled
        await RisingEdge(dut.clk_i)
        assert dut.tx_o.value == 1, "tx_o moved while disabled"

    tx_task = cocotb.start_soon(
        capture_tx_frame(dut, divisor=2, parity_en=0, stop_bits_count=1)
    )
    await enable_uart(dut, divisor=2)
    data_byte, parity_bit, stops = await tx_task
    assert data_byte == byte
    assert parity_bit is None
    assert stops == [1]


@uart_test()
@phased_test
async def test_rx_ignored_while_disabled(dut):
    await start(dut)
    divisor = 2
    await write_reg(dut, SETTINGS, settings_word(divisor=divisor))  # configure, stay disabled
    await drive_rx_frame(dut, divisor, 0x99, idle_cycles=divisor * OVERSAMPLE)
    rx_fill, _ = await read_reg(dut, RX_FILL)
    assert rx_fill == 0, "a frame was received while disabled"

    await write_reg(dut, CONTROL, control_word(enable=1))
    await drive_rx_frame(dut, divisor, 0x99, idle_cycles=divisor * OVERSAMPLE)
    rx_fill2, _ = await read_reg(dut, RX_FILL)
    assert rx_fill2 == 1, "receiver did not pick up a frame once enabled"


@uart_test()
@phased_test
async def test_tx_fifo_full_ignore_new(dut):
    await start(dut)
    for i in range(FIFO_DEPTH):
        ack = await write_reg(dut, DATA, i & 0xFF)
        assert ack == 1
    tx_fill, _ = await read_reg(dut, TX_FILL)
    assert tx_fill == FIFO_DEPTH

    await write_reg(dut, DATA, 0xAA)  # 129th push, dropped
    tx_fill2, _ = await read_reg(dut, TX_FILL)
    assert tx_fill2 == FIFO_DEPTH, "FIFO-full write increased occupancy"
    errors, _ = await read_reg(dut, ERRORS)
    assert errors & ERR_TX_OVERFLOW


@uart_test()
@phased_test
async def test_rx_fifo_full_ignore_new(dut):
    await start(dut)
    divisor = 2
    await enable_uart(dut, divisor=divisor)
    gap = divisor * OVERSAMPLE
    for i in range(FIFO_DEPTH):
        await drive_rx_frame(dut, divisor, i & 0xFF, idle_cycles=gap)
    rx_fill, _ = await read_reg(dut, RX_FILL)
    assert rx_fill == FIFO_DEPTH

    await drive_rx_frame(dut, divisor, 0xAA, idle_cycles=gap)  # 129th, dropped
    rx_fill2, _ = await read_reg(dut, RX_FILL)
    assert rx_fill2 == FIFO_DEPTH, "FIFO-full frame increased occupancy"
    errors, _ = await read_reg(dut, ERRORS)
    assert errors & ERR_RX_OVERFLOW


@uart_test()
@phased_test
async def test_tx_fifo_ordering(dut):
    await start(dut)
    bytes_ = [0x11, 0x22, 0x33]
    for b in bytes_:
        await write_reg(dut, DATA, b)
    tx_task = cocotb.start_soon(
        capture_tx_frame(dut, divisor=2, parity_en=0, stop_bits_count=1)
    )
    await enable_uart(dut, divisor=2)
    data_byte, _, _ = await tx_task
    assert data_byte == bytes_[0]
    for expected in bytes_[1:]:
        data_byte, _, _ = await capture_tx_frame(dut, divisor=2, parity_en=0, stop_bits_count=1)
        assert data_byte == expected


@uart_test()
@phased_test
async def test_rx_fifo_ordering(dut):
    await start(dut)
    divisor = 2
    await enable_uart(dut, divisor=divisor)
    bytes_ = [0xAA, 0xBB, 0xCC]
    for b in bytes_:
        await drive_rx_frame(dut, divisor, b, idle_cycles=divisor * OVERSAMPLE)
    rx_fill, _ = await read_reg(dut, RX_FILL)
    assert rx_fill == len(bytes_)
    for expected in bytes_:
        popped, ack = await read_reg(dut, DATA)
        assert ack == 1 and popped == expected


# =========================================================================
# Reset scope
# =========================================================================


@uart_test()
@phased_test
async def test_rst_i_clears_everything(dut):
    await start(dut)
    await write_reg(dut, SETTINGS, settings_word(divisor=5, parity_en=1))
    await write_reg(dut, CONTROL, control_word(enable=1))
    await write_reg(dut, DATA, 0x42)
    ctrl, _ = await read_reg(dut, CONTROL)
    assert ctrl & CTRL_ENABLE, "sanity: should be enabled before rst_i"

    dut.rst_i.value = 1
    await RisingEdge(dut.clk_i)
    dut.rst_i.value = 0
    await SETTLE

    ctrl2, _ = await read_reg(dut, CONTROL)
    settings2, _ = await read_reg(dut, SETTINGS)
    errors2, _ = await read_reg(dut, ERRORS)
    tx_fill2, _ = await read_reg(dut, TX_FILL)
    assert ctrl2 == 0
    assert settings2 == 0
    assert errors2 == 0
    assert tx_fill2 == 0


@uart_test()
@phased_test
async def test_control_reset_preserves_settings(dut):
    await start(dut)
    divisor = 5
    await enable_uart(dut, divisor=divisor)
    await write_reg(dut, DATA, 0x42)

    await write_reg(dut, CONTROL, control_word(enable=1, reset=1))
    await read_reg(dut, CONTROL)  # the write above already committed the internal reset synchronously

    settings_after, _ = await read_reg(dut, SETTINGS)
    tx_fill_after, _ = await read_reg(dut, TX_FILL)
    assert settings_after == settings_word(divisor=divisor), (
        "control.reset must not touch settings"
    )
    assert tx_fill_after == 0, "control.reset must clear FIFO occupancy"


# =========================================================================
# Serial timing -- normal procedure
# =========================================================================


@uart_test()
@phased_test
async def test_tx_byte_8n1(dut):
    await start(dut)
    divisor = 2
    await enable_uart(dut, divisor=divisor)
    byte = 0xA5
    await write_reg(dut, DATA, byte)
    data_byte, parity_bit, stops = await capture_tx_frame(
        dut, divisor, parity_en=0, stop_bits_count=1
    )
    assert data_byte == byte
    assert parity_bit is None
    assert stops == [1]


@uart_test()
@phased_test
async def test_tx_byte_with_parity(dut):
    await start(dut)
    divisor = 2
    byte = 0x0F
    for parity_type in (0, 1):
        await enable_uart(dut, divisor=divisor, parity_en=1, parity_type=parity_type)
        await write_reg(dut, DATA, byte)
        data_byte, parity_bit, stops = await capture_tx_frame(
            dut, divisor, parity_en=1, stop_bits_count=1
        )
        assert data_byte == byte
        assert parity_bit == expected_parity(byte, parity_type)
        assert stops == [1]
        await disable_uart(dut)


@uart_test()
@phased_test
async def test_tx_byte_two_stop_bits(dut):
    await start(dut)
    divisor = 2
    await enable_uart(dut, divisor=divisor, stop_bits=1)
    byte = 0x3C
    await write_reg(dut, DATA, byte)
    data_byte, parity_bit, stops = await capture_tx_frame(
        dut, divisor, parity_en=0, stop_bits_count=2
    )
    assert data_byte == byte
    assert parity_bit is None
    assert stops == [1, 1]


@uart_test()
@phased_test
async def test_rx_byte_8n1(dut):
    await start(dut)
    divisor = 2
    await enable_uart(dut, divisor=divisor)
    byte = 0x5A
    await drive_rx_frame(dut, divisor, byte, idle_cycles=divisor * OVERSAMPLE)
    rx_fill, _ = await read_reg(dut, RX_FILL)
    assert rx_fill == 1
    popped, ack = await read_reg(dut, DATA)
    assert ack == 1 and popped == byte
    rx_fill2, _ = await read_reg(dut, RX_FILL)
    assert rx_fill2 == 0


@uart_test()
@phased_test
async def test_rx_byte_with_parity_and_two_stop_bits(dut):
    await start(dut)
    divisor = 2
    for parity_type in (0, 1):
        await enable_uart(
            dut, divisor=divisor, parity_en=1, parity_type=parity_type, stop_bits=1
        )
        byte = 0x81
        await drive_rx_frame(
            dut,
            divisor,
            byte,
            parity_en=1,
            parity_type=parity_type,
            stop_bits_count=2,
            idle_cycles=divisor * OVERSAMPLE,
        )
        popped, ack = await read_reg(dut, DATA)
        assert ack == 1 and popped == byte
        errors, _ = await read_reg(dut, ERRORS)
        assert errors == 0
        await disable_uart(dut)


@uart_test()
@phased_test
async def test_full_duplex(dut):
    await start(dut)
    divisor = 2
    await enable_uart(dut, divisor=divisor)
    tx_byte, rx_byte = 0x77, 0x88
    await write_reg(dut, DATA, tx_byte)

    tx_task = cocotb.start_soon(
        capture_tx_frame(dut, divisor, parity_en=0, stop_bits_count=1)
    )
    await drive_rx_frame(dut, divisor, rx_byte, idle_cycles=divisor * OVERSAMPLE)
    data_byte, parity_bit, stops = await tx_task
    assert data_byte == tx_byte
    assert parity_bit is None
    assert stops == [1]

    popped, ack = await read_reg(dut, DATA)
    assert ack == 1 and popped == rx_byte


# =========================================================================
# Serial timing -- edge / error cases
# =========================================================================


@uart_test()
@phased_test
async def test_rx_glitch_rejected(dut):
    """A low pulse shorter than the start-bit recheck window (8/16 ticks)
    is abandoned silently -- no frame committed, no error flagged."""
    await start(dut)
    divisor = 2
    await enable_uart(dut, divisor=divisor)
    bit_cycles = divisor * OVERSAMPLE

    dut.rx_i.value = 0
    await ClockCycles(dut.clk_i, bit_cycles // 4)
    dut.rx_i.value = 1
    await ClockCycles(dut.clk_i, bit_cycles * 12)  # comfortably longer than one frame

    rx_fill, _ = await read_reg(dut, RX_FILL)
    assert rx_fill == 0
    errors, _ = await read_reg(dut, ERRORS)
    assert errors == 0


@uart_test()
@phased_test
async def test_rx_framing_error(dut):
    """A framing-error frame is dropped, not delivered -- see uart.md's
    Design rationale ('A framing/parity-error frame is dropped')."""
    await start(dut)
    divisor = 2
    await enable_uart(dut, divisor=divisor)
    await drive_rx_frame(
        dut, divisor, 0xA5, corrupt_stop=True, idle_cycles=divisor * OVERSAMPLE
    )
    errors, _ = await read_reg(dut, ERRORS)
    assert errors & ERR_FRAMING
    rx_fill, _ = await read_reg(dut, RX_FILL)
    assert rx_fill == 0, "a framing-error byte was pushed onto the RX FIFO"

    await write_reg(dut, ERRORS, ERR_FRAMING)
    errors2, _ = await read_reg(dut, ERRORS)
    assert errors2 & ERR_FRAMING == 0


@uart_test()
@phased_test
async def test_rx_parity_error(dut):
    """A parity-error frame is dropped, not delivered -- see uart.md's
    Design rationale ('A framing/parity-error frame is dropped')."""
    await start(dut)
    divisor = 2
    await enable_uart(dut, divisor=divisor, parity_en=1, parity_type=0)
    await drive_rx_frame(
        dut,
        divisor,
        0x81,
        parity_en=1,
        parity_type=0,
        corrupt_parity=True,
        idle_cycles=divisor * OVERSAMPLE,
    )
    errors, _ = await read_reg(dut, ERRORS)
    assert errors & ERR_PARITY
    rx_fill, _ = await read_reg(dut, RX_FILL)
    assert rx_fill == 0, "a parity-error byte was pushed onto the RX FIFO"

    await write_reg(dut, ERRORS, ERR_PARITY)
    errors2, _ = await read_reg(dut, ERRORS)
    assert errors2 & ERR_PARITY == 0


@uart_test()
@phased_test
async def test_rx_back_to_back_frames_no_gap(dut):
    await start(dut)
    divisor = 2
    await enable_uart(dut, divisor=divisor)
    bytes_ = [0x01, 0x02, 0x03]
    for b in bytes_:
        await drive_rx_frame(dut, divisor, b, idle_cycles=0)  # zero gap between frames
    await ClockCycles(dut.clk_i, divisor * OVERSAMPLE)  # settle after the last stop bit

    rx_fill, _ = await read_reg(dut, RX_FILL)
    assert rx_fill == len(bytes_)
    for expected in bytes_:
        popped, ack = await read_reg(dut, DATA)
        assert ack == 1 and popped == expected
    errors, _ = await read_reg(dut, ERRORS)
    assert errors == 0


# =========================================================================
# Realistic-parameter smoke tests
# =========================================================================


async def realistic_loopback(dut, divisor):
    await start(dut)
    await enable_uart(dut, divisor=divisor)
    loop_task = cocotb.start_soon(loopback_tx_to_rx(dut))

    byte = 0x3C
    await write_reg(dut, DATA, byte)
    bit_cycles = divisor * OVERSAMPLE
    await ClockCycles(dut.clk_i, bit_cycles * 11)  # 10 bit periods (8N1) + margin

    rx_fill, _ = await read_reg(dut, RX_FILL)
    assert rx_fill == 1, f"rx_fill={rx_fill}, expected 1 after loopback at divisor={divisor}"
    popped, ack = await read_reg(dut, DATA)
    assert ack == 1 and popped == byte, (
        f"looped-back byte={popped:#04x}, expected {byte:#04x} at divisor={divisor}"
    )
    errors, _ = await read_reg(dut, ERRORS)
    assert errors == 0

    loop_task.kill()


@uart_test()
@phased_test
async def test_loopback_100mhz_divisor_54(dut):
    """~115740 baud, ~0.47% off standard 115200."""
    await realistic_loopback(dut, divisor=54)


@uart_test()
@phased_test
async def test_loopback_100mhz_divisor_651(dut):
    """~9600.6 baud, ~0.006% off standard 9600."""
    await realistic_loopback(dut, divisor=651)
