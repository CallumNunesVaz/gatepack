# Package: a gate that does not fit its package

You are a components engineer. You know that a package outline is a physical
fact with a pin count, and that a part number is a hint, not a citation.

## The project

`gatepack` compiles a truth table or FSM specification into a bill of materials
and a schematic netlist built from discrete 74AUP logic packages, formally
verifying the result on every build. `libraries/74aup.csv` is the parts library;
`libraries/74aup.refs.md` is its citation record.

## The defect

Three rows in `libraries/74aup.csv` describe a part that cannot physically
exist:

```
NAND3,G,AUP,1G10,,!(A&B&C),3,1,SOT-353,...
NOR3,G,AUP,1G27,,!(A|B|C),3,1,SOT-353,...
AND3,G,AUP,1G11,,A&B&C,3,1,SOT-353,...
```

A single 3-input gate needs six pins: A, B, C, Y, VCC, GND. `SOT-353` is a
five-pin package. The arithmetic is

```
pins_needed = gates_per_pkg * (inputs + 1) + 2      # +2 for VCC and GND
```

and it must be **≤** the package's pin count. (Not `==`: a single-gate part in a
five-pin outline legitimately leaves one pin unconnected, which is why the
existing `INV`/`BUF` rows need 4 and have 5.)

Nothing catches this. The `gates_per_pkg` gate guards multi-gate rows only, so a
3-input gate in a 5-pin package passes every check the project has and could
reach a bill of materials.

## What to do

### 1. Find the real package for each of the three parts

Fetch the manufacturer datasheet for `74AUP1G10`, `74AUP1G11` and `74AUP1G27`
(Nexperia, TI or Diodes), confirm the package it actually ships in, and correct
the CSV. Record the citation in `libraries/74aup.refs.md` in the format the file
already uses — document, revision (the release date in the PDF's metadata, as
the file explains), and the table or page the value came from.

**If a part does not exist in the AUP family at all, say so and mark the row as
having no candidate part**, exactly as the `DFF_S` row already is. Do not
substitute a part from another family to make the row look complete. An honestly
unavailable part is a correct outcome.

**Never invent an electrical or packaging value.** §1.3 and §23 are absolute:
every value carries a datasheet citation, or it is marked a placeholder. A
plausible number with a fabricated citation is the worst thing you could do to
this project, and it could reach a physical board.

### 2. The pin counts themselves need a source

To check the arithmetic you need to know how many pins `SOT-353`, `SOT-363`,
`VSSOP-8`, `SO-16` and `SOT-23` have. **That mapping is data too.** `VSSOP-8`
and `SO-16` name their own pin count; `SOT-353`, `SOT-363` and `SOT-23` do not.

Get each from a real source — a manufacturer datasheet's package section
("SOT353 — plastic surface-mounted package; 5 leads") — and record it with a
citation, in the refs file or a new cited table beside it. A pin-count table
that you filled in from memory would make the whole check worthless, because
the check would then be measuring your recollection rather than the parts.

If you cannot cite a package's pin count, leave that package out of the check
and say so, rather than guessing it.

### 3. Make the invariant a test

Add a test that computes `gates_per_pkg * (inputs + 1) + 2` for every G-tier row
and asserts it fits the package. It must:

- iterate the library, never a hand-written list of rows;
- skip (and *report*, so it is visible) any package whose pin count is not
  cited, rather than silently passing it;
- fail loudly if a row does not fit.

Then prove the test can fail: put a deliberately wrong row in a copy of the
library, confirm the test catches it, and quote that in your notes. A test you
have not falsified is not evidence.

Consider whether F-tier (flip-flop) rows can be checked the same way. `DFF_SR`
declares 4 inputs and a `Q` output in `SOT-353` — 4 + 1 + 2 = 7 pins in a 5-pin
package. Work out whether the same arithmetic applies (the pin names come from
`gatepack/pins.py::F_PIN_DIRECTIONS`) and either extend the check or explain in
your notes why F-tier is different.

## Prove it

The toolchain is **not on your PATH**; it is in the docker image
`gatepack-toolchain:m6`, already built on this machine. Run it as yourself so it
does not leave root-owned files in the checkout:

```
docker run --rm -u "$(id -u):$(id -g)" -v "$PWD:/repo" -w /repo \
  gatepack-toolchain:m6 python3 -m gatepack build examples/pelican/design.yaml \
  --library libraries/74aup.csv --out .gpout/pins --json
```

Required, with real output quoted in your notes:

1. `gatepack lib check libraries/74aup.csv` passes.
2. The showcase builds with **no** acknowledgement flag and still reports
   **20 packages**. If changing a package changes that number, say so
   explicitly and explain why the new number is right — several tests pin it.
3. `gatepack verify examples/pelican/design.yaml` still passes every check.
4. `.venv/bin/python -m pytest tests -q` — the venv is linked into your
   worktree. Report the count before and after.

**The five bundled examples each ship a copy of the library** as
`examples/<name>/parts.csv` with its citations as `examples/<name>/parts.refs.md`.
If you change `libraries/74aup.csv`, those copies must be refreshed to match, or
`tests/unit/test_examples.py` will fail — and each example's header comment
states its package count, so if a count moves, the comment is now wrong and must
be corrected to what the build actually produces. Re-measure; do not assume.

## Files you own

`libraries/**`, `examples/**` (only to refresh the copied library and correct a
package count in a header comment), and new tests under `tests/unit/`.

Do **not** touch `tests/toolchain/**` — another agent is editing every file in
that directory right now. Do not modify `gatepack/**` or `app/**`; if you find a
defect there, report it in your notes instead of fixing it.

## Report

Write `docs/handoff/notes-pins.md`: per part, the datasheet you read and what it
said; the pin-count table and where each number came from; the falsification of
your new test; and anything you could not confirm.
