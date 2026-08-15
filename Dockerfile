# gatepack toolchain — reproducible build container (§5.2, §17)
#
# Pinned on purpose: the design requires byte-identical output for a given
# commit + container, so there must be no `latest` tags and no unpinned pulls
# in the reproducibility path.  Reproducibility is §5.2 / §14 R7.

# Base image: Debian bookworm.  The tag is pinned; for full reproducibility the
# image digest should be pinned at M0 once this build is validated (this
# Dockerfile has NOT been built in the current environment).
FROM debian:bookworm-slim

# ---------------------------------------------------------------------------
# Tool versions.  ALL of these tags are PLACEHOLDERS to be confirmed during
# M0 (the toolchain spike, §20).  They are plausible but have not been
# exercised here.
# ---------------------------------------------------------------------------
ARG YOSYS_VERSION=yosys-0.40
ARG SBY_VERSION=v0.44
ARG ESPRESSO_VERSION=v2.4

# Build + runtime dependencies.
#  - iverilog (Icarus Verilog) is installed from the Debian archive; its
#    version is pinned transitively by the base-image tag above.  Confirm the
#    exact iverilog version at M0.
#  - z3 is the SMT solver used by sby (SymbiYosys) for formal verification
#    (M5/M6).  Confirm the exact solver + version at M0.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential clang bison flex libreadline-dev gawk tcl-dev \
        libffi-dev git mercurial make pkg-config zlib1g-dev \
        python3 python3-pip iverilog z3 \
    && rm -rf /var/lib/apt/lists/*

# Yosys.  abc is bundled with Yosys as a git submodule (§4: "ABC ... via
# Yosys"), so abc is pinned by the Yosys checkout's submodule commit rather
# than separately.  Pinning a release tag + `--depth 1` is a compromise; pin a
# full commit SHA at M0 for strongest reproducibility.
RUN git clone --depth 1 --branch "${YOSYS_VERSION}" \
        https://github.com/YosysHQ/yosys.git /opt/yosys \
 && cd /opt/yosys \
 && git submodule update --init --recursive \
 && make config-clang \
 && make -j"$(nproc)" \
 && make install

# SymbiYosys (sby) — formal properties + equivalence fallback (§11, §C4).
# `make install` places the sby driver + yosys-smtbmc; the z3 solver is
# provided above.  Confirm the exact install target at M0.
RUN git clone --depth 1 --branch "${SBY_VERSION}" \
        https://github.com/YosysHQ/sby.git /opt/sby \
 && cd /opt/sby \
 && make install

# Espresso (maintained fork) — two-level logic minimiser, needed for the async
# backend (v0.2) and M-cell cover work.  The fork URL, tag and build
# invocation are placeholders; confirm all three at M0.
RUN git clone --depth 1 --branch "${ESPRESSO_VERSION}" \
        https://github.com/classabbyamp/espresso.git /opt/espresso \
 && cd /opt/espresso \
 && make \
 && make install

WORKDIR /work
