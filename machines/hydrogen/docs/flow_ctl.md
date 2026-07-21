# Hydrogen Flow Control Unit — v1 Specification

Machine generation: **hydrogen** (H, atomic number 1 — first machine
generation, per the codename convention in `CLAUDE.md`).

Status: **implemented** — `machines/hydrogen/rtl/flow_ctl.sv`,
verified by `machines/hydrogen/rtl/tb/test_flow_ctl.py`
(`just check :hydrogen:flow_ctl`). The `FLOW_CTL` instruction encoding this
module decodes — including its condition-code table — is specified in
`isa.md` (major opcode `0x2`); this document covers the RTL module
boundary and timing built around that encoding, the same split `alu.md`/
`regfile.md` use relative to `isa.md`.

## Overview

This module owns the **program counter** as internal register state, and is
the single place `pc_o`'s next value gets decided, every cycle — not just
for taken jumps. It receives the entire fetched instruction word
(`bus.instruction`, see Interface) every cycle and self-detects whether
it's even the target, by comparing the instruction's class against
`IC_FLOW_CTL`. This resolves `regfile.md`'s previously-open "PC's own module
boundary" question: the PC does not live in the register file (no shared
datapath with `R0`–`R7`, see `regfile.md`'s Overview) and does not live in
a yet-to-be-designed control unit either — it lives here, alongside the
address arithmetic (`pc + offset` for relative jumps) that only makes sense
next to the register it operates on.

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

See `implementation.md` for the shared clock/reset convention these ports
follow. `rst_i` may be asserted by whatever this module's own upstream
reset fan-out is, or pulsed externally by a future reset controller module
(see Design rationale) — this module can't distinguish the two and doesn't
need to.

### `flow_ctl_if`

Everything else bundles into one interface, `flow_ctl_if`, mirroring
`alu_if`'s single-consumer/single-shape reasoning: this interface is what
gets handed to the control unit as a single instance, same pattern as
`alu_if`'s `alu`/`requester` modports.

| Field | Dir | Width | Description |
|-------|-----|-------|--------------|
| `instruction` | in | 32 (`instr_t`) | Entire fetched instruction word |
| `val1` | in | 32 | Comparison operand A |
| `val2` | in | 32 | Comparison operand B, ignored by |
| | | | `z`/`nz`/`always`/`overflow`/`not_overflow`/`nop` |
| `goto_val` | in | 32 | Register-indirect target candidate |
| `overflow` | in | 1 | Latched ALU overflow flag |
| `error` | in | 1 | Aggregated illegal-instruction exception line |
| `pc` | out | 32 | Program counter, registered, word address |

(Dir is from the `flow_ctl` modport.) `instruction` decodes `r`/`i`/`op`/
`imm` internally and self-detects relevance via `instruction.flow_ctl.ic ==
IC_FLOW_CTL`, per `CLAUDE.md`'s functional-units-get-the-whole-instruction
decision. `val1`/`val2` are `regfile.read1`/`read2` data, permanently
wired from `instruction.flow_ctl.src1_addr`/`.src2_addr` system-wide
(`CLAUDE.md`'s fixed-register-position decision), always driven regardless
of which `op` is active. `goto_val` is `regfile.read3.value`; `read3.addr`
is permanently wired from `instruction.flow_ctl.target.is_reg.jump_to_addr`
system-wide, same as `read1`/`read2` — this module doesn't drive that
address itself. Named `goto_val`, not `goto` — the latter is a reserved
C++ keyword and breaks Verilator's cocotb code generation. `overflow` is
the ALU's overflow flag as latched by `alu_status` (`alu_status.md`), not
read from the ALU directly. `error` is the aggregated illegal-instruction
exception line from the control unit — see Behavior for its priority.

The `requester` modport mirrors every direction, same pattern as `alu_if`'s.
No `dest`-style write field to the register file — this module only ever
writes its own internal `pc`, never `R0`–`R7`, matching `regfile.md`'s own
prediction of this ("a future flow-control unit ... will only ever write
the PC, never a GPR"). Nor is there a `goto_addr` output — `read3`'s
address is fixed system-wide wiring, not something this module drives,
exactly like `read1`/`read2` — see Design rationale.

The rest of this document keeps the `_i`/`_o` suffixed names
(`val1_i`, `pc_o`, ...) when describing behavior, matching how `alu.md`
refers to `bus.value1` etc. rather than the bare interface field names —
read `X_i`/`X_o` below as this interface's `X` field, direction implied by
the suffix.

## Behavior

First, decoded once from `bus.instruction` every cycle, unconditionally:

```
is_flow_ctl = (instruction.flow_ctl.ic == IC_FLOW_CTL)
r           = instruction.flow_ctl.is_relative
i           = instruction.flow_ctl.is_imm
op          = instruction.flow_ctl.op            // only consulted when is_flow_ctl
imm         = instruction.flow_ctl.target.is_imm.imm   // i=1 case, 16b
```

`goto_val_i` (`regfile.read3.value`) is available every cycle regardless of
`i`, since `read3.addr` is unconditionally, permanently wired from
`instruction.flow_ctl.target.is_reg.jump_to_addr` system-wide — this module
never drives that address itself (see Design rationale). When `i=1`, that
same 16-bit range is really part of `imm`'s bit pattern rather than a
meaningful register index, so `read3` ends up reading some arbitrary
register — harmless, since `goto_val_i` is never read in that branch
(see the `target` computation below).

Then, every rising `clk_i` edge, `pc_o`'s next value follows a fixed
priority order:

1. **`rst_i`** — `pc_o <= ResetVector` (`32'h10`), unconditionally, above
   every other input. See Design rationale for why `0x10` and not `0x0`.
2. **`error_i`** — `pc_o <= ErrorVector` (`32'h0`), unconditionally
   overriding `op` and every operand input that cycle.
3. **`!is_flow_ctl`** — `pc_o <= pc_o + 1`. A separate fall-through branch,
   not routed through `op`/the case statement below — see Design rationale
   for how this differs from an earlier revision.
4. **Condition per `op`** (only reached when `is_flow_ctl`) evaluates
   `val1_i`/`val2_i`/`overflow_i` per `isa.md`'s Operations table. If taken:
   - `target = i ? extend(imm, r) : goto_val_i` — `extend` sign-extends `imm` to
     32 bits when `r` is set, zero-extends otherwise ("relative is always
     signed, absolute is always unsigned").
   - If `r`: compute the *exact*, unbounded sum `pc_o + target` in a 34-bit
     signed intermediate — wide enough that the true sum can never wrap
     while being computed. If that exact sum falls outside `[0, 2^32-1]`,
     treat it as an error: `pc_o <= ErrorVector`, same target as `error_i`,
     even though this is a *different* mechanism (see Design rationale) —
     it isn't `error_i`, nothing external asserted anything, this module
     detected it internally, this cycle. Otherwise `pc_o <= (pc_o +
     target)[31:0]`.
   - If not `r` (absolute): `pc_o <= target` directly — `target` is already
     guaranteed in-range (see Design rationale), no check needed.
5. **Not taken, including a real `FLOW_CTL` `nop`/`op == FLOW_CTL_OP_NOP`**:
   `pc_o <= pc_o + 1`. Reserved `op` values (`0xC`–`0xF`) also land here via
   the case statement's `default:`, but resolve to `pc_o <= ErrorVector`
   rather than fall-through — an unrecognized `op` value on an actual
   `FLOW_CTL` instruction is treated as illegal, not as a no-op.

## Design rationale

- **Everything but `clk_i`/`rst_i` bundles into `flow_ctl_if`.** The
  deciding factor: this whole interface gets handed to one consumer, the
  control unit, as a single instance — exactly the condition `alu_if`'s own
  rationale names for bundling ("the ALU has exactly one interaction shape
  used by a single consumer every cycle"). `clk_i`/`rst_i` stay outside it
  regardless, per the project-wide clock/reset-never-in-an-interface
  convention (`regfile.md`).
- **PC lives here, not the register file or a control unit.** `regfile.md`
  already carved the PC out for having no shared datapath with `R0`–`R7`;
  putting it in this module instead keeps the PC next to the only arithmetic
  that ever touches it (relative-jump `pc + offset`), and matches
  `regfile.md`'s own speculation that this unit "will only ever write the
  PC, never a GPR."
- **`bus.instruction` is the whole 32-bit instruction; this module
  self-detects relevance.** Per `CLAUDE.md`'s functional-units-get-the-
  whole-instruction decision — an earlier revision had the control unit
  pre-decode `r`/`i`/`op`/`imm` into separate ports and synthesize a
  "not-mine" default externally whenever the major opcode wasn't
  `FLOW_CTL`. Now this module does both itself: decode every field from
  `bus.instruction`, and take a separate fall-through path when
  `instruction.flow_ctl.ic != IC_FLOW_CTL`. Removes an entire class of
  control-unit logic (per-unit field slicing, per-unit "not your
  instruction" defaults) without changing this module's own behavior at
  all.
- **Self-detection is a separate branch, not routed through `op`.** An
  earlier revision of this design forced `op` to `FLOW_CTL_OP_NOP`
  internally for a non-`FLOW_CTL` instruction, so the real `nop` encoding
  and self-detection's fall-through shared one code path (the case
  statement's `NOP` arm). The current RTL instead checks
  `instruction.flow_ctl.ic != IC_FLOW_CTL` in its own `else if` branch,
  ahead of the case statement — a real `FLOW_CTL` `nop` and a non-`FLOW_CTL`
  instruction now produce `pc_o <= pc_o + 1` via two different lines of
  RTL, not one shared path. Functionally identical either way; this is a
  structural difference from what an earlier revision of this document
  described, corrected here to match the current implementation.
- **Register-indirect target via a 3rd regfile read port, `read3`.** Mirrors
  `isa.md`'s own `LOAD_IMM`/`LOAD` split (fixed-immediate address vs.
  register-indirect computed address) for the same reason: a fixed jump
  target doesn't need a register read, but a computed one (jump tables,
  function-pointer-style dispatch) genuinely does, and Hydrogen has no
  hardware stack/call-return to provide that indirection another way.
  Confirms `regfile.md`'s own prediction that "a future core variant needing
  a 3rd read port is one more instantiation, not an interface redefinition."
- **`read3.addr` fixed system-wide, not driven by this module.** An earlier
  revision had this module decode `jump_to_addr` and output it directly as
  `goto_addr_o`, reasoning that `read3` had no other consumer so a fixed
  cross-opcode position wasn't needed. Revisited: even with only one
  consumer *today*, leaving `read3` addressable only through a
  module-owned output would mean any *future* opcode also needing a 3rd
  register read couldn't share it without reintroducing exactly the
  per-opcode arbitration problem `read1`/`read2` were fixed to avoid — see
  `isa.md`'s fixed-register-position decision.
- **`error_i` as an aggregated input, not generated internally.** This
  module doesn't itself decide what counts as illegal — that's spread
  across the ALU's `bus.error` (`isa.md`'s Errors), reserved major opcodes
  (`isa.md`), and reserved `FLOW_CTL` `op` values, all funneled into one
  line by the control unit. This module just reacts uniformly: force
  `pc_o <= ErrorVector`, unconditionally, regardless of what `op` says that
  cycle. Ties to `CLAUDE.md`'s exception/trap-handling future direction —
  this is a deliberately minimal precursor, not that mechanism.
- **Reset vector `0x10`, error vector `0x0`.** Reserves a fixed 16-word
  region (`0x0`–`0xF`) for a small, primitive exception handler — enough for
  something like "record an error code, then loop" — without building real
  trap/privilege infrastructure. Real code execution starts at `0x10`. Both
  values are `isa_pkg::ResetVector`/`isa_pkg::ErrorVector` — not part of
  `isa.md`'s instruction *encoding* (no field in any opcode encodes them),
  but centralized in the same package since they're a fixed, module-level
  convention this module and any future consumer (e.g. a trap handler)
  need to agree on.
- **Out-of-range relative targets force `pc_o <= ErrorVector`, computed
  internally, not via `error_i`.** An unchecked relative jump whose true
  target falls outside `[0, 2^32-1]` would otherwise silently wrap to some
  unrelated, semantically meaningless address and start executing whatever
  is there — exactly the kind of failure mode worth trapping rather than
  allowing. Deliberately a *different* mechanism from `error_i` despite
  sharing `ErrorVector` as the target: `error_i` is something external the
  control unit aggregated and asserted; this is `flow_ctl` detecting a
  problem in its own arithmetic, this cycle, with no other module involved.
  Absolute targets (`r=0`) need no equivalent check — `goto_val_i` is
  already a full 32-bit value with no way to be out-of-range, and
  zero-extended `imm` is bounded well within range by construction.
- **`overflow_i` sourced from the `alu_status` module, not the ALU
  directly.** The ALU is purely combinational and stateless (`alu.md`) —
  its `bus.overflow` is only valid during the same cycle as the instruction
  that produced it. By the time a later `FLOW_CTL` instruction checks it,
  the ALU's live output belongs to an unrelated instruction (or none), so
  something has to remember the flag across that gap. `alu_status` is the
  dedicated module that owns the latch (a general control unit and a
  stateful ALU were both considered and rejected — see `alu_status.md`'s
  Design rationale). Keeps this module's scope as "consumes a flag," not
  "owns one."
- **No halt/reset handling in this module at all.** Both were originally
  considered as `FLOW_CTL` sub-opcodes, then moved out: stop/reset are a
  genuinely different concern (peripheral/interface reset sequencing,
  possibly boot-time startup control) that doesn't belong bundled with
  branch evaluation. They're deferred to a separate, not-yet-designed
  future major opcode dispatching to a not-yet-designed reset controller
  module. A software `reset` would have that controller pulse this module's
  existing `rst_i` — reusing the reset path already defined above rather
  than adding a second, competing way to force `pc_o`. `halt` needs no
  dedicated hardware at all: a `jump` targeting its own current address
  already produces "spin forever" using ops this module already has; a
  *real* hardware halt (stalling the clock/pipeline for power-safe idle)
  would need a stall/enable network threaded through every clocked module,
  which doesn't exist yet and is future work if ever needed.

## Deferred / future ideas (explicitly out of scope for v1)

Encoding-level deferrals (reserved `op` values, a multi-flag status
register) are listed in `isa.md`; this module's own:

- **Stop/reset major opcode + reset controller module** — not yet designed;
  see Design rationale.
- **Real hardware `halt`** (clock/stall-based, vs. the software self-jump
  idiom used for v1) — needs a stall/enable network that doesn't exist yet.

## External dependencies (not part of this module)

- `regfile`'s `read1`/`read2`/`read3` being permanently wired from
  `instruction.flow_ctl.src1_addr`/`.src2_addr`/`.target.is_reg.jump_to_addr`
  — system-wide wiring (`CLAUDE.md`'s fixed-register-position decision,
  three slots), not something any one module drives, including this one.
- Aggregating every illegal-instruction condition (ALU `bus.error`, reserved
  major opcodes, reserved `FLOW_CTL` `op` values) into the single `error_i`
  line — still genuinely control-unit territory, since it spans multiple
  modules' outputs.
