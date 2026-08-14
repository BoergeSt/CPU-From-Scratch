# Hydrogen D-Bus Interconnect — v1 Specification

Machine generation: **hydrogen** (H, atomic number 1 — first machine
generation, per the codename convention in `CLAUDE.md`).

Status: **designed, not yet implemented** — module boundary, ports, and v1
address map settled in design discussion; no RTL (`d_bus_interconnect.sv`)
exists yet.

## Overview

The D-bus-specific interconnect named in `bus.md`'s Module boundaries
section — the one module, project-wide, that compares an address against a
range. Sits between `core_glue`'s `bus_D` master port and every real D-bus
slave (`bram`'s `bus_D` port, the virtual UART, future peripherals),
performing `bus.md`'s four jobs: decode, translate, enable-gate, and
response mux. The I-bus needs no equivalent module (`bus.md`'s direct
point-to-point `bus_if` into `bram`'s second port).

**Purely combinational — no `clk_i`/`rst_i`.** Decode/translate/gate/mux
carry no state of their own; same reasoning as `CLAUDE.md`'s ALU decision
("purely combinational... no `clock_i`/`reset_i`/enable" for logic with
nothing to register).

## Interface

### Ports

| Port | Modport | Connects to |
|---|---|---|
| `core_if` | `bus_if.slave` | `core_glue`'s `bus_D` (`bus_if.master`) |
| `bram_if` | `bus_if.master` | `bram`'s `bus_D` port (`bus_if.slave`) |
| `uart0_if` | `bus_if.master` | The virtual UART's `bus` port (`bus_if.slave`, `uart.md`) |

`uart0_if`, not `uart_if` — named for a specific instance slot, not the
peripheral type, since `bus.md`'s peripheral model expects more than one
same-VLNV instance to coexist on a bus eventually (e.g. a second UART).

### Address map (v1)

All addresses are **word addresses** (`isa.md`, `bus.md` — not repeated
here).

| Slave | Base | Size (decoded) | Range |
|---|---|---|---|
| `bram_if` (BRAM) | `0x00000` | `0x10000` (fixed) | `0x00000`–`0x0FFFF` |
| — reserved — | `0x10000` | `0x100` | `0x10000`–`0x100FF` |
| `uart0_if` (UART) | `0x10100` | `8` | `0x10100`–`0x10107` |

`bram_if`'s decoded range is a fixed `0x0000`–`0xFFFF` (`addr[31:16] == 0`),
independent of whatever `bram`'s own `Size` parameter is actually
instantiated with — every address in that window is forwarded to
`bram_if` with `enable = 1`, and `bram` itself is the one that returns
`ack = 0` for anything at or past its real `Size` (`bram.md`'s existing
range check). This module never needs to know `bram`'s `Size` at all, and
growing `bram` later (up to the full `0x10000`-word window) needs no
change here. `bram_if` sees the raw `addr` (its base is `0`); `uart0_if`
sees `addr[2:0]` as its local address. The remaining `0x100`-word gap
before `uart0_if` is headroom for future system-level registers; nothing
is decoded there in v1 — an access in that range behaves like any other
unmapped address: no slave enabled, `ack = 0`.

UART's 8-word block is this module's decode granularity, not a per-register
one — which of `uart.md`'s six registers (`0x10100`–`0x10105`) a given
access targets, and that `0x10106`/`0x10107` are reserved, is entirely
`uart.sv`'s own internal decode on the `addr[2:0]` it's handed (already
implemented, `default: bus.ack = 1'h0`). This module only needs to
recognize the full aligned block as belonging to `uart0_if`.

## Behavior

- **Decode**: compare `core_if.addr` against each slave's base/size (or,
  where a slave's block is power-of-2-sized and aligned, an address-bit
  match — same outcome, e.g. `uart0_if`'s `addr[31:3] == 'h10100 >> 3`).
- **Translate**: the matched slave sees a base-relative local address, not
  the raw global one — `bus.md`'s reasoning (peripherals stay
  base-address-agnostic, relocatable without touching their own RTL).
- **Enable-gate**: only the matched slave's `enable` is asserted that
  cycle; every other slave's `enable` is driven `0` regardless of its other
  input lines. `wdata`/`we`/the translated `addr` fan out to every slave
  unmuxed — harmless, since only the enabled one acts on them.
- **Response mux**: `core_if.rdata`/`core_if.ack` reflect whichever slave
  matched. An unmapped address enables no slave, so `ack = 0` and
  `rdata = 0` fall out without any explicit "invalid address" case.
- No wait states, no registered state anywhere in this module — every
  signal above is a same-cycle combinational function of `core_if.addr`,
  consistent with `bus.md`'s no-wait-state protocol.

## Design rationale

- **A dedicated module, not folded into `core_glue`.** `core_glue` is
  CPU-internal glue (ALU/flow_ctl/regfile wiring) with no notion of address
  ranges; `bus.md` restricts every address-range comparison project-wide to
  this one module, so it stays the sole place a new slave's placement is
  ever expressed.
- **Fixed named ports (`core_if`/`bram_if`/`uart0_if`), not a generic
  array of slave ports.** Matches today's fixed, small slave count (two).
  A generated, parametrized slave list (SV `generate` over an array of
  `{base, size}`) is the natural next step once the slave count grows
  enough to make three hand-written ports repetitive — the same
  structural-generation territory `CLAUDE.md`'s still-open Amaranth
  question is about. Not needed yet; revisit if/when a third or fourth
  peripheral lands.
- **`bram` and `uart` stay base-address-agnostic.** Neither slave module
  has (or needs) a `Base` parameter — only this module knows where each
  slave sits in the global map, per `bus.md`'s "translate, don't just
  decode" rationale. Relocating a slave later is a one-line change here,
  not an edit to the slave's own RTL.

## Deferred / future ideas (explicitly out of scope for v1)

- **Generic parametrized slave list** — see Design rationale above; revisit
  once port count stops being small and fixed.
- **Additional peripherals** (GPIO, a second UART instance, ...) — added
  incrementally to both the port list and the address map, one at a time,
  per this doc's original planned build order below.
- ~~**BRAM growth**~~ — already handled by construction: `bram_if`'s decoded
  window is fixed at the full `0x10000` words regardless of `bram`'s actual
  `Size`, so growing `bram` needs no change to this module.

## Planned build order

Historical context for why this module lands after BRAM and the control
unit rather than first — the earlier steps are already done.

| Step | Deliverable | Status |
|---|---|---|
| 1 | BRAM (main memory) | **done** |
| 2 | Control unit (`core_glue`) | **done** |
| 3 | This interconnect + `LOAD`/`STORE` logic | **done**, see note below |
| 4 | Peripherals (UART, GPIO, ...) | **in progress** — UART first |

Step 3 already happened in a simplified form: with only `bram` on the
D-bus, `core_glue.bus_D` was wired straight into `bram.bus_D` with no
decode step (base `0`, no other slave to distinguish from). This module is
that step made real now that a second slave exists.

## External dependencies (not part of this document)

- `hydrogen.sv`'s existing `sim/hydrogen_bus_d_unoptflat.vlt` Verilator
  waiver (a `bus_D` UNOPTFLAT false-positive from `core_glue`'s
  address-in/data-out `always_comb`) may need broadening once a second
  combinational hop (this module) sits between `core_glue` and `bram` on
  the same signal — not a design concern, just a lint step to expect.
