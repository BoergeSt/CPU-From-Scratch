# Hydrogen Implementation Notes

Machine generation: **hydrogen** (H, atomic number 1 — first machine
generation, per the codename convention in `CLAUDE.md`).

This document collects implementation conventions shared across multiple
Hydrogen modules, so each module's own doc states only what's specific to
it rather than repeating the shared convention. Audience: whoever implements
or reviews this machine generation's RTL — not the ISA/programmer-facing
contract, which lives in `isa.md`.

## Clock and reset

- **Single clock domain.** One `clk_i` drives every clocked module in this
  machine generation (`CLAUDE.md`'s "Single clock domain to start" decision
  — multi-clock-domain design and CDC are an explicit future learning goal,
  not yet started).
- **Reset is synchronous, active-high**, project-wide convention
  (`CLAUDE.md`). `rst_i` is sampled only on `clk_i`'s rising edge, so it
  can't itself cause a timing violation, and takes unconditional priority
  over any other input on the same edge unless a module's own doc states
  otherwise.
- **`clk_i`/`rst_i` are plain module ports, never part of a bus-style
  interface** (`alu_if`, `flow_ctl_if`, `regfile_read_if`/
  `regfile_write_if`, and the planned `bus_if` all keep them external). Per
  the lowRISC-derived naming convention in `CLAUDE.md`: clock declared
  first in the port list, reset immediately after.
- **The ALU is the one exception**: purely combinational, no `clk_i`/
  `rst_i` at all (`CLAUDE.md`'s "ALU: purely combinational for Phase 1"
  decision; see `alu.md`).
- What each clocked module actually resets to (e.g. `regfile`'s 8 registers
  clearing to `0`, `flow_ctl`'s `pc_o <= ResetVector`, `alu_status`'s
  `overflow_o <= 0`) is module-specific behavior, documented in that
  module's own doc, not here.
