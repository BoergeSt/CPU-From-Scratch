# FIFO — v1 Specification

Status: **implemented** — `common/fifo/rtl/fifo.sv`, verified by
`common/fifo/rtl/tb/test_fifo.py` (`just check :common:fifo`).

Shared, cross-machine component — not tied to any machine generation. First
component placed under `common/`, per `CLAUDE.md`'s shared/cross-machine
layout item; see Design rationale for why it lives here rather than under a
specific `machines/<codename>/`.

## Overview

A generic, parametrized, single-clock-domain synchronous FIFO — a plain
enqueue/dequeue queuing primitive, not a peripheral (no bus interface, no
memory-mapped registers). Intended to be instantiated wherever a machine
generation needs FIFO buffering, so that behavior only needs to be specified
and verified once.

The write side and read side are two separate interfaces
(`fifo_write_if`/`fifo_read_if`), not one bundle — see Design rationale.

## Interface

### Parameters

| Parameter | Default | Description |
|---|---|---|
| `DataWidth` | `32` | Width in bits of each stored element |
| `FillWidth` | `8` | Occupancy-count width; sets depth — see Design rationale |

Queue depth is always `2**(FillWidth-1)` — not an independently settable
parameter, see Design rationale.

### Clock and reset

`clk_i`/`rst_i` are plain module ports, not part of either interface below —
same convention as `regfile.md`. `rst_i` is synchronous, active-high — see
Behavior.

### Write interface (`fifo_write_if`)

| Field | Dir | Width | Description |
|---|---|---|---|
| `enable` | in | 1 | Write (enqueue) request |
| `data` | in | `DataWidth` | Value to enqueue when a write is accepted |
| `full` | out | 1 | `1` iff occupancy equals the queue depth |
| `overflow` | out | 1 | Set when a write is attempted while full — see Behavior |
| `fill` | out | `FillWidth` | Current occupancy, `0`–depth inclusive |

(Dir is from the `fifo` modport; the mirrored `requester` modport reverses
every direction.)

### Read interface (`fifo_read_if`)

| Field | Dir | Width | Description |
|---|---|---|---|
| `enable` | in | 1 | Read (dequeue) request |
| `data` | out | `DataWidth` | Dequeued value, valid only when a read is accepted |
| `empty` | out | 1 | `1` iff occupancy is `0` |
| `underflow` | out | 1 | Set when a read is attempted while empty — see Behavior |
| `fill` | out | `FillWidth` | Current occupancy — see below |

Same value as the write interface's `fill` (both driven by the same
internal count) — see Design rationale for why it's carried on both sides.

(Dir is from the `fifo` modport; the mirrored `requester` modport reverses
every direction.)

## Behavior

`write.full`/`read.empty`/`fill` reflect the queue's occupancy as of the
start of the current cycle. `write.enable` and `read.enable` are evaluated
against that same pre-cycle occupancy, independently of each other:

| Condition | Effect |
|---|---|
| `write.enable && !write.full` | write accepted, `fill+1` next cycle |
| `write.enable && write.full` | write dropped, `write.overflow` set, no state change |
| `read.enable && !read.empty` | read accepted, `read.data` valid, `fill-1` next cycle |
| `read.enable && read.empty` | `read.data = 0`, `read.underflow` set, no state change |
| `!read.enable` (any) | `read.data = 0` |

- **Ordering.** Values are dequeued in the same order they were enqueued.
- **No same-cycle write-to-read bypass.** A value enqueued this cycle is not
  visible on `read.data` until at least the next cycle — concretely, a
  simultaneous `write.enable && read.enable` on an empty queue enqueues the
  value but `read.enable` still sees pre-cycle `read.empty == 1` and
  underflows; the written value only becomes readable on a later
  `read.enable`.
- **`write.full && write.enable && read.enable`** is evaluated the same way:
  `read.enable` succeeds (dequeues the oldest value, freeing a slot), but
  `write.enable` still sees pre-cycle `write.full == 1` and overflows — the
  write is dropped even though a slot became free in the same cycle. Net
  `fill` change is `-1`. See Design rationale for the tradeoff this implies.
- **Reset.** While `rst_i` is high at a rising `clk_i` edge, `fill` returns
  to `0` (`read.empty = 1`, `write.full = 0`) and any previously enqueued
  value not yet read is discarded — it can no longer be dequeued, regardless
  of how it got there. Reset takes unconditional priority over a
  simultaneous `write.enable`/`read.enable` on the same edge — matches
  `regfile.md`'s identical rule.
- **`write.overflow`/`read.underflow` are combinational, not sticky and not
  edge-triggered.** Each tracks its triggering condition directly
  (`write.enable && write.full`, `read.enable && read.empty`) — set for as
  long as that condition holds, including across a clock edge if the
  triggering enable stays asserted, and clear the moment it stops holding.
  No latch, no clear/acknowledge mechanism, no pulse-shaping logic.

## Design rationale

- **Two interfaces (`fifo_write_if`/`fifo_read_if`), not one bundle.**
  Unlike `alu_if` (one interaction shape, one consumer), a FIFO's entire
  purpose is decoupling a producer from a consumer, so a write-only
  consumer shouldn't be handed read-capable signals it can never legally
  drive, and vice versa — the same reasoning `regfile.md` gives for its
  read/write interface split. `fill` is the one field genuinely relevant to
  both sides (e.g. watermark-based flow control), so it's carried by both
  interfaces rather than forcing one side to reach across to the other's
  instance for it; both are driven by the same internal count, so they can
  never disagree. Cost of the split: `DataWidth`/`FillWidth` now need to
  match across three declarations (the module and both interface
  instances) at every instantiation site, with nothing but Verilator's own
  width checking enforcing that agreement.
- **`FillWidth` is the public parameter; queue depth is derived, not an
  independent parameter.** An earlier version exposed a `Size` (depth)
  parameter directly, with `FillWidth` derived from it — this is the
  reverse. Two reasons: depth is required to be a power of two (see below),
  and making `FillWidth` (not depth) the parameter makes that a structural
  guarantee rather than a documented-but-unenforced constraint, since every
  legal `FillWidth` produces a power-of-two depth by construction. It also
  means the module and both interfaces take the *same* parameter with the
  same meaning, rather than the module's depth needing translation into the
  interfaces' `FillWidth` at every instantiation site.
- **No same-cycle write-to-read bypass (no "cut-through" path).** A bypass
  mux from `write.data` straight to `read.data` for the empty-write-then-read
  case would add real combinational complexity for a one-cycle latency win
  in a single corner case, which isn't performance-critical for this
  project's currently anticipated use (small, byte-scale peripheral
  buffering). Kept out for v1; see Deferred.
- **`write.full`/`write.enable`/`read.enable` interaction resolved by
  pre-cycle state, uniformly with the empty-side case.** The alternative —
  letting a simultaneous write succeed because a read is freeing a slot the
  same cycle — is the mirror image of the bypass case above and carries the
  same added-complexity cost, so it's rejected for the same reason.
  Accepted tradeoff: a producer topping off a full queue in the exact cycle
  a slot frees up sees a spurious `write.overflow` and must retry, rather
  than the write silently succeeding.
- **`full`/`empty` provided alongside `fill`, not derived by every caller.**
  `fill == depth` / `fill == 0` are cheap comparisons, but depth isn't
  independently visible outside the module (see above) — deriving them at
  every instantiation site would require every consumer to duplicate that
  comparison itself instead of it being computed once here.
- **`read.data = 0` whenever a read isn't accepted this cycle** (idle, or
  underflow), not just during underflow specifically. Otherwise `read.data`
  would show stale data left over from a previous read when `read.enable`
  is simply low, which is both non-deterministic-looking from outside the
  module and awkward to assert on in a testbench.
- **`write.overflow`/`read.underflow` as plain combinational flags, not
  sticky/latched.** Latching requires a clear/acknowledge mechanism, which
  is a policy decision that varies by consumer (e.g. a peripheral's status
  register might want write-1-to-clear sticky error bits) — building that
  in here would bake one specific consumer's needs into an otherwise
  generic component. A consumer that wants sticky behavior latches the
  combinational flag itself.
- **Queue depth must be a power of two.** Keeps wraparound arithmetic exact
  without extra range-check logic. Enforced structurally by `FillWidth`
  being the parameter (see above), rather than by convention.
- **Placed under `common/`, not a specific `machines/<codename>/`.** This is
  the first component with no dependency on any machine-specific state
  (ISA, bus protocol, address map) — unlike a bus-attached peripheral, which
  would need to stay under `machines/<codename>/` for as long as it depends
  on that machine's own bus interface, this module has no bus interface at
  all and is usable by any future machine generation unchanged.

## Deferred / future ideas (explicitly out of scope for v1)

- **Same-cycle write-to-read bypass / cut-through path** — rejected for v1
  simplicity (see Design rationale); revisit only if a concrete
  latency-sensitive consumer needs it.
- **Sticky/write-1-to-clear `write.overflow`/`read.underflow`** — left to
  whatever consumer needs it (e.g. a future peripheral status register),
  not built in here.
- **Non-power-of-two queue depth** — not supported; no concrete need yet.
- **First-word-fall-through (FWFT) read mode** — an alternative to the
  current "valid only the cycle `read.enable` is accepted" `read.data`
  semantics, where the head element is exposed continuously without
  needing `read.enable` to look ahead. Not requested.
