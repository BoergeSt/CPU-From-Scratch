# CPU-from-scratch (32-bit)

A from-scratch 32-bit CPU/system project — custom ISA, custom bus, no vendor
IP. Built for fun, as a personal challenge to understand how a CPU and the
system around it actually work, from the gates up.

## Disclaimer

Provided as-is, with no warranty and no guarantee of correctness, safety, or
fitness for any purpose — see [`LICENSE`](LICENSE) for the full terms.

## What's in here

- **HDL** (`machines/*/rtl/`, `common/`) — a custom CPU and supporting bus/
  peripherals, written in SystemVerilog from scratch (no vendor IP blocks).
- **A custom assembler** (`machines/*/software/toolchain/`) targeting the
  CPU's own instruction set.
- **Machine code** (`machines/*/software/examples/`) — example/diagnostic
  programs written in that assembly, actually running on the simulated CPU.

## AI Policy

- **RTL and the machine-code example programs** — written entirely by hand,
  no AI-generated content. Same for the assembler's original design. This
  is where the actual learning and challenge is, so I'm not delegating it.
- **The assembler's later extensions, tests (`rtl/tb/`), and the build
  harness** (FuseSoC cores, `Justfile`) — done with AI assistance, but
  scoped to specific tasks/scenarios I define up front, not open-ended AI
  design.
- **Documentation** (`docs/`, inline comments) — written by AI, but the
  content is mine: sourced from bullet points I write and an interactive
  Q&A where I make every real design decision. AI's job is drafting and
  organizing, not deciding.

## License

[GPL-2.0-or-later](https://spdx.org/licenses/GPL-2.0-or-later.html) — see
[`LICENSE`](LICENSE).

## Required tools

- **[Podman](https://podman.io/)** — runs the pinned toolchain container
  (Verilator, Yosys, SymbiYosys, Verible, FuseSoC/Edalize, cocotb). Nothing
  in the batch/CLI flow is installed on the host directly.
- **[just](https://github.com/casey/just)** — thin command runner wrapping
  the container/FuseSoC invocations (`just check`, `just sim`,
  `just toolchain-build`, ...). Run `just --list` for all recipes.

## Optional tools

- **[Surfer](https://surfer-project.org/)** — waveform viewer for the
  `.fst` traces produced by `just sim <core>` (always traced, see the cores'
  `sim` target). Not published on
  crates.io under a usable name (`surfer` on crates.io is an unrelated
  crate) — install straight from the project's GitLab repo:

  ```sh
  cargo install --locked --git https://gitlab.com/surfer-project/surfer.git --tag v0.7.0 surfer
  ```

  On Fedora, Surfer needs OpenSSL dev headers to build:

  ```sh
  sudo dnf install openssl openssl-devel
  ```

  [GTKWave](https://gtkwave.sourceforge.net/) is a mature alternative for
  viewing the same `.fst` files.

## Quick start

```sh
just toolchain-build      # build the toolchain container (once, or after a version bump)
just core-list            # list available FuseSoC cores
just check :hydrogen:alu  # lint + simulate a core (always traces)
just coverage :hydrogen:alu  # simulate with line/branch/toggle coverage, annotate source
just view :hydrogen:alu   # open the last trace in Surfer
```

### Running a program on the simulated CPU

```sh
just run machines/hydrogen/software/examples/uart_hello_world.S      # assemble + run for a fixed cycle count
just run-interactive machines/hydrogen/software/examples/uart_echo.S # native PTY-bridged UART session
just view-run                                                        # open the trace from the most recent `just run`
```

`just run-interactive` opens a virtual COM port at `dev/uart0.pty` (a real PTY,
bridged to the simulated UART via a Unix socket). Connect to it from another
terminal with any serial console program, e.g.
[`tio`](https://github.com/tio/tio) or `screen`:

```sh
tio dev/uart0.pty
```
