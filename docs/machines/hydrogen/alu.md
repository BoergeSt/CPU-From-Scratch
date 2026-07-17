# Hydrogen ALU — v1 Specification

Machine generation: **hydrogen** (H, atomic number 1 — first machine
generation, per the codename convention in `CLAUDE.md`).

Status: **implemented** — `fpga/rtl/machines/hydrogen/alu.sv`, verified by
`fpga/rtl/machines/hydrogen/tb/test_alu.py` (`just check :hydrogen:alu`).
Line/branch/toggle coverage: `just coverage :hydrogen:alu`. Line coverage is
expected to be short of 100% here: the reserved-opcode `default:` case (see
CLAUDE.md's illegal-instruction-exception item under Future directions) has
no directed test hitting it yet, since none exists to exercise the
opcode-0xC–0xF path.

## Overview

The ALU is a stateless, purely combinational module: `bus.result` and
`bus.overflow` are pure functions of `bus.operation`, `bus.value1`, and
`bus.value2`, valid within the same cycle. This matches Hydrogen's
single-cycle core model, where the register file and PC (outside this
module) are what actually get clocked, capturing the ALU's output at the
end of each cycle. Since there's no internal state, the module has no
clock or reset port either.

All operands and results are **unsigned**. There is no signed-arithmetic
support in this version (see Deferred ideas).

## Interface

The ALU has a single port, `bus`, of interface type `alu_if` (defined in
`alu_if.sv`), connected via the `alu` modport.

| `alu_if` field | Dir (from `alu` modport) | Width | Description |
|----------------|---------------------------|-------|--------------|
| `operation`    | in  | 4  | Opcode select (see Operations table)   |
| `value1`       | in  | 32 | Operand 1, unsigned                    |
| `value2`       | in  | 32 | Operand 2, unsigned (ignored by `NOT`) |
| `result`       | out | 32 | Result, unsigned                       |
| `overflow`     | out | 1  | See Flags below                        |

The `requester` modport mirrors every direction (the side driving the ALU
sees `operation`/`value1`/`value2` as outputs and `result`/`overflow` as
inputs) — see `alu_if.sv`.

No clock/reset ports — see Overview.

## Operations

12 operations in this version, encoded in 4 bits with 4 codes reserved for
future growth (see Deferred ideas). Encoding below is a suggested grouping
(arithmetic, then shifts, then bitwise) — free to renumber when writing the
actual SV `localparam`s; the grouping/numbering itself carries no functional
meaning.

| Code   | Mnemonic | Result                                   | `bus.value2` used? |
|--------|----------|-------------------------------------------|-------------------|
| `0x0`  | `ADD`    | `bus.value1 + bus.value2` (mod 2³²)            | yes |
| `0x1`  | `SUB`    | `bus.value1 - bus.value2` (mod 2³²)            | yes |
| `0x2`  | `MUL`    | low 32 bits of `bus.value1 * bus.value2`       | yes |
| `0x3`  | `MULH`   | high 32 bits of `bus.value1 * bus.value2`      | yes |
| `0x4`  | `LSHIFT` | `bus.value1 << bus.value2`                     | yes (shift amount) |
| `0x5`  | `RSHIFT` | `bus.value1 >> bus.value2`                     | yes (shift amount) |
| `0x6`  | `AND`    | `bus.value1 & bus.value2`                      | yes |
| `0x7`  | `OR`     | `bus.value1 \| bus.value2`                     | yes |
| `0x8`  | `XOR`    | `bus.value1 ^ bus.value2`                      | yes |
| `0x9`  | `NOT`    | `~bus.value1`                                | **no** — unary |
| `0xA`  | `NAND`   | `~(bus.value1 & bus.value2)`                   | yes |
| `0xB`  | `NOR`    | `~(bus.value1 \| bus.value2)`                  | yes |
| `0xC`–`0xF` | reserved | — | — |

Shift amounts: `bus.value2` is used directly as the shift amount, with no
masking. A shift amount ≥ 32 is well-defined (see Flags): `LSHIFT` produces
0, `RSHIFT` produces 0.

## Flags

A single `bus.overflow` bit, meaning consistently across every op that sets
it: **the value in `bus.result` does not equal the true mathematical result,
because information needed to reconstruct it was discarded or wrapped.**

Per operation:

- **`ADD`** — overflow when the true sum needs a 33rd bit (unsigned
  carry-out): `bus.overflow = (bus.value1 + bus.value2) > 32'hFFFF_FFFF` (i.e. the
  33rd bit of the widened sum).
- **`SUB`** — overflow when `bus.value2 > bus.value1` (result would go negative,
  wraps mod 2³²).
- **`MUL`** — overflow when the discarded high word is nonzero, i.e. the
  true 64-bit product doesn't fit in 32 bits.
- **`MULH`** — never overflows. Nothing is discarded — `MULH` *is* the part
  that `MUL` would otherwise drop.
- **`LSHIFT`** — overflow when any bit shifted out past bit 31 is `1`.
  General rule, covering both a large shift amount and a smaller shift on an
  already-high operand: for shift amount `n < 32`, overflow iff the top `n`
  bits of `bus.value1` (i.e. `bus.value1[31 -: n]`) are nonzero; for `n >= 32`,
  overflow iff `bus.value1 != 0`.
- **`RSHIFT`** — never overflows. An unsigned right shift is a truncating
  division by a power of two; losing low-order bits is the expected,
  non-error behavior of that operation, not data loss in the same sense as
  the other ops.
- **`AND`/`OR`/`XOR`/`NOT`/`NAND`/`NOR`** — flag-free. No overflow concept
  applies to bitwise operations; `bus.overflow` is `0` for all of these.

## Design rationale

- **`bus` interface (`alu_if`) instead of five flat ports**: bundles the
  operand/opcode/result/flag signals into one interface with mirrored
  `alu`/`requester` modports, so whatever drives the ALU connects through
  the same interface instance instead of every signal being wired by hand
  at each instantiation — the general interfaces-over-flat-ports
  convention from `CLAUDE.md`. Which module actually plays the
  `requester` side (the register file directly, or a control-unit-owned
  operand mux that also handles the immediate-flag ALU operand from
  `docs/machines/hydrogen/isa.md`) is still an open module-boundary
  question — see that document.
- **Combinational, no clock/reset**: required by the single-cycle core
  model (Phase 1 target) — a registered/pipelined ALU would add a cycle of
  latency between operands and result, which belongs to a later, deliberate
  revision (see Deferred ideas and `CLAUDE.md`'s "ALU: purely combinational
  for Phase 1" decision).
- **Unsigned-only**: chosen to keep the first iteration simple. Every
  overflow/shift/comparison rule above is simpler because there's no
  separate signed-overflow case to also define.
- **`MUL`/`MULH` split instead of a 64-bit `bus.result` or dual output
  ports**: keeps `bus.result` a uniform 32 bits across every operation, so
  nothing downstream (register file, future ISA encoding) needs to special
  case one op's port width. Mirrors real ISA conventions (e.g. RISC-V's
  `mul`/`mulh` pair) for the same reason.
- **Single `bus.overflow` bit, not a flags struct**: carry-out, a zero flag,
  and an addressable/movable flags register were all considered and are
  genuinely useful ideas, but add complexity (multi-word carry chaining
  needs a `carry_i` input and an `addc` op that don't exist yet; an
  addressable flags register raises save/restore-across-interrupts
  questions that are premature before the interrupts phase even starts).
  Deferred rather than dropped — see below.
- **No hardware `divide`/`mod`**: division and remainder share one
  underlying combinational circuit (a divider naturally produces both
  quotient and remainder), exactly as `MUL`/`MULH` share one multiplier —
  so they belong together in the same future revision, not built
  separately or in isolation now.

## Deferred / future ideas (explicitly out of scope for v1)

Not forgotten — intentionally parked for a later revision:

- **`DIV`/`MOD`** — as a pair, sharing one division circuit (quotient +
  remainder outputs), the same relationship as `MUL`/`MULH`. Needs its own
  decisions later: divide-by-zero behavior, whether both outputs are always
  computed or selected by opcode.
- **Separate `carry_o`** (distinct from `bus.overflow`) — to support future
  multi-word/64-bit addition via chained `add`+`addc`. Needs a `carry_i`
  input and an `addc` opcode, neither of which exist yet.
- **`zero_o` flag** — result-is-zero, useful for future compare/branch
  instructions.
- **Flags bundled as a `flags_o` struct** — worth revisiting once there is
  more than one flag bit; premature with only `bus.overflow`.
- **Addressable/movable flags register** (à la x86 EFLAGS / ARM CPSR) —
  vs. the v1 approach of a flag consumed only by a dedicated conditional
  branch instruction (e.g. `jump_on_overflow`). Deferred because it
  entangles with how flags get saved/restored across interrupts, which is
  itself a future roadmap item, not yet designed.
- **Signed arithmetic** — two's-complement add/sub/shift/compare semantics,
  dropped for v1 to keep the first iteration simple.
- **Registered/pipelined ALU** — see `CLAUDE.md`'s "ALU: purely
  combinational for Phase 1" decision; a future revision, not an oversight.

## Control-unit note (not part of this module)

Because the ALU is combinational and the core is single-cycle,
`bus.overflow` is only valid during the same cycle as the instruction that
produced it. A future conditional-branch instruction consuming it (e.g.
`jump_on_overflow`) will need the control unit to latch `bus.overflow` into a
small implicit flip-flop at the end of that cycle, since the next cycle's
ALU inputs already belong to the next instruction. This is a control-unit
design detail, not something the ALU itself needs to handle.
