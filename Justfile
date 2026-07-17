# Build/refresh the pinned OSS CAD Suite + FuseSoC toolchain container.
# See CLAUDE.md's "Toolchain reproducibility" decision for what's in scope.
toolchain-build:
    podman build -t fpga-toolchain:dev -f scripts/fpga-toolchain.Dockerfile scripts/

# Run a FuseSoC target against a core, e.g. `just fusesoc lint :hydrogen:alu:0`
fusesoc target core:
    podman run --rm --userns=keep-id -e HOME=/tmp -v "{{justfile_directory()}}":/work:Z -w /work fpga-toolchain:dev \
        fusesoc --cores-root fpga/rtl/machines run --target={{target}} "{{core}}"

# Lint then sim a core in one step, e.g. `just check :hydrogen:alu`
# Stops after lint if it fails, since there's no point simulating broken RTL.
check core: (fusesoc "lint" core) (fusesoc "sim" core)

# Sim a core with FST waveform tracing enabled, e.g. `just waves :hydrogen:alu`.
# Trace lands at build/<core>_0/sim-waves/dump.fst -- open with GTKWave/Surfer.
waves core: (fusesoc "sim-waves" core)

# Open an already-built trace in Surfer, e.g. `just view :hydrogen:alu`.
# Deliberately does not re-run the sim -- run `just waves` first (or again,
# if the trace is stale); kept separate so viewing a trace never forces a
# resim, which matters once sims stop being sub-second.
view core:
    #!/usr/bin/env sh
    set -eu
    dump="build/{{ replace(trim_start_match(core, ":"), ":", "_") }}_0/sim-waves/dump.fst"
    if ! command -v surfer >/dev/null 2>&1; then
        echo "surfer not found on PATH -- see README.md's Optional tools section to install it" >&2
        exit 1
    fi
    if [ ! -f "$dump" ]; then
        echo "no trace found at $dump -- run 'just waves {{core}}' first" >&2
        exit 1
    fi
    surfer "$dump"

# List every FuseSoC core discoverable under fpga/rtl/machines
core-list:
    podman run --rm --userns=keep-id -e HOME=/tmp -v "{{justfile_directory()}}":/work:Z -w /work fpga-toolchain:dev \
        fusesoc --cores-root fpga/rtl/machines core list
