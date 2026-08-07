# Build/refresh the pinned OSS CAD Suite + FuseSoC toolchain container.
# See CLAUDE.md's "Toolchain reproducibility" decision for what's in scope.
toolchain-build:
    podman build -t fpga-toolchain:dev -f scripts/fpga-toolchain.Dockerfile scripts/

# Assemble a Hydrogen source file into a raw binary image (assembler.md),
# e.g. `just assemble machines/hydrogen/software/examples/factorial.S`.
# Output is the input path with its extension replaced by .bin. Runs on
# the host (gcc + python3), not the container -- the assembler is a plain
# host-side tool, not part of the Verilator/Yosys toolchain.
assemble file:
    #!/usr/bin/env sh
    set -eu
    out="{{without_extension(file)}}.bin"
    gcc -E -P -x c "{{file}}" | python3 machines/hydrogen/software/toolchain/assemble.py - -o "$out"
    echo "assembled: $out"

# Run a FuseSoC target against a core -- internal helper, use `lint`/`sim` below.
# Two --cores-root flags (machines/, common/): FuseSoC's --cores-root is an
# append-action option, so each root needs its own flag, not a
# space-separated list -- confirmed against fusesoc/main.py in the pinned
# image. common/ holds shared, non-machine-specific components (e.g.
# common/fifo/, see CLAUDE.md's Repo conventions) that a machine core may
# come to depend on, so it must be on the cores-root list whenever any core
# is resolved, not just :common:* cores themselves.
_fusesoc target core:
    podman run --rm --userns=keep-id -e HOME=/tmp -v "{{justfile_directory()}}":/work:Z -w /work fpga-toolchain:dev \
        fusesoc --cores-root machines --cores-root common run --target={{target}} "{{core}}"

# Lint a core, e.g. `just lint :hydrogen:alu`
lint core: (_fusesoc "lint" core)

# Sim a core (always traces -- see the cores' `sim` target), e.g.
# `just sim :hydrogen:alu`. Exits nonzero if any cocotb test failed --
# fusesoc/edalize's own exit code doesn't reflect that (confirmed: it
# returns 0 even with FAIL>0), only a genuine build/lint error does.
sim core:
    #!/usr/bin/env sh
    set -u
    output=$(just _fusesoc "sim" "{{core}}" 2>&1)
    status=$?
    printf '%s\n' "$output"
    [ "$status" -ne 0 ] && exit "$status"
    fail_count=$(printf '%s\n' "$output" | grep -oE 'FAIL=[0-9]+' | tail -1 | cut -d= -f2)
    [ -n "$fail_count" ] && [ "$fail_count" -ne 0 ] && exit 1
    exit 0

# Lint, sim, then elaborate a core in one step, e.g. `just check
# :hydrogen:alu`. Stops after lint if it fails, there's no point
# simulating broken RTL. Elaborate goes through Yosys/slang -- a
# different frontend/elaborator than Verilator's lint, so it's a real
# additional check, not a repeat of `lint`.
check core: (lint core) (sim core) (elaborate core)

# Sim a core with line/branch/toggle coverage instrumentation (the core's
# `coverage` target -- see e.g. regfile.core), then annotate the source
# with per-line hit counts, e.g. `just coverage :hydrogen:regfile`. Same
# FAIL>0 check as `sim`. Coverage is informative, not a pass/fail gate --
# uncovered lines/toggles are lines in `annotated/*.sv` marked `%00`, not
# necessarily a bug (e.g. untoggled register bits directed tests never
# happened to exercise).
coverage core:
    #!/usr/bin/env sh
    set -u
    output=$(just _fusesoc "coverage" "{{core}}" 2>&1)
    status=$?
    printf '%s\n' "$output"
    [ "$status" -ne 0 ] && exit "$status"
    fail_count=$(printf '%s\n' "$output" | grep -oE 'FAIL=[0-9]+' | tail -1 | cut -d= -f2)
    if [ -n "$fail_count" ] && [ "$fail_count" -ne 0 ]; then
        exit 1
    fi
    dir="build/{{ replace(trim_start_match(core, ":"), ":", "_") }}_0/coverage"
    podman run --rm --userns=keep-id -e HOME=/tmp -v "{{justfile_directory()}}":/work:Z -w /work/$dir fpga-toolchain:dev \
        verilator_coverage --annotate annotated coverage.dat

# Check every "checkable" core in one machine, e.g. `just check-machine
# hydrogen`. "Checkable" means the core's .core file defines a `lint`
# target -- skips dependency-only interface cores (e.g. alu_if), which have
# no lint/sim target to run. Every core still runs even if an earlier one
# fails, so the summary always covers all of them; full build/sim output
# only prints for a failing core, keeping a healthy run's output short.
# Exits nonzero if anything failed.
check-machine machine:
    #!/usr/bin/env sh
    set -u
    failed=0
    summary=$(mktemp)
    trap 'rm -f "$summary"' EXIT
    for core_file in machines/{{machine}}/rtl/*.core; do
        name=$(basename "$core_file" .core)
        grep -q '^  lint:' "$core_file" || continue
        printf 'checking :%s:%s ... ' "{{machine}}" "$name"
        output=$(just check ":{{machine}}:$name" 2>&1)
        status=$?
        result=$(printf '%s\n' "$output" | grep -oE 'TESTS=[0-9]+ PASS=[0-9]+ FAIL=[0-9]+ SKIP=[0-9]+' | tail -1)
        if [ "$status" -ne 0 ]; then
            failed=1
            status_word="FAILED"
            [ -z "$result" ] && result="LINT/BUILD FAILED"
            echo "FAILED"
            printf '%s\n' "$output"
        else
            status_word="ok"
            echo "ok"
        fi
        printf '%s\t%s\t%s\n' "$name" "$status_word" "$result" >> "$summary"
    done
    printf '\n=== check-%s summary ===\n' "{{machine}}"
    python3 scripts/format-check-summary.py < "$summary"
    exit $failed

# Check every core in the hydrogen machine.
check-hydrogen: (check-machine "hydrogen")

# Check every "checkable" core under common/ (shared, non-machine-specific
# components, e.g. common/fifo/ -- see CLAUDE.md's Repo conventions), e.g.
# `just check-common`. Same "checkable" discovery and quiet-unless-failing
# convention as check-machine, just rooted at common/*/rtl/ instead of one
# machines/<name>/rtl/, and with no per-directory wrapper recipe since
# common/ isn't split into named generations the way machines/ is.
check-common:
    #!/usr/bin/env sh
    set -u
    failed=0
    summary=$(mktemp)
    trap 'rm -f "$summary"' EXIT
    for core_file in common/*/rtl/*.core; do
        [ -e "$core_file" ] || continue
        name=$(basename "$core_file" .core)
        grep -q '^  lint:' "$core_file" || continue
        printf 'checking :common:%s ... ' "$name"
        output=$(just check ":common:$name" 2>&1)
        status=$?
        result=$(printf '%s\n' "$output" | grep -oE 'TESTS=[0-9]+ PASS=[0-9]+ FAIL=[0-9]+ SKIP=[0-9]+' | tail -1)
        if [ "$status" -ne 0 ]; then
            failed=1
            status_word="FAILED"
            [ -z "$result" ] && result="LINT/BUILD FAILED"
            echo "FAILED"
            printf '%s\n' "$output"
        else
            status_word="ok"
            echo "ok"
        fi
        printf '%s\t%s\t%s\n' "$name" "$status_word" "$result" >> "$summary"
    done
    printf '\n=== check-common summary ===\n'
    python3 scripts/format-check-summary.py < "$summary"
    exit $failed

# Check every core in every machine under machines/, plus every core under
# common/. Same as `check-hydrogen` today since hydrogen is the only
# machine that exists yet -- stays correct without edits once more machine
# codenames show up.
check-all:
    #!/usr/bin/env sh
    set -u
    failed=0
    for dir in machines/*/; do
        just check-machine "$(basename "$dir")" || failed=1
    done
    just check-common || failed=1
    exit $failed

# Run coverage for every "checkable" core in one machine, e.g.
# `just coverage-machine hydrogen`. "Checkable" means the core's .core file
# defines a `coverage` target -- same discovery pattern as check-machine.
# Same quiet-unless-failing convention as check-machine: full output only
# prints for a failing core, and a summary table lands at the end either way.
coverage-machine machine:
    #!/usr/bin/env sh
    set -u
    failed=0
    summary=$(mktemp)
    trap 'rm -f "$summary"' EXIT
    for core_file in machines/{{machine}}/rtl/*.core; do
        name=$(basename "$core_file" .core)
        grep -q '^  coverage:' "$core_file" || continue
        printf 'coverage :%s:%s ... ' "{{machine}}" "$name"
        output=$(just coverage ":{{machine}}:$name" 2>&1)
        status=$?
        if [ "$status" -ne 0 ]; then
            failed=1
            status_word="FAILED"
            echo "FAILED"
            printf '%s\n' "$output"
        else
            status_word="ok"
            echo "ok"
        fi
        printf '### %s\t%s\n%s\n' "$name" "$status_word" "$output" >> "$summary"
    done
    printf '\n=== coverage-%s summary ===\n' "{{machine}}"
    python3 scripts/format-coverage-summary.py < "$summary"
    exit $failed

# Coverage for every core in the hydrogen machine.
coverage-hydrogen: (coverage-machine "hydrogen")

# Coverage for every "coverable" core under common/, e.g.
# `just coverage-common`. Same discovery/summary pattern as
# coverage-machine, rooted at common/*/rtl/ -- see check-common's identical
# reasoning.
coverage-common:
    #!/usr/bin/env sh
    set -u
    failed=0
    summary=$(mktemp)
    trap 'rm -f "$summary"' EXIT
    for core_file in common/*/rtl/*.core; do
        [ -e "$core_file" ] || continue
        name=$(basename "$core_file" .core)
        grep -q '^  coverage:' "$core_file" || continue
        printf 'coverage :common:%s ... ' "$name"
        output=$(just coverage ":common:$name" 2>&1)
        status=$?
        if [ "$status" -ne 0 ]; then
            failed=1
            status_word="FAILED"
            echo "FAILED"
            printf '%s\n' "$output"
        else
            status_word="ok"
            echo "ok"
        fi
        printf '### %s\t%s\n%s\n' "$name" "$status_word" "$output" >> "$summary"
    done
    printf '\n=== coverage-common summary ===\n'
    python3 scripts/format-coverage-summary.py < "$summary"
    exit $failed

# Coverage for every core in every machine under machines/, plus every core
# under common/. Same "stays correct as machines are added" reasoning as
# check-all.
coverage-all:
    #!/usr/bin/env sh
    set -u
    failed=0
    for dir in machines/*/; do
        just coverage-machine "$(basename "$dir")" || failed=1
    done
    just coverage-common || failed=1
    exit $failed

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

# Run a Hydrogen program on the real core, e.g. `just run
# machines/hydrogen/software/examples/factorial.S`. Accepts either a .S
# source file (auto-assembled first via `just assemble`) or an already-
# assembled .bin -- run.py has no way to tell source from bytecode, so
# feeding it source directly loads the raw text as "instructions"
# (garbage). Cycle count via the optional second arg (default 1000).
# Always traces -- `just view-run` afterward, same "never forces a resim"
# reasoning as `view`. hydrogen.core's `run` target loads $HYDROGEN_PROGRAM
# into BRAM hierarchically (tb/run.py) rather than running the fixed
# directed suite.
run program cycles="1000":
    #!/usr/bin/env sh
    set -eu
    case "{{program}}" in
        *.S|*.s)
            bin="{{without_extension(program)}}.bin"
            just assemble "{{program}}"
            ;;
        *)
            bin="{{program}}"
            ;;
    esac
    podman run --rm --userns=keep-id -e HOME=/tmp \
        -e HYDROGEN_PROGRAM=/work/"$bin" -e HYDROGEN_CYCLES={{cycles}} \
        -v "{{justfile_directory()}}":/work:Z -w /work fpga-toolchain:dev \
        fusesoc --cores-root machines --cores-root common run --target=run :hydrogen:hydrogen

# Open the trace from the most recent `just run`.
view-run:
    #!/usr/bin/env sh
    set -eu
    dump="build/hydrogen_hydrogen_0/run/dump.fst"
    if ! command -v surfer >/dev/null 2>&1; then
        echo "surfer not found on PATH -- see README.md's Optional tools section to install it" >&2
        exit 1
    fi
    if [ ! -f "$dump" ]; then
        echo "no trace found at $dump -- run 'just run <program>' first" >&2
        exit 1
    fi
    surfer "$dump"

# Elaborate a core through Yosys (slang frontend) as a generic,
# technology-independent netlist -- no target device, just structure/
# synthesizability (generic cells). The core's `elaborate` target (e.g.
# regfile.core) points at a dedicated <module>_elab_top.sv with flat
# ports, not the cocotb tb_top -- opt's dead-code elimination needs real
# outputs to keep the design alive, and tb_top (driven/read hierarchically
# by cocotb) has none; confirmed empirically, not a hypothetical.
# `toplevel` is read back from FuseSoC's own resolved eda.yml rather than
# guessed from the core name, so it always matches whatever the .core file
# actually declares.
# Output: build/<core>_0/elaborate/netlist.svg (+ .dot) -- open directly
# (`just view-netlist <core>`), no special viewer needed.
elaborate core:
    #!/usr/bin/env sh
    set -eu
    just _fusesoc elaborate "{{core}}"
    name="{{ replace(trim_start_match(core, ":"), ":", "_") }}_0"
    dir="build/$name/elaborate"
    top=$(grep '^toplevel:' "$dir/$name.eda.yml" | awk '{print $2}')
    files=$(find "$dir/src" -name '*.sv' | sed 's|^|/work/|' | tr '\n' ' ')
    printf '%s\n' \
        "plugin -i slang" \
        "read_slang $files --top $top" \
        "proc" \
        "opt" \
        "stat" \
        "show -format svg -prefix /work/$dir/netlist" \
        > "$dir/elaborate.ys"
    podman run --rm --userns=keep-id -e HOME=/tmp -v "{{justfile_directory()}}":/work:Z -w /work fpga-toolchain:dev \
        yosys -s "/work/$dir/elaborate.ys"
    echo "netlist: $dir/netlist.svg"

# Open an already-elaborated netlist in the system's default SVG viewer,
# e.g. `just view-netlist :hydrogen:regfile`. Same "viewing never forces
# a rebuild" reasoning as `view` (waveforms) -- run `just elaborate`
# first (or again, if stale).
view-netlist core:
    #!/usr/bin/env sh
    set -eu
    svg="build/{{ replace(trim_start_match(core, ":"), ":", "_") }}_0/elaborate/netlist.svg"
    if [ ! -f "$svg" ]; then
        echo "no netlist found at $svg -- run 'just elaborate {{core}}' first" >&2
        exit 1
    fi
    xdg-open "$svg"

# Elaborate every "checkable" core in one machine, e.g. `just
# elaborate-machine hydrogen`. "Checkable" means the core's .core file
# defines an `elaborate` target -- same discovery pattern as
# check-machine. Every core still runs even if an earlier one fails, so
# the summary always covers all of them; full output only prints for a
# failing core, keeping a healthy run's output short. Exits nonzero if
# anything failed.
elaborate-machine machine:
    #!/usr/bin/env sh
    set -u
    failed=0
    for core_file in machines/{{machine}}/rtl/*.core; do
        name=$(basename "$core_file" .core)
        grep -q '^  elaborate:' "$core_file" || continue
        printf 'elaborating :%s:%s ... ' "{{machine}}" "$name"
        output=$(just elaborate ":{{machine}}:$name" 2>&1)
        status=$?
        if [ "$status" -ne 0 ]; then
            failed=1
            echo "FAILED"
            printf '%s\n' "$output"
        else
            echo "ok"
        fi
    done
    exit $failed

# Elaborate every core in the hydrogen machine.
elaborate-hydrogen: (elaborate-machine "hydrogen")

# Elaborate every "elaboratable" core under common/, e.g.
# `just elaborate-common`. Same discovery pattern as elaborate-machine,
# rooted at common/*/rtl/ -- see check-common's identical reasoning.
elaborate-common:
    #!/usr/bin/env sh
    set -u
    failed=0
    for core_file in common/*/rtl/*.core; do
        [ -e "$core_file" ] || continue
        name=$(basename "$core_file" .core)
        grep -q '^  elaborate:' "$core_file" || continue
        printf 'elaborating :common:%s ... ' "$name"
        output=$(just elaborate ":common:$name" 2>&1)
        status=$?
        if [ "$status" -ne 0 ]; then
            failed=1
            echo "FAILED"
            printf '%s\n' "$output"
        else
            echo "ok"
        fi
    done
    exit $failed

# Elaborate every core in every machine under machines/, plus every core
# under common/. Same "stays correct as machines are added" reasoning as
# check-all.
elaborate-all:
    #!/usr/bin/env sh
    set -u
    failed=0
    for dir in machines/*/; do
        just elaborate-machine "$(basename "$dir")" || failed=1
    done
    just elaborate-common || failed=1
    exit $failed

# List every FuseSoC core discoverable under machines/ or common/
core-list:
    podman run --rm --userns=keep-id -e HOME=/tmp -v "{{justfile_directory()}}":/work:Z -w /work fpga-toolchain:dev \
        fusesoc --cores-root machines --cores-root common core list
