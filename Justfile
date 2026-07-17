# Build/refresh the pinned OSS CAD Suite + FuseSoC toolchain container.
# See CLAUDE.md's "Toolchain reproducibility" decision for what's in scope.
toolchain-build:
    podman build -t fpga-toolchain:dev -f scripts/fpga-toolchain.Dockerfile scripts/

# Run a FuseSoC target against a core -- internal helper, use `lint`/`sim` below.
_fusesoc target core:
    podman run --rm --userns=keep-id -e HOME=/tmp -v "{{justfile_directory()}}":/work:Z -w /work fpga-toolchain:dev \
        fusesoc --cores-root fpga/rtl/machines run --target={{target}} "{{core}}"

# Lint a core, e.g. `just lint :hydrogen:alu`
lint core: (_fusesoc "lint" core)

# Sim a core (always traces -- see the cores' `sim` target), e.g. `just sim :hydrogen:alu`
sim core: (_fusesoc "sim" core)

# Lint then sim a core in one step, e.g. `just check :hydrogen:alu`
# Stops after lint if it fails, there's no point simulating broken RTL.
check core: (lint core) (sim core)

# Open an already-built trace in Surfer, e.g. `just view :hydrogen:alu`.
# `sim` always traces (see the cores' `sim` target), so this just opens
# whatever's already at build/<core>_0/sim/dump.fst -- run `just sim` or
# `just check` first (or again, if the trace is stale). Deliberately does
# not re-run the sim itself, so viewing a trace never forces a resim, which
# matters once sims stop being sub-second.
view core:
    #!/usr/bin/env sh
    set -eu
    dump="build/{{ replace(trim_start_match(core, ":"), ":", "_") }}_0/sim/dump.fst"
    if ! command -v surfer >/dev/null 2>&1; then
        echo "surfer not found on PATH -- see README.md's Optional tools section to install it" >&2
        exit 1
    fi
    if [ ! -f "$dump" ]; then
        echo "no trace found at $dump -- run 'just sim {{core}}' first" >&2
        exit 1
    fi
    surfer "$dump"

# List every FuseSoC core discoverable under fpga/rtl/machines
core-list:
    podman run --rm --userns=keep-id -e HOME=/tmp -v "{{justfile_directory()}}":/work:Z -w /work fpga-toolchain:dev \
        fusesoc --cores-root fpga/rtl/machines core list
