# Hydrogen Flow Control Unit — v1 Specification

Machine generation: **hydrogen** (H, atomic number 1 — first machine
generation, per the codename convention in `CLAUDE.md`).

Status: **specified, not yet implemented.** Planned RTL:
`fpga/rtl/machines/hydrogen/flow_ctl.sv` (plus `flow_ctl_if.sv` if the ports
below end up bundled into an interface — see Interface), tests:
`fpga/rtl/machines/hydrogen/tb/test_flow_ctl.py`. Nothing here exists in RTL
yet; this document captures the module boundary agreed on before
implementation, per the project's usual working order (module boundary →
tests → RTL, see `CLAUDE.md`'s Working style notes). The `FLOW_CTL`
instruction encoding this module decodes is specified in `isa.md`
(major opcode `0x2`) — this document covers the RTL module boundary and
behavior built around that encoding, the same split `alu.md`/`regfile.md`
already use relative to `isa.md`.

## Overview

This module owns the **program counter** as internal register state, and is
the single place `pc_o`'s next value gets decided, every cycle — not just
for taken jumps. It receives the entire fetched instruction word
(`opcode_i`, see Interface) every cycle and self-detects whether it's even
the target: whenever the major opcode isn't `FLOW_CTL`, this module forces
its own internal condition to `nop` (`op = 4'h0`), so `pc_o <= pc_o + 1`
fall-through is the same code path as an untaken conditional jump, not a
bypass around this module. This resolves
`regfile.md`'s previously-open "PC's own module boundary" question: the PC
does not live in the register file (no shared datapath with `R0`–`R7`, see
`regfile.md`'s Overview) and does not live in a yet-to-be-designed control
unit either — it lives here, alongside the address arithmetic (`pc + offset`
for relative jumps) that only makes sense next to the register it operates
on.

This module also houses Hydrogen's first, deliberately primitive
illegal-instruction handling: `error_i`, an aggregated exception line driven
by the control unit, unconditionally forces `pc_o` to a fixed handler
address. This is a minimal precursor to the real exception/trap handling
named as a future direction in `CLAUDE.md` — not that mechanism itself.

Explicitly **not** this module's job: halt and reset. See Design rationale.

## Interface

### Clock and reset

| Field | Dir | Width | Description |
|-------|-----|-------|--------------|
| `clk_i` | in | 1 | Clock |
| `rst_i` | in | 1 | Synchronous active-high reset; `pc_o <= ResetVector` (see Behavior) |

Plain ports, matching `regfile.sv`'s convention (clock first, reset
immediately after, kept outside the bundled data interface below — same
"clk/rst never part of an interface" convention `regfile.md` already
states). Reset is synchronous, active-high, project-wide convention. `rst_i`
may be asserted by whatever this module's own upstream reset fan-out is, or
pulsed externally by a future reset controller module (see Design
rationale) — this module can't distinguish the two and doesn't need to.

### `flow_ctl_if`

Everything else bundles into one interface, `flow_ctl_if`, mirroring
`alu_if`'s single-consumer/single-shape reasoning — an earlier revision of
this document left bundling as an open question, now resolved: this
interface is what gets handed to the control unit as a single instance,
same pattern as `alu_if`'s `alu`/`requester` modports.

| Field | Dir (from `flow_ctl` modport) | Width | Description |
|-------|-------------------------------|-------|--------------|
| `opcode` | in | 32 | Entire fetched instruction word, per `CLAUDE.md`'s functional-units-get-the-whole-instruction decision. This module decodes `r`/`i`/`op`/`imm` from it internally and self-detects relevance by comparing `opcode[31:28]` against `FLOW_CTL`'s major opcode (`0x2`, `isa.md`) |
| `val1` | in | 32 | Comparison operand A — `regfile.read1.data`, permanently wired from `opcode[2:0]` system-wide (`CLAUDE.md`'s fixed-register-position decision), always driven |
| `val2` | in | 32 | Comparison operand B — `regfile.read2.data`, from `opcode[5:3]`, always driven; ignored by `z`/`nz`/`always`/`overflow`/`not_overflow`/`nop` |
| `goto_val` | in | 32 | `regfile.read3.data` — register-indirect target candidate. `read3.addr` is permanently wired from `opcode[8:6]` system-wide, same as `read1`/`read2` (`CLAUDE.md`'s fixed-register-position decision, now three slots) — this module doesn't drive that address itself. Named `goto_val`, not `goto` — the latter is a reserved C++ keyword and breaks Verilator's cocotb code generation |
| `overflow` | in | 1 | ALU overflow flag, **latched in the `alu_status` module** (`alu_status.md`), not read from the ALU directly |
| `error` | in | 1 | Aggregated illegal-instruction exception line from the control unit — unconditional override, see Behavior |
| `pc` | out | 32 | Program counter, registered, word address |

The `requester` modport mirrors every direction, same pattern as `alu_if`'s
— see `flow_ctl_if.sv` once written. No `dest`-style write field to the
register file — this module only ever writes its own internal `pc`, never
`R0`–`R7`, matching `regfile.md`'s own prediction of this ("a future
flow-control unit ... will only ever write the PC, never a GPR"). `r`/`i`/
`op` are no longer separate fields (an earlier revision of this document
had them) — see Design rationale. Nor is there a `goto_addr` output (an even
earlier revision had one) — `read3`'s address is fixed system-wide wiring,
not something this module drives, exactly like `read1`/`read2` — see Design
rationale.

The rest of this document keeps the `_i`/`_o` suffixed names
(`opcode_i`, `val1_i`, `pc_o`, ...) when describing behavior, matching how
`alu.md` refers to `bus.value1` etc. rather than the bare interface field
names — read `X_i`/`X_o` below as this interface's `X` field, direction
implied by the suffix.

## Operations

`op` (decoded from `opcode_i[25:22]`, see Behavior) selects one of 12
defined values (4 bits, 4 reserved for future growth) — numbering below is
a suggested grouping only, same caveat `alu.md` and `isa.md` already state
for their own opcode tables.

| Code | Mnemonic | Condition | Uses `val2_i`? |
|------|----------|-----------|-----------------|
| `0x0` | `nop`/never | never taken | no |
| `0x1` | `l` | `val1_i < val2_i` | yes |
| `0x2` | `le` | `val1_i <= val2_i` | yes |
| `0x3` | `g` | `val1_i > val2_i` | yes |
| `0x4` | `ge` | `val1_i >= val2_i` | yes |
| `0x5` | `z` | `val1_i == 0` | no |
| `0x6` | `nz` | `val1_i != 0` | no |
| `0x7` | `eq` | `val1_i == val2_i` | yes |
| `0x8` | `neq` | `val1_i != val2_i` | yes |
| `0x9` | `always` | always taken | no |
| `0xA` | `overflow` | `overflow_i == 1` | no |
| `0xB` | `not_overflow` | `overflow_i == 0` | no |
| `0xC`–`0xF` | reserved | — | — |

`l`/`le`/`g`/`ge` are **unsigned** comparisons, consistent with the ALU's
v1-wide unsigned-only scope (`alu.md`). The only signed interpretation
anywhere in `FLOW_CTL` is `r`'s relative-target case (`pc + target`,
two's-complement) — comparisons themselves never are.

`always` deliberately gets its own encoded value rather than being expressed
as `eq` with `val1_addr == val2_addr` (which is functionally equivalent,
since a register always equals itself) — see Design rationale.

## Behavior

First, decoded once from `opcode_i` every cycle, unconditionally:

```
is_flow_ctl = (opcode_i[31:28] == FlowCtlOpcode)   // 4'h2, isa.md
r           = opcode_i[27]
i           = opcode_i[26]
op          = is_flow_ctl ? opcode_i[25:22] : 4'h0  // self-detection: force
                                                     // nop/never when this
                                                     // instruction isn't ours
imm          = opcode_i[21:6]                       // i=1 case, 16b -- this
                                                      // range includes bits
                                                      // [8:6], which are also
                                                      // read3.addr's fixed
                                                      // position; see below
```

`goto_val_i` (`regfile.read3.data`) is available every cycle regardless of `i`,
since `read3.addr` is unconditionally, permanently wired from `opcode_i[8:6]`
system-wide — this module never drives that address itself (see Design
rationale). When `i=1`, `opcode_i[8:6]` is really part of `imm`'s bit
pattern rather than a meaningful register index, so `read3` ends up reading
some arbitrary register — harmless, since `goto_val_i` is simply never read in
that branch (see the `target` computation below).

Then, every rising `clk_i` edge, `pc_o`'s next value follows a fixed
priority order:

1. **`rst_i`** — `pc_o <= 32'h10` (`ResetVector`), unconditionally, above
   every other input. See Design rationale for why `0x10` and not `0x0`.
2. **`error_i`** — `pc_o <= 32'h0` (`ErrorVector`), unconditionally
   overriding `op` and every operand input that cycle.
3. **Condition per `op`** evaluates `val1_i`/`val2_i`/`overflow_i` per the
   Operations table. If taken:
   - `target = i ? extend(imm, r) : goto_val_i` — `extend` sign-extends `imm` to
     32 bits when `r` is set, zero-extends otherwise ("relative is always
     signed, absolute is always unsigned").
   - If `r`: compute the *exact*, unbounded sum `pc_o + target` (e.g. in a
     34-bit signed intermediate — wide enough that the true sum can never
     wrap while being computed, see `alu_status.md`-style width reasoning).
     If that exact sum falls outside `[0, 2^32-1]`, treat it as an error:
     `pc_o <= ErrorVector`, same target `0x0` as `error_i` (see next
     Behavior step), even though this is a *different* mechanism (see
     Design rationale) — it isn't `error_i`, nothing external asserted
     anything, this module detected it internally, this cycle. Otherwise
     `pc_o <= (pc_o + target)[31:0]`.
   - If not `r` (absolute): `pc_o <= target` directly — `target` is already
     guaranteed in-range (see Design rationale), no check needed.
4. **Not taken** (including `op == 4'h0`, whether from a real `FLOW_CTL`
   `nop` or self-detection forcing it for a non-`FLOW_CTL` instruction):
   `pc_o <= pc_o + 1`.

## Design rationale

- **Everything but `clk_i`/`rst_i` bundles into `flow_ctl_if`.** Resolves
  what an earlier revision of this document left open. The deciding factor:
  this whole interface gets handed to one consumer, the control unit, as a
  single instance — exactly the condition `alu_if`'s own rationale names for
  bundling ("the ALU has exactly one interaction shape used by a single
  consumer every cycle"). `clk_i`/`rst_i` stay outside it regardless, per
  the project-wide clock/reset-never-in-an-interface convention
  (`regfile.md`).
- **PC lives here, not the register file or a control unit.** `regfile.md`
  already carved the PC out for having no shared datapath with `R0`–`R7`;
  putting it in this module instead keeps the PC next to the only arithmetic
  that ever touches it (relative-jump `pc + offset`), and matches
  `regfile.md`'s own speculation that this unit "will only ever write the
  PC, never a GPR."
- **`opcode_i` is the whole 32-bit instruction; this module self-detects
  relevance.** Per `CLAUDE.md`'s functional-units-get-the-whole-instruction
  decision — an earlier revision had the control unit pre-decode `r`/`i`/
  `op`/`imm` into separate ports and synthesize `opcode_i = 4'h0` externally
  whenever the major opcode wasn't `FLOW_CTL`. Now this module does both
  itself: decode every field from `opcode_i`, and force `op = 4'h0`
  internally when `opcode_i[31:28] != FlowCtlOpcode`. Removes an entire
  class of control-unit logic (per-unit field slicing, per-unit "not your
  instruction" defaults) without changing this module's own behavior at all.
- **Uniform next-PC path, no bypass.** Whether `op = 4'h0` comes from a real
  `FLOW_CTL` `nop` or this module's own self-detection forcing it for a
  non-`FLOW_CTL` instruction, it's the same code path (see next bullet). One
  priority-encoded mux decides `pc_o` every cycle, full stop — no second,
  parallel "normal fall-through" path to keep in sync with this one.
- **Register-indirect target via a 3rd regfile read port, `read3`.** Mirrors
  `isa.md`'s own `LOADI`/`LOAD` split (fixed-immediate address vs.
  register-indirect computed address) for the same reason: a fixed jump
  target doesn't need a register read, but a computed one (jump tables,
  function-pointer-style dispatch) genuinely does, and Hydrogen has no
  hardware stack/call-return to provide that indirection another way.
  Confirms `regfile.md`'s own prediction that "a future core variant needing
  a 3rd read port is one more instantiation, not an interface redefinition."
- **`read3.addr` fixed system-wide at `opcode_i[8:6]`, not driven by this
  module.** An earlier revision had this module decode `jump_to_addr` and
  output it directly as `goto_addr_o`, reasoning that `read3` had no other
  consumer so a fixed cross-opcode position wasn't needed. Revisited: even
  with only one consumer *today*, leaving `read3` addressable only through a
  module-owned output would mean any *future* opcode also needing a 3rd
  register read couldn't share it without reintroducing exactly the
  per-opcode arbitration problem `read1`/`read2` were fixed to avoid. So
  `[8:6]` became a third universal slot alongside `[2:0]`/`[5:3]`
  (`CLAUDE.md`'s fixed-register-position decision) even though nothing else
  uses it yet — `jump_to_addr` just happens to be the first and only current
  occupant.
- **`imm` overlaps `jump_to_addr`'s `[8:6]` bits when `i=1`, rather than
  losing that range.** Reserving `[8:6]` unconditionally (like `val1`/`val2`)
  was considered and rejected: unlike `val1`/`val2`, which serve a purpose
  independent of `i` (comparison, needed in every mode), `jump_to_addr` and
  `imm` are mutually exclusive along the very same axis `i` already
  selects — there's no reason to keep `jump_to_addr` "reserved" once `imm`
  is what's actually meaningful. `read3` still gets read unconditionally in
  that case (regfile reads are free), it just reads whatever register the
  immediate's bit pattern happens to name — harmless, since `goto_val_i` is
  provably unused whenever `i=1` (same category of "read, but result
  discarded" as `val2_i` already is for several `op` values).
- **`val1_i`/`val2_i` fixed at `opcode_i[2:0]`/`opcode_i[5:3]`, always
  present regardless of `i`.** Per `CLAUDE.md`'s fixed-register-position
  decision, shared with the `ALU`'s `src1`/`src2` (`alu.md`) — `regfile`'s
  `read1`/`read2` are permanently wired from those bits system-wide, so this
  module (like the ALU) never computes or requests that address itself.
  Keeping the fields always-present regardless of `i` also avoids
  fragmenting `FLOW_CTL` into per-condition sub-formats to reclaim a few
  bits that aren't needed — only `12` of `16` `op` values are used and
  register mode already leaves `13` bits reserved, so there's no real
  pressure to economize further.
- **No immediate-flag on `val1_i`/`val2_i`**, unlike the ALU's `src1`/`src2`.
  `z`/`nz` already cover "compare against a constant" well enough that a
  general register-vs-immediate comparison wasn't judged worth the added
  encoding complexity.
- **`op=0x0` double-duty**: it's both the real, programmer-visible `FLOW_CTL`
  `nop`/never encoding *and* the value this module forces internally via
  self-detection for every non-`FLOW_CTL` instruction (see the `opcode_i`
  self-detection bullet above) — one code path serves both, not two that
  have to agree.
- **`always` as a dedicated `op` value, not `Rx eq Rx`.** The self-comparison
  trick is functionally equivalent and would have kept `op` at 3 bits
  instead of 4 (the only actual cost of the dedicated value). Rejected
  because a self-comparison is opaque in disassembly (an unconditional jump
  shouldn't read as an arbitrary "R0 eq R0") and awkward to target directly
  with a cocotb test case — one bit was judged cheap next to that.
- **`r` orthogonal to `i`.** Four meaningful combinations: fixed absolute
  target, fixed PC-relative offset, computed absolute target via register,
  computed PC-relative offset via register — all genuinely useful, so kept
  as two independent bits rather than collapsing any pair.
- **`error_i` as an aggregated input, not generated internally.** This
  module doesn't itself decide what counts as illegal — that's spread across
  the ALU's `bus.error` (reserved opcodes `0xC`–`0xF`, see `alu.md`'s Errors
  section), reserved major opcodes (`isa.md`), and reserved `FLOW_CTL` `op`
  values, all funneled into one line by the control unit. This module just
  reacts uniformly: force `pc_o <= 0`,
  unconditionally, regardless of what `op` says that cycle. Ties to
  `CLAUDE.md`'s exception/trap-handling future direction — this is a
  deliberately minimal precursor, not that mechanism.
- **Reset vector `0x10`, error vector `0x0`.** Reserves a fixed 16-word
  region (`0x0`–`0xF`) for a small, primitive exception handler — enough for
  something like "record an error code, then loop" — without building real
  trap/privilege infrastructure. Real code execution starts at `0x10`.
- **Out-of-range relative targets force `pc_o <= ErrorVector`, computed
  internally, not via `error_i`.** Traces back to the very first message in
  this module's design thread, which grouped "over/underflow" together with
  illegal instructions under one `error` concept — that got split apart
  once `error_i` became an aggregated *external* input (ALU/major-opcode/
  `op` illegality, none of which this module can detect itself), and
  PC-arithmetic range wasn't carried forward as its own decision at the
  time. It's real: an unchecked relative jump whose true target falls
  outside `[0, 2^32-1]` would otherwise silently wrap to some unrelated,
  semantically meaningless address and start executing whatever's there —
  exactly the kind of "catastrophic" failure mode worth trapping rather
  than allowing. Deliberately a *different* mechanism from `error_i`
  despite sharing `ErrorVector` as the target: `error_i` is something
  external the control unit aggregated and asserted; this is `flow_ctl`
  detecting a problem in its own arithmetic, this cycle, with no other
  module involved. Absolute targets (`r=0`) need no equivalent check —
  `goto_val_i` is already a full 32-bit value with no way to be
  out-of-range, and zero-extended `imm` is bounded well within range by
  construction.
- **`overflow_i` sourced from the `alu_status` module, not the ALU
  directly.** The ALU is purely combinational and stateless (`alu.md`) —
  its `bus.overflow` is only valid during the same cycle as the instruction
  that produced it. By the time a later `FLOW_CTL` instruction checks it,
  the ALU's live output belongs to an unrelated instruction (or none), so
  something has to remember the flag across that gap. `alu.md`'s own
  "Overflow latching" section covers this from the ALU's side; `alu_status`
  is the dedicated module that owns the latch (a general control unit and a
  stateful ALU were both considered and rejected — see `alu_status.md`'s
  Design rationale). Keeps this module's scope as "consumes a flag," not
  "owns one."
- **No halt/reset handling in this module at all.** Both were originally
  considered as `FLOW_CTL` sub-opcodes, then moved out: `isa.md`'s major
  opcode table already reserved `FLOW_CTL` for "jumps, stop/reset, etc.,"
  but stop/reset are a genuinely different concern (peripheral/interface
  reset sequencing, possibly boot-time startup control) that doesn't belong
  bundled with branch evaluation. They're deferred to a separate, not-yet-
  designed future major opcode dispatching to a not-yet-designed reset
  controller module. A software `reset` would have that controller pulse
  this module's existing `rst_i` — reusing the reset path already defined
  above rather than adding a second, competing way to force `pc_o`. `halt`
  needs no dedicated hardware at all: a `jump` targeting its own current
  address already produces "spin forever" using ops this module already
  has; a *real* hardware halt (stalling the clock/pipeline for power-safe
  idle) would need a stall/enable network threaded through every clocked
  module, which doesn't exist yet and is future work if ever needed.

## Deferred / future ideas (explicitly out of scope for v1)

- **`op` values `0xC`–`0xF`** — reserved for future growth (e.g. `overflow`
  was itself added into what was originally reserved space).
- **`flow_ctl_if.sv` itself** — not written yet; this document specifies its
  fields (Interface) but the actual interface/modport RTL is still to come.
- **Stop/reset major opcode + reset controller module** — not yet designed;
  see Design rationale.
- **Real hardware `halt`** (clock/stall-based, vs. the software self-jump
  idiom used for v1) — needs a stall/enable network that doesn't exist yet.
- **`ResetVector`/`ErrorVector` as named constants** (`0x10`/`0x0`) rather
  than bare literals repeated at each use site — an implementation detail
  for whenever the RTL is written, not a design question.
- **Multi-flag status register** (beyond just `overflow` — zero, negative,
  carry, etc.) — cross-references `alu.md`'s own deferred `flags_o` struct
  idea; premature with only one flag consumed so far.

## External dependencies (not part of this module)

An earlier revision of this document had a long list here — decoding
`FLOW_CTL`'s fields, driving `opcode_i = 4'h0` for non-`FLOW_CTL`
instructions, latching overflow — because a general control unit was
expected to do all of it. Broadcasting the whole instruction (`opcode_i`)
and self-detection (Behavior) pulled the field-decode and nop-substitution
work into this module itself, and the overflow latch moved into its own
dedicated `alu_status` module (`alu_status.md`). What's left, genuinely
outside this module:

- `regfile`'s `read1`/`read2`/`read3` being permanently wired from
  `opcode_i[2:0]`/`opcode_i[5:3]`/`opcode_i[8:6]` — system-wide wiring
  (`CLAUDE.md`'s fixed-register-position decision, three slots), not
  something any one module drives, including this one (an earlier revision
  had this module drive `read3.addr` itself — see Design rationale).
- Aggregating every illegal-instruction condition (ALU `bus.error`, reserved
  major opcodes, reserved `FLOW_CTL` `op` values) into the single `error_i`
  line — still genuinely control-unit territory, since it spans multiple
  modules' outputs.
