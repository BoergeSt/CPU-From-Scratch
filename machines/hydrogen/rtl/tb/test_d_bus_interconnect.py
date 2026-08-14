"""cocotb testbench for the Hydrogen D-bus interconnect (see
machines/hydrogen/docs/interconnect.md).

Purely combinational (no clk_i/rst_i): every test drives core_if (the
master side) and bram_if/uart0_if's rdata/ack (standing in for the real
slaves), awaits a settle delay, then checks decode/translation/enable-
gating/response-mux against interconnect.md's v1 address map.
"""

import functools

import cocotb
from cocotb.triggers import Timer

# Mirrors d_bus_interconnect_tb_top.sv's test_phase_e -- order must match
# the SV declaration (index + 1, since PHASE_IDLE is 0). phased_test()
# below uses this to drive dut.dbg_test_phase, which shows the currently-
# running test by name in the waveform (Surfer/GTKWave enum decode) -- all
# tests below share one simulation run and one continuous waveform dump,
# so this is what makes a given test's slice of the timeline identifiable
# at all.
PHASE_NAMES = [
    "test_bram_range_enables_bram_only",
    "test_uart_range_enables_uart_only",
    "test_reserved_gap_is_unmapped",
    "test_past_uart_range_is_unmapped",
    "test_bram_address_translation_is_identity",
    "test_uart_address_translation_is_local_3_bit",
    "test_response_mux_reflects_selected_slave",
    "test_unmapped_response_ignores_slave_outputs",
    "test_enable_low_selects_no_slave",
    "test_wdata_and_we_fan_out_to_every_slave",
    "test_bram_uart_boundary",
    "test_reserved_gap_boundaries",
    "test_decode_independent_of_we",
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


SETTLE = Timer(1, unit="ns")

BRAM_BASE = 0x00000
BRAM_TOP = 0x0FFFF
RESERVED_BASE = 0x10000
RESERVED_TOP = 0x100FF
UART_BASE = 0x10100
UART_TOP = 0x10107
PAST_UART = 0x10108


async def drive(
    dut,
    *,
    addr=0,
    enable=1,
    we=0,
    wdata=0,
    bram_rdata=0,
    bram_ack=0,
    uart_rdata=0,
    uart_ack=0,
):
    dut.core_if.addr.value = addr
    dut.core_if.enable.value = enable
    dut.core_if.we.value = we
    dut.core_if.wdata.value = wdata
    dut.bram_if.rdata.value = bram_rdata
    dut.bram_if.ack.value = bram_ack
    dut.uart0_if.rdata.value = uart_rdata
    dut.uart0_if.ack.value = uart_ack
    await SETTLE


@cocotb.test()
@phased_test
async def test_bram_range_enables_bram_only(dut):
    """Any address in bram_if's fixed 0x00000-0x0FFFF window enables
    bram_if and never uart0_if, independent of bram's real instantiated
    Size (interconnect.md's Address map)."""
    for addr in (BRAM_BASE, 0x1, 0x1000, 0xABCD, BRAM_TOP):
        await drive(dut, addr=addr)
        assert int(dut.bram_if.enable.value) == 1, f"addr={addr:#x}"
        assert int(dut.uart0_if.enable.value) == 0, f"addr={addr:#x}"


@cocotb.test()
@phased_test
async def test_uart_range_enables_uart_only(dut):
    """Every address in uart0_if's 8-word block enables uart0_if and never
    bram_if."""
    for addr in range(UART_BASE, UART_TOP + 1):
        await drive(dut, addr=addr)
        assert int(dut.uart0_if.enable.value) == 1, f"addr={addr:#x}"
        assert int(dut.bram_if.enable.value) == 0, f"addr={addr:#x}"


@cocotb.test()
@phased_test
async def test_reserved_gap_is_unmapped(dut):
    """The 0x10000-0x100FF gap between bram_if's window and uart0_if
    enables neither slave and reports ack=0/rdata=0."""
    for addr in (RESERVED_BASE, 0x10080, RESERVED_TOP):
        await drive(dut, addr=addr)
        assert int(dut.bram_if.enable.value) == 0, f"addr={addr:#x}"
        assert int(dut.uart0_if.enable.value) == 0, f"addr={addr:#x}"
        assert int(dut.core_if.ack.value) == 0, f"addr={addr:#x}"
        assert int(dut.core_if.rdata.value) == 0, f"addr={addr:#x}"


@cocotb.test()
@phased_test
async def test_past_uart_range_is_unmapped(dut):
    """An address past uart0_if's block is unmapped, same as the reserved
    gap."""
    for addr in (PAST_UART, 0x1FFFF, 0xFFFF_FFFF):
        await drive(dut, addr=addr)
        assert int(dut.bram_if.enable.value) == 0, f"addr={addr:#x}"
        assert int(dut.uart0_if.enable.value) == 0, f"addr={addr:#x}"
        assert int(dut.core_if.ack.value) == 0, f"addr={addr:#x}"


@cocotb.test()
@phased_test
async def test_bram_address_translation_is_identity(dut):
    """bram_if's base is 0, so it sees the raw global address unchanged."""
    for addr in (BRAM_BASE, 0x1, 0x1234, BRAM_TOP):
        await drive(dut, addr=addr)
        assert int(dut.bram_if.addr.value) == addr, f"addr={addr:#x}"


@cocotb.test()
@phased_test
async def test_uart_address_translation_is_local_3_bit(dut):
    """uart0_if sees addr[2:0] (global addr - 0x10100) as its local
    address."""
    for addr in range(UART_BASE, UART_TOP + 1):
        await drive(dut, addr=addr)
        assert int(dut.uart0_if.addr.value) == addr - UART_BASE, f"addr={addr:#x}"


@cocotb.test()
@phased_test
async def test_response_mux_reflects_selected_slave(dut):
    """core_if.rdata/ack track whichever slave is actually selected, not a
    fixed one -- exercised with distinct rdata and opposite ack values on
    each slave."""
    await drive(
        dut,
        addr=BRAM_BASE,
        bram_rdata=0xAAAA_0001,
        bram_ack=1,
        uart_rdata=0xBBBB_0002,
        uart_ack=0,
    )
    assert int(dut.core_if.rdata.value) == 0xAAAA_0001
    assert int(dut.core_if.ack.value) == 1

    await drive(
        dut,
        addr=UART_BASE,
        bram_rdata=0xAAAA_0001,
        bram_ack=1,
        uart_rdata=0xBBBB_0002,
        uart_ack=0,
    )
    assert int(dut.core_if.rdata.value) == 0xBBBB_0002
    assert int(dut.core_if.ack.value) == 0


@cocotb.test()
@phased_test
async def test_unmapped_response_ignores_slave_outputs(dut):
    """An unmapped access reports ack=0/rdata=0 even if both slaves happen
    to be driving nonzero rdata and ack=1."""
    await drive(
        dut,
        addr=RESERVED_BASE,
        bram_rdata=0xDEAD_BEEF,
        bram_ack=1,
        uart_rdata=0xFEED_FACE,
        uart_ack=1,
    )
    assert int(dut.core_if.ack.value) == 0
    assert int(dut.core_if.rdata.value) == 0


@cocotb.test()
@phased_test
async def test_enable_low_selects_no_slave(dut):
    """core_if.enable=0 asserts neither slave's enable, regardless of
    addr."""
    for addr in (BRAM_BASE, UART_BASE):
        await drive(dut, addr=addr, enable=0)
        assert int(dut.bram_if.enable.value) == 0, f"addr={addr:#x}"
        assert int(dut.uart0_if.enable.value) == 0, f"addr={addr:#x}"


@cocotb.test()
@phased_test
async def test_wdata_and_we_fan_out_to_every_slave(dut):
    """wdata/we fan out to every slave unmuxed (bus.md), even the one that
    isn't enabled -- only each slave's own addr differs (translated)."""
    for addr in (BRAM_BASE, UART_BASE):
        await drive(dut, addr=addr, we=1, wdata=0x1234_5678)
        assert int(dut.bram_if.wdata.value) == 0x1234_5678, f"addr={addr:#x}"
        assert int(dut.bram_if.we.value) == 1, f"addr={addr:#x}"
        assert int(dut.uart0_if.wdata.value) == 0x1234_5678, f"addr={addr:#x}"
        assert int(dut.uart0_if.we.value) == 1, f"addr={addr:#x}"


@cocotb.test()
@phased_test
async def test_bram_uart_boundary(dut):
    """bram_if's last word (0xFFFF) enables bram_if; the very next address
    (0x10000) is already the reserved gap."""
    await drive(dut, addr=BRAM_TOP)
    assert int(dut.bram_if.enable.value) == 1
    assert int(dut.uart0_if.enable.value) == 0

    await drive(dut, addr=RESERVED_BASE)
    assert int(dut.bram_if.enable.value) == 0
    assert int(dut.uart0_if.enable.value) == 0


@cocotb.test()
@phased_test
async def test_reserved_gap_boundaries(dut):
    """The reserved gap's last word (0x100FF) stays unmapped; the next
    address (0x10100) is uart0_if's first word."""
    await drive(dut, addr=RESERVED_TOP)
    assert int(dut.bram_if.enable.value) == 0
    assert int(dut.uart0_if.enable.value) == 0

    await drive(dut, addr=UART_BASE)
    assert int(dut.uart0_if.enable.value) == 1
    assert int(dut.uart0_if.addr.value) == 0


@cocotb.test()
@phased_test
async def test_decode_independent_of_we(dut):
    """Decode depends only on addr/enable, not we -- writes route the same
    way reads do."""
    for addr, expect_bram, expect_uart in (
        (BRAM_BASE, 1, 0),
        (UART_BASE, 0, 1),
        (RESERVED_BASE, 0, 0),
    ):
        await drive(dut, addr=addr, we=1)
        assert int(dut.bram_if.enable.value) == expect_bram, f"addr={addr:#x}"
        assert int(dut.uart0_if.enable.value) == expect_uart, f"addr={addr:#x}"
