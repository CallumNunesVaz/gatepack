import { describe, expect, it } from 'vitest';
import type { ProvenanceMap } from '../../shared/api';
import { resolveSpecAnchor, resolveStructuralLine } from './specAnchor';
import type { Selection } from './types';

const EMPTY: ProvenanceMap = { entries: [], coverage: 0 };

function provenance(entries: ProvenanceMap['entries']): ProvenanceMap {
  return { entries, coverage: 0 };
}

/* ------------------------------------------------------------------ */
/* fixtures                                                            */
/* ------------------------------------------------------------------ */

// Two transitions carry the SAME `when` guard ("go") but different from/to
// pairs. A resolver that searches the text for the guard (or returns line 1 /
// the first match) points at the wrong transition; the anchor must key on the
// from/to pair.
const TWIN_GUARD_SPEC = `name: twoguard
timing_model: synchronous
clock: {signal: clk, freq_hz: 1000, source: OSC}
reset: {signal: rst_n, active: low, source: SUPERVISOR}
encoding: one_hot
inputs:
  - {name: go, sync: false}
outputs:
  - {name: out}
states: [A, B, C]
initial: A
transitions:
  - {from: A, to: B, when: "go"}
  - {from: B, to: C, when: "go"}
  - {from: C, to: A, when: "go"}
output_logic:
  out: "state == C"
`;

// Block-format lists so every state / input / property has its own line, which
// is what makes per-item line resolution observable (a flow list collapses
// them onto one line).
const BLOCK_SPEC = `name: structured
timing_model: synchronous
clock: {signal: clk, freq_hz: 1000, source: OSC}
reset: {signal: rst_n, active: low, source: SUPERVISOR}
encoding: one_hot
inputs:
  - {name: a, sync: false}
  - {name: b, sync: true}
outputs:
  - {name: y}
states:
  - IDLE
  - RUN
initial: IDLE
transitions:
  - {from: IDLE, to: RUN, when: "1"}
properties:
  - {name: p1, kind: invariant, expr: "a"}
output_logic:
  y: "state == RUN"
`;

describe('resolveSpecAnchor — structural route', () => {
  it('locates a transition by its from/to pair, not by searching the guard text', () => {
    // Lines 13, 14 and 15 all carry `when: "go"`. Selecting B -> C must land on
    // line 14, not the first match (13) and not line 1.
    const anchor = resolveSpecAnchor(
      { kind: 'transition', from: 'B', to: 'C' },
      EMPTY,
      TWIN_GUARD_SPEC,
    );
    expect(anchor).toEqual({ line: 14, route: 'structural', confidence: 'exact' });
  });

  it('distinguishes the first of two identical guards from the second', () => {
    const first = resolveSpecAnchor({ kind: 'transition', from: 'A', to: 'B' }, EMPTY, TWIN_GUARD_SPEC);
    const second = resolveSpecAnchor({ kind: 'transition', from: 'B', to: 'C' }, EMPTY, TWIN_GUARD_SPEC);
    expect(first?.line).toBe(13);
    expect(second?.line).toBe(14);
    expect(first?.line).not.toBe(second?.line);
  });

  it('locates each state, input and property on its own line in block form', () => {
    expect(resolveSpecAnchor({ kind: 'state', id: 'RUN' }, EMPTY, BLOCK_SPEC)).toEqual({
      line: 13,
      route: 'structural',
      confidence: 'exact',
    });
    expect(resolveSpecAnchor({ kind: 'input', name: 'b' }, EMPTY, BLOCK_SPEC)?.line).toBe(8);
    expect(resolveSpecAnchor({ kind: 'property', name: 'p1' }, EMPTY, BLOCK_SPEC)?.line).toBe(18);
  });

  it('returns null (no link) for a state that is not declared', () => {
    expect(resolveSpecAnchor({ kind: 'state', id: 'MISSING' }, EMPTY, BLOCK_SPEC)).toBeNull();
  });

  it('returns null rather than line 1 for kinds it cannot locate', () => {
    expect(resolveSpecAnchor({ kind: 'package', refdes: 'U1' }, EMPTY, BLOCK_SPEC)).toBeNull();
    expect(resolveSpecAnchor({ kind: 'minterm', index: 0 }, EMPTY, BLOCK_SPEC)).toBeNull();
    expect(resolveSpecAnchor({ kind: 'cexStep', property: 'p1', cycle: 0 }, EMPTY, BLOCK_SPEC)).toBeNull();
  });
});

describe('resolveSpecAnchor — provenance route', () => {
  it('resolves a cell to the line carried by its provenance pointer', () => {
    const cell: Selection = { kind: 'cell', name: '$abc$1$2' };
    const anchor = resolveSpecAnchor(
      cell,
      provenance([
        { pointer: 'design.yaml:42:transitions[2]', nets: ['n1'], cells: ['$abc$1$2'], confidence: 'exact' },
      ]),
      BLOCK_SPEC,
    );
    expect(anchor).toEqual({ line: 42, route: 'provenance', confidence: 'exact' });
  });

  it('resolves a net to an inferred line when only an inferred pointer survives', () => {
    const net: Selection = { kind: 'net', name: 'n1' };
    const anchor = resolveSpecAnchor(
      net,
      provenance([
        { pointer: 'design.yaml:7:inputs[0]', nets: ['n1'], cells: [], confidence: 'inferred' },
      ]),
      BLOCK_SPEC,
    );
    expect(anchor).toEqual({ line: 7, route: 'provenance', confidence: 'inferred' });
  });

  it('prefers an exact pointer over an inferred one for the same cell', () => {
    const cell: Selection = { kind: 'cell', name: '$abc$1$2' };
    const anchor = resolveSpecAnchor(
      cell,
      provenance([
        { pointer: 'design.yaml:9:states', nets: [], cells: ['$abc$1$2'], confidence: 'inferred' },
        { pointer: 'design.yaml:20:transitions[0]', nets: [], cells: ['$abc$1$2'], confidence: 'exact' },
      ]),
      BLOCK_SPEC,
    );
    expect(anchor).toEqual({ line: 20, route: 'provenance', confidence: 'exact' });
  });

  it('returns null for a cell with no matching provenance entry', () => {
    expect(resolveSpecAnchor({ kind: 'cell', name: 'nope' }, EMPTY, BLOCK_SPEC)).toBeNull();
  });

  it('skips a pointer that carries no line (a pointer is not a line)', () => {
    const cell: Selection = { kind: 'cell', name: '$abc$1$2' };
    const anchor = resolveSpecAnchor(
      cell,
      provenance([
        { pointer: 'design.yaml:transitions[2]', nets: [], cells: ['$abc$1$2'], confidence: 'exact' },
      ]),
      BLOCK_SPEC,
    );
    expect(anchor).toBeNull();
  });
});

/* ------------------------------------------------------------------ */
/* Widened structural route (§5)                                       */
/* ------------------------------------------------------------------ */

// Every construct lives on its own line, so a resolver that returns the first
// item (or line 1) is observably wrong for the ones below.
const WIDE_SPEC = `name: full
timing_model: synchronous
clock: {signal: clk, freq_hz: 1000, source: OSC}
reset: {signal: rst_n, active: low, source: SUPERVISOR}
encoding: one_hot
inputs:
  - {name: a, sync: false}
  - {name: b, sync: true}
outputs:
  - {name: x}
  - {name: y}
  - {name: z}
expressions:
  first: "a & b"
  second: "a | b"
states: [S0]
initial: S0
transitions:
  - {from: S0, to: S0, when: "1"}
output_logic:
  x: "a"
  y: "b"
test_points:
  - {net: tp1}
  - {net: tp2}
macros:
  - {instance: m1, cell: DFF, clock: clk}
  - {instance: m2, cell: CNT4, clock: clk}
constraints:
  vcc: 3.3
  max_flops: 8
packing:
  force_groups:
    - [a, b]
`;

describe('resolveStructuralLine — every construct, keyed on identity not position', () => {
  it('locates the second output, not the first', () => {
    expect(resolveStructuralLine(WIDE_SPEC, { kind: 'output', name: 'y' })).toBe(11);
    expect(resolveStructuralLine(WIDE_SPEC, { kind: 'output', name: 'z' })).toBe(12);
  });

  it('locates an expression by name, not the first expression', () => {
    expect(resolveStructuralLine(WIDE_SPEC, { kind: 'expression', name: 'second' })).toBe(15);
  });

  it('locates a test point by net name, not the first test point', () => {
    expect(resolveStructuralLine(WIDE_SPEC, { kind: 'testPoint', net: 'tp2' })).toBe(25);
  });

  it('locates a macro by instance, not the first macro', () => {
    expect(resolveStructuralLine(WIDE_SPEC, { kind: 'macro', instance: 'm2' })).toBe(28);
  });

  it('locates a constraint field, not the first constraint line', () => {
    expect(resolveStructuralLine(WIDE_SPEC, { kind: 'constraint', field: 'max_flops' })).toBe(31);
  });

  it('locates the packing force_groups block', () => {
    expect(resolveStructuralLine(WIDE_SPEC, { kind: 'packing', field: 'force_groups' })).toBe(34);
  });

  it('returns null for an absent construct rather than line 1', () => {
    expect(resolveStructuralLine(WIDE_SPEC, { kind: 'output', name: 'nope' })).toBeNull();
    expect(resolveStructuralLine(WIDE_SPEC, { kind: 'expression', name: 'nope' })).toBeNull();
    expect(resolveStructuralLine(WIDE_SPEC, { kind: 'macro', instance: 'nope' })).toBeNull();
  });
});

describe('resolveSpecAnchor — inferred fallback for a net with no provenance', () => {
  it('infers an output by name, labelled inferred and never exact', () => {
    const anchor = resolveSpecAnchor({ kind: 'net', name: 'y' }, EMPTY, WIDE_SPEC);
    expect(anchor).toEqual({ line: 11, route: 'structural', confidence: 'inferred' });
  });

  it('infers an input by name', () => {
    const anchor = resolveSpecAnchor({ kind: 'net', name: 'a' }, EMPTY, WIDE_SPEC);
    expect(anchor).toEqual({ line: 7, route: 'structural', confidence: 'inferred' });
  });

  it('returns null for a net that matches nothing, and never invents a link', () => {
    expect(resolveSpecAnchor({ kind: 'net', name: '$abc$133$new_n12_' }, EMPTY, WIDE_SPEC)).toBeNull();
  });

  it('returns null for a cell with no provenance — no cone/nearest-construct guess', () => {
    expect(resolveSpecAnchor({ kind: 'cell', name: '$abc$1$2' }, EMPTY, WIDE_SPEC)).toBeNull();
  });

  it('a real provenance entry still wins over the name fallback', () => {
    const anchor = resolveSpecAnchor(
      { kind: 'net', name: 'y' },
      provenance([
        { pointer: 'design.yaml:9:outputs[0]', nets: ['y'], cells: [], confidence: 'exact' },
      ]),
      WIDE_SPEC,
    );
    expect(anchor).toEqual({ line: 9, route: 'provenance', confidence: 'exact' });
  });
});
