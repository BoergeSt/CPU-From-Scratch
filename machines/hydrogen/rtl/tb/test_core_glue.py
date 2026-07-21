"""cocotb testbench for the Hydrogen core glue (see interconnect.md's
"Control unit" build-order step -- doc not yet renamed to core_glue).

Purely combinational (no clk_i/rst_i): every test drives the "given" side of
every interface -- bus_if_I.rdata (the fetched instruction word),
regfile read1/2/3.value, alu_if.result/overflow/error, alu_status_if.
latched_overflow, flow_ctl_if.pc, bus_if_D.rdata/ack -- awaits a settle
delay, then checks the side core_glue computes.
"""

import cocotb
from cocotb.triggers import Timer

SETTLE = Timer(1, unit="ns")

IC_ALU = 0x0
IC_IMM_SET = 0x1
IC_FLOW_CTL = 0x2
IC_LOAD_IMM = 0x3
IC_STORE_IMM = 0x4
IC_LOAD = 0x5
IC_STORE = 0x6
RESERVED_ICS = [0x7, 0x8, 0x9, 0xA, 0xB, 0xC, 0xD, 0xE, 0xF]

ALU_OP_ADD = 0x0
FLOW_CTL_OP_ALWAYS = 0x9
FLOW_CTL_OP_OVERFLOW = 0xA


def make_generic(ic, dest=0, src1=0, src2=0, src3=0):
    """Assemble a 32-bit instruction word using only the fields fixed at the
    same position across every opcode (isa.md's fixed-register-position
    decision): dest [27:25], src3_addr [8:6], src2_addr [5:3], src1_addr
    [2:0]. Every other bit is left 0."""
    return (
        (ic & 0xF) << 28
        | (dest & 0x7) << 25
        | (src3 & 0x7) << 6
        | (src2 & 0x7) << 3
        | (src1 & 0x7) << 0
    )


def make_reserved(ic, src1=0, src2=0, src3=0):
    return make_generic(ic, dest=0, src1=src1, src2=src2, src3=src3)


def make_alu(dest=0, alu_op=ALU_OP_ADD, is_imm_src1=0, is_imm_src2=0, imm=0, src1=0, src2=0):
    return (
        (IC_ALU & 0xF) << 28
        | (dest & 0x7) << 25
        | (alu_op & 0xF) << 21
        | (is_imm_src1 & 0x1) << 20
        | (is_imm_src2 & 0x1) << 19
        | (imm & 0x1FFF) << 6
        | (src2 & 0x7) << 3
        | (src1 & 0x7) << 0
    )


def make_imm_set(dest=0, imm=0):
    return (IC_IMM_SET & 0xF) << 28 | (dest & 0x7) << 25 | (imm & 0x1FF_FFFF)


def make_flow_ctl(op=FLOW_CTL_OP_ALWAYS, r=0, i=0, imm=0, jump_to_addr=0, src1=0, src2=0):
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


def make_load_imm(dest=0, imm=0):
    """isa.md: LOAD_IMM -- ic[31:28], dest[27:25], imm[24:0]."""
    return (IC_LOAD_IMM & 0xF) << 28 | (dest & 0x7) << 25 | (imm & 0x1FF_FFFF)


def make_store_imm(imm=0, src=0):
    """isa.md: STORE_IMM -- ic[31:28], imm[27:3], src[2:0]. `src` sits at the
    universal [2:0] read position, same as every other opcode's first
    register-read operand."""
    return (IC_STORE_IMM & 0xF) << 28 | (imm & 0x1FF_FFFF) << 3 | (src & 0x7)


def make_load(dest=0, offset=0, base=0):
    """isa.md: LOAD -- ic[31:28], dest[27:25], offset[24:3], base[2:0].
    `base` sits at the universal [2:0] read position."""
    return (IC_LOAD & 0xF) << 28 | (dest & 0x7) << 25 | (offset & 0x3F_FFFF) << 3 | (base & 0x7)


def make_store(offset=0, src=0, base=0):
    """isa.md: STORE -- ic[31:28], offset[27:6], src[5:3], base[2:0]. `src`/
    `base` sit at the universal [5:3]/[2:0] read positions."""
    return (
        (IC_STORE & 0xF) << 28
        | (offset & 0x3F_FFFF) << 6
        | (src & 0x7) << 3
        | (base & 0x7)
    )


async def drive(
    dut,
    *,
    rdata=0,
    ack=1,
    r1_value=0,
    r2_value=0,
    r3_value=0,
    alu_result=0,
    alu_overflow=0,
    alu_error=0,
    latched_overflow=0,
    pc=0,
    bus_d_rdata=0,
    bus_d_ack=1,
):
    dut.bus_I.rdata.value = rdata
    dut.bus_I.ack.value = ack
    dut.bus_D.rdata.value = bus_d_rdata
    dut.bus_D.ack.value = bus_d_ack
    dut.read_1.value.value = r1_value
    dut.read_2.value.value = r2_value
    dut.read_3.value.value = r3_value
    dut.alu.result.value = alu_result
    dut.alu.overflow.value = alu_overflow
    dut.alu.error.value = alu_error
    dut.alu_status.latched_overflow.value = latched_overflow
    dut.flow_ctl.pc.value = pc
    await SETTLE


@cocotb.test()
async def test_register_read_addresses_always_tap_fixed_positions(dut):
    """read1/read2/read3.addr mirror instruction bits [2:0]/[5:3]/[8:6]
    unconditionally, regardless of major opcode -- no opcode-dependent
    address mux anywhere (CLAUDE.md's fixed-register-position decision)."""
    cases = [
        (IC_ALU, 1, 2, 3),
        (IC_FLOW_CTL, 5, 6, 7),
        (IC_IMM_SET, 4, 0, 0),
        (IC_STORE_IMM, 2, 0, 0),
        (IC_LOAD, 6, 0, 0),
        (IC_STORE, 1, 3, 0),
        (0x7, 7, 7, 7),
    ]
    for ic, src1, src2, src3 in cases:
        instr = make_generic(ic, src1=src1, src2=src2, src3=src3)
        await drive(dut, rdata=instr)
        assert int(dut.read_1.addr.value) == src1, f"ic={ic:#x}"
        assert int(dut.read_2.addr.value) == src2, f"ic={ic:#x}"
        assert int(dut.read_3.addr.value) == src3, f"ic={ic:#x}"


@cocotb.test()
async def test_instruction_broadcast_to_every_functional_unit(dut):
    """The fetched instruction word (bus_if_I.rdata) is broadcast unchanged
    to alu_if/flow_ctl_if/alu_status_if.instruction -- CLAUDE.md's
    functional-units-get-the-whole-instruction decision."""
    instr = make_alu(dest=1, alu_op=ALU_OP_ADD, src1=2, src2=3)
    await drive(dut, rdata=instr)
    assert int(dut.alu.instruction.value) == instr
    assert int(dut.flow_ctl.instruction.value) == instr
    assert int(dut.alu_status.instruction.value) == instr


@cocotb.test()
async def test_alu_and_flow_ctl_share_read1_read2_value(dut):
    """alu_if.value1/value2 and flow_ctl_if.value1/value2 both mirror
    regfile read1/read2.value -- the same physical read ports serve both
    units (isa.md's fixed-register-position decision)."""
    instr = make_generic(IC_ALU, src1=1, src2=2)
    await drive(dut, rdata=instr, r1_value=0xAAAA_0001, r2_value=0xBBBB_0002)
    assert int(dut.alu.value1.value) == 0xAAAA_0001
    assert int(dut.alu.value2.value) == 0xBBBB_0002
    assert int(dut.flow_ctl.value1.value) == 0xAAAA_0001
    assert int(dut.flow_ctl.value2.value) == 0xBBBB_0002


@cocotb.test()
async def test_flow_ctl_goto_val_from_read3(dut):
    """flow_ctl_if.goto_val mirrors regfile read3.value -- the
    register-indirect jump target (flow_ctl.md)."""
    instr = make_generic(IC_FLOW_CTL, src3=5)
    await drive(dut, rdata=instr, r3_value=0xCCCC_0003)
    assert int(dut.flow_ctl.goto_val.value) == 0xCCCC_0003


@cocotb.test()
async def test_alu_status_receives_live_alu_overflow(dut):
    """alu_status_if.overflow mirrors the ALU's live bus.overflow, forwarded
    unconditionally every cycle (alu_status.md)."""
    instr = make_alu(alu_op=ALU_OP_ADD)
    await drive(dut, rdata=instr, alu_overflow=1)
    assert int(dut.alu_status.overflow.value) == 1

    await drive(dut, rdata=instr, alu_overflow=0)
    assert int(dut.alu_status.overflow.value) == 0


@cocotb.test()
async def test_flow_ctl_receives_latched_overflow(dut):
    """flow_ctl_if.overflow mirrors alu_status_if.latched_overflow, not the
    ALU's live flag -- flow_ctl.md's overflow/not_overflow conditions read
    the latched value."""
    instr = make_flow_ctl(op=FLOW_CTL_OP_OVERFLOW)
    await drive(dut, rdata=instr, latched_overflow=1, alu_overflow=0)
    assert int(dut.flow_ctl.overflow.value) == 1

    await drive(dut, rdata=instr, latched_overflow=0, alu_overflow=1)
    assert int(dut.flow_ctl.overflow.value) == 0


@cocotb.test()
async def test_i_bus_fetches_at_pc_every_cycle(dut):
    """bus_if_I.addr follows flow_ctl_if.pc, enable is permanently 1 (fetch
    happens every cycle unconditionally), we is permanently 0 (bus.md)."""
    await drive(dut, pc=0x10)
    assert int(dut.bus_I.addr.value) == 0x10
    assert int(dut.bus_I.enable.value) == 1
    assert int(dut.bus_I.we.value) == 0

    await drive(dut, pc=0x1234)
    assert int(dut.bus_I.addr.value) == 0x1234


@cocotb.test()
async def test_bus_d_disabled_for_non_d_bus_opcodes(dut):
    """bus_if_D.enable stays 0 for every opcode that doesn't touch the
    D-bus -- ALU/IMM_SET/FLOW_CTL/reserved."""
    instrs = [
        make_alu(alu_op=ALU_OP_ADD),
        make_imm_set(dest=1, imm=5),
        make_flow_ctl(op=FLOW_CTL_OP_ALWAYS),
    ] + [make_reserved(ic) for ic in RESERVED_ICS]
    for instr in instrs:
        await drive(dut, rdata=instr)
        assert int(dut.bus_D.enable.value) == 0, f"instr={instr:#010x}"


@cocotb.test()
async def test_alu_writeback(dut):
    """A legal ALU instruction writes alu_if.result to regfile at
    instruction.generic.dest, enable=1."""
    instr = make_alu(dest=3, alu_op=ALU_OP_ADD, src1=1, src2=2)
    await drive(dut, rdata=instr, alu_result=0x1234_5678, alu_error=0)
    assert int(dut.write.addr.value) == 3
    assert int(dut.write.value.value) == 0x1234_5678
    assert int(dut.write.enable.value) == 1


@cocotb.test()
async def test_alu_writeback_suppressed_on_error(dut):
    """An illegal ALU encoding (alu_error=1) suppresses the regfile write --
    write.enable stays 0, so the ALU's result never commits on its way to
    ErrorVector."""
    instr = make_alu(dest=3, alu_op=ALU_OP_ADD, src1=1, src2=2)
    await drive(dut, rdata=instr, alu_result=0xDEAD_BEEF, alu_error=1)
    assert int(dut.write.enable.value) == 0


@cocotb.test()
async def test_imm_set_writeback(dut):
    """IMM_SET writes its zero-extended 25-bit immediate to regfile at
    instruction.generic.dest, enable=1."""
    instr = make_imm_set(dest=5, imm=0x1FF_FFFF)
    await drive(dut, rdata=instr)
    assert int(dut.write.addr.value) == 5
    assert int(dut.write.value.value) == 0x1FF_FFFF
    assert int(dut.write.enable.value) == 1


@cocotb.test()
async def test_flow_ctl_and_reserved_never_write(dut):
    """FLOW_CTL and reserved major opcodes never assert regfile enable --
    neither ever writes a GPR (flow_ctl.md)."""
    instrs = [make_flow_ctl(op=FLOW_CTL_OP_ALWAYS)] + [make_reserved(ic) for ic in RESERVED_ICS]
    for instr in instrs:
        await drive(dut, rdata=instr)
        assert int(dut.write.enable.value) == 0, f"instr={instr:#010x}"


@cocotb.test()
async def test_error_on_reserved_major_opcode(dut):
    """Any reserved major opcode (0x7-0xF) forces flow_ctl_if.error high
    (isa.md lists 0x7-0xF as reserved)."""
    for ic in RESERVED_ICS:
        await drive(dut, rdata=make_reserved(ic))
        assert int(dut.flow_ctl.error.value) == 1, f"ic={ic:#x}"


@cocotb.test()
async def test_error_on_alu_illegal_encoding(dut):
    """alu_if.error, when the active instruction is actually ALU, forces
    flow_ctl_if.error high (isa.md's Errors)."""
    instr = make_alu(alu_op=ALU_OP_ADD)
    await drive(dut, rdata=instr, alu_error=1)
    assert int(dut.flow_ctl.error.value) == 1


@cocotb.test()
async def test_alu_error_ignored_when_not_alu_instruction(dut):
    """alu_if.error is gated by the real instruction class -- garbage bits
    at the ALU's field positions during a non-ALU instruction must not trip
    flow_ctl_if.error (alu.md's Overview: the ALU computes bus.error
    unconditionally every cycle; gating it on the real class is the
    control unit's job)."""
    for instr in (make_flow_ctl(op=FLOW_CTL_OP_ALWAYS), make_imm_set(dest=1, imm=5)):
        await drive(dut, rdata=instr, alu_error=1)
        assert int(dut.flow_ctl.error.value) == 0, f"instr={instr:#010x}"


@cocotb.test()
async def test_no_error_on_legal_instructions(dut):
    """A legal ALU (no error), IMM_SET, or FLOW_CTL instruction leaves
    flow_ctl_if.error low."""
    for instr in (
        make_alu(alu_op=ALU_OP_ADD),
        make_imm_set(dest=1, imm=5),
        make_flow_ctl(op=FLOW_CTL_OP_ALWAYS),
    ):
        await drive(dut, rdata=instr, alu_error=0)
        assert int(dut.flow_ctl.error.value) == 0, f"instr={instr:#010x}"


@cocotb.test()
async def test_error_on_i_bus_ack_failure(dut):
    """An I-bus fetch that fails to ack forces flow_ctl_if.error high
    (bus.md's ack semantics)."""
    await drive(dut, rdata=make_alu(alu_op=ALU_OP_ADD), ack=0)
    assert int(dut.flow_ctl.error.value) == 1


@cocotb.test()
async def test_error_on_d_bus_ack_failure(dut):
    """A D-bus access that fails to ack forces flow_ctl_if.error high, but
    only when bus_D.enable is actually asserted -- an opcode that never
    touches the D-bus can't be spuriously tripped by bus_D.ack (bus.md's
    `enable && !ack` formula)."""
    instr = make_load_imm(dest=1, imm=0x100)
    await drive(dut, rdata=instr, bus_d_ack=0)
    assert int(dut.flow_ctl.error.value) == 1

    await drive(dut, rdata=make_alu(alu_op=ALU_OP_ADD), bus_d_ack=0)
    assert int(dut.flow_ctl.error.value) == 0


@cocotb.test()
async def test_load_imm(dut):
    """LOAD_IMM: bus_D.addr is the zero-extended 25-bit imm, enable=1,
    we=0; write.addr=dest, write.value=bus_D.rdata, write.enable=1 --
    unconditionally, not suppressed by a D-bus ack failure (unlike the ALU
    illegal-encoding case)."""
    for imm in (0, 0x1FF_FFFF, 0x0ABC_DEF):
        instr = make_load_imm(dest=3, imm=imm)
        await drive(dut, rdata=instr, bus_d_rdata=0xCAFE_BABE)
        assert int(dut.bus_D.addr.value) == imm, f"imm={imm:#x}"
        assert int(dut.bus_D.enable.value) == 1
        assert int(dut.bus_D.we.value) == 0
        assert int(dut.write.addr.value) == 3
        assert int(dut.write.value.value) == 0xCAFE_BABE
        assert int(dut.write.enable.value) == 1


@cocotb.test()
async def test_store_imm(dut):
    """STORE_IMM: bus_D.addr is the zero-extended 25-bit imm, enable=1,
    we=1, wdata=src's value (read_1, since src sits at the universal [2:0]
    read position); never asserts write.enable."""
    instr = make_store_imm(imm=0x1FF_FFFF, src=2)
    await drive(dut, rdata=instr, r1_value=0x1234_5678)
    assert int(dut.bus_D.addr.value) == 0x1FF_FFFF
    assert int(dut.bus_D.enable.value) == 1
    assert int(dut.bus_D.we.value) == 1
    assert int(dut.bus_D.wdata.value) == 0x1234_5678
    assert int(dut.write.enable.value) == 0


LOAD_STORE_OFFSET_CASES = [
    (0, "zero offset"),
    (100, "positive offset"),
    (-10, "negative offset, two's complement"),
]


@cocotb.test()
async def test_load_effective_address_and_writeback(dut):
    """LOAD's effective address is base's value + offset, offset
    interpreted as two's complement (isa.md); write.addr=dest,
    write.value=bus_D.rdata, write.enable=1."""
    for offset, description in LOAD_STORE_OFFSET_CASES:
        instr = make_load(dest=4, offset=offset, base=1)
        await drive(dut, rdata=instr, r1_value=0x1000, bus_d_rdata=0xDEAD_0000)
        expected_addr = (0x1000 + offset) & 0xFFFF_FFFF
        assert int(dut.bus_D.addr.value) == expected_addr, description
        assert int(dut.bus_D.enable.value) == 1
        assert int(dut.bus_D.we.value) == 0
        assert int(dut.write.addr.value) == 4
        assert int(dut.write.value.value) == 0xDEAD_0000
        assert int(dut.write.enable.value) == 1


@cocotb.test()
async def test_store_effective_address_and_no_writeback(dut):
    """STORE's effective address is base's value + offset, same semantics
    as LOAD; wdata=src's value (read_2, since src sits at the universal
    [5:3] read position); never asserts write.enable."""
    for offset, description in LOAD_STORE_OFFSET_CASES:
        instr = make_store(offset=offset, src=3, base=2)
        await drive(dut, rdata=instr, r1_value=0x2000, r2_value=0x9999_8888)
        expected_addr = (0x2000 + offset) & 0xFFFF_FFFF
        assert int(dut.bus_D.addr.value) == expected_addr, description
        assert int(dut.bus_D.enable.value) == 1
        assert int(dut.bus_D.we.value) == 1
        assert int(dut.bus_D.wdata.value) == 0x9999_8888
        assert int(dut.write.enable.value) == 0


@cocotb.test()
async def test_load_effective_address_underflow_forces_error(dut):
    """LOAD: if the true (unbounded) base + offset sum is negative, that's
    an error -- same treatment as flow_ctl's relative-jump underflow
    (flow_ctl.md's Design rationale). bus_D.enable stays 0 -- the bus never
    activates on an out-of-range address."""
    instr = make_load(dest=4, offset=-10, base=1)
    await drive(dut, rdata=instr, r1_value=5)
    assert int(dut.flow_ctl.error.value) == 1
    assert int(dut.bus_D.enable.value) == 0


@cocotb.test()
async def test_load_effective_address_overflow_forces_error(dut):
    """LOAD: if the true sum exceeds 2**32-1, same treatment as the
    underflow case above."""
    instr = make_load(dest=4, offset=16, base=1)
    await drive(dut, rdata=instr, r1_value=0xFFFF_FFFF)
    assert int(dut.flow_ctl.error.value) == 1
    assert int(dut.bus_D.enable.value) == 0


@cocotb.test()
async def test_store_effective_address_underflow_forces_error(dut):
    """STORE: same underflow treatment as LOAD."""
    instr = make_store(offset=-10, src=3, base=2)
    await drive(dut, rdata=instr, r1_value=5, r2_value=0x1111_1111)
    assert int(dut.flow_ctl.error.value) == 1
    assert int(dut.bus_D.enable.value) == 0


@cocotb.test()
async def test_store_effective_address_overflow_forces_error(dut):
    """STORE: same overflow treatment as LOAD."""
    instr = make_store(offset=16, src=3, base=2)
    await drive(dut, rdata=instr, r1_value=0xFFFF_FFFF, r2_value=0x1111_1111)
    assert int(dut.flow_ctl.error.value) == 1
    assert int(dut.bus_D.enable.value) == 0
