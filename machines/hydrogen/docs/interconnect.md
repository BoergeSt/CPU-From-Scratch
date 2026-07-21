# Hydrogen D-Bus Interconnect — Planned Structure

Machine generation: **hydrogen** (H, atomic number 1 — first machine
generation, per the codename convention in `CLAUDE.md`).

Status: **not yet implemented / design phase.** No RTL exists yet for this
module (exact filename/location not finalized — see `bus.md`'s External
dependencies). This document captures its envisioned structure and where it
sits in the planned build order, so the plan survives even though several
other pieces land first. Per the "I define module boundaries → Claude
writes tests → I implement RTL" working order in `CLAUDE.md`.

## Overview

This is the D-bus-specific interconnect named in `bus.md`'s Module
boundaries section — the module doing address decode, address translation,
per-slave enable-gating, and response muxing across BRAM/UART/GPIO/future
slaves. The I-bus needs no equivalent module (direct point-to-point `bus_if`
into BRAM's second port). See `bus.md` for the protocol and the four jobs
themselves — not repeated here.

## Planned build order

| Step | Deliverable | Outcome |
|------|-------------|---------|
| 1 | BRAM (main memory) | Dual-port, combinational read |
| 2 | Control unit | First workable prototype |
| 3 | This interconnect + `LOAD`/`STORE` logic | D-bus becomes real |
| 4 | Peripherals (UART, GPIO, ...) | Added incrementally |

1. **BRAM**: dual-port, combinational read (`bus.md`'s no-wait-state
   decision) — one `bus_if.slave` port per bus (I and D).
2. **Control unit**: wires `alu`/`flow_ctl`/`regfile`/BRAM's I-port
   together. `ALU`/`IMM_SET`/`FLOW_CTL` instructions run end to end;
   `LOAD`/`STORE` not yet functional, since the D-bus doesn't exist yet.
3. **This interconnect + the control unit's `LOAD`/`STORE` logic**: land
   together — the interconnect has no reason to exist without something
   driving it. Slave count at this point: BRAM's D-port only, no
   peripherals.
4. **Peripherals** (virtual UART, virtual GPIO, ...): added to the
   interconnect incrementally, one at a time, once the BRAM-only D-bus
   round-trips.

Provisional — this is a plan, not a commitment; expect it to shift as
earlier steps surface real constraints.

## Design rationale

- **Control unit before this module.** Gets to a real, testable
  end-to-end prototype (fetch → decode → execute → writeback for
  register-only instructions) before tackling the more involved D-side,
  rather than blocking any working system on the interconnect being done
  first.
- **This module and `LOAD`/`STORE` control-unit logic as one step, not
  two.** Neither is independently useful: the interconnect has nothing to
  decode without a master issuing real D-bus transactions, and `LOAD`/
  `STORE` logic has nothing to talk to without the interconnect (or at
  least a stand-in single-slave D-bus) existing.
- **Peripherals added one at a time, after the baseline works.** Each
  addition is then a small, isolated, independently testable change to the
  interconnect's slave list — rather than designing the full slave set
  (and its address map) up front before anything on the D-bus has been
  proven to work at all.
