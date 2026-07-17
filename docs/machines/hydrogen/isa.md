# Hydrogen ISA — v1 Specification (Register File + Instruction Encoding)

Machine generation: **hydrogen** (H, atomic number 1 — first machine
generation, per the codename convention in `CLAUDE.md`).

Status: **specified, not yet implemented.** The ALU
(`fpga/rtl/machines/hydrogen/alu.sv`, see `alu.md`) is the only piece of the
datapath built so far. This document specifies the register file's
architectural shape and the full instruction encoding it and the (not yet
designed) control unit/decoder will need to implement.

## Overview

Hydrogen is a single-cycle core (see `CLAUDE.md`'s Phase 1 target). This
document covers the two pieces that sit around the already-built ALU: the
register file's architectural contract, and the 32-bit instruction encoding
that drives it. Memory is **word-addressed** (see Design rationale) and
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
| `0x3` | `LOADI` | Load from an immediate (fixed) address |
| `0x4` | `STORI` | Store to an immediate (fixed) address |
| `0x5` | `LOAD` | Load from a register-indirect + offset address |
| `0x6` | `STORE` | Store to a register-indirect + offset address |
| `0x7`–`0xF` | reserved | Free for future growth (e.g. `FLOW_CTL` variants, sub-word load/store) |

As with the ALU's op-code table, this numbering is a suggested grouping
only — free to renumber when writing the actual SV `localparam`s.

### `ALU` — `0x0`

```
[27:25] dest        (3b)  destination register index, R0-R7
[24:21] alu_op      (4b)  matches alu.sv's decode directly (alu.md)
[20]    is_imm_src1 (1b)  1 = src1 is the immediate below, 0 = register
[19]    is_imm_src2 (1b)  1 = src2 is the immediate below, 0 = register
[18:6]  imm         (13b) unsigned immediate payload — used by whichever
                           operand is flagged immediate, if either
[5:3]   src2_addr   (3b)  register index R0-R7 — always read regardless
                           of is_imm_src2, ignored by unary NOT
[2:0]   src1_addr   (3b)  register index R0-R7 — always read regardless
                           of is_imm_src1
```

`src1_addr`/`src2_addr` sit at fixed positions `[2:0]`/`[5:3]` shared with
every other opcode that reads two registers (`FLOW_CTL`'s `val1`/`val2`, see
below) — see `CLAUDE.md`'s fixed-register-position decision and Design
rationale. The addressed register is always read, whether or not the
corresponding `is_imm` flag ends up overriding it with `imm` instead.

`is_imm_src1`/`is_imm_src2` both being `1` simultaneously is **illegal**
(unlike an earlier version of this encoding where it was legal-but-pointless)
— `alu.sv` flags it via `bus.error`, see `alu.md`'s Errors section. At most
one operand may be sourced from `imm` per instruction.

`dest` is always a plain 3-bit register index — a destination can't
meaningfully be "an immediate," so unlike `src1`/`src2` it carries no flag
bit (see Design rationale).

### `IMM_SET` — `0x1`

```
[27:25] dest  (3b)  destination register index
[24:0]  imm   (25b) zero-extended into bits [24:0] of the register;
                     bits [31:25] of the register are cleared to 0
```

### `LOADI` — `0x3`, `STORI` — `0x4`

```
LOADI: [27:25] dest (3b)  [24:0] addr (25b, word address)
STORI: [27:25] src  (3b)  [24:0] addr (25b, word address)
```

`addr` is a fixed word address baked directly into the instruction — no
register is involved in address computation. Reaches 2²⁵ words (128 MB)
directly.

### `LOAD` — `0x5`, `STORE` — `0x6`

```
LOAD:  [27:25] dest (3b)  [24:22] base (3b)  [21:0] offset (22b)
STORE: [27:25] src  (3b)  [24:22] base (3b)  [21:0] offset (22b)
```

Effective address = `base` register's value + `offset`, both interpreted as
word addresses/offsets. `offset` is **two's complement**, reaching ±2²¹
words (±32 MB) from `base`.

### `FLOW_CTL` — `0x2`

```
[27]    r          (1b)  target mode: 1 = relative (pc + target, signed),
                          0 = absolute (target used directly, unsigned)
[26]    i          (1b)  target source: 1 = immediate, 0 = register-indirect
[25:22] op         (4b)  condition, matches flow_ctl.sv's decode directly
                          (flow_ctl.md)
i=0: [8:6]  jump_to_addr (3b) register index R0-R7 holding the jump target
     [21:9] reserved, must be 0
i=1: [21:6] imm (16b) two's-complement signed target/offset value —
                       overlaps jump_to_addr's [8:6], reinterpreted
                       (see flow_ctl.md)
[5:3]   val2_addr  (3b)  comparison operand B, register index R0-R7 —
                          always read, ignored by several op values
                          (see flow_ctl.md)
[2:0]   val1_addr  (3b)  comparison operand A, register index R0-R7 —
                          always read
```

`val1_addr`/`val2_addr`/`jump_to_addr` sit at the fixed `[2:0]`/`[5:3]`/
`[8:6]` positions shared with the `ALU`'s `src1_addr`/`src2_addr` above —
see `CLAUDE.md`'s fixed-register-position decision, now three universal
slots rather than two. `jump_to_addr` claims the 3rd slot even though no
other opcode currently uses it, specifically so a future opcode needing a
3rd register read can reuse the same fixed position and permanent wiring,
rather than `read3` needing per-opcode arbitration the way `read1`/`read2`
did before they were fixed. Unlike the `ALU`'s `src1`/`src2`, `val1`/`val2`
have no immediate-flag option (see `flow_ctl.md`'s Design rationale) —
they're always register reads.

`op`'s condition table, per-op `val1`/`val2` usage, the `r`/`i` interaction,
and the full RTL module boundary this feeds are specified in `flow_ctl.md`,
same split as `alu.md`'s relationship to the `ALU` opcode above. Stop/reset
are not part of this opcode — see Overview and Deferred ideas below.

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
  (`alu.md`).
- **`dest` stays 3 bits, not widened to match `src1`/`src2`.** A
  destination is always a register — giving it a flag bit would create a
  meaningless "immediate destination" encoding that would need to be either
  silently ignored or explicitly reserved/trapped for no functional gain.
  Fixed-width also keeps the register-file write-address decode a plain
  3-bit index.
- **Unsigned-only ALU immediate.** Signed would cost nothing in bit width
  but adds interpretation complexity; `SUB` already covers subtraction, so
  the range asymmetry doesn't cost real capability. Same reasoning as the
  old `0`–`7` version, unchanged by the width growing to `13` bits.
- **`IMM_SET` zero-extends, doesn't sign-extend.** Consistent with the ALU
  immediate's unsigned choice. Negative values are obtainable via `NOT`
  followed by `ADD #1` (two's-complement negation) using instructions that
  already exist, without needing sign-extension semantics baked into
  `IMM_SET` itself. A full 32-bit constant (beyond 25 bits) is likewise
  achievable with existing instructions — two `IMM_SET`s plus `LSHIFT`/`OR`
  — no new opcode required.
- **`LOAD`/`STORE` base+offset, not bare register-indirect.** An earlier
  draft only had `LOADI`/`STORI`-style fixed-immediate addressing, which
  cannot support any computed/indexed access (arrays, pointer-style
  traversal) — every address would have to be a compile-time constant.
  Splitting into a fixed-address form (`LOADI`/`STORI` — fine for
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

## Deferred / future ideas (explicitly out of scope for v1)

- **Stop/reset opcode** — moved out of `FLOW_CTL` (jumps/conditional
  branches are now specified, see above and `flow_ctl.md`) into a separate,
  not-yet-assigned future major opcode, dispatching to a not-yet-designed
  reset controller module (peripheral/interface reset sequencing, possibly
  boot-time startup control).
- **Overflow flag consumer** — resolved: `FLOW_CTL`'s `overflow`/
  `not_overflow` conditions (`flow_ctl.md`) consume the ALU's `overflow_o`
  (see `alu.md`), via a flag latched in the dedicated `alu_status` module
  (`alu_status.md`), not the ALU itself and not a general control unit.
- **Sub-word (byte/halfword) load/store** — would need new opcodes and
  would force a reconsideration of word-addressing (see rationale above).
  No current use case; deferred, not ruled out.
- **`NOT`'s ignored `src2` field convention** — hardware ignores it
  regardless, but whether the assembler should canonicalize it to a fixed
  value (e.g. `0`) for readable disassembly is a small open detail, not yet
  decided.
- **Hardware stack / call-return / context windows** — explicitly out of
  scope for this iteration, per original design request.
