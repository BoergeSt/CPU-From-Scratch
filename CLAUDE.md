# Project: CPU-from-scratch (32-bit)

## Overview

Successor to an earlier from-scratch 8-bit CPU project (Basys3 FPGA, SystemVerilog,
Vivado). This iteration targets a 32-bit architecture with a full system
around the core: memory-mapped bus, bridges, interrupt controller, DMA. Goal is
deep understanding of CPU/system architecture — not speed of delivery.

**Hard constraint: everything is built from scratch. No vendor IP blocks, no
third-party CPU/bus/peripheral cores dropped in as black boxes.** Reference
designs (e.g. LiteX's Wishbone interconnect) may be *studied* for patterns but
not integrated wholesale.

## Roadmap / learning goals

Step-by-step, not a fixed spec — each phase should meaningfully challenge
understanding, not just add features for their own sake.

**Phase 1 (current target): minimal functional system.** Single-cycle core
(ALU + custom ISA subset) + custom bus + BRAM main memory + a virtual UART +
virtual GPIO, exercised end-to-end by a hand-assembled test program in
cocotb. First "it's alive" milestone: get a program running that does
something observable through the virtual UART (see the cocotb/Verilator
simulation-speed discussion — a PTY-bridged UART for live interactive
terminal access is a nice stretch goal once the model exists, not required
for the milestone itself).

**Future directions — unordered, aspirational, not all guaranteed to
happen:**
- HW interrupts
- Exception/trap handling (illegal opcode, div-by-zero, misaligned access,
  etc.) — distinct from HW interrupts; needs a control-unit trap path +
  handler dispatch that doesn't exist yet. First concrete trigger: the
  Hydrogen ALU's reserved opcodes (0xC–0xF) currently fall through to the
  `default:` case and silently return zero, with no diagnostic at all —
  no real illegal-instruction exception exists yet.
- Multi-level execution / privilege levels (ARM-style EL0/EL1/...,
  secure/non-secure worlds) — ties into exception/trap handling above,
  since real architectures typically raise privilege on a trap (e.g. a
  syscall exception). Related to the Secure-boot-style PoC item below but
  distinct: this is about runtime privilege separation, not boot-time
  attestation.
- Clock domain crossing / multi-clock design (already an explicit learning
  goal, see the "Single clock domain to start" decision below)
- DMA
- Caches
- Multi-cycle/pipelined ALU & CPU
- Multi-core
- HW accelerators (e.g. simple graphics or crypto — exact target open)
- Bus hierarchy: separate high-throughput vs peripheral bus segments joined
  by a bridge (the "bridges" already named in the Overview's system scope)
- Secure-boot-style PoC (mechanism/concept only, no real security guarantee)
- Checksums/ECC
- Very far ahead: simple branch prediction

**Software/toolchain ambition — beyond last time's basic assembler:**
Assembler (again, presumably more capable) → simple compiler for a small
language targeting the custom ISA → debugger → LLVM backend for the custom
ISA as the furthest-out reach goal. Note: an LLVM backend is not a lighter
alternative to writing a from-scratch compiler — LLVM's target-description
and instruction-selection machinery has real depth of its own — it buys the
rest of LLVM's frontend/optimizer ecosystem for free once built, at a real
up-front cost.

### Versioning & naming (provisional — revisit as real generations emerge)

Nothing to version yet until Phase 1 produces a first working generation —
treat this as a lean, not a finalized rule, same spirit as the still-open
Amaranth/debug-strategy items.

- **Peripherals version via FuseSoC's own VLNV model**, not a bespoke
  scheme. A breaking change bumps the version (e.g. `uart:1.0.0` →
  `uart:2.0.0`); old and new coexist as distinct dependency targets so
  different machine generations can depend on different peripheral
  versions; non-breaking changes stay in-place (no new version). This keeps
  the "every commit passes all tests" rule bounded — most changes create no
  new permanently-tested line, only real breaking forks do. File layout
  mirrors it: `fpga/rtl/peripherals/<name>/v1/`, `v2/`, ...
- **Machine generations (core + wired-in peripherals + bus, as one
  top-level FuseSoC core) get a codename, not a sequential number.** The
  roadmap's "future directions" are explicitly unordered and not
  all guaranteed to happen — numbering would imply a false strict
  succession. Codename theme: **chemical elements**, in atomic-number order
  as a loose reference ordering only, not a version chain. Layout:
  `fpga/rtl/machines/<codename>/{alu.sv, regfile.sv, control.sv, ...}` plus
  a `<codename>.core` wiring in pinned peripheral versions from the shared
  library.

## Decided

- **Simulation-only for now.** Real FPGA hardware bring-up (Basys3 or a future
  board) is a deferred future phase, not a current goal. Don't optimize for
  synthesis/timing yet, but keep RTL synthesizable-style (no sim-only
  constructs that would need a rewrite later).
- **Fully open source toolchain.** No Vivado, no proprietary sim. See Tooling
  below.
- **Primary HDL: SystemVerilog.** Existing skill from the 8-bit project.
- **Simulator: Verilator**, primary and default.
- **Verification: cocotb** (Python-based testbenches) as the main verification
  layer, driving Verilator. Small directed SV testbenches only for quick
  smoke checks during RTL development.
- **Waveforms:** GTKWave (mature default), evaluating Surfer (newer, FST-native,
  faster) alongside it.
- **Linting:** Verible for SV lint/format.
- **Formal verification:** SymbiYosys + Yosys (open SAT backends) for
  properties on the bus fabric specifically (arbiter mutual exclusion,
  address decoder completeness) — directed sim won't catch rare interleaving
  bugs there.
- **Build/dependency management:** FuseSoC + Edalize, so the same core
  descriptions can later retarget from Verilator to a real toolchain (Vivado,
  or F4PGA/openXC7 for a fully open Xilinx flow) without rewrites.
- **Coverage:** Verilator line/toggle coverage (`--coverage`); cocotb-coverage
  for functional coverage once past initial bring-up.
- **ISA: custom, not RISC-V — for now.** Chosen deliberately over RISC-V:
  RISC-V's toolchain/spec maturity is attractive but also means most of the
  hard problems (ISA design, encoding trade-offs, toolchain bring-up) are
  already solved for you. Going custom means encountering those problems
  directly, which is the point of this project, and keeps the initial scope
  smaller than adopting a full mature ISA spec. May be revisited later —
  don't treat this as permanently closed.
- **Bus/interconnect: fully custom protocol, not Wishbone/AXI.** Same
  reasoning as the ISA choice — designing the bus/handshake from scratch
  (rather than implementing an existing spec) is more consistent with the
  project's from-scratch goal and keeps early scope small. Revisit if the
  custom bus becomes a bottleneck to the rest of the system.
- **I/O addressing: memory-mapped, not port-mapped.** The 8-bit project used
  port-mapped I/O (separate address space for peripherals, dedicated
  in/out-style instructions) — simpler at the time but restrictive in
  practice. This iteration goes memory-mapped: peripherals live in the same
  address space as memory, addressed by the same load/store instructions, no
  dedicated I/O instructions needed. Matches the bus/bridges/interrupt
  controller/DMA system scope already stated in the Overview.
- **Main memory: BRAM-as-main-memory to start.** A real DDR controller from
  scratch is a large side-project on its own; BRAM keeps the initial memory
  system simple. A documented hard-IP DDR exception can be added later if/when
  targeting real hardware.
- **Modularity: every component should be reusable and self-contained.**
  RTL modules (bus components, peripherals, etc.) should be parametrized and
  avoid hard-coding system-specific assumptions where reasonably avoidable,
  so pieces can be reused across designs or swapped out later rather than
  rewritten. Apply the same principle on the software side (toolchain,
  scripts) where it doesn't cost significant extra complexity.
- **Global build orchestration: `just` (Justfile), not Make or CMake.**
  FuseSoC/Edalize already own the fine-grained HDL build/dependency graph,
  and cocotb owns test execution — the top level only needs a thin, readable
  command runner wrapping those (`just build alu`, `just test bus-arbiter`,
  `just lint`, `just ci`), not a second incremental-build system. Make's
  value proposition (file-timestamp-based incremental rebuilds) is unused
  here, so its syntax cost — `.PHONY` boilerplate, and especially the
  literal-tab-vs-spaces requirement for recipe lines, a classic silent
  failure mode that gets riskier the more a tool (rather than a careful
  human) is making incremental edits to the file over time — buys nothing.
  CMake is the wrong paradigm entirely unless the custom-ISA toolchain ends
  up being a multi-file C/C++ codebase, in which case it could double up as
  that toolchain's own build system.
- **Toolchain reproducibility: Docker container, built from YosysHQ's OSS
  CAD Suite tarball.** Verilator/Yosys/SymbiYosys are version-sensitive and
  distro packages are usually stale, so pin them via a container — same
  pattern as `kas-container` for Yocto: identical results regardless of
  host. The container is scoped to the batch/CLI toolchain only (Verilator,
  Yosys, SymbiYosys, Verible, FuseSoC/Edalize, cocotb); it writes waveform
  files (`.fst`/`.vcd`) to a mounted volume as output. GTKWave/Surfer stay
  native on the host and just open those files — no GUI/X11 passthrough
  needed, since waveform viewing is a separate step outside the container.
  Use OSS CAD Suite as the base layer (prebuilt, versions tested together)
  rather than building each tool from source in the Dockerfile. CI should
  use the same image as local dev, for the same reason kas-container does.
- **Single clock domain to start.** Multi-clock-domain design and clock
  domain crossing (synchronizers, gray-code FIFOs, metastability) is an
  explicit *future learning goal*, not just a deferred nice-to-have — when
  that phase starts, treat it like RTL authorship generally: work through
  the CDC concepts hands-on rather than being handed a working design.
- **Reset convention: synchronous, active-high (`rst`).** Synchronous reset
  is sampled only on the clock edge, so it can't itself cause a timing
  violation. Asynchronous reset's release is an async event relative to the
  clock and needs its own release synchronizer to avoid metastability on
  release — effectively a miniature CDC circuit, which is premature given
  CDC is an explicitly deferred future learning goal (see above), not
  something to half-do now. Active-high avoids double-negative logic
  (`if (rst)` vs `if (!rst_n)`); active-low's traditional safety argument is
  about external async hardware reset lines specifically, which doesn't
  apply to an internally-driven synchronous reset. Note for the eventual
  hardware phase (not relevant now, sim-only): consider avoiding resets on
  registers entirely where FPGA config-time initial values suffice, since
  resets can block some efficient hardware inference (e.g. SRL packing).
- **Bus/module ports: SV interfaces + modports, not flat ports.** The custom
  bus (and module ports generally) are defined as an `interface` with
  `master`/`slave` modports rather than each signal listed individually in
  every module and wired by hand at every instantiation — this is exactly
  the pain point that motivated moving from Verilog to SystemVerilog in the
  first place. Verilator has broad interface/modport support as of 5.x; the
  only real limitation (modports can't sit at hierarchical-block boundaries
  under Verilator's "hierarchical Verilation" compile-speed feature) doesn't
  apply at this project's scale.
- **Naming convention: lowRISC Verilog Coding Style Guide, adapted for
  active-high reset.** Adopting an existing, publicly documented convention
  (used in real open-source silicon, e.g. OpenTitan/Ibex) rather than
  inventing one from scratch. Key points: port suffixes `_i`/`_o`/`_io`
  (input/output/inout); active-low signals get an `_n` immediately before
  the direction suffix (e.g. `cs_ni`), no extra underscore; clock port
  declared first in the port list, reset(s) immediately after; parameters in
  PascalCase (e.g. `parameter int unsigned Width = 8`). The one deliberate
  deviation from lowRISC's own default: since this project uses active-high
  reset (see above), the reset port is `rst_i`, not lowRISC's `rst_ni` — the
  `_n` infix convention still applies to any other active-low signal
  introduced later.
- **Word size: fixed 32-bit, not parametrized.** Considered parametrizing
  (XLEN-style) for future 64-bit or a smaller/FPGA-friendlier width, but
  hardware cost of a wider datapath scales roughly linearly with bit width
  (not exponentially like representable value range does), so a real
  from-scratch 32-bit core is very unlikely to be the thing that doesn't fit
  on real hardware (e.g. PicoRV32, a comparable real 32-bit RISC-V core,
  runs in ~1000-3000 LUTs — well inside a Basys3-class FPGA's budget).
  Combined with "simulation-only for now, don't optimize for
  synthesis/timing yet," resource fit is something to measure empirically
  during the (already deferred) hardware bring-up phase, not design around
  now. Individual components may still be parametrized piece by piece later
  if desired — this isn't a ban on parameters generally, just a decision not
  to build the whole datapath generically around word size up front.
- **ALU: purely combinational for Phase 1 — no `clock_i`/`reset_i`/enable.**
  Matches the single-cycle core model: the ALU is stateless combinational
  logic (op/operands in, result/flags out, same cycle); only the register
  file/PC get clocked, capturing the ALU's output at the end of the cycle.
  A registered/pipelined ALU (e.g. multi-cycle multiply/divide, pipeline
  stages) is a deliberate future revision, not an oversight — see
  "Multi-cycle/pipelined ALU & CPU" under Future directions above.

## Open / undecided — ask before assuming

These have been discussed but **not decided**. Don't assume an answer; flag
the decision point if it becomes relevant.

- **Amaranth (Python HDL) for the bus fabric.** Discussed as a good fit for
  parametrized, structural-generation-heavy modules (crossbar, arbiter,
  address decoder) where SV `generate` gets unwieldy — while keeping the CPU
  core itself in SV. This would be a targeted, mixed-language experiment via
  FuseSoC, not a language switch for the whole project. Less obviously
  applicable now that the bus is a custom protocol rather than an existing
  spec, but still worth considering once the fabric gets structurally
  complex. Not decided whether to actually do this.
- **Debug strategy on real hardware** (future phase): with a custom ISA, the
  RISC-V debug spec / OpenOCD path is off the table, so this now means
  designing a custom debug protocol (e.g. simple UART monitor/bootloader) from
  scratch too. Not designed yet — deferred along with the rest of the
  hardware bring-up phase.

## Repo conventions

```
fpga/                 all RTL/verification side
  rtl/                  SystemVerilog sources, one module per file
  rtl/machines/<codename>/<module>.core   per-module FuseSoC core file, alongside
                          its RTL -- FuseSoC deprecates fileset files living
                          outside the directory containing the .core file
  rtl/machines/<codename>/tb/  cocotb Python testbenches for that machine's
                          modules, same reasoning -- nested with the RTL +
                          .core file rather than a flat top-level tb/
  tb/formal/             SVA properties + sby configs (bus fabric, arbiters
                          first) -- cross-module, so stays top-level
  sim/                   Verilator waivers only (per-module .core files live
                          alongside their RTL, see above)
software/              everything that runs ON the CPU, or builds things that do
  examples/              sample/test/diagnostic programs (ISA-agnostic placeholder
                          until the ISA decision below is made)
  toolchain/             assembler/compiler — only populated if a custom ISA is
                          chosen; if RISC-V is chosen this stays mostly empty and
                          software/ is just examples/ + linker scripts, since the
                          GCC/LLVM toolchain is used as-is
scripts/               repo-wide helper scripts (lint runners, coverage report
                        generation, setup) — kept flat for now, split out a
                        fpga/scripts/ later only if this gets crowded
docs/                  design notes / per-module & per-program docs, written
                        proactively by Claude as modules/programs are completed
                        (see Working style notes)
.github/workflows/     CI: verible lint -> verilator build+test -> sby formal
```

- Don't commit tool-generated binary project state (this matters more once a
  Vivado/F4PGA target exists — Tcl/script-generated project, not checked-in
  `.xpr`).
- Occasionally run RTL through Yosys `read_verilog`/elaboration even without a
  real synth target, to catch synthesizability issues Verilator's
  simulation-oriented lint misses.

## Commit conventions

**Wait for an explicit signal before committing.** Do the work, leave it
staged/unstaged in the working tree, and wait — the repo owner will say when
to commit. This supersedes Claude Code's general default of committing
proactively as part of normal work: fixing a bad commit (rewriting history,
untangling an amend) is friction the repo owner would rather avoid, so
committing itself is treated as a deliberate, reviewed step, not an
automatic one. Applies to local commits; pushing to a remote was already a
separate, more-impactful action requiring its own ask every time, per normal
practice.

- **Style: Conventional Commits** — `type(scope): summary`, blank line, then
  a body explaining what changed and why. Types: `feat`, `fix`, `chore`,
  `docs`, `test`, `refactor`, `perf`, `build`, `ci`. Imperative mood subject,
  no trailing period, keep the summary line short.
- **Scope: module-level by default, area-level as fallback.** Use the
  specific module/component name when a change is localized (`feat(alu)`,
  `fix(bus-arbiter)`); fall back to a top-level area (`fpga`, `software`,
  `docs`, `scripts`, `repo`, `ci`) only when the change is genuinely
  cross-cutting and doesn't belong to one module.
- **Trailers, based on who wrote the diff content:**
  - `--signoff` (adds `Signed-off-by: <your git identity>`) on commits
    containing content you wrote.
  - `Assisted-By: Claude <...>` trailer on commits containing content Claude
    wrote.
  - Since Claude commits under your local git identity, `--signoff` always
    stamps your name regardless — it's the trailer's *presence*, not a
    different name, that signals authorship here.
- **Split commits along the authorship boundary.** Don't combine your
  hand-written code with Claude-written content (tests, docs) into one
  commit just because they're part of the same logical change — commit them
  separately (e.g. your ALU RTL as one commit, Claude's cocotb tests for it
  as the next commit), even if that means several commits landing
  back-to-back for one feature. Every commit gets exactly one trailer type,
  never both.
- **Commits must be atomic.** Each commit does exactly one logical thing —
  don't bundle unrelated changes even if they happened in the same session.
  Split further than the authorship boundary above if a single
  author-consistent change still contains more than one logical change.
- **Every commit must build and pass all tests that exist at that point in
  history.** Run the relevant build (Verilator/FuseSoC) and test suite
  (cocotb, formal where applicable) before finalizing each commit, not just
  once at the end of a series — this keeps the history bisectable. A commit
  introducing RTL without its tests yet (per the authorship split above)
  must still compile and pass the existing test suite; it just isn't
  expected to be covered by tests that don't exist until the following
  commit.

## Working style notes

- I (the repo owner) have a strong embedded Linux / BSP background (NXP
  i.MX, U-Boot, Yocto, device trees) but this is a from-scratch digital
  design learning project — treat HDL/verification questions on their own
  terms, not through an embedded-Linux-application lens.
- Prior FPGA project experience: 8-bit CPU on Basys3 (Artix-7) in
  SystemVerilog/Vivado.
- **It's been a few years since the 8-bit project — design decisions won't
  always arrive fully-formed.** During ISA/architecture design discussions
  especially, offer concrete examples or a short menu of options rather than
  open-ended questions where reasonable; expect iteration rather than
  instant decisiveness, and don't read hesitation as lack of interest.
- **RTL authorship: I write the SystemVerilog myself.** The learning is in
  writing rtl/, not in receiving it — Claude's role there is to review,
  explain, catch bugs, and discuss alternatives, not to generate the HDL.
  Don't write or rewrite rtl/ files directly unless I explicitly ask for an
  exception (e.g. pure boilerplate). Exception: low-level, mechanical fixes
  — naming-convention violations, formatting, other style-guide compliance
  issues — can be applied directly without asking first, since there's no
  design learning lost in fixing those. Anything touching actual logic/
  design still goes through me.
- **Advice and suggestions are welcome at any point, unprompted.** Don't
  hold back observations, alternatives, or concerns until asked — flag them
  as they come up during review/discussion, same spirit as the proactive
  documentation rule above.
- **Test authorship: cocotb tests (tb/) may be written by Claude, but only
  for cases I specify.** I direct what scenarios/edge cases/coverage matter;
  Claude implements the cocotb Python for exactly those. Don't proactively
  invent additional test cases or coverage beyond what was asked without
  flagging them first — propose, don't just add.
- **Working order: I define module boundaries → Claude writes tests against
  that interface → I implement the RTL to pass them.** Once a module's
  ports/interface and the scenarios that matter are settled, Claude writes
  the cocotb tests targeting that (not-yet-implemented) interface, and I
  write the RTL against those tests, iterating locally until they pass. This
  *authoring* order is independent of the *commit* order in Commit
  conventions below (RTL commit, then a following tests commit, split along
  the authorship boundary) — tests can exist and be iterated against well
  before the commit that introduces them.
- **Documentation authorship: Claude writes documentation, proactively,
  both inline and standalone.** This is a deliberate override of Claude
  Code's normal default of writing minimal/no comments. Once a module
  (rtl/), program (software/), or design element is functionally complete,
  write: header comments/docstrings for it (purpose, port/parameter
  descriptions, usage) in the source file itself, and a standalone doc under
  docs/ covering design intent/rationale — without waiting to be asked each
  time. I'll review and edit afterward; that's expected, not a signal to stop
  doing this proactively.
