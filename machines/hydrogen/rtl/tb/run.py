"""cocotb harness that loads an assembled Hydrogen program (see
machines/hydrogen/docs/assembler.md) into the real BRAM array and runs it
for a fixed number of cycles, logging final PC/register state.

Not a directed test -- no assertions, just execution + observation, driven
by `just run`. Preloading is hierarchical, same as test_hydrogen.py's
load_program: nothing external can drive the I-bus, the core itself owns
it. Assumes the image starts at word address 0x0 (assembler.md's
convention: every program's earliest `.org` is 0x0, holding the
error/halt handler).
"""

import os

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer

CLOCK_PERIOD_NS = 10
NUM_REGS = 8
DEFAULT_CYCLES = 1000


async def load_program(dut, path):
    with open(path, "rb") as f:
        data = f.read()
    num_words = len(data) // 4
    cocotb.log.info("Loading %d words from %s", num_words, path)
    for i in range(0, len(data), 4):
        word = int.from_bytes(data[i : i + 4], byteorder="little")
        dut.bram.bram[i // 4].value = word
    await Timer(1, unit="ns")
    for addr in range(num_words):
        readback = int(dut.bram.bram[addr].value)
        cocotb.log.info("bram[%#04x] = %#010x", addr, readback)


@cocotb.test()
async def run(dut):
    program_path = os.environ["HYDROGEN_PROGRAM"]
    num_cycles = int(os.environ.get("HYDROGEN_CYCLES", DEFAULT_CYCLES))

    await load_program(dut, program_path)

    cocotb.start_soon(Clock(dut.clk_i, CLOCK_PERIOD_NS, unit="ns").start())
    dut.rst_i.value = 1
    # A clock edge-based wait here (RisingEdge/ClockCycles) would resolve
    # against the clock's own first toggle, which lands at this same
    # simulation instant (start_soon only schedules the clock, it starts
    # ticking once this coroutine yields) -- reset would be asserted and
    # cleared within one simulation timestamp, functionally fine (the
    # flip-flops still sample it) but invisible in a trace, which only
    # records the settled value per distinct time point. A fixed-duration
    # wait sidesteps the clock's own start-up timing entirely.
    await Timer(CLOCK_PERIOD_NS, unit="ns")
    dut.rst_i.value = 0

    for _ in range(num_cycles):
        await RisingEdge(dut.clk_i)

    cocotb.log.info("Final state after %d cycles:", num_cycles)
    cocotb.log.info("PC = %#010x", int(dut.flow_ctl_if.pc.value))
    for r in range(NUM_REGS):
        cocotb.log.info("R%d = %#010x", r, int(dut.regfile.registers[r].value))
