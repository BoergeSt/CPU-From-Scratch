#!/usr/bin/env bash
# Computes GPI_USERS fresh from the pinned cocotb install at container start.
# Edalize's cocotb integration predates cocotb 2.0's GPI_USERS requirement
# (it only sets the now-ignored LIBPYTHON_LOC), so this papers over that
# upstream gap. Computed here rather than hardcoded so it can never go stale
# relative to whatever cocotb version is actually installed in this image.
set -euo pipefail

export GPI_USERS="$(cocotb-config --libpython);$(cocotb-config --pygpi-entry-point)"

exec "$@"
