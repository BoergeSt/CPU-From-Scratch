# Toolchain container per CLAUDE.md: pinned OSS CAD Suite (Verilator, Yosys,
# SymbiYosys, cocotb, GTKWave, Surfer) + FuseSoC/Edalize on top. Scoped to the
# batch/CLI toolchain only -- GTKWave/Surfer stay native on the host for
# waveform viewing; this image just needs to produce the .fst/.vcd files.
FROM debian:bookworm-slim

ARG OSS_CAD_SUITE_TAG=2026-06-29
ARG OSS_CAD_SUITE_DATE=20260629

# fontconfig + fonts-dejavu-core: Yosys's `show` renders netlists via
# Graphviz+Pango, which needs a real font to compute text-extent metrics --
# without one, Pango can't describe a null font, floods stderr, and falls
# back to guesswork metrics (the render still completes either way).
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        ca-certificates \
        clang \
        curl \
        fontconfig \
        fonts-dejavu-core \
        liblz4-dev \
        make \
        perl \
        zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

RUN curl -fsSL -o /tmp/oss-cad-suite.tgz \
        "https://github.com/YosysHQ/oss-cad-suite-build/releases/download/${OSS_CAD_SUITE_TAG}/oss-cad-suite-linux-x64-${OSS_CAD_SUITE_DATE}.tgz" \
    && tar -xzf /tmp/oss-cad-suite.tgz -C /opt \
    && rm /tmp/oss-cad-suite.tgz

ENV PATH="/opt/oss-cad-suite/bin:/opt/oss-cad-suite/py3bin:${PATH}"

RUN pip3 install --no-cache-dir fusesoc edalize

COPY fpga-toolchain-entrypoint.sh /usr/local/bin/fpga-toolchain-entrypoint.sh
RUN chmod +x /usr/local/bin/fpga-toolchain-entrypoint.sh

WORKDIR /work
ENTRYPOINT ["/usr/local/bin/fpga-toolchain-entrypoint.sh"]
