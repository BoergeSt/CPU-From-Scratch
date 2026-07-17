# CPU-from-scratch (32-bit)

A from-scratch 32-bit CPU/system project — custom ISA, custom bus, no vendor
IP. See [`CLAUDE.md`](CLAUDE.md) for the full design rationale, roadmap, and
repo conventions.

## Required tools

- **[Podman](https://podman.io/)** — runs the pinned toolchain container
  (Verilator, Yosys, SymbiYosys, Verible, FuseSoC/Edalize, cocotb). Nothing
  in the batch/CLI flow is installed on the host directly.
- **[just](https://github.com/casey/just)** — thin command runner wrapping
  the container/FuseSoC invocations (`just check`, `just waves`,
  `just toolchain-build`, ...). Run `just --list` for all recipes.

## Optional tools

- **[Surfer](https://surfer-project.org/)** — waveform viewer for the
  `.fst` traces produced by `just waves <core>`. Not published on
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
just check :hydrogen:alu  # lint + simulate a core
just waves :hydrogen:alu  # simulate with FST tracing, then open the dump in Surfer/GTKWave
```
