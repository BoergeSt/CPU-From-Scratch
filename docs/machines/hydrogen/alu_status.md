# Hydrogen ALU Status Latch (`alu_status`) — v1 Specification

Machine generation: **hydrogen** (H, atomic number 1 — first machine
generation, per the codename convention in `CLAUDE.md`).

Status: **implemented** — `fpga/rtl/machines/hydrogen/alu_status.sv`,
verified by `fpga/rtl/machines/hydrogen/tb/test_alu_status.py`
(`just check :hydrogen:alu_status`).

## Overview

This module exists to answer one question: where does the ALU's
`bus.overflow` flag live between the cycle it's produced and the later
cycle a `FLOW_CTL` `overflow`/`not_overflow` instruction wants to read it
(`isa.md`, `flow_ctl.md`)? The ALU itself can't hold it — it's purely
combinational and stateless by deliberate decision (`CLAUDE.md`'s "ALU:
purely combinational for Phase 1"), and a design pass partway through this
module's own design considered reversing that (giving the ALU a clock and
latching its own overflow) before rejecting it, for the same reason
`regfile.md` originally carved the PC out of the register file: no shared
datapath between the latch and the ALU's arithmetic justifies bundling them
in one module (see Design rationale). A general control unit owning the
latch was also considered and rejected — see Design rationale.

Like the ALU and the flow-control unit, this module receives the entire
fetched instruction word every cycle (`CLAUDE.md`'s functional-units-get-
the-whole-instruction decision) and self-detects whether the current cycle
is even an `ALU` instruction, rather than something external telling it so.

## Interface

| Field | Dir | Width | Description |
|-------|-----|-------|--------------|
| `clk_i` | in | 1 | Clock |
| `rst_i` | in | 1 | Synchronous active-high reset; `overflow_o <= 0` |
| `instruction` | in | 32 (`instr_t`) | Entire fetched instruction word |
| `overflow_i` | in | 1 | The ALU's live `bus.overflow` |
| `overflow_o` | out | 1 | Registered, latched flag |

`instruction` is the same value the ALU and flow-control unit receive,
used here only to self-detect `ALU` cycles (`instruction.generic.ic ==
IC_ALU`). `overflow_i` is wired directly from `alu.sv` — combinational,
present every cycle regardless of which instruction is actually active.
`overflow_o` feeds `flow_ctl`'s `overflow_i`.

`instruction` is typed `isa_pkg::instr_t`, so the port list needs the
package's types in scope — this module's `import isa_pkg::*;` sits in the
module header, not the body (see `isa.md`'s SV implementation section for
why that placement is required here specifically).

## Behavior

```
is_alu = (instruction.generic.ic == IC_ALU)   // isa.md
```

Every rising `clk_i` edge:

1. **`rst_i`** — `overflow_o <= 0`, unconditionally.
2. **`is_alu`** — `overflow_o <= overflow_i`: capture the ALU's live flag,
   since this cycle's `overflow_i` is actually meaningful.
3. **Otherwise** — `overflow_o <= overflow_o`: hold. The ALU's live
   `overflow_i` this cycle belongs to whatever non-`ALU` instruction is
   actually executing and means nothing, so it must not overwrite the last
   real value — a `FLOW_CTL` `overflow` check several instructions after
   the `ALU` op that set it still needs to see that op's flag, not garbage
   from whatever ran in between.

## Design rationale

- **Separate module, not inside the ALU.** The alternative — give the ALU
  `clk_i`/`rst_i` and have it latch its own overflow — was seriously
  considered during this module's design and rejected: it directly reverses
  `CLAUDE.md`'s "Decided" ALU-combinational choice, it would have made
  `alu.md`'s currently trivial, zero-clock-complexity test suite need
  reset/cross-cycle sequencing for one signal, and it breaks the clean
  "the ALU is stateless, full stop" invariant relied on for reasoning about
  the datapath (and needed again whenever the "Multi-cycle/pipelined ALU"
  future direction actually happens). A dedicated module costs one more
  small file — comparable in size to `alu_if.sv` — in exchange for keeping
  all of that intact.
- **Separate module, not inside a general control unit.** `flow_ctl.md`'s
  first pass at this design put the latch in an unspecified "control unit,"
  since that seemed like the natural place for anything cross-cutting.
  Revisited once `alu.sv`/`flow_ctl.sv` both moved to receiving the whole
  instruction and self-detecting relevance internally — the latch doesn't
  need a central decoder to tell it when to update, it can self-detect
  exactly the same way, so there's no longer a reason to route it through
  anything central at all.
- **Self-detects via `instruction.generic.ic`, not an external enable.**
  Same pattern as `alu.md`/`flow_ctl.md` — consistent with `CLAUDE.md`'s
  functional-units-get-the-whole-instruction decision, and means nothing
  else in the system needs to know this module exists in order to drive it
  correctly.
- **Hold, not clear, on non-`ALU` cycles.** The latch's entire purpose is
  surviving the gap between an `ALU` instruction and a later, unrelated-cycle
  `FLOW_CTL` check — clearing `overflow_o` on every non-`ALU` cycle would
  defeat that; only a real `rst_i` clears it.
- **Reset to `0`, synchronous, active-high** — matches `CLAUDE.md`'s
  project-wide reset convention, same as every other clocked module in this
  design.

## Deferred / future ideas (explicitly out of scope for v1)

- **Multi-flag status register** (zero, negative, carry, beyond just
  `overflow`) — this module's name already anticipates outgrowing a single
  bit; cross-references `isa.md`'s own deferred flags-struct idea.
  Premature with only `overflow` consumed by anything so far.
