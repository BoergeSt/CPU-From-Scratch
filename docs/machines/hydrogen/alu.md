# Hydrogen ALU — v1 Specification

Machine generation: **hydrogen** (H, atomic number 1 — first machine
generation, per the codename convention in `CLAUDE.md`).

Status: **implemented** — `fpga/rtl/machines/hydrogen/alu.sv`, verified by
`fpga/rtl/machines/hydrogen/tb/test_alu.py` (`just check :hydrogen:alu`).
Line/branch/toggle coverage: `just coverage :hydrogen:alu`. Line coverage is
expected to be short of 100% here: the reserved-opcode `default:` case (see
`CLAUDE.md`'s illegal-instruction-exception item under Future directions)
has no directed test hitting it yet, since none exists to exercise the
`alu_op` `0xC`–`0xF` path.

This document covers the RTL module boundary, interface, and timing.
Everything about what an `ALU` instruction means — the operations table,
overflow rules, illegal encodings, operand-sourcing rules — is specified in
`isa.md`; this module implements that encoding and doesn't restate it.

## Overview

The ALU is a stateless, purely combinational module: `bus.result`,
`bus.overflow`, and `bus.error` are pure functions of `bus.instruction`,
`bus.value1`, and `bus.value2`, valid within the same cycle. This matches
Hydrogen's single-cycle core model, where the register file and PC (outside
this module) are what actually get clocked, capturing the ALU's output at
the end of each cycle. Since there's no internal state, the module has no
clock or reset port either.

`bus.instruction` is the **entire 32-bit fetched instruction word**,
typed `isa_pkg::instr_t`, not a pre-decoded field — per `CLAUDE.md`'s
functional-units-get-the-whole-instruction decision. The ALU decodes
`bus.instruction.alu.op`, `.is_imm_src1`/`.is_imm_src2`, and `.imm` every
cycle unconditionally; it does not compare `bus.instruction`'s major-opcode
field (`.generic.ic`) against `IC_ALU` anywhere, so `bus.result`/
`bus.overflow`/`bus.error` are computed from whatever bits sit in those
field positions even on a cycle where the active instruction isn't an
`ALU` op. This is safe only because nothing downstream is expected to read
these outputs on such a cycle — a future control unit gates register-file
writes and error aggregation on the real instruction class, not on
anything the ALU itself asserts.

## Interface

The ALU has a single port, `bus`, of interface type `alu_if` (defined in
`alu_if.sv`), connected via the `alu` modport.

| `alu_if` field | Dir | Width | Description |
|----------------|-----|-------|--------------|
| `instruction`  | in  | 32 (`instr_t`) | Entire fetched instruction word |
| `value1`       | in  | 32 | Register read1 data |
| `value2`       | in  | 32 | Register read2 data, ignored by `NOT` |
| `result`       | out | 32 | Result, unsigned |
| `overflow`     | out | 1  | See `isa.md`'s Flags |
| `error`        | out | 1  | Illegal-encoding flag, see `isa.md`'s Errors |

(Dir is from the `alu` modport.) `instruction` is described in Overview.
`value1`/`value2` are the values of whichever registers
`instruction.alu.src1_addr`/`.src2_addr` name, always driven regardless of
`is_imm_src1`/`is_imm_src2`. The `requester` modport mirrors every
direction (the side driving the ALU sees `instruction`/`value1`/`value2`
as outputs and `result`/`overflow`/`error` as inputs) — see `alu_if.sv`.
`value1`/`value2` come from `regfile`'s `read1`/`read2` ports, which are
permanently wired to `instruction.alu.src1_addr`/`.src2_addr` system-wide
(`CLAUDE.md`'s fixed-register-position decision) — no module, including
this one, computes or requests that address.

No clock/reset ports — see Overview.

## Design rationale

- **`bus` interface (`alu_if`) instead of five flat ports**: bundles the
  operand/instruction/result/flag signals into one interface with mirrored
  `alu`/`requester` modports, so whatever drives the ALU connects through
  the same interface instance instead of every signal being wired by hand
  at each instantiation — the general interfaces-over-flat-ports
  convention from `CLAUDE.md`.
- **`bus.instruction` is the whole 32-bit instruction, not a pre-decoded
  4-bit field.** Per `CLAUDE.md`'s functional-units-get-the-whole-
  instruction decision — the ALU decodes `alu_op`/`is_imm_src1`/
  `is_imm_src2`/`imm` itself, rather than something upstream pre-slicing
  those fields. This also resolves what used to be an open question here
  about which module plays the interface's `requester` side:
  `value1`/`value2` are just `regfile`'s fixed `read1`/`read2` data, wired
  system-wide (see Interface), no operand-mux module needed at all.
- **`value1`/`value2` fixed at `instruction.alu.src1_addr`/`.src2_addr`,
  always read regardless of `is_imm_src1`/`is_imm_src2`.** Per
  `CLAUDE.md`'s fixed-register-position decision — shared with
  `FLOW_CTL`'s `val1`/`val2` (`flow_ctl.md`), so `regfile`'s `read1`/
  `read2` ports never need opcode-dependent address routing.
- **Combinational, no clock/reset**: required by the single-cycle core
  model (Phase 1 target) — a registered/pipelined ALU would add a cycle of
  latency between operands and result, which belongs to a later, deliberate
  revision (see Deferred ideas and `CLAUDE.md`'s "ALU: purely combinational
  for Phase 1" decision).
- **No major-opcode self-detection.** Unlike `flow_ctl.sv`/`alu_status.sv`,
  this module never compares `bus.instruction.generic.ic` against `IC_ALU`
  — it decodes and computes unconditionally every cycle. Its outputs are
  only meaningful on a cycle where the active instruction actually is
  `ALU`-encoded; a future control unit is responsible for not consuming
  `bus.result`/`bus.overflow`/`bus.error` on any other cycle. Adding a
  self-detected "not my instruction" default here would duplicate logic
  the control unit already has to do to decide which module's output to
  commit.

## Deferred / future ideas (explicitly out of scope for v1)

Not forgotten — intentionally parked for a later revision. Encoding-level
deferrals (`DIV`/`MOD`, a `carry` flag, signed arithmetic, etc.) are listed
in `isa.md`; this module's own:

- **Registered/pipelined ALU** — see `CLAUDE.md`'s "ALU: purely
  combinational for Phase 1" decision; a future revision, not an oversight.

## Overflow latching (not part of this module)

Because the ALU is combinational and the core is single-cycle,
`bus.overflow` is only valid during the same cycle as the instruction that
produced it. The conditional-branch instructions consuming it — `overflow`
and `not_overflow` in `flow_ctl.md`'s `FLOW_CTL` encoding — need something
to latch `bus.overflow` into a flip-flop at the end of that cycle, since the
next cycle's ALU inputs already belong to the next instruction. That's the
dedicated `alu_status` module (`alu_status.md`), not the ALU itself (which
stays purely combinational, `CLAUDE.md`'s "Decided") and not a general
control unit (an earlier design pass considered putting the latch there,
before settling on a small self-contained module instead — see
`alu_status.md`'s Design rationale).
