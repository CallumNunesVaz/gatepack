# gatepack toolchain — reproducible build container (§5.2, §17)
#
# Pinned on purpose: the design requires byte-identical output for a given
# commit + container, so there must be no `latest` tags and no unpinned pulls
# in the reproducibility path.  Reproducibility is §5.2 / §14 R7.

# ---------------------------------------------------------------------------
# Reproducibility pins.  These are now RESOLVED values, each looked up from the
# upstream registry or repository rather than guessed.
#
# What is verified and what is not, stated plainly:
#   - every pin below was resolved against the real registry/remote;
#   - this image has NOT been built end to end, so the build recipe itself
#     (source builds of Yosys and espresso) is unproven;
#   - every measured finding in docs/M0-FINDINGS.md and docs/M6-FINDINGS.md was
#     taken in the image built by `Dockerfile.probe`, which installs Debian's
#     PACKAGED Yosys rather than building it here.  The two are different
#     toolchains and must not be conflated: do not attribute a measurement made
#     in one to the other until this image is built and re-measured.
# ---------------------------------------------------------------------------

# Base image.  The *tag* alone (bookworm-slim) is a floating reference; §5.5 /
# R7 require the immutable digest.  Resolved 2026-08-16 with
# `docker inspect --format '{{index .RepoDigests 0}}' debian:bookworm-slim`.
ARG BASE_DIGEST=sha256:abd67ffcfa541b485a3dff59865ab629aa048a6c613e639d36e7456b0b229241

FROM debian:bookworm-slim@${BASE_DIGEST}

# Tool checkouts, pinned by full commit SHA (not movable tags/branches),
# resolved with `git ls-remote` against each upstream.  abc is a Yosys
# submodule, so it is pinned by the Yosys commit's submodule pointer rather
# than a separate ARG.
# `yosys-0.23`, the version every measurement in docs/M0-FINDINGS.md and
# docs/M6-FINDINGS.md was taken against.
ARG YOSYS_COMMIT=3546d8bfafc4891d1041c58dc439b01a6c14bca8
# The espresso fork URL previously recorded here (classabbyamp/espresso)
# does not exist - it 404s. The maintained fork is chipsalliance/espresso,
# pinned below, and the clone URL further down was corrected to match.
ARG ESPRESSO_COMMIT=0288253ca9459539d341bb1ada10406a74efc721

# sby is no longer a placeholder: measured at M6 (docs/M6-FINDINGS.md §5).
# It is pinned by bare commit rather than tag because the oldest tagged sby
# release is `yosys-0.26` and the pinned Yosys is older than that, so no tag
# matches. The current release v0.68 is measured NOT to work here — it emits
# `formalff -hierarchy`, an option that postdates the pinned Yosys.
# If YOSYS_COMMIT is ever moved forward, this pin must be re-measured, not
# assumed to still hold.
ARG SBY_COMMIT=beb8b3c6e38ee716cd9771eb906c37684e83eab4

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
# backend (v0.2) and M-cell cover work.  URL and commit are resolved; the build
# invocation (`make && make install`) is still unconfirmed because this image
# has not been built.
RUN git clone https://github.com/chipsalliance/espresso.git /opt/espresso \
 && cd /opt/espresso \
 && git checkout "${ESPRESSO_COMMIT}" \
 && make \
 && make install

WORKDIR /work
