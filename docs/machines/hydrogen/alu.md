# Hydrogen ALU — v1 Specification

Machine generation: **hydrogen** (H, atomic number 1 — first machine
generation, per the codename convention in `CLAUDE.md`).

Status: **design spec, not yet implemented.**

## Overview

The ALU is a stateless, purely combinational module: `result_o` and
`overflow_o` are pure functions of `operation_i`, `value1_i`, and
`value2_i`, valid within the same cycle. This matches Hydrogen's
single-cycle core model, where the register file and PC (outside this
module) are what actually get clocked, capturing the ALU's output at the
end of each cycle. Since there's no internal state, the module has no
clock or reset port either.

All operands and results are **unsigned**. There is no signed-arithmetic
support in this version (see Deferred ideas).

## Interface

| Port           | Dir | Width | Description                                   |
|----------------|-----|-------|------------------------------------------------|
| `operation_i`  | in  | 4     | Opcode select (see Operations table)            |
| `value1_i`     | in  | 32    | Operand 1, unsigned                             |
| `value2_i`     | in  | 32    | Operand 2, unsigned (ignored by `NOT`)          |
| `result_o`     | out | 32    | Result, unsigned                                |
| `overflow_o`   | out | 1     | See Flags below                                 |

No clock/reset ports — see Overview.

## Operations

12 operations in this version, encoded in 4 bits with 4 codes reserved for
future growth (see Deferred ideas). Encoding below is a suggested grouping
(arithmetic, then shifts, then bitwise) — free to renumber when writing the
actual SV `localparam`s; the grouping/numbering itself carries no functional
meaning.

| Code   | Mnemonic | Result                                   | `value2_i` used? |
|--------|----------|-------------------------------------------|-------------------|
| `0x0`  | `ADD`    | `value1_i + value2_i` (mod 2³²)            | yes |
| `0x1`  | `SUB`    | `value1_i - value2_i` (mod 2³²)            | yes |
| `0x2`  | `MUL`    | low 32 bits of `value1_i * value2_i`       | yes |
| `0x3`  | `MULH`   | high 32 bits of `value1_i * value2_i`      | yes |
| `0x4`  | `LSHIFT` | `value1_i << value2_i`                     | yes (shift amount) |
| `0x5`  | `RSHIFT` | `value1_i >> value2_i`                     | yes (shift amount) |
| `0x6`  | `AND`    | `value1_i & value2_i`                      | yes |
| `0x7`  | `OR`     | `value1_i \| value2_i`                     | yes |
| `0x8`  | `XOR`    | `value1_i ^ value2_i`                      | yes |
| `0x9`  | `NOT`    | `~value1_i`                                | **no** — unary |
| `0xA`  | `NAND`   | `~(value1_i & value2_i)`                   | yes |
| `0xB`  | `NOR`    | `~(value1_i \| value2_i)`                  | yes |
| `0xC`–`0xF` | reserved | — | — |

Shift amounts: `value2_i` is used directly as the shift amount, with no
masking. A shift amount ≥ 32 is well-defined (see Flags): `LSHIFT` produces
0, `RSHIFT` produces 0.

## Flags

A single `overflow_o` bit, meaning consistently across every op that sets
it: **the value in `result_o` does not equal the true mathematical result,
because information needed to reconstruct it was discarded or wrapped.**

Per operation:

- **`ADD`** — overflow when the true sum needs a 33rd bit (unsigned
  carry-out): `overflow_o = (value1_i + value2_i) > 32'hFFFF_FFFF` (i.e. the
  33rd bit of the widened sum).
- **`SUB`** — overflow when `value2_i > value1_i` (result would go negative,
  wraps mod 2³²).
- **`MUL`** — overflow when the discarded high word is nonzero, i.e. the
  true 64-bit product doesn't fit in 32 bits.
- **`MULH`** — never overflows. Nothing is discarded — `MULH` *is* the part
  that `MUL` would otherwise drop.
- **`LSHIFT`** — overflow when any bit shifted out past bit 31 is `1`.
  General rule, covering both a large shift amount and a smaller shift on an
  already-high operand: for shift amount `n < 32`, overflow iff the top `n`
  bits of `value1_i` (i.e. `value1_i[31 -: n]`) are nonzero; for `n >= 32`,
  overflow iff `value1_i != 0`.
- **`RSHIFT`** — never overflows. An unsigned right shift is a truncating
  division by a power of two; losing low-order bits is the expected,
  non-error behavior of that operation, not data loss in the same sense as
  the other ops.
- **`AND`/`OR`/`XOR`/`NOT`/`NAND`/`NOR`** — flag-free. No overflow concept
  applies to bitwise operations; `overflow_o` is `0` for all of these.

## Design rationale

- **Combinational, no clock/reset**: required by the single-cycle core
  model (Phase 1 target) — a registered/pipelined ALU would add a cycle of
  latency between operands and result, which belongs to a later, deliberate
  revision (see Deferred ideas and `CLAUDE.md`'s "ALU: purely combinational
  for Phase 1" decision).
- **Unsigned-only**: chosen to keep the first iteration simple. Every
  overflow/shift/comparison rule above is simpler because there's no
  separate signed-overflow case to also define.
- **`MUL`/`MULH` split instead of a 64-bit `result_o` or dual output
  ports**: keeps `result_o` a uniform 32 bits across every operation, so
  nothing downstream (register file, future ISA encoding) needs to special
  case one op's port width. Mirrors real ISA conventions (e.g. RISC-V's
  `mul`/`mulh` pair) for the same reason.
- **Single `overflow_o` bit, not a flags struct**: carry-out, a zero flag,
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
- **Separate `carry_o`** (distinct from `overflow_o`) — to support future
  multi-word/64-bit addition via chained `add`+`addc`. Needs a `carry_i`
  input and an `addc` opcode, neither of which exist yet.
- **`zero_o` flag** — result-is-zero, useful for future compare/branch
  instructions.
- **Flags bundled as a `flags_o` struct** — worth revisiting once there is
  more than one flag bit; premature with only `overflow_o`.
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
`overflow_o` is only valid during the same cycle as the instruction that
produced it. A future conditional-branch instruction consuming it (e.g.
`jump_on_overflow`) will need the control unit to latch `overflow_o` into a
small implicit flip-flop at the end of that cycle, since the next cycle's
ALU inputs already belong to the next instruction. This is a control-unit
design detail, not something the ALU itself needs to handle.
