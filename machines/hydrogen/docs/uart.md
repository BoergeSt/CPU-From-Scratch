# Hydrogen UART — v1 Specification

Machine generation: **hydrogen** (H, atomic number 1 — first machine
generation, per the codename convention in `CLAUDE.md`).

Status: **designed, not yet implemented** — register map and behavioral
contract settled in design discussion; no RTL (`uart.sv`) exists yet.

## Overview

Hydrogen's virtual UART (`CLAUDE.md`'s Phase 1 "it's alive" milestone) — a
memory-mapped, D-bus-only peripheral (never instruction-fetched from, per
`bus.md`'s I-bus topology) providing asynchronous serial TX/RX with a
software-programmable baud rate. A live PTY-bridged terminal connection is a
documented future stretch goal (`CLAUDE.md`); this module's job is the
register/protocol contract, independent of whatever eventually drives its
physical pins in simulation or hardware.

**Placed under `machines/hydrogen/` for now**, not a shared/cross-machine
peripheral location — see Design rationale.

## Interface

### Ports

| Port | Dir | Width | Description |
|------|-----|-------|--------------|
| `clk_i` | in | 1 | Clock |
| `rst_i` | in | 1 | Synchronous, active-high reset — detail below |
| `bus` | — | — | `bus_if.slave` (`bus.md`); this module's only bus port. Unlike `bram` (which has both `bus_I`/`bus_D`, per `bus.md`'s topology), every other D-bus-only slave has nothing to disambiguate from, so no `_D` suffix |
| `rx_i` | in | 1 | Raw asynchronous incoming serial line |
| `tx_o` | out | 1 | Outgoing serial line, idles high |

`rx_i`/`tx_o` weren't pinned down in earlier discussion beyond "the module
needs a portmap" — added here since a UART can't function without them;
naming follows the project's existing `_i`/`_o` convention.

**`rst_i` behavior**: zeroes `control`, `settings`, and `errors`, and resets
both FIFOs to empty. "Resets to empty" means the read/write pointer or
occupancy counter (depending on implementation) returns to its empty value
— the FIFO storage arrays themselves are **not** cleared, same reasoning as
`bram.md`'s no-reset-on-storage decision: a stale byte sitting in an
unaddressed FIFO slot is harmless, since nothing can read it before it's
overwritten by the next write, so there's no reason to pay reset fan-out
across the 128-entry arrays. The small control/status registers still get a
real reset — that cost is negligible, and a known power-up state (in
particular `enable = 0`, so the device can't transmit before software
configures it) is worth having.

Distinct from `control.reset` (see Register map) — that is a
software-triggered soft reset limited to the same internal datapath state
(FIFO pointers/counts, bit-timing counters, error latches); only `rst_i`
also touches `control`/`settings`/`errors`.

### Local address decode

This module only examines `addr[2:0]`. The base address placing it
somewhere in Hydrogen's memory map, and translating the global address down
to this local one, is the D-bus interconnect's job (`bus.md`'s Design
rationale), not this module's.

## Register map

| Local addr | Name | Access | Description |
|---|---|---|---|
| `0x0` | `control` | RW | Enable, soft reset — detail below |
| `0x1` | `settings` | RW | Parity, stop bits, divisor — detail below |
| `0x2` | `errors` | RW (W1C) | Sticky error flags — detail below |
| `0x3` | `data` | RW | TX FIFO push / RX FIFO pop — detail below |
| `0x4` | `tx_fill` | RO | TX FIFO occupancy, `0`–`128` |
| `0x5` | `rx_fill` | RO | RX FIFO occupancy, `0`–`128` |
| `0x6`–`0x7` | — | — | Reserved (bus error) |

### `control` (`0x0`)

| Bit | Name | Description |
|---|---|---|
| `0` | `enable` | `1` = UART active, `0` = disabled. Gates `settings` writes and all TX/RX activity — see Behavior. A write attempting to set this bit `1` while `settings.divisor == 0` is ignored (bit stays `0`) — see Design rationale |
| `1` | `reset` | Write `1` to clear internal state; self-clears next cycle |
| `31:2` | — | Reserved, RAZ/WI |

`reset` resets FIFO occupancy (pointers/counts) to empty, plus bit-timing
counters and error latches, only — it never touches `settings`, and (like
`rst_i`) doesn't clear the FIFO storage arrays themselves.

### `settings` (`0x1`)

| Bits | Name | Description |
|---|---|---|
| `0` | `parity_type` | `0` = even, `1` = odd. Ignored when `parity_en = 0` |
| `1` | `parity_en` | `1` = parity enabled, `0` = disabled (no parity bit) |
| `2` | `stop_bits` | `0` = 1 stop bit, `1` = 2 stop bits |
| `14:3` | `divisor` | 12-bit raw cycle count per 16x-oversample tick; `0` is invalid — see `control.enable` |
| `31:15` | — | Reserved, RAZ/WI |

`parity_type`/`parity_en` are two independent flags, not a 3-value
enum with a reserved code — every one of the 4 possible bit patterns is a
well-defined configuration (`parity_en = 0` means "no parity" regardless of
`parity_type`), so there's no invalid encoding to define behavior for
(see Design rationale).

`divisor = clk_freq / (baud * 16)`, computed by software for the actual
input clock — the hardware has no notion of clock frequency or baud rate as
such, only this count (see Design rationale). Writes to this register while
`control.enable = 1` are silently ignored, no error flag.

### `errors` (`0x2`, write-1-to-clear)

| Bit | Name | Set when |
|---|---|---|
| `0` | `tx_overflow` | `data` write while the TX FIFO was already full (write dropped) |
| `1` | `rx_overflow` | A received byte arrived while the RX FIFO was full (byte dropped) |
| `2` | `framing_err` | An expected stop bit sampled low instead of high |
| `3` | `parity_err` | Received parity bit didn't match the computed parity |
| `31:4` | — | Reserved, RAZ/WI |

A bit clears only when explicitly written `1`; writing `0` to a bit is a
no-op, and reading never clears anything. `parity_err` is only meaningful
when `settings.parity_en = 1`. A frame that triggers either `framing_err`
or `parity_err` is dropped — not pushed onto the RX FIFO — same
ignore-new-on-fault treatment as `rx_overflow`, just with a different
trigger condition.

### `data` (`0x3`)

- **Write**: low 8 bits pushed onto the TX FIFO, bits `31:8` ignored. FIFO
  full → write dropped, `errors.tx_overflow` set, no bus error.
- **Read**: pops the oldest RX byte into bits `7:0`, bits `31:8` always `0`.
  FIFO empty → returns `32'h0000_0000`, no error flag — software must check
  `rx_fill != 0` before trusting the value (see Design rationale).

### `tx_fill` / `rx_fill` (`0x4`/`0x5`)

8-bit occupancy count, `0` (empty) to `128` (full); bits `31:8` always `0`.

## Behavior

- **`control.enable` gates all TX/RX activity, not just `settings` writes.**
  While `enable = 0`: the `data` FIFOs still accept pushes/pops normally (so
  software can preload TX bytes before enabling), but the TX state machine
  never drains the TX FIFO onto `tx_o` (stays idle-high), and the RX
  synchronizer/start-bit detector ignores `rx_i` entirely — no partial frame
  is ever in flight when `enable` transitions in either direction.
- **Fixed, non-configurable**: 8 data bits, 16x RX oversampling, 128-entry
  FIFO depth (TX and RX). See Design rationale.
- **RX synchronization + glitch rejection**: `rx_i` is asynchronous to
  `clk_i` and is synchronized internally (2-FF synchronizer) before any
  start-bit logic sees it — this module never assumes its input arrives
  already clock-synchronous. On a falling edge of the synchronized line
  (candidate start bit), the receiver waits 8 oversample ticks (half of 16)
  to reach the bit center and re-checks the line is still low before
  committing; if not, it abandons and resumes looking for an edge. Every
  later bit in the frame is then sampled once per 16 ticks from that
  established center — always mid-bit.
- **FIFO-full policy: ignore-new, consistently for TX and RX.** Neither
  direction overwrites already-buffered data.
- **`settings` writes while enabled, and `data` reads while RX-empty, are
  documented usage contracts, not error conditions** — see Design
  rationale for why neither raises a flag.

## Design rationale

- **Raw cycle-count divisor register (16550-style), not a fixed
  clock/baud lookup table.** The register just counts input-clock cycles;
  software computes the right value for whatever clock this instance is
  actually driven by. A precalculated table would bake in specific clock
  assumptions — exactly what a configurable divisor is meant to avoid.
- **Fixed 16x oversampling, not a runtime-configurable oversample field.**
  Rounding `clk/(baud*oversample)` to an integer doesn't get monotonically
  more or less accurate as oversample changes — the achievable error
  depends on how close that specific ratio happens to land to an integer,
  which varies unpredictably per (clock, baud) pair (worked through
  concretely in design discussion for 100 MHz/115200 baud). Since the
  divisor register already gives full clock-cycle precision on its own,
  oversample count isn't the axis that buys accuracy — it's fixed at a
  conventional value, keeping the mid-bit-alignment logic a synthesis-time
  constant rather than something that has to scale with a config register.
- **Fixed 8 data bits, no configurable 5–8-bit field.** 5–7-bit modes are a
  holdover from pre-ASCII teletype-era serial use; essentially no real
  UART traffic uses them today, so a config field for that range wouldn't
  be exercised.
- **`parity_en`/`parity_type` as two independent flags, not a 3-value
  enum with a reserved 4th code.** An enum shape (`none`/`odd`/`even` in 3 of
  4 possible 2-bit values) leaves `2'b11` needing a defined behavior even
  though it's a software mistake — the same category of question as the
  rejected "misuse" error bits, but here avoidable outright rather than
  needing an answer: splitting the field into enable + type means every one
  of the 4 bit patterns is already a well-defined configuration (both
  `2'b00` and `2'b01` simply mean "disabled"), so there's no reserved
  encoding left to define behavior for.
- **Reset (`rst_i` and `control.reset` alike) clears FIFO pointers/counts,
  not the underlying storage array.** Same reasoning as `bram.md`'s
  no-reset-on-storage decision: an unread FIFO slot's stale byte is
  harmless, since nothing can observe it before it's overwritten by the
  next write, so only the small pointer/count state that governs what's
  currently visible needs to return to a known value — not the 128-entry
  array itself.
- **`control`/`settings` split into separate registers.** Keeps
  enabling/disabling and the internal-state reset from ever perturbing
  configuration, and lets `settings` specifically be gated on `enable`
  without special-casing the enable bit inside its own gate.
- **`settings` writes while enabled are silently ignored, not
  bus-errored.** Changing baud/parity/stop-bits mid-frame would corrupt
  whatever's in flight; rejecting the write while enabled prevents that by
  construction instead of leaving it as a documented gotcha for software to
  avoid on its own.
- **`divisor == 0` is rejected by gating `control.enable`'s write, not flagged as a
  runtime error.** Unlike a plain misuse case, an unhandled `divisor == 0`
  isn't just "software did something pointless" — it makes the oversample-tick
  generator's behavior implementation-dependent (whether the comparator is
  `counter == divisor` or `counter == divisor - 1`, a 12-bit `-1` wraps to
  `0xFFF`, etc.), the same category of ambiguity the `parity_en`/
  `parity_type` split avoids elsewhere in this doc. Rather than pick one
  RTL interpretation and call the other wrong, `0` is defined as never
  reachable while enabled: a write attempting `enable: 0→1` while
  `settings.divisor == 0` is silently ignored, same shape as the existing
  settings-write-while-enabled precedent below. Only the `0→1` transition is
  gated — writing `enable = 0` always succeeds unconditionally, so software
  can never get stuck unable to disable the device. Because `settings` writes
  while `enable == 1` are already ignored, `divisor` can't become `0` after a
  valid enable either — so gating only at enable-write-time is sufficient to
  guarantee `settings.divisor != 0` holds for the entire time `enable == 1`,
  and the TX/RX bit-timing datapath can rely on that invariant unconditionally
  rather than carrying its own redundant runtime check.
- **No dedicated "software misused the interface" error bits** — considered
  and rejected for settings-write-while-enabled, data-read-while-empty, and
  reserved-bit writes. All three only occur if software already deviated
  from the documented contract, unlike `tx_overflow`/`rx_overflow`/
  `framing_err`/`parity_err`, which are triggered by conditions outside
  software's control (a slow consumer, a noisy line, a misconfigured peer).
  Bugs in this project's own firmware are expected to surface via the
  cocotb test suite and waveform inspection during development, not via a
  runtime flag meant for diagnosing an already-deployed system blind.
  Reserved bits specifically follow RAZ/WI (read-as-zero, write-ignored):
  there's no flip-flop behind them, so there's nothing to flag.
- **`errors` uses write-1-to-clear, not clear-on-read.** Clear-on-read
  (what real UARTs like the 16550's LSR traditionally do) is unsafe once
  several sticky flags share one register that might get read for reasons
  unrelated to any specific flag — a read could silently clear a pending
  flag the caller never inspected. W1C avoids this: reads are always
  side-effect-free, and a write only clears bits it explicitly sets to `1`;
  writing `0` to an untouched bit is a no-op, so there's no race between a
  newly-arriving error and software clearing bits it never looked at.
- **`framing_err` and `parity_err` kept as separate bits**, rather than one
  combined "erroneous transmission" flag. Distinguishing which occurred is
  real, cheap diagnostic value: a framing error points at a likely
  baud-rate/noise problem, a parity error at data corruption or a
  parity-mode mismatch with the far end — different next debugging step.
- **A framing/parity-error frame is dropped, not delivered.** Pushing a
  known-corrupt byte onto the RX FIFO anyway (flag-and-deliver, the choice
  some real UARTs make) would force every reader of `data` to also check
  `errors` to know whether the byte it just popped was trustworthy —
  reintroducing per-access ambiguity `errors`' W1C design already avoids
  elsewhere. Dropping keeps `errors` as the sole place a fault is visible
  and `data` free of corrupt bytes, at the cost of the corrupt byte itself
  being unrecoverable — acceptable, since a framing/parity error means the
  bits themselves are already suspect.
- **Ignore-new (not overwrite-oldest) on FIFO-full, both directions.** For
  TX this is the only sensible choice — never silently corrupt an
  already-queued-but-unsent byte. RX mirrors it for consistency, and
  because overwriting the oldest unread RX byte would silently drop data
  the consumer hasn't seen yet; `rx_overflow` exists precisely to surface
  "software isn't draining fast enough" rather than have hardware paper
  over it by discarding old, possibly-still-needed data.
- **`data` read-while-empty returns `0`, not a bus error or a sentinel.**
  `0x00` is also a legitimate received byte, so the value alone is
  ambiguous by design — software is expected to check `rx_fill != 0` before
  trusting a read, the same contract real FIFO-backed UARTs rely on.
- **Placed under `machines/hydrogen/`, not a shared/cross-machine
  peripheral location.** `CLAUDE.md`'s versioning scheme intends
  peripherals to eventually be referenced (not duplicated) across machine
  generations, but that needs a settled generic bus interface, and
  `bus_if` (`bus.md`) is currently Hydrogen-specific with no cross-machine
  abstraction defined yet. Living here for now avoids inventing that
  abstraction prematurely; relocating later should be a move, not a
  redesign, since nothing in this module depends on anything
  Hydrogen-specific beyond `bus_if` itself.

## Deferred / future ideas (explicitly out of scope for v1)

- **Majority-vote RX sampling** — sampling 3 consecutive oversample ticks
  near bit-center and taking a 2-of-3 vote, instead of the single mid-bit
  sample under Behavior, was discussed as a cheap extra-robustness option
  but not committed to for v1.
- **Break condition detection** — not requested; can be added later.
- **Interrupt line** — `errors`/`tx_fill`/`rx_fill` are polled-only in v1;
  no interrupt controller exists in Hydrogen yet (`CLAUDE.md`'s roadmap
  lists HW interrupts as a future direction), so there's nothing to wire an
  interrupt output to yet.
- **Configurable FIFO depth / oversample / data length** — all fixed at
  v1's chosen values (128 entries, 16x, 8 bits) rather than module
  parameters; revisit only if a concrete need for a different value arises.
- **Fractional/NCO-style divisor generator** — discussed as an alternative
  to plain integer-divisor rounding for clock/baud combinations with poor
  rounding error; no concrete target needs it yet, so not designed.

## External dependencies (not part of this document)

- The D-bus interconnect's assignment of this peripheral's base address
  within Hydrogen's memory map (`bus.md`) — not decided yet.
- Internal TX/RX bit-level state machine design (shift registers, bit
  counters, exact start/data/parity/stop sequencing) — this document
  specifies the register-level contract and required behavior, not the
  internal implementation, per `CLAUDE.md`'s "operational standpoint by
  default" documentation convention.
