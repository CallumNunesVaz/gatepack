# Package C — more bundled examples, and only the parts they honestly need

Read `docs/handoff/delegation-rules.md` first. Every rule there applies.

## The task

Add several more canonical digital-logic circuits to `examples/`, and whatever
library parts they genuinely require.

## The rule that outranks the task

**Never invent an electrical or packaging value.** §1.3/[R4-21]: every value in
a parts table carries a datasheet citation with document revision and table/page,
or it is *explicitly marked a placeholder*. A plausible number with a fabricated
citation is the worst thing you can do to this project — it can reach a physical
board.

Read `libraries/74aup.refs.md` before you touch `libraries/74aup.csv`. It tells
you the current, honest state:

* **Every electrical figure in the library is already a PLACEHOLDER** —
  `vcc_min`, `vcc_max`, `tpd_ns`, `iq_ua`, the manufacturer lists and the part
  numbers. None are datasheet-verified.
* **Packaging is different.** `gates_per_pkg` and `package` are individually
  cited for the multi-gate rows, because a wrong `gates_per_pkg` produces a
  netlist that physically cannot be built.
* `area` is not datasheet data at all — it is gatepack's own cost weight.

So there are exactly two acceptable ways to add a part:

1. You have a **real datasheet** open, and you transcribe it with the document
   revision and table/page into `74aup.refs.md`. If you cannot name the
   document revision, you do not have this option.
2. You add the row with electrical figures marked **placeholder in exactly the
   way the existing rows are**, and say so in the refs file, and do **not**
   claim packaging you have not cited.

There is no third option. Do not copy a figure from another row "because it is
a similar part". Do not interpolate. Do not reason from a family name to a
voltage. If you find yourself writing a number you cannot source, stop and
write it up in the notes instead.

**The best outcome is examples that need no new parts at all.** The existing
cell set — `INV BUF AND2 AND3 NAND2 NAND3 NOR2 NOR3 OR2 XOR2 MUX2`, the `DFF`
family, `CNT4`, `SUPERVISOR`, `OSC` — is enough to synthesise essentially any
FSM. Prefer designs that land on it. Adding a part is a cost, not an achievement.

## What makes a good example here

Read `examples/parity/design.yaml` and `examples/pelican/design.yaml` first.
The bar is not "a design that compiles" — it is a *teaching artefact*: a header
comment explaining what the circuit is, what it demonstrates, and why it is
worth looking at, then a spec whose comments earn their place.

Every example must also carry the §1.3 declaration the others do:

```
# Synthetic, written for this project (§1.3). Nothing here is derived from any
# real product or datasheet application note.
```

That is a statement of fact you are responsible for keeping true. Canonical
textbook circuits — a vending machine, a combination lock, a lift controller, a
Gray-code counter, a seven-segment decoder, an edge detector, a stepper
sequencer, a traffic light — are all fine, because the *class* of circuit is
common property. Do not reproduce a specific published design, a vendor
application note, or anything you are recalling verbatim.

Aim for **four to six** new examples spanning:

* at least one purely combinational (`states: [S0]`, everything in
  `output_logic`) — `parity` is the model;
* at least one multi-output design, to exercise a wider truth table;
* at least one that is genuinely sequential with a non-trivial state graph;
* a range of sizes, including one small enough to read whole on screen.

## Your file scope — nothing outside it

* `examples/**` (new directories, and the existing ones only if you must)
* `libraries/74aup.csv` and `libraries/74aup.refs.md`
* `gatepack/examples.py`
* `tests/unit/test_examples.py`, `tests/toolchain/test_examples.py` (whichever
  exist; add to them)
* `docs/BUILD-NOTES-examples2.md`, `docs/handoff/notes-examples2.md`

**Off-limits** (another agent is working there right now): `app/**`,
`scripts/**`, `.github/**`, the `start` script. Also always off-limits:
`gatepack-design.md`, `docs/*-FINDINGS.md`, `docs/MILESTONE-AUDIT.md`,
`docs/GUI-AUDIT.md`, `app/shared/api.ts`.

## Each example must actually work — measured, not asserted

An example that does not verify is worse than no example: it ships as a broken
first impression. For **every** example you add, run the real toolchain and
paste the output into your notes:

```
docker run --rm -u "$(id -u):$(id -g)" -v "$PWD:/repo" -w /repo \
  gatepack-toolchain:m6 bash -c \
  'python3 -m gatepack verify examples/<name>/design.yaml \
     --library libraries/74aup.csv --build /tmp/b_<name>'
```

It must report `verification: passed`, with equivalence, exhaustive simulation
and the mutation suite all passing. If a design is too large for exhaustive
simulation, the tool will say so — that is a legitimate result, but say which
examples are in that position rather than letting it pass unremarked.

Each example directory needs `design.yaml` and `parts.csv` (copy the library
subset the design needs, as the existing examples do), plus `parts.refs.md`
where the existing ones have one.

## Acceptance

1. Every new example verifies green through the container, with the transcript
   in your notes.
2. `.venv/bin/python -m pytest -q` — **723 pass, 5 skip** at baseline; all still
   passing plus whatever you add.
3. `gatepack examples list --json` includes each new example with a real summary
   line (it is taken from the first comment line of `design.yaml`).
4. A test that fails if an example stops verifying, or if `parts.csv` and
   `design.yaml` disagree about which cells exist.
5. `gatepack lib check` still reports **no missing citations** — every cell in
   the library has a `74aup.refs.md` entry, including any you add.
6. If you added a part: a test asserting its row is marked placeholder, so a
   later reader cannot mistake it for verified data.

## The failure mode to avoid

This project has shipped nine pieces of machinery that reported a status while
measuring nothing. The version of that here is a `parts.csv` row with a
confident `tpd_ns` that nobody measured, sitting in a file whose header says
values are cited. **If you cannot source a number, mark it placeholder and say
so.** An honest placeholder is worth more than a plausible fabrication, and the
project already runs on placeholders — it is not a failure to add another.

## Output

`docs/BUILD-NOTES-examples2.md` and `docs/handoff/notes-examples2.md`: what you
added, the verify transcript for each, every number you could not source and how
you marked it, and the three things you are least confident about.
