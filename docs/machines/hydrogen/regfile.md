# Hydrogen Register File — v1 Specification

Machine generation: **hydrogen** (H, atomic number 1 — first machine
generation, per the codename convention in `CLAUDE.md`).

Status: **implemented** — `fpga/rtl/machines/hydrogen/regfile.sv`, verified
by `fpga/rtl/machines/hydrogen/tb/test_regfile.py`
(`just check :hydrogen:regfile`). Line/branch/toggle coverage:
`just coverage :hydrogen:regfile` — toggle coverage is expected to be short
of 100% since the directed tests don't necessarily drive every one of the
256 storage bits through both transitions. The architectural register set
itself
(`R0`–`R7`, widths, "no hardwired zero") is defined in `isa.md` — this
document specifies the RTL module boundary, interface, and behavior built
around that architecture.

## Overview

This module is deliberately scoped as **just the general-purpose register
storage** — a plain, ISA-agnostic 2-read/1-write array — not a central node
that also owns ALU operand routing, flow control, or memory access. That
routing/decoding work belongs to a future control unit, kept out of this
module so it stays small, testable in isolation, and reusable across future
machine generations regardless of how their instruction encodings differ.

Concretely out of scope for this module:

- **The program counter.** No instruction field can ever name the PC as an
  operand — every register-selecting field in `isa.md` (`dest`, `src1`,
  `src2`, `base`) is a plain 3-bit `R0`–`R7` index, with no encoding space
  for PC. Combined with `isa.md`'s relative-jump semantics, which keep any
  PC arithmetic internal to the future flow-control unit, there is no
  shared datapath between the PC and `R0`–`R7` that would justify placing
  them in the same module. The PC's own module boundary is now decided: it
  lives in the flow-control unit as internal register state, alongside the
  address arithmetic that operates on it — see `flow_ctl.md`.
- **The immediate-flag operand encoding.** `isa.md`'s `src1`/`src2` fields
  are 4 bits (immediate flag + 3-bit payload); this module's read ports only
  understand plain 3-bit register indices. Deciding between "read register
  N" and "use this literal value" is future control-unit territory.
- **`alu_if`.** Whether this module's read/write ports connect directly to
  `alu_if`'s `requester` side, or through an intermediate control-unit-owned
  operand mux, is explicitly left open in `alu.md` and not resolved here.
- **The memory bus.** Not connected to this module in this version.

## Interface

### Clock and reset

`clk_i` and `rst_i` are plain module ports, not part of either interface
below. See `implementation.md` for the shared clock/reset convention;
matching how `alu_if` itself keeps clock/reset outside the data interface
(there, because the ALU has none at all; here, because they're
conventionally kept out of bus-style interfaces regardless).

While `rst_i` is high at a rising `clk_i` edge, all 8 registers (`R0`–`R7`)
are set to `0`. A POR (power-on-reset) event — asserting `rst_i` at least
once — is required before register contents are architecturally defined.

### Read port (`regfile_read_if`)

One reusable interface type, instantiated **three times** (`read1`, `read2`,
`read3` in `regfile.sv`) — all three instances are functionally identical.
Named generically rather than after the ALU's `src1`/`src2` operand roles
(`isa.md`), since a consumer other than the ALU can use these ports for
something else entirely — concretely, `read3` is claimed by the flow-control
unit's register-indirect jump target (`goto_i` in `flow_ctl.md`), not an ALU
operand at all.

| Field | Dir | Width | Description |
|-------|-----|-------|--------------|
| `addr` | in  | 3 (`reg_addr_e`) | Register index `R0`–`R7` to read |
| `data` | out | 32 | Current value of the addressed register |

(Dir is from the `regfile` modport.) `data` is combinational, no clock
involved. The mirrored `requester` modport reverses both directions,
matching the `alu`/`requester` pattern already established by `alu_if`.

### Write port (`regfile_write_if`)

One instance.

| Field | Dir | Width | Description |
|-------|-----|-------|--------------|
| `addr` | in | 3 (`reg_addr_e`) | Register index `R0`–`R7` to write |
| `data` | in | 32 | Value to write |
| `write_en` | in | 1 | Write enable — see Behavior |

(Dir is from the `regfile` modport.) Same mirrored-modport pattern as the
read port.

Two separate interface types (2 read instances + 1 write instance) rather
than one bundle spanning both — see Design rationale.

## Behavior

- **Reads are combinational and continuous.** Each read port's `data`
  reflects the current value of the register selected by `addr` at all
  times, with no clock involved — forced by the single-cycle core's
  combinational-ALU model (`alu.md`): a registered read would add a cycle
  of latency the ALU has no way to wait for.
- **Writes are synchronous.** On the rising edge of `clk_i`, if
  `write_en` is high, the register addressed by `addr` is loaded with
  `data`. If `write_en` is low, no register changes (outside of reset).
- **Reset takes unconditional priority over a simultaneous write.** If
  `rst_i` and `write_en` are both high on the same rising edge, all 8
  registers are cleared to `0` and the pending write is discarded — reset
  is not just "the default when nothing else is happening," it overrides
  write_en whenever both are asserted together.
- **Same-address same-cycle read + write** (e.g. an instruction that reads
  `R1` as an operand and also writes its result back to `R1`) needs no
  special-case bypass logic. Reads reflect the pre-write value throughout
  the cycle; the write commits atomically at the clock edge and is only
  visible starting the following cycle. This falls directly out of
  flip-flop semantics (reads driven from `Q`, writes captured into `D` at
  the edge) — no read-after-write forwarding mux is needed.
- **All 8 registers are architecturally uniform.** No hardwired-zero
  register, per `isa.md`'s explicit rejection of that idea — every register
  is freely writable general-purpose storage.

## Design rationale

- **Scoped as a plain GPR array, not a central datapath hub** — matches
  `CLAUDE.md`'s modularity/reusability principle. A 2R1W register array is
  useful to any core; a module that also understands this ISA's flow
  control, immediate encoding, and memory routing would need reworking for
  every future machine generation even though the "8×32-bit registers" part
  never changed.
- **PC excluded**, for the reasons under Overview — no shared datapath with
  `R0`–`R7` to justify bundling, same logic already used to keep the ALU
  itself dumb and ISA-agnostic (`alu.md`).
- **`clk_i`/`rst_i` as plain ports, not part of an interface** — consistent
  with the project's naming convention and with keeping clock/reset outside
  bus-style interfaces generally.
- **Split read-port / write-port interfaces, instead of one bundle like
  `alu_if`.** `alu_if` bundles everything because the ALU has exactly one
  interaction shape used by a single consumer every cycle. This module's
  read and write sides will likely have different consumers — e.g. a future
  flow-control unit will need to *read* `R0`–`R7` (register-relative jump
  targets, comparisons) but will only ever write the PC, never a GPR. A
  read-only consumer should only need to know the read-port shape, not be
  handed write-capable signals it can never legally drive. The split also
  scales cleanly with `isa.md`'s port-count note ("2 reads + 1 write" is
  literally 2 instances of one reusable type + 1 of another) — confirmed by
  `read3`: the flow-control unit's need for a 3rd read port (`flow_ctl.md`)
  turned out to be exactly one more instantiation of `regfile_read_if`, no
  interface redefinition.
- **Combinational reads, synchronous writes** — forced by the single-cycle
  core model already committed to for the combinational ALU; see Behavior.
- **No internal read-during-write bypass logic** — same-address same-cycle
  read/write is naturally correct with plain flip-flop semantics; adding a
  forwarding mux would be solving a problem that doesn't exist. See
  Behavior.
- **Reset value `0`, synchronous, active-high** — matches `CLAUDE.md`'s
  project-wide reset convention. A POR event is required at the start of
  operation, same as any synchronous-reset flip-flop bank.

## Deferred / future ideas (explicitly out of scope for v1)

- **Immediate-flag operand decode / ALU operand mux** — future control-unit
  territory, per `isa.md`'s `src1`/`src2` encoding.
- **`alu_if` `requester` role** — still open per `alu.md`; not resolved by
  this module's boundary.
- **Memory bus connection** — future work, per `CLAUDE.md`'s Phase 1 target.
