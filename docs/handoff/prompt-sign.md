# Package: signing, made real — from "wired" to "verifiably signed"

You are a release engineer who has shipped signed desktop applications on macOS
and Windows and knows that the failure mode is a build that *claims* to be
signed and is not.

## The project

`gatepack` compiles a truth table or FSM specification into a bill of materials
and a schematic netlist built from discrete 74AUP logic packages, formally
verifying the result on every build. GPL-3.0-or-later, one tree, core and app
versioned together at 0.1.0.

## Where signing stands

`.github/workflows/release.yml` builds a tag-triggered matrix (Linux, macOS,
Windows), `app/electron-builder.yml` carries the signing configuration, and the
whole thing is driven by repository secrets: `CSC_LINK`, `CSC_KEY_PASSWORD`,
`APPLE_ID`, `APPLE_APP_SPECIFIC_PASSWORD`, `APPLE_TEAM_ID`. Absent those, the
build succeeds unsigned and says so.

That is the scaffolding. The maintainer now wants signing **incorporated** —
which means everything that can be true before a credential exists must be true,
and the moment credentials are supplied the result must be *verified* signed
rather than assumed.

## The rule that governs this package

**No signing material may be fabricated.** No self-signed certificate presented
as a real one, no placeholder Team ID, no identity invented to make a build
pass. A self-signed certificate generated *for testing* is acceptable only if it
is unmistakably labelled as such, never produced by a release build, and never
capable of being mistaken for a real signature. If in doubt, do not create it.

## What to build

### 1. Verification, not assumption

The most important part. After signing, the workflow must **verify the artefact
is actually signed** and fail the release if it is not:

- macOS: `codesign --verify --deep --strict --verbose=2`, then
  `spctl --assess --type execute` for the Gatekeeper verdict, and
  `xcrun stapler validate` for the notarisation ticket.
- Windows: verify the Authenticode signature and that it chains to a trusted
  root — `signtool verify /pa /v` where available.
- Linux: no OS signing, but the artefacts must be covered by `SHA256SUMS`, and
  a detached GPG signature over that file is worth supporting if a
  `GPG_PRIVATE_KEY` secret is present.

A signed build that is not verified is the same class of defect this project has
spent its history eliminating: a status reported by something that did not
measure it.

### 2. The unsigned path must stay honest and obvious

With no secrets set, the workflow must still complete and must mark the output
unmistakably: in the job summary, in the release notes, and in a file shipped
beside the artefacts. A user must learn a build is unsigned from the project,
not from their operating system's warning dialog.

Make the two paths **structurally distinct** rather than differing by a quiet
conditional — someone reading the workflow should be able to tell at a glance
which one ran, and the artefact names or the release body should make it
evident.

### 3. Local signing, for a maintainer with credentials on their own machine

Not everyone releases from CI. Provide a documented, scripted local path that
reads credentials from the environment (never from a file in the repo, and
never printed to a log), runs the same verification as CI, and refuses to
produce a "signed" artefact it cannot verify.

### 4. Document what the maintainer must obtain

`docs/RELEASING.md` must tell someone with no prior context exactly what to get
and how:

- Apple: Developer Program membership, a **Developer ID Application**
  certificate (not Mac App Store), exporting it as a `.p12`, base64-encoding it
  for `CSC_LINK`, creating an app-specific password, and finding the Team ID.
- Windows: an Authenticode code-signing certificate, the OV/EV distinction and
  what EV requires (hardware token, which does not work in CI — say so plainly
  rather than letting someone discover it after buying one).
- Which secret name carries which value, and how to set them.
- What a maintainer should check to confirm a release really is signed.

Be concrete and correct. If you are unsure whether a detail still holds — Apple
changes this often — say so in the document rather than stating it confidently.

### 5. Prove the machinery works without credentials

You have no credentials, so you cannot produce a real signed build. You *can*
prove the logic:

- a test that the verification step **fails** when handed an unsigned artefact
  (this is the one that matters — build the unsigned artefact and confirm the
  check rejects it);
- a test that the unsigned path produces its markers;
- a workflow lint so the YAML cannot silently break.

Report honestly which parts remain unexercisable until a credential exists.

## Files you own

`.github/workflows/release.yml` and any new workflow, `app/electron-builder.yml`,
`app/signing/**`, `scripts/` files relating to signing/checksums/SBOM,
`docs/RELEASING.md`, and new tests under `tests/`.

## Off-limits — another agent is in this repo right now

`libraries/**`, `examples/**`, `gatepack/parts.py`, `gatepack/build.py`,
`app/tests/e2e/**` — the showcase agent.

Also: `docs/MILESTONE-AUDIT.md`, `gatepack-design.md` — inputs. Note the repo
URL is now `https://github.com/CallumNunesVaz/gatepack` and `appId` is
`io.github.callumnunesvaz.gatepack`; the deb `maintainer` field is still a
marked placeholder because publishing a personal address is the maintainer's
call — leave it as a TODO, do not invent one.
