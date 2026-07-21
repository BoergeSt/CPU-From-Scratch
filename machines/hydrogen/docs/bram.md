# Hydrogen BRAM — v1 Specification

Machine generation: **hydrogen** (H, atomic number 1 — first machine
generation, per the codename convention in `CLAUDE.md`).

Status: **implemented** — `machines/hydrogen/rtl/bram.sv`, verified by
`machines/hydrogen/rtl/tb/test_bram.py` (`just check :hydrogen:bram`).

## Overview

This module is Hydrogen's main memory (`CLAUDE.md`'s "BRAM-as-main-memory to
start" decision) — a single flat storage array exposed through **two**
`bus_if` slave ports, one per bus defined in `bus.md`'s Harvard I/D split:
`bus_I` for instruction fetch, `bus_D` for data load/store. Both ports view
the *same* underlying storage — there is one memory array, not two — so a
write made through `bus_D` is visible through `bus_I` as well (e.g.
self-modifying code, or a program that reads back something it just wrote
via a different access path), subject to the ordinary one-cycle synchronous-
write latency described under Behavior.

## Interface

### Clock

`clk_i` is a plain module port, not part of either bus interface — same
"clock/reset never part of an interface" convention as `regfile.md`. There is
deliberately no `rst_i` — see Behavior.

### Parameter

| Parameter | Default | Description |
|-----------|---------|--------------|
| `Size` | `4096` (`0x1000`) | Number of 32-bit words of storage. Default is 4K instructions. |

### Bus ports (`bus_if.slave`)

Two instances, `bus_I` and `bus_D`, both the `slave` modport of `bus_if`
(field table and per-field semantics: `bus.md`'s Protocol section — not
repeated here). The two ports are **not symmetric**:

| Port | Reads | Writes |
|------|-------|--------|
| `bus_I` | yes | **no** — `we` is ignored; `bus_I` can never modify storage regardless of what's driven on it |
| `bus_D` | yes | yes |

## Behavior

- **No reset.** There is no automatic zeroing of storage on `rst_i` or
  power-up — whatever bit pattern is in the underlying storage at
  simulation/hardware start is what reads back, until something explicitly
  writes it. This matches real FPGA block-RAM primitives, which generally
  have no run-time reset network of their own. A POR-style "known state"
  guarantee that `regfile.md` gives its registers does **not** exist here;
  any test or program that depends on a particular value at some address
  must have written that value itself first.
- **Startup loading is TBD.** Some mechanism to get a program's instructions
  and initial data into `bram` before the core starts fetching from address
  0 is required for a runnable system, but that mechanism is not designed
  yet — see Deferred / future ideas.
- **Reads are combinational on both ports**, matching `bus.md`'s no-wait-
  state decision: `rdata` reflects the addressed word (or `0`, per below)
  continuously, with no clock involved.
  - If a port's `enable` is low, that port's `rdata` and `ack` are both `0`,
    regardless of `addr`.
  - If `enable` is high and `addr < Size`, `ack` is `1` and `rdata` is the
    current contents of that word.
  - If `enable` is high and `addr >= Size`, `ack` is `0` and `rdata` is `0`
    (no valid word exists to return).
- **`ack` is given if and only if the port is enabled and `addr < Size`** —
  true independently for `bus_I` and `bus_D`; one port's `ack` does not
  depend on the other port's state.
- **Writes are synchronous, `bus_D` only.** On the rising edge of `clk_i`,
  if `bus_D.enable` and `bus_D.we` are both high and `bus_D.addr < Size`,
  the addressed word is loaded with `bus_D.wdata`. `bus_I.we` is ignored
  outright — `bus_I` can never write, even if its `we` is driven high.
  A `bus_D` write attempt at `addr >= Size` has no effect on storage (there
  is nothing at that address to write).
- **Same-address same-cycle read + write**, whether the read is on the same
  port that's writing (`bus_D` writing while also reading its own `rdata`)
  or the other port (`bus_I` reading the exact word `bus_D` is writing),
  behaves like `regfile.md`'s identical case: the combinational read
  reflects the pre-write value for the entire cycle, and the new value only
  from the following cycle on — ordinary flip-flop `Q`-vs-`D` semantics, no
  bypass logic needed. This holds uniformly regardless of `we`; a port's
  `rdata` is never gated by its own write activity.
- **The two ports operate independently** when addressed at different
  locations in the same cycle — `bus_I`'s response never depends on what
  `bus_D` is doing that cycle (beyond both observing the same underlying
  storage), and vice versa.

## Design rationale

- **Two `bus_if.slave` ports onto one shared array, not two independent
  memories.** Matches `bus.md`'s Harvard-at-the-bus-level, unified-address-
  space-above-it design: instruction fetch and data access are physically
  separate ports so they can both be served in the same cycle, but they
  address the same memory map, so a single backing array is correct — two
  independent arrays would let instruction and data views of the same
  address silently disagree.
- **`bus_I` cannot write.** Fetch is a read-only access path by construction
  — no instruction encoding in `isa.md` can direct a store through the I-bus
  — so wiring `bus_I.we` to anything would only be a latent way to corrupt
  memory through a path that's supposed to be inert. Ignoring it outright
  (rather than, say, asserting it's tied low at the master) keeps that
  guarantee in the slave itself, independent of what the I-bus master side
  ever does.
- **No reset**, per `CLAUDE.md`'s hardware note under Reset convention:
  avoiding resets on registers where FPGA config-time initial values suffice
  can matter for efficient block-RAM inference. For a 4K-word array, forcing
  a synchronous reset network across every word would also be the kind of
  large, per-bit reset fan-out real BRAM primitives don't have natively.
  Simulation-only for now (`CLAUDE.md`), so this is a forward-looking
  hardware-mapping decision more than a present necessity, but keeping the
  behavior reset-free from the start avoids a later behavior change.
- **Combinational read, synchronous write** — combinational read matches
  `bus.md`'s no-wait-state protocol decision (every slave responds the same
  cycle); `bus.md` already flags this as a deliberate simulation-only
  tradeoff against real synchronous-read block-RAM primitives, to be
  revisited at the hardware bring-up phase.
- **`ack` per-port, decided purely by `enable`+range.** Consistent with
  `bus.md`'s definition of `ack` as "address matched a known slave, no
  downstream fault" — `bram` has no fault condition of its own beyond
  addressing outside `Size`, so `ack` collapses to exactly the range check.

## Deferred / future ideas (explicitly out of scope for v1)

- **Startup/initial content loading mechanism.** Explicitly TBD — options
  discussed only in passing so far include a simulation-only `$readmemh`-
  style preload, a synthesizable init file baked into the bitstream, or a
  bus-driven bootloader written through `bus_D` before the core starts
  fetching. Not designed yet.
- **Wait-states.** Per `bus.md`'s Deferred section — `bram`'s combinational
  read is the concrete instance of that tradeoff; revisit together.
