# Package: the toolchain tests must not vandalise the checkout

You are a build engineer who has spent an afternoon working out why a local
command suddenly failed with EACCES, and does not intend anyone to spend
another one.

## The project

`gatepack` compiles a truth table or FSM specification into a bill of materials
and a schematic netlist built from discrete 74AUP logic packages, formally
verifying the result on every build. Its toolchain tests (`tests/toolchain/`)
run the real Yosys/ABC/sby stack inside the docker image
`gatepack-toolchain:m6`, mounting the repository into the container.

## The defect

They mount the repo and run **as root**:

```python
subprocess.run([
    "docker", "run", "--rm",
    "-v", f"{REPO}:/repo", "-w", "/repo", IMAGE,
    "python3", "-m", "gatepack", *argv,
])
```

Everything the container writes into the checkout — `build/`, `.gpout/`,
anything a test forgets to clean up — is owned by root. The developer's *next*
local run then fails:

```
error: [Errno 13] Permission denied: 'build/generated.v'
```

That is not hypothetical; it happened, and the working tree had to be cleaned
with a second root container before an ordinary `gatepack verify` would run.

The fix is one flag — `-u "$(id -u):$(id -g)"` — which the `start` script
already passes and these tests do not. `tests/toolchain/test_examples.py` was
fixed in passing; every other call site was not.

## What to do

### 1. One helper, not thirteen edits

There are roughly a dozen `docker run` call sites across `tests/toolchain/`,
several with their own subtly different argument order. Do not paste the flag
into each one. Add a small shared helper in `tests/toolchain/` — a module the
other test modules import — that builds the command, and route every call site
through it.

The helper should cover what the call sites actually need. Read them first:
some mount `{REPO}:/repo`, some mount a temp working directory, some run
`python3 -m gatepack`, some run `rm -rf`, some run a bare shell command. Design
for what is there rather than forcing every case into one shape, and leave the
odd one out alone if bending it would obscure what the test does.

Note that `os.getuid()`/`os.getgid()` do not exist on Windows. These tests
already require docker and skip without it, so decide what is honest — skipping,
or falling back — and say which you chose and why.

### 2. Do not change what any test asserts

This is a mechanical change to *how* a container is invoked. If a test's
assertions or expected values change, something has gone wrong. The one thing
that may legitimately need adjusting: a test that previously relied on root to
write somewhere, or one that cleans up by running `rm -rf` in a root container —
that cleanup may no longer need root, and may no longer be able to remove files
it once could. Work out the right behaviour rather than leaving a cleanup that
silently does nothing.

### 3. Prove it

Before your change, note which files in the repo are root-owned:

```
find . -user root -not -path './.git/*' | head -40
```

Clean them (a root container can: `docker run --rm -v "$PWD:/repo" -w /repo
gatepack-toolchain:m6 rm -rf .gpout build`), then run the full toolchain suite
with your change:

```
.venv/bin/python -m pytest tests/toolchain -q
```

and afterwards show that `find . -user root -not -path './.git/*'` returns
**nothing new**. That is the acceptance criterion, and quoting the real before
and after in your notes is the evidence. 59 tests pass and 1 skips at baseline;
report the count after.

Also confirm an ordinary local command still works afterwards without a cleanup
step — that is the failure this package exists to remove.

## The rules that govern this repo

- Never fake or assume a tool result. Run the tests.
- Do not weaken an assertion to make a test pass.
- Never touch any path outside the project directory — **reads included**.
- Do not commit. Leave the work in the tree for review.

## Files you own

`tests/toolchain/**`, and `scripts/` only if you find the same defect there
(`scripts/bundle_toolchain.py` has its own `docker run` calls — check whether
they write into the repo or only into a scratch directory, and say which).

Do **not** touch `libraries/**`, `examples/**` or `tests/unit/**` — another
agent is working in those right now. Do not modify `gatepack/**` or `app/**`.

## Report

Write `docs/handoff/notes-dockeruser.md`: the call sites you changed, the shape
of the helper and why, the before/after `find -user root` output, the test
counts, and anything you deliberately left alone.
