# Hydrogen ISA — v1 Specification (Register File + Instruction Encoding)

Machine generation: **hydrogen** (H, atomic number 1 — first machine
generation, per the codename convention in `CLAUDE.md`).

Status: **implemented.** The register file (`regfile.sv`, see `regfile.md`),
the ALU (`alu.sv`, see `alu.md`), and the flow-control unit (`flow_ctl.sv`,
see `flow_ctl.md`) all consume the encoding specified here. This document is
the single source of truth for what a Hydrogen instruction word means —
per-module RTL behavior, interface, and timing live in each module's own
doc, cross-referencing this one instead of re-describing the encoding.

## Overview

Hydrogen is a single-cycle core (see `CLAUDE.md`'s Phase 1 target). This
document covers the two pieces that sit around the datapath: the register
file's architectural contract, and the 32-bit instruction encoding that
drives it, including its SystemVerilog implementation (`isa_pkg.sv`, see
below). Memory is **word-addressed** (see Design rationale) and
**memory-mapped** (peripherals and RAM share one address space, per
`CLAUDE.md`'s I/O addressing decision) — this document doesn't cover the bus
or memory map itself, only how instructions reference addresses.

Deliberately out of scope for this iteration, per explicit request: no
hardware stack, no call/return support, no context-window/register-banking
mechanism. Jumps and conditional branches are specified under `FLOW_CTL`
below (full module boundary and rationale in `flow_ctl.md`); stop/reset are
explicitly **not** part of `FLOW_CTL` — deferred to a separate, not-yet-
assigned future major opcode dispatching to a not-yet-designed reset
controller module.

## Register file

- **8 general-purpose registers**, 32 bits each, `R0`–`R7`. All eight are
  architecturally uniform — none is hardwired to a constant or otherwise
  special-cased (see Design rationale).
- **1 program counter**, 32 bits, holds a **word address** (see Instruction
  encoding below) of the next instruction to fetch.
- Architecturally, the busiest single instruction (`ALU`) needs 2 register
  reads (`src1`, `src2`) and 1 register write (`dest`) in the same cycle;
  every other instruction needs at most 1 read or 1 write. This is a
  constraint on the register file's required port count, not a prescription
  of its RTL implementation.

## Reset and error vectors

| Vector | Value | Word address | Trigger |
|--------|-------|---------------|---------|
| `ResetVector` | `0x10` | 16 | PC on reset — first instruction fetched |
| `ErrorVector` | `0x0`  | 0  | PC on an illegal-instruction/trap condition |

Both are word addresses, same as the PC itself. Word addresses `0x0`–`0xF`
are reserved for a small exception handler; real program code starts at
`0x10`. See `flow_ctl.md` for the conditions that trigger `ErrorVector` and
their priority against normal execution. Defined in `isa_pkg.sv` as
`ResetVector`/`ErrorVector` — not part of the instruction encoding itself,
since no field in any opcode encodes them.

## Instruction encoding

Every instruction is a single 32-bit word: a 4-bit major opcode in
`[31:28]`, followed by a 28-bit parameter field whose layout depends on the
opcode.

### Major opcodes

| Code | Mnemonic | Meaning |
|------|----------|---------|
| `0x0` | `ALU` | ALU operation, register/immediate operands |
| `0x1` | `IMM_SET` | Load a 25-bit immediate into a register |
| `0x2` | `FLOW_CTL` | Jumps and conditional branches — PC control, see below |
| `0x3` | `LOAD_IMM` | Load from an immediate (fixed) address |
| `0x4` | `STORE_IMM` | Store to an immediate (fixed) address |
| `0x5` | `LOAD` | Load from a register-indirect + offset address |
| `0x6` | `STORE` | Store to a register-indirect + offset address |
| `0x7`–`0xF` | reserved | Free for future growth |

Candidates for the reserved range include `FLOW_CTL` variants and sub-word
load/store, neither designed yet. These values match `isa_pkg.sv`'s
`instr_class_e` exactly (`IC_ALU`, `IC_IMM_SET`, ...) — that enum is the
pinned, canonical implementation of this table, not an independent
numbering (see SV implementation).

### `ALU` — `0x0`

| Bits | Field | Width | Description |
|------|-------|-------|-------------|
| `[27:25]` | `dest` | 3 | Destination register index, R0–R7 |
| `[24:21]` | `alu_op` | 4 | Selects the operation, see Operations below |
| `[20]` | `is_imm_src1` | 1 | 1 = src1 is the immediate below, 0 = register |
| `[19]` | `is_imm_src2` | 1 | 1 = src2 is the immediate below, 0 = register |
| `[18:6]` | `imm` | 13 | Unsigned immediate payload, see Operand sourcing |
| `[5:3]` | `src2_addr` | 3 | Register index R0–R7, ignored by unary `NOT` |
| `[2:0]` | `src1_addr` | 3 | Register index R0–R7 |

`src1_addr`/`src2_addr` sit at fixed positions `[2:0]`/`[5:3]` shared with
every other opcode that reads two registers (`FLOW_CTL`'s `val1`/`val2`, see
below) — see `CLAUDE.md`'s fixed-register-position decision and Design
rationale. The addressed register is always read, whether or not the
corresponding `is_imm` flag ends up overriding it with `imm` instead.

`is_imm_src1`/`is_imm_src2` both being `1` simultaneously is **illegal**
(unlike an earlier version of this encoding where it was legal-but-pointless)
— `alu.sv` flags it via `bus.error`, see Errors below. At most one operand
may be sourced from `imm` per instruction.

`dest` is always a plain 3-bit register index — a destination can't
meaningfully be "an immediate," so unlike `src1`/`src2` it carries no flag
bit (see Design rationale).

#### Operand sourcing

Each operand's flag bit picks between the addressed register's value and
the shared `imm` field: if `is_imm_src1` is set, the effective `value1` is
`imm`, zero-extended to 32 bits, instead of the addressed register's
contents; otherwise it's the register's contents unchanged. `value2`/
`is_imm_src2` follow the same rule independently. Every operand reference
in the Operations table below means this effective (post-substitution)
value, not necessarily the raw register read.

#### Operations

12 operations in this version, selected by the 4-bit `alu_op` field, with 4
codes reserved for future growth (see Deferred ideas). These values match
`isa_pkg.sv`'s `alu_op_e` exactly (`ALU_OP_ADD`, `ALU_OP_SUB`, ...).

| Code   | Mnemonic | Result                                   | `value2` used? |
|--------|----------|-------------------------------------------|-------------------|
| `0x0`  | `ADD`    | `value1 + value2` (mod 2³²)            | yes |
| `0x1`  | `SUB`    | `value1 - value2` (mod 2³²)            | yes |
| `0x2`  | `MUL`    | low 32 bits of `value1 * value2`       | yes |
| `0x3`  | `MULH`   | high 32 bits of `value1 * value2`      | yes |
| `0x4`  | `LSHIFT` | `value1 << value2`                     | yes (shift amount) |
| `0x5`  | `RSHIFT` | `value1 >> value2`                     | yes (shift amount) |
| `0x6`  | `AND`    | `value1 & value2`                      | yes |
| `0x7`  | `OR`     | `value1 \| value2`                     | yes |
| `0x8`  | `XOR`    | `value1 ^ value2`                      | yes |
| `0x9`  | `NOT`    | `~value1`                                | **no** — unary |
| `0xA`  | `NAND`   | `~(value1 & value2)`                   | yes |
| `0xB`  | `NOR`    | `~(value1 \| value2)`                  | yes |
| `0xC`–`0xF` | reserved | `result = 0`, illegal encoding (see Errors) | — |

Shift amounts: `value2` is used directly as the shift amount, with no
masking. A shift amount ≥ 32 is well-defined (see Flags): `LSHIFT` produces
0, `RSHIFT` produces 0.

`MUL`/`MULH` are a deliberate split, not a 64-bit result or dual output
ports: it keeps the ALU's result a uniform 32 bits across every operation,
so nothing downstream (register file, this encoding) needs to special-case
one op's result width. Mirrors real ISA conventions (e.g. RISC-V's
`mul`/`mulh` pair) for the same reason.

There is no hardware `DIV`/`MOD` in this version — see Deferred ideas.

All operands and results are **unsigned**. There is no signed-arithmetic
support in this version (see Deferred ideas). Signed would cost nothing in
bit width but adds interpretation complexity; `SUB` already covers
subtraction, so the range asymmetry doesn't cost real capability.

#### Flags

A single `overflow` bit, meaning consistently across every op that sets it:
**the result does not equal the true mathematical result, because
information needed to reconstruct it was discarded or wrapped.**

Per operation:

- **`ADD`** — overflow when the true sum needs a 33rd bit (unsigned
  carry-out): `value1 + value2` exceeds 2³²−1.
- **`SUB`** — overflow when `value2 > value1` (result would go negative,
  wraps mod 2³²).
- **`MUL`** — overflow when the discarded high word is nonzero, i.e. the
  true 64-bit product doesn't fit in 32 bits.
- **`MULH`** — never overflows. Nothing is discarded — `MULH` *is* the part
  that `MUL` would otherwise drop.
- **`LSHIFT`** — overflow when any bit shifted out past bit 31 is `1`.
  General rule, covering both a large shift amount and a smaller shift on an
  already-high operand: for shift amount `n < 32`, overflow iff the top `n`
  bits of `value1` are nonzero; for `n >= 32`, overflow iff `value1` is
  nonzero at all.
- **`RSHIFT`** — never overflows. An unsigned right shift is a truncating
  division by a power of two; losing low-order bits is the expected,
  non-error behavior of that operation, not data loss in the same sense as
  the other ops.
- **`AND`/`OR`/`XOR`/`NOT`/`NAND`/`NOR`** — flag-free. No overflow concept
  applies to bitwise operations; `overflow` is `0` for all of these.

A single flag bit, not a flags struct: carry-out, a zero flag, and an
addressable/movable flags register were all considered — see Deferred
ideas.

`overflow`'s only consumer is `FLOW_CTL`'s `overflow`/`not_overflow`
conditions (see below), via a flag latched in the dedicated `alu_status`
module (`alu_status.md`) — the ALU itself is combinational and stateless
(`alu.md`), so `overflow` is only valid the same cycle it's produced.

#### Errors

An `ALU` instruction is an illegal encoding, flagged via `alu.sv`'s
`bus.error`, in exactly two cases:

1. `alu_op` is one of the reserved codes `0xC`–`0xF`.
2. `is_imm_src1` and `is_imm_src2` are both `1` — ambiguous, since there's
   one shared `imm` field for either operand (see Operand sourcing).

Every other combination is legal. This is Hydrogen's first concrete
illegal-instruction signal — the trigger `CLAUDE.md`'s exception/trap-
handling future direction names explicitly. `bus.error` is that diagnostic;
it is not itself the exception/trap mechanism — a future control unit is
expected to fold it, alongside other illegal-instruction sources (reserved
major opcodes, reserved `FLOW_CTL` `op` values), into the single `error_i`
line consumed by the flow-control unit's exception path (`flow_ctl.md`).

### `IMM_SET` — `0x1`

| Bits | Field | Width | Description |
|------|-------|-------|-------------|
| `[27:25]` | `dest` | 3 | Destination register index |
| `[24:0]` | `imm` | 25 | Zero-extended into the register; bits `[31:25]` cleared to 0 |

### `LOAD_IMM` — `0x3`, `STORE_IMM` — `0x4`

| Bits | Field | Width | Description |
|------|-------|-------|-------------|
| `[27:25]` | `dest`/`src` | 3 | Register index (`dest` for `LOAD_IMM`, `src` for `STORE_IMM`) |
| `[24:0]` | `addr` | 25 | Word address |

`addr` is a fixed word address baked directly into the instruction — no
register is involved in address computation. Reaches 2²⁵ words (128 MB)
directly.

### `LOAD` — `0x5`, `STORE` — `0x6`

| Bits | Field | Width | Description |
|------|-------|-------|-------------|
| `[27:25]` | `dest`/`src` | 3 | Register index (`dest` for `LOAD`, `src` for `STORE`) |
| `[24:22]` | `base` | 3 | Base register index |
| `[21:0]` | `offset` | 22 | Two's-complement offset from `base`'s value |

Effective address = `base` register's value + `offset`, both interpreted as
word addresses/offsets. `offset` is **two's complement**, reaching ±2²¹
words (±32 MB) from `base`.

### `FLOW_CTL` — `0x2`

| Bits | Field | Mode | Width | Description |
|------|-------|------|-------|-------------|
| `[27]` | `r` | — | 1 | Relative (`pc+target`, signed) or absolute (unsigned) |
| `[26]` | `i` | — | 1 | Immediate or register-indirect target |
| `[25:22]` | `op` | — | 4 | Condition, see Operations below |
| `[21:9]` | `reserved` | `i=0` | 13 | Must be 0 |
| `[8:6]` | `jump_to_addr` | `i=0` | 3 | Register index R0–R7 holding the jump target |
| `[21:6]` | `imm` | `i=1` | 16 | Two's-complement target/offset (`flow_ctl.md`) |
| `[5:3]` | `val2_addr` | — | 3 | Comparison operand B, register index R0–R7 |
| `[2:0]` | `val1_addr` | — | 3 | Comparison operand A, register index R0–R7 |

`r`/`i` are each `1` for relative/immediate, `0` for absolute/
register-indirect. `val1_addr`/`val2_addr` are always read regardless of
`op`; `val2_addr` is ignored by several `op` values (see Operations below).

`val1_addr`/`val2_addr`/`jump_to_addr` sit at the fixed `[2:0]`/`[5:3]`/
`[8:6]` positions shared with the `ALU`'s `src1_addr`/`src2_addr` above —
see `CLAUDE.md`'s fixed-register-position decision, now three universal
slots rather than two. `jump_to_addr` claims the 3rd slot even though no
other opcode currently uses it, specifically so a future opcode needing a
3rd register read can reuse the same fixed position and permanent wiring,
rather than `read3` needing per-opcode arbitration the way `read1`/`read2`
did before they were fixed. Unlike the `ALU`'s `src1`/`src2`, `val1`/`val2`
have no immediate-flag option (see Design rationale) — they're always
register reads.

#### Operations

`op` selects one of 12 defined values (4 bits, 4 reserved for future
growth). These values match `isa_pkg.sv`'s `flow_op_e` exactly
(`FLOW_CTL_OP_NOP`, `FLOW_CTL_OP_LESS`, ...).

| Code | Mnemonic | Condition | Uses `val2`? |
|------|----------|-----------|-----------------|
| `0x0` | `nop`/never | never taken | no |
| `0x1` | `l` | `val1 < val2` | yes |
| `0x2` | `le` | `val1 <= val2` | yes |
| `0x3` | `g` | `val1 > val2` | yes |
| `0x4` | `ge` | `val1 >= val2` | yes |
| `0x5` | `z` | `val1 == 0` | no |
| `0x6` | `nz` | `val1 != 0` | no |
| `0x7` | `eq` | `val1 == val2` | yes |
| `0x8` | `neq` | `val1 != val2` | yes |
| `0x9` | `always` | always taken | no |
| `0xA` | `overflow` | ALU `overflow == 1` | no |
| `0xB` | `not_overflow` | ALU `overflow == 0` | no |
| `0xC`–`0xF` | reserved | — | — |

`overflow`/`not_overflow` check the ALU's overflow flag as latched by
`alu_status` (see Flags above).

`l`/`le`/`g`/`ge` are **unsigned** comparisons, consistent with the ALU's
v1-wide unsigned-only scope. The only signed interpretation anywhere in
`FLOW_CTL` is `r`'s relative-target case (`pc + target`, two's-complement)
— comparisons themselves never are.

`always` has its own encoded value rather than being expressed as `eq` with
`val1_addr == val2_addr` (functionally equivalent, since a register always
equals itself) — see Design rationale.

`op`'s full priority order against `r`/`i`/`error_i`/`rst_i`, and the RTL
module boundary that implements it, are specified in `flow_ctl.md`.

## SV implementation (`isa_pkg.sv`)

The encoding above is implemented as a SystemVerilog package,
`fpga/rtl/machines/hydrogen/isa_pkg.sv`, imported by every module that
decodes an instruction word (`alu.sv`, `alu_status.sv`, `flow_ctl.sv`,
`regfile.sv`'s read/write interfaces). Every RTL module receives the entire
32-bit instruction (`CLAUDE.md`'s functional-units-get-the-whole-
instruction decision) as this package's `instr_t` type, rather than a flat
`logic [31:0]`.

### Types

| Type | Kind | Covers |
|------|------|--------|
| `instr_class_e` | enum | Major opcode (`IC_ALU`, `IC_IMM_SET`, ...) |
| `reg_addr_e` | enum | Register index, `R0`–`R7` (`REG_R0`–`REG_R7`) |
| `alu_op_e` | enum | `ALU`'s `alu_op` field (`ALU_OP_ADD`, ...) |
| `flow_op_e` | enum | `FLOW_CTL`'s `op` field (`FLOW_CTL_OP_NOP`, ...) |
| `generic_instr_t` | struct | Fields fixed at the same position across every opcode |
| `alu_instr_t` | struct | `ALU`'s full field layout |
| `flow_ctl_target_reg_t` | struct | `FLOW_CTL`'s `i=0` trailer |
| `flow_ctl_target_imm_t` | struct | `FLOW_CTL`'s `i=1` trailer |
| `flow_ctl_target_t` | union | `is_reg`/`is_imm` — the `i=0`/`i=1` |
| | | trailer views over the same 16 bits |
| `flow_ctl_instr_t` | struct | `FLOW_CTL`'s full field layout |
| `instr_t` | union | `raw` plus one member per struct above |

`generic_instr_t` covers `ic` (`[31:28]`), `dest` (`[27:25]`), and
`src3_addr`/`src2_addr`/`src1_addr` (`[8:6]`/`[5:3]`/`[2:0]`) — everything
a future control unit needs to hardwire regardless of which opcode is
active. `flow_ctl_target_reg_t` covers `reserved` (`[21:9]`) and
`jump_to_addr` (`[8:6]`); `flow_ctl_target_imm_t` covers `imm` (`[21:6]`).
`instr_t`'s members are `raw` (`logic [31:0]`), `generic`, `alu`, and
`flow_ctl` — it's the type every module's instruction port carries.

`flow_ctl_target_t`'s two members (`is_reg`, `is_imm`) are both single-field
structs, rather than `is_imm` being a bare `logic [15:0]`: this keeps both
access paths the same shape (`target.is_reg.jump_to_addr`,
`target.is_imm.imm`), so neither branch reads as the "default" or "special
case" relative to the other.

`generic_instr_t` and the opcode-specific structs (`alu_instr_t`,
`flow_ctl_instr_t`) are different *views* of the same 32 bits via `instr_t`,
not different data — reading `instruction.generic.ic` and
`instruction.alu.ic` on the same instruction word returns the same value,
since both are the same `[31:28]` bits under a different field name.

### Naming convention

Follows the lowRISC Verilog Coding Style Guide, same as the rest of this
project (`CLAUDE.md`): enum type names `snake_case` with an `_e` suffix;
struct/union type names `snake_case` with a `_t` suffix; enum values
`ALL_CAPS`, since these are "defined opcode assignments" — the guide's own
example of when `ALL_CAPS` applies, as opposed to incidental values like
state-machine encodings.

Enum values are prefixed (`IC_`, `REG_`, `ALU_OP_`, `FLOW_CTL_OP_`) rather
than bare (`ALU`, `R0`, `ADD`, ...). SystemVerilog enum literals are not
scoped to their enum type — unlike e.g. Rust or C++'s `enum class`, `ADD`
would become a plain identifier directly in `isa_pkg`'s namespace, not
`alu_op_e::ADD`, creating both a same-package collision risk (a future
`flow_op_e` member named `OVERFLOW` sitting in the same flat namespace as an
`alu_op_e` member) and a risk of colliding with an importing module's own
signal names (e.g. `overflow_i`). The prefix is the manual substitute for
the automatic scoping the language doesn't provide.

### Reserved encodings

Reserved major-opcode values (`0x7`–`0xF`) and reserved sub-op values
(`ALU`'s `0xC`–`0xF`, `FLOW_CTL`'s `0xC`–`0xF`) are not given names in their
respective enums — only the currently-defined values are. A reserved bit
pattern still casts into the enum type without error (SV permits any bit
pattern in an enum-typed packed field; it matches no named literal),
so each consuming module catches it the same way: a `default:` branch on a
`unique0 case` over the relevant field. This mirrors the pattern already
used for the reserved sub-op values themselves (see Errors above and
`flow_ctl.md`'s Behavior) — no separate mechanism is needed for the
enum-level "unnamed value" case versus the RTL-level "reserved code" case,
since they're the same event.

`unique0`, not `unique`: a plain `unique case` combined with a `default`
branch is redundant in a way some tools (including `slang`) flag — `unique`
already asserts every case is covered, which is inconsistent with also
providing a catch-all for the cases it claims aren't possible. `unique0`
asserts mutual exclusivity of the listed items without also asserting
exhaustiveness, which is the actually-true property here.

### Design rationale

- **A shared package, not per-module bit-slicing.** Every module used to
  decode instruction fields with its own hardcoded bit ranges
  (`bus.opcode[24:21]`, etc.). A layout change meant finding and updating
  every occurrence by hand across every module that happened to read that
  field. Centralizing the field/value definitions in one package means a
  layout change touches this file and this file alone; every consuming
  module's own decode logic is expressed in terms of named fields and
  values that don't change when the underlying bit positions do.
- **Types the instruction port itself, not just named constants for
  bit-slicing.** An earlier pass only pulled major-opcode/sub-op *values*
  into named constants, leaving field *positions* as bare bit-range slices
  at every use site. Typing the whole instruction word as `instr_t` and
  giving every opcode format its own packed struct removes the bit ranges
  entirely — field access becomes `instruction.alu.alu_op` instead of
  `instruction[24:21]`, so a field's width or position changing is
  invisible to every consumer, not just its value.
- **`generic_instr_t` alongside the opcode-specific structs.** The fields
  it exposes (`ic`, `dest`, `src1_addr`/`src2_addr`/`src3_addr`) are fixed
  at the same position across every opcode by `CLAUDE.md`'s
  fixed-register-position decision — a consumer that only cares about those
  (e.g. a future control unit routing register addresses to the register
  file) can use this view without needing to know or care which specific
  opcode is active.
- **Enums, not plain `logic` vectors, for values that are never
  arithmetic'd.** `instr_class_e`/`reg_addr_e`/`alu_op_e`/`flow_op_e` are
  all closed sets of values that are only ever compared or propagated, never
  added/subtracted/shifted — SV enums give real type-checking (an
  un-cast plain integer can't be assigned into an enum-typed signal) for
  exactly that usage, at the cost of needing an explicit cast anywhere a
  value genuinely does need arithmetic. `pc`/memory addresses and the `imm`
  payload fields stay plain `logic` vectors for the opposite reason — they
  participate in ordinary arithmetic constantly, and SV has no operator
  overloading, so a strong type there would force a cast at every add
  instead of at the rare point of illegitimate use.
- **`flow_ctl_target_t` as a nested union, not two independent top-level
  `instr_t` members.** An earlier version had `flow_ctl_instr_t` and a
  separate `flow_ctl_imm_instr_t`, each independently declaring the fields
  common to both (`ic`, `is_relative`, `is_imm`, `op`, `src1_addr`,
  `src2_addr`) and differing only in the trailing 16 bits. That duplication
  meant a common field change had to be made in both places, with nothing
  enforcing that both stay in sync. Factoring only the differing 16 bits
  into a nested union (`flow_ctl_target_t`) inside one `flow_ctl_instr_t`
  removes the duplication at the cost of one more `.` in the access path
  for the trailer fields specifically (`target.is_imm.imm` vs. what would
  have been a top-level `flow_ctl_imm.imm`).
- **Module-header `import`, not file-scope, when a port needs a package
  type.** The lowRISC guide disallows `import pkg::*;` at file/`$root`
  scope. Where a module's own port list needs a package type (`alu_status`'s
  `instruction` port), the guide's module-header import syntax
  (`module alu_status import isa_pkg::*; (...);`) is used instead — its
  scope covers the whole module, ports and body alike, so it also covers
  body-level uses of the package (e.g. `IC_ALU`) without a second import.
  Where a module's ports don't need a package type directly (only its body
  does, e.g. `alu.sv`), the import stays in the body, per the guide's other
  sanctioned placement.

## Design rationale

- **Word-addressed, not byte-addressed, memory.** There are no sub-word
  (byte/halfword) load/store instructions in this version, so
  byte-addressing's only benefit — addressing an individual byte — is
  currently unusable. Word-addressing also sidesteps alignment entirely
  (every representable address is valid by construction, vs. byte-addressed
  word-only access needing to reject/ignore `address[1:0] != 0`, a class of
  bug this project has no illegal-access/trap handling for yet — see
  `CLAUDE.md`'s exception-handling future direction). It also matches BRAM's
  natural word-indexed structure and doubles the effective address reach
  per instruction bit spent. Byte-addressing is a natural future revision
  alongside sub-word load/store opcodes, not ruled out permanently.
- **Fixed `[2:0]`/`[5:3]` register-operand positions, shared across every
  opcode that reads two registers.** Replaces an earlier version of this
  encoding where each opcode placed its register fields wherever was locally
  convenient. Adopted after the encoding changed shape several times during
  design — under fixed positions, `read1`/`read2` (regfile) are permanent
  constant taps off those instruction bits, with zero opcode-dependent
  muxing anywhere in the system, current or future. See `CLAUDE.md`'s
  fixed-register-position decision.
- **`is_imm_src1`/`is_imm_src2` as separate flag bits, not a combined
  flag+payload field per operand.** An earlier version widened each operand
  field itself (3→4 bits: flag + 3-bit payload) to carry a small immediate
  inline. Once `src1_addr`/`src2_addr` became fixed-position and always-read
  (previous bullet), that approach no longer works — the address bits can't
  double as payload bits when they're unconditionally spent on an address.
  Splitting the flag out and giving the immediate its own dedicated `13`-bit
  field (versus the old scheme's `3` bits, unsigned `0`–`7`) is a side
  effect of that change, not an independent goal — but it does buy a much
  wider immediate for free.
- **`is_imm_src1`/`is_imm_src2` both `1` is illegal, not legal-but-pointless.**
  An earlier version allowed both simultaneously (harmless — an assembler
  would just fold two known constants at assemble time). With one shared
  `imm` field serving either operand now, "both immediate" is ambiguous
  (which operand does `imm` belong to?), so it's a real illegal encoding,
  not just a wasteful one — `alu.sv` detects and flags it via `bus.error`
  (see Errors above).
- **`dest` stays 3 bits, not widened to match `src1`/`src2`.** A
  destination is always a register — giving it a flag bit would create a
  meaningless "immediate destination" encoding that would need to be either
  silently ignored or explicitly reserved/trapped for no functional gain.
  Fixed-width also keeps the register-file write-address decode a plain
  3-bit index.
- **`IMM_SET` zero-extends, doesn't sign-extend.** Consistent with the ALU
  immediate's unsigned choice. Negative values are obtainable via `NOT`
  followed by `ADD #1` (two's-complement negation) using instructions that
  already exist, without needing sign-extension semantics baked into
  `IMM_SET` itself. A full 32-bit constant (beyond 25 bits) is likewise
  achievable with existing instructions — two `IMM_SET`s plus `LSHIFT`/`OR`
  — no new opcode required.
- **`LOAD`/`STORE` base+offset, not bare register-indirect.** An earlier
  draft only had `LOAD_IMM`/`STORE_IMM`-style fixed-immediate addressing,
  which cannot support any computed/indexed access (arrays, pointer-style
  traversal) — every address would have to be a compile-time constant.
  Splitting into a fixed-address form (`LOAD_IMM`/`STORE_IMM` — fine for
  MMIO/global-fixed addresses) and a register-indirect + offset form
  (`LOAD`/`STORE` — for computed addresses) covers both needs without
  overloading one encoding.
- **`LOAD`/`STORE` offset is two's complement, not sign-magnitude.**
  Two's-complement sign-extension is free in hardware (fan out the sign bit
  into the new upper bits, no logic gates) and the subsequent addition
  reuses the exact same adder needed for the unsigned case — two's
  complement is specifically defined so that ordinary binary addition
  produces the correct signed result. Sign-magnitude would need a
  conditional add/subtract datapath (strictly more hardware) and carries a
  redundant zero representation (`+0` and `-0`), a real verification cost
  for no benefit here.
- **No hardwired-zero register.** Considered (cheap free `MOV`, cheap
  compare-to-zero for future branches) but rejected: the immediate-flag ALU
  operand already covers the "need a zero operand" case, and special-casing
  one of the eight registers was judged more confusing than the convenience
  is worth. All 8 registers are uniform general-purpose.
- **`always` as a dedicated `FLOW_CTL` op value, not `Rx eq Rx`.** The
  self-comparison trick is functionally equivalent and would have kept `op`
  at 3 bits instead of 4 (the only actual cost of the dedicated value).
  Rejected because a self-comparison is opaque in disassembly (an
  unconditional jump shouldn't read as an arbitrary "R0 eq R0") and awkward
  to target directly with a directed test — one bit was judged cheap next
  to that.
- **No immediate-flag on `FLOW_CTL`'s `val1`/`val2`**, unlike the `ALU`'s
  `src1`/`src2`. `z`/`nz` already cover "compare against a constant" well
  enough that a general register-vs-immediate comparison wasn't judged
  worth the added encoding complexity.

## Deferred / future ideas (explicitly out of scope for v1)

- **Stop/reset opcode** — moved out of `FLOW_CTL` (jumps/conditional
  branches are now specified, see above and `flow_ctl.md`) into a separate,
  not-yet-assigned future major opcode, dispatching to a not-yet-designed
  reset controller module (peripheral/interface reset sequencing, possibly
  boot-time startup control).
- **`DIV`/`MOD`** — as a pair, sharing one division circuit (quotient +
  remainder outputs), the same relationship as `MUL`/`MULH`. Needs its own
  decisions later: divide-by-zero behavior, whether both outputs are always
  computed or selected by opcode.
- **Separate `carry` flag** (distinct from `overflow`) — to support future
  multi-word/64-bit addition via chained `add`+`addc`. Needs a `carry_i`
  input and an `addc` opcode, neither of which exist yet.
- **`zero` flag** — result-is-zero, useful for future compare/branch
  instructions.
- **Flags bundled as a struct** — worth revisiting once there is more than
  one flag bit; premature with only `overflow`.
- **Addressable/movable flags register** (à la x86 EFLAGS / ARM CPSR) —
  vs. the v1 approach of a flag consumed only by a dedicated conditional
  branch instruction (`overflow`/`not_overflow`). Deferred because it
  entangles with how flags get saved/restored across interrupts, which is
  itself a future roadmap item, not yet designed.
- **Signed arithmetic** — two's-complement add/sub/shift/compare semantics,
  dropped for v1 to keep the first iteration simple.
- **Sub-word (byte/halfword) load/store** — would need new opcodes and
  would force a reconsideration of word-addressing (see rationale above).
  No current use case; deferred, not ruled out.
- **`NOT`'s ignored `src2` field convention** — hardware ignores it
  regardless, but whether the assembler should canonicalize it to a fixed
  value (e.g. `0`) for readable disassembly is a small open detail, not yet
  decided.
- **Hardware stack / call-return / context windows** — explicitly out of
  scope for this iteration, per original design request.
- **`FLOW_CTL` `op` values `0xC`–`0xF`** — reserved for future growth (e.g.
  `overflow` was itself added into what was originally reserved space).
- **Multi-flag status register** (beyond just `overflow` — zero, negative,
  carry, etc.) — premature with only one flag consumed so far.
