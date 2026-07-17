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
mechanism. Flow control beyond raw straight-line execution (jumps,
conditional branches, stop/reset) is reserved as an opcode but not designed.

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
| `0x2` | `FLOW_CTL` | Reserved — jumps, stop/reset, etc. Not designed. |
| `0x3` | `LOADI` | Load from an immediate (fixed) address |
| `0x4` | `STORI` | Store to an immediate (fixed) address |
| `0x5` | `LOAD` | Load from a register-indirect + offset address |
| `0x6` | `STORE` | Store to a register-indirect + offset address |
| `0x7`–`0xF` | reserved | Free for future growth (e.g. `FLOW_CTL` variants, sub-word load/store) |

As with the ALU's op-code table, this numbering is a suggested grouping
only — free to renumber when writing the actual SV `localparam`s.

### `ALU` — `0x0`

```
[27:25] dest    (3b)  destination register index, R0-R7
[24:21] src1    (4b)  operand 1 select — see below
[20:17] src2    (4b)  operand 2 select — see below, ignored by unary NOT
[16:13] alu_op  (4b)  matches alu.sv's operation_i encoding directly (alu.md)
[12:0]  reserved       must be 0
```

`src1`/`src2` field format (identical for both): top bit is an
**immediate flag**, low 3 bits are the payload.

| flag bit | low 3 bits mean |
|----------|-----------------|
| `0` | register index R0–R7; operand = that register's value |
| `1` | literal unsigned value 0–7; operand = that value, zero-extended to 32 bits |

All 16 values of the 4-bit field are meaningful (8 register selects + 8
immediates) — there is no reserved/invalid sub-encoding within this field.
`src1` and `src2` both being flagged as immediate simultaneously is legal
(fully defined — each field decodes independently) but pointless, since an
assembler would just fold two known constants at assemble time; it is not
reserved or trapped.

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

Reserved. No parameter encoding designed yet — deferred along with jumps,
conditional branches, and stop/reset semantics.

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
- **`src1`/`src2` immediate-flag operand.** Widening the operand field from
  3 to 4 bits (flag + 3-bit payload) lets ALU ops take a small unsigned
  literal directly, without spending a separate `IMM_SET` instruction and a
  register for common small constants (loop increments, `#0`/`#1`, etc.).
  Exhaustively encodes all 16 values of the field with no reserved
  sub-encoding.
- **`dest` stays 3 bits, not widened to match `src1`/`src2`.** A
  destination is always a register — giving it a flag bit would create a
  meaningless "immediate destination" encoding that would need to be either
  silently ignored or explicitly reserved/trapped for no functional gain.
  Fixed-width also keeps the register-file write-address decode a plain
  3-bit index.
- **Unsigned-only ALU immediate (0–7).** Signed would cost nothing in bit
  width but adds interpretation complexity for a 3-bit field; `SUB` already
  covers subtraction, so the range asymmetry doesn't cost real capability.
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

- **`FLOW_CTL` encoding** — jumps, conditional branches, stop/reset. Reserved
  opcode, undesigned.
- **Overflow flag consumer** — the ALU's `overflow_o` (see `alu.md`) is
  currently computed every cycle and unconsumed. Needs either a status/flags
  register or a branch-on-overflow instruction, tied to `FLOW_CTL` design.
- **Sub-word (byte/halfword) load/store** — would need new opcodes and
  would force a reconsideration of word-addressing (see rationale above).
  No current use case; deferred, not ruled out.
- **`NOT`'s ignored `src2` field convention** — hardware ignores it
  regardless, but whether the assembler should canonicalize it to a fixed
  value (e.g. `0`) for readable disassembly is a small open detail, not yet
  decided.
- **Hardware stack / call-return / context windows** — explicitly out of
  scope for this iteration, per original design request.
