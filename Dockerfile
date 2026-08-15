# gatepack toolchain — reproducible build container (§5.2, §17)
#
# Pinned on purpose: the design requires byte-identical output for a given
# commit + container, so there must be no `latest` tags and no unpinned pulls
# in the reproducibility path.  Reproducibility is §5.2 / §14 R7.

# ---------------------------------------------------------------------------
# Reproducibility pins.  ALL of the values below are TODO(M0) PLACEHOLDERS.
# They are deliberately invalid so that the build FAILS LOUDLY until the M0
# toolchain spike (§20) records the real values against the pinned toolchain.
# Nothing here was looked up from a registry; nothing here is presented as a
# verified digest or commit.  Do not build this image until M0 fills them in.
# ---------------------------------------------------------------------------

# Base image.  The *tag* alone (bookworm-slim) is a floating reference; §5.5 /
# R7 require the immutable digest.  TODO(M0): record
# `docker inspect --format '{{index .RepoDigests 0}}' debian:bookworm-slim`.
ARG BASE_DIGEST=sha256:TODO_M0_base_digest_placeholder

FROM debian:bookworm-slim@${BASE_DIGEST}

# Tool checkouts, pinned by full commit SHA (not movable tags/branches).
# TODO(M0): record `git rev-parse HEAD` on each checkout at the intended version.
# abc is a Yosys submodule, so it is pinned by the Yosys commit's submodule
# pointer, not a separate ARG.
ARG YOSYS_COMMIT=TODO_M0_yosys_commit_placeholder
ARG SBY_COMMIT=TODO_M0_sby_commit_placeholder
ARG ESPRESSO_COMMIT=TODO_M0_espresso_commit_placeholder

# Build + runtime dependencies.
#  - iverilog (Icarus Verilog) and z3 (the SMT solver sby uses for formal
#    verification, M5/M6) come from the Debian archive; their exact versions
#    are pinned transitively by the base-image digest above.  TODO(M0): record
#    `iverilog -V` / `z3 --version` from the built image.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential clang bison flex libreadline-dev gawk tcl-dev \
        libffi-dev git mercurial make pkg-config zlib1g-dev \
        python3 python3-pip iverilog z3 \
    && rm -rf /var/lib/apt/lists/*

# Yosys.  abc is bundled with Yosys as a git submodule (§4: "ABC ... via
# Yosys"), so abc is pinned by the Yosys checkout's submodule commit rather
# than separately.  The checkout is a full clone so the pinned commit SHA is
# always reachable, then `checkout` detaches HEAD at that exact commit.
RUN git clone https://github.com/YosysHQ/yosys.git /opt/yosys \
 && cd /opt/yosys \
 && git checkout "${YOSYS_COMMIT}" \
 && git submodule update --init --recursive \
 && make config-clang \
 && make -j"$(nproc)" \
 && make install

# SymbiYosys (sby) — formal properties + equivalence fallback (§11, §C4).
# `make install` places the sby driver + yosys-smtbmc; the z3 solver is
# provided above.  TODO(M0): confirm the exact install target.
RUN git clone https://github.com/YosysHQ/sby.git /opt/sby \
 && cd /opt/sby \
 && git checkout "${SBY_COMMIT}" \
 && make install

# Espresso (maintained fork) — two-level logic minimiser, needed for the async
# backend (v0.2) and M-cell cover work.  The fork URL and build invocation are
# placeholders; confirm all three at M0.
RUN git clone https://github.com/classabbyamp/espresso.git /opt/espresso \
 && cd /opt/espresso \
 && git checkout "${ESPRESSO_COMMIT}" \
 && make \
 && make install

WORKDIR /work
