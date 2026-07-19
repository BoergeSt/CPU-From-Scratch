# Hydrogen Bus Protocol — v1 Specification

Machine generation: **hydrogen** (H, atomic number 1 — first machine
generation, per the codename convention in `CLAUDE.md`).

Status: **protocol implemented** — `fpga/rtl/machines/hydrogen/bus_if.sv`.
No interconnect or slave module exists yet (BRAM, the control unit, and the
D-bus interconnect itself are all still ahead of this — see
`interconnect.md` for the planned build order). This document captures the
protocol decision reached in design discussion, per the "I define module
boundaries → Claude writes tests → I implement the RTL" working order in
`CLAUDE.md`.

## Overview

Hydrogen's single-cycle core needs two memory accesses in the same cycle:
instruction fetch (`pc` → instruction word) and, on `LOAD`/`STORE`, a data
access. One shared bus cannot carry two transactions in the same cycle
regardless of arbitration — arbitration resolves *contention between
masters*, it doesn't let one bus carry two transactions at once. The fix,
matching how real CPUs split this at the L1 cache level (separate I-cache
and D-cache ports into the core, even though the architecture is Von
Neumann/unified-address-space above that point), is a **Harvard split at
the bus level**: two independent bus instances, one for fetch (I-bus) and
one for data (D-bus), both addressing the same unified memory map (still
memory-mapped per `CLAUDE.md`'s I/O-addressing decision — the split is
physical, not architectural).

What's shared between the two is the **protocol** (this document, `bus_if`)
— the signal-level handshake. What differs is the **topology**:

- **I-bus**: one master (fetch), one slave (BRAM). Instructions are never
  fetched from a peripheral, so there's nothing to address-decode — a
  direct point-to-point `bus_if` connection into BRAM's second port, no
  interconnect module needed.
- **D-bus**: one master (control unit), multiple slaves (BRAM, virtual
  UART, virtual GPIO, ...). This side needs a real address decoder +
  read-data mux — an interconnect module, still with only one master so no
  arbiter, just decode.

Both are single-master today, so neither needs arbitration in v1. A future
multi-master addition (e.g. DMA, per `CLAUDE.md`'s roadmap) is expected to
look like AXI's crossbar model rather than AHB's single shared bus: give
each master an independent path, and arbitrate only at the specific slave
two masters actually collide on, not globally. `bus_if`, defined once and
reused at every port, is what makes that composable later without a
protocol redesign.

## Module boundaries

`bus_if` (see Protocol) is the shared protocol; how many modules speak it,
and in what topology, differs between the two buses:

- **I-bus**: no interconnect module. Fetch logic drives a `bus_if.master`
  wired directly into BRAM's second `bus_if.slave` port — one master, one
  slave, nothing to decode.
- **D-bus**: a dedicated interconnect module sits between the control
  unit's `bus_if.master` and every real slave's `bus_if.slave` port (BRAM's
  first port, virtual UART, virtual GPIO, ...). It owns all D-bus decode
  logic, project-wide — no other module ever compares an address against a
  range. Concretely, four jobs:
  1. **Decode** — compare the incoming global `addr` against each slave's
     known base/size to determine which one (if any) is targeted.
  2. **Translate** — present the matched slave with a local, base-relative
     address, not the raw global one (see Design rationale).
  3. **Enable-gate** — only the matched slave's `enable` goes high that
     cycle; every other slave sees `enable = 0` regardless of what's on its
     other input lines.
  4. **Mux the response** — `rdata`/`ack` back to the master reflect
     whichever slave was matched. (`wdata`/`we`/translated `addr` fan out
     to every slave unmuxed — only the gated one acts on them.)

No generic "bus-slave wrapper" module exists in v1 — `bram.sv`, `uart.sv`,
and `gpio.sv` each implement `bus_if.slave` directly (see Design
rationale).

## Protocol

`bus_if`, an SV interface with `master`/`slave` modports, per `CLAUDE.md`'s
bus/module-port convention. `clk_i`/`rst_i` stay outside it, as plain ports
on every clocked module — same "clock/reset never part of an interface"
convention documented in `implementation.md`.

| Field | Dir | Width | Description |
|-------|-----|-------|--------------|
| `addr` | out | 32 | Word address |
| `wdata` | out | 32 | Write data |
| `rdata` | in | 32 | Read data |
| `enable` | out | 1 | Transaction strobe — gates the access, |
| | | | see Design rationale |
| `we` | out | 1 | `1` = write, `0` = read |
| `ack` | in | 1 | Address matched a slave with no downstream fault |
| | | | (bundled as one bit); folds into `flow_ctl`'s |
| | | | `error_i` as `enable && !ack`, see `flow_ctl.md` |

(Dir is from the `master` modport.)

`wdata`/`rdata` are separate unidirectional fields, not one bidirectional
bus, despite never being meaningfully active in the same transaction — see
Design rationale.

There is deliberately **no ready/wait-state signal** in v1 — `ack` and
every slave's response resolve within the same cycle, unconditionally. See
Design rationale.

## Design rationale

- **Two bus instances sharing one protocol, not one N-slave fabric
  connecting everything.** A single fabric reaching both fetch and data
  would force the I-side to carry address-decode logic it structurally
  never needs (fetch never targets a peripheral). Two independently
  hand-rolled protocols would duplicate the handshake definition for no
  reason and cost reuse (`CLAUDE.md`'s "every component should be reusable
  and self-contained"). One shared `bus_if`, instantiated in two different
  topologies (point-to-point for I, decoder+mux for D), gets uniformity
  where it matters (both feed the same `bus_if`-shaped BRAM slave port,
  both can report `ack`) without forcing unneeded complexity onto the
  simpler side.
- **`wdata`/`rdata` split, not a literal bidirectional net.** The "never
  need read and write simultaneously" observation is real, but SV
  `inout`/tristate is idiomatically reserved for top-level physical pads,
  not internal module-to-module buses — it has no well-defined
  multi-driver semantics for internal FPGA logic, and Verilator doesn't
  model tristate contention realistically. A mux at the slave side (or
  simply ignoring `wdata` on a read) gets the same "never both meaningful
  at once" property without literal bidirectional wiring.
- **`enable` is load-bearing on the D-bus specifically, not just a nicety.**
  Only some cycles are a real `LOAD`/`STORE`; without a strobe, a peripheral
  with a side-effecting read (e.g. a UART RX FIFO that pops a byte on read)
  would fire on every cycle the D-bus happens to present its address,
  whether or not the instruction that cycle was actually a load. `enable`
  gates that. (I-bus ties `enable` high permanently — fetch happens every
  cycle unconditionally — but keeps the same field for protocol
  uniformity.)
- **No wait-state/ready signal in v1 — every slave responds combinationally,
  same cycle.** This isn't a simplification of convenience; it's required
  for consistency with the core's existing single-cycle model, where the
  ALU is "stateless combinational... only the register file/PC get
  clocked" (`CLAUDE.md`). A slave allowed to stall would force *some*
  instructions to take more than one cycle, breaking that model. The real
  cost lands on the memory module: FPGA block-RAM primitives are typically
  synchronous-read (registered output), so a combinational-read BRAM model
  doesn't map to them efficiently — an explicit, deliberate tradeoff here,
  covered by `CLAUDE.md`'s "simulation-only for now, don't optimize for
  synthesis/timing yet." Revisit when BRAM itself is designed, and again at
  the (already deferred) hardware bring-up phase.
- **A stall, if ever needed, would not be an ISA opcode.** Considered and
  rejected during design discussion: encoding "wait" as a `FLOW_CTL`
  operation that holds `pc` would put a microarchitectural timing concern
  into the instruction stream, where a program has no way to know ahead of
  time that a particular access will be slow. The correct shape, if a slow
  slave is ever introduced, is a transparent hardware freeze (hold `pc` and
  regfile-write-enable for a cycle) driven by a live bus signal — invisible
  to software, the same way real CPUs stall on a cache miss without a
  dedicated instruction. Not needed now, given the no-wait-state decision
  above; recorded here so the idea isn't reinvented incorrectly later.
- **`ack`, a single positive-confirmation bit, not a bare `error` flag.**
  "Address not valid" and "matched a slave that itself reports a fault" are
  treated identically by every consumer (both mean the access failed), so
  there's no reason to carry them as separate bits: `ack` is "address
  matched a known slave" AND "that slave reports no fault," collapsing both
  failure modes into one signal. An unmapped address then falls out as
  `ack = 0` without anything needing to actively assert a fault — the same
  problem real bus protocols solve this way (Wishbone's `ACK_I`, classic
  VMEbus `DTACK*`). Feeds `flow_ctl`'s aggregated `error_i` as `enable &&
  !ack` — gated by `enable`, since an idle cycle with no transaction isn't a
  failed one — alongside the ALU's `bus.error` and reserved-opcode
  detection (`isa.md`), the same future exception/trap-handling path
  (`CLAUDE.md`'s roadmap) those already feed. Despite the name matching
  protocols where `ACK` implies variable-latency handshaking, this `ack`
  stays purely combinational, resolved the same cycle as `addr`/`enable` —
  it does not reopen the no-wait-state decision above. Whether any v1 slave
  (BRAM/UART/GPIO) has an independent fault condition to report at all, or
  `ack` collapses to pure address-decode for now, isn't decided yet —
  depends on how the D-bus's address decoder is designed.
- **The D-bus interconnect translates addresses, not just decodes them.**
  Forwarding the raw global address to every slave unchanged would mean
  each peripheral has to know its own base address internally to make
  sense of it — baking a specific memory-map placement into the
  peripheral's own RTL and breaking the relocatable, reusable-across-
  machine-generations peripheral model `CLAUDE.md`'s FuseSoC VLNV
  shared-library scheme depends on. Translating to a local, base-relative
  address at the interconnect keeps every peripheral itself
  base-address-agnostic.
- **No generic bus-slave wrapper module for v1.** A wrapper that adapts
  `bus_if` into some simpler peripheral-facing shape earns its keep by
  hiding complexity a peripheral shouldn't have to deal with —
  handshaking, variable latency, multi-phase addressing. `bus_if` doesn't
  have any of that (see Protocol's no-wait-state decision), so adding a
  translation layer over something already this thin would be exactly the
  premature abstraction `CLAUDE.md` warns against. Becomes relevant later
  specifically if a second, structurally different bus segment appears
  (`CLAUDE.md`'s "Bus hierarchy" future direction — high-throughput vs.
  peripheral segments joined by a bridge), not before.
- **Future multi-master: per-slave arbitration, not a global arbiter.**
  Recorded here so the direction is on record even though nothing needs it
  yet: `CLAUDE.md`'s bus-hierarchy future direction (DMA, separate
  high-throughput/peripheral segments) should look like AXI's crossbar
  model — each master gets an independent path to each slave, and an
  arbiter sits only at a slave two masters could actually collide on — not
  AHB's single shared bus with one central grant. `bus_if`, reused at every
  port, is what makes adding that later composable rather than a redesign.

## Deferred / future ideas (explicitly out of scope for v1)

- **Wait-states / bus stalling** for a slave that can't always respond
  same-cycle (e.g. a future real DDR controller, per `CLAUDE.md`'s
  documented hard-IP DDR exception for the eventual hardware phase) — needs
  the stall/enable network named above, which doesn't exist yet.
- **Multi-master arbitration** (DMA, additional bus masters) — see Design
  rationale's crossbar note above; no arbiter exists or is needed at v1's
  single-master-per-bus scale.
- **Bus hierarchy** (separate high-throughput vs. peripheral segments
  joined by a bridge, per `CLAUDE.md`'s roadmap) — today's D-bus
  interconnect is a single flat decoder across all slaves; segmenting it is
  future work once slave count/traffic patterns justify it.

## External dependencies (not part of this document)

- The D-bus interconnect's concrete memory map — actual base/size for each
  slave (BRAM/UART/GPIO), and therefore its real slave count — still needs
  its own design pass; Module boundaries above settles the module's job,
  not its parameters.
- BRAM's dual-port design — one `bus_if` slave port per bus (I and D),
  combinational read per the no-wait-state decision above.
- Aggregating this protocol's `ack` (as `enable && !ack`) alongside the
  ALU's `bus.error` and reserved-opcode detection into `flow_ctl`'s single
  `error_i` line — still control-unit territory, per `flow_ctl.md`'s own
  External dependencies.
