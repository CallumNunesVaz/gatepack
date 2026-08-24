import { describe, expect, it } from 'vitest';
import {
  appendListItem,
  applyTopLevelEdit,
  parseDesignText,
  removeListItem,
  renameInput,
  renameState,
  setInputSync,
  setTestPoints,
  type DesignModel,
  type Transition,
  setTransitionFrom,
  setTransitionTo,
  setTransitionWhen,
  setPropertyExpr,
} from './model';
import type { YValue } from './yaml';

const XOR2 = `name: xor2
timing_model: synchronous
clock: {signal: clk, freq_hz: 1000, source: OSC}
reset: {signal: rst_n, active: low, source: SUPERVISOR}
encoding: one_hot
inputs:
  - {name: a, sync: false}
  - {name: b, sync: false}
outputs:
  - {name: y}
states: [S0]
initial: S0
transitions:
  - {from: S0, to: S0, when: "1"}
output_logic:
  y: "a ^ b"
`;

describe('parseDesignText', () => {
  it('extracts the structured model', () => {
    const { model, diagnostics } = parseDesignText(XOR2);
    expect(diagnostics).toEqual([]);
    expect(model).not.toBeNull();
    const m = model as DesignModel;
    expect(m.name).toBe('xor2');
    expect(m.inputs.map((i) => i.name)).toEqual(['a', 'b']);
    expect(m.outputs.map((o) => o.name)).toEqual(['y']);
    expect(m.states).toEqual(['S0']);
    expect(m.outputLogic).toEqual({ y: 'a ^ b' });
    expect(m.transitions).toEqual([{ from: 'S0', to: 'S0', when: '1' }]);
  });

  it('flags a transition to an undeclared state', () => {
    const bad = XOR2.replace('to: S0', 'to: NOPE');
    const { diagnostics } = parseDesignText(bad);
    expect(diagnostics.some((d) => d.code === 'ED1015')).toBe(true);
  });

  it('flags a bad expression in output_logic', () => {
    const bad = XOR2.replace('"a ^ b"', '"a &"');
    const { diagnostics } = parseDesignText(bad);
    expect(diagnostics.some((d) => d.code === 'ED1021')).toBe(true);
  });

  it('flags a guard that references state ==', () => {
    const bad = XOR2.replace('when: "1"', 'when: "state == S0"');
    const { diagnostics } = parseDesignText(bad);
    expect(diagnostics.some((d) => d.code === 'ED1020')).toBe(true);
  });
});

describe('graph edits are document mutations', () => {
  it('editing a transition guard produces changed YAML text', () => {
    const model = parseDesignText(XOR2).model as DesignModel;
    const transitions: Transition[] = [
      { ...model.transitions[0], when: 'a & b' },
      { from: 'S0', to: 'S0', when: '1' },
    ];
    const { text, diagnostics } = applyTopLevelEdit(
      XOR2,
      'transitions',
      () => transitions.map((t) => ({ from: t.from, to: t.to, when: t.when })),
    );
    expect(text).toContain('when: "a & b"');
    expect(text).toContain('when: "1"');
    expect(diagnostics).toEqual([]);
    // The text is still the authoritative, parseable document.
    expect(parseDesignText(text).model).not.toBeNull();
  });

  it('retargeting a transition (reconnect) updates the target', () => {
    const two = XOR2.replace('states: [S0]', 'states: [S0, S1]')
      .replace('when: "1"}', 'when: "x"}')
      .replace('outputs:\n  - {name: y}', 'outputs:\n  - {name: y}')
      .replace('inputs:\n  - {name: a, sync: false}\n  - {name: b, sync: false}',
        'inputs:\n  - {name: a, sync: false}\n  - {name: b, sync: false}\n  - {name: x, sync: false}');
    const model = parseDesignText(two).model as DesignModel;
    const transitions: Transition[] = model.transitions.map((t) =>
      t.from === 'S0' && t.to === 'S0' ? { ...t, to: 'S1' } : t,
    );
    const { text } = applyTopLevelEdit(two, 'transitions', () =>
      transitions.map((t) => ({ from: t.from, to: t.to, when: t.when })),
    );
    expect(text).toContain('to: S1');
  });

  it('adding a transition appends a new row', () => {
    const model = parseDesignText(XOR2).model as DesignModel;
    const transitions: Transition[] = [...model.transitions, { from: 'S0', to: 'S0', when: '1' }];
    const { text } = applyTopLevelEdit(XOR2, 'transitions', () =>
      transitions.map((t) => ({ from: t.from, to: t.to, when: t.when })),
    );
    expect(text.split('- {from:').length - 1).toBe(2);
  });

  it('node positions never appear in the produced YAML', () => {
    // Simulate the FSM graph flow: positions are recorded separately and are
    // never handed to the document editor.
    const positions = { S0: { x: 12345, y: 67890 } };
    const model = parseDesignText(XOR2).model as DesignModel;
    const transitions: Transition[] = [...model.transitions, { from: 'S0', to: 'S0', when: '1' }];
    const { text } = applyTopLevelEdit(XOR2, 'transitions', () =>
      transitions.map((t) => ({ from: t.from, to: t.to, when: t.when })),
    );
    expect(text).not.toContain('12345');
    expect(text).not.toContain('67890');
    expect(text).not.toContain('"x":');
    expect(text).not.toContain('layout');
    expect(text).not.toContain('position');
    expect(positions.S0.x).toBe(12345); // positions live elsewhere
  });
});

describe('renameState', () => {
  it('renames a state across states, initial, transitions and output_logic', () => {
    const doc = XOR2
      .replace('states: [S0]', 'states: [IDLE, RUN]')
      .replace('initial: S0', 'initial: IDLE')
      .replace('transitions:\n  - {from: S0, to: S0, when: "1"}',
        'transitions:\n  - {from: IDLE, to: RUN, when: "1"}\n  - {from: RUN, to: IDLE, when: "1"}')
      .replace('output_logic:\n  y: "a ^ b"', 'output_logic:\n  y: "state == RUN"');
    const { text } = renameState(doc, 'RUN', 'RUNNING');
    const { model } = parseDesignText(text);
    expect(model).not.toBeNull();
    const m = model as DesignModel;
    expect(m.states).toEqual(['IDLE', 'RUNNING']);
    expect(m.initial).toBe('IDLE');
    expect(m.transitions.map((t) => t.to)).toEqual(['RUNNING', 'IDLE']);
    expect(m.transitions.map((t) => t.from)).toEqual(['IDLE', 'RUNNING']);
    expect(m.outputLogic['y']).toBe('state == RUNNING');
  });

  it('does not match a state name that is a prefix of another identifier', () => {
    const doc = XOR2
      .replace('states: [S0]', 'states: [RUN, RUNNING]')
      .replace('initial: S0', 'initial: RUN');
    const { text } = renameState(doc, 'RUN', 'ACTIVE');
    expect(text).toContain('states: [ACTIVE, RUNNING]');
    expect(text).toContain('initial: ACTIVE');
    // `RUNNING` is a different state, untouched.
    expect(text).toContain('RUNNING');
  });
});

describe('renameState — a line-level splice, not a round-trip', () => {
  // The exact defect from the brief: renaming RUN->ACTIVE used to re-serialise
  // four blocks, deleting three comments and reflowing three collections into
  // flow style.
  const ANNOTATED = [
    'name: guard',
    'timing_model: synchronous',
    'clock: {signal: clk, freq_hz: 1000, source: OSC}',
    'reset: {signal: rst_n, active: low, source: SUPERVISOR}',
    'encoding: one_hot',
    'inputs:',
    '  - {name: go, sync: false}',
    'outputs:',
    '  - {name: busy}',
    'states:',
    '  # IDLE is the power-on state; do not reorder, the encoder is stable on order',
    '  - IDLE',
    '  - RUN',
    'initial: IDLE',
    'transitions:',
    "  # the operator's start button, debounced in hardware",
    '  - {from: IDLE, to: RUN, when: "go"}',
    'output_logic:',
    '  # asserted only in RUN — safety-relevant, see review 2026-03',
    '  busy: "state == RUN"',
    '',
  ].join('\n');

  it('preserves every comment and every block/flow style it does not change', () => {
    const { text } = renameState(ANNOTATED, 'RUN', 'ACTIVE');

    // None of the three comments survive a round-trip; all three survive here.
    expect(text).toContain('# IDLE is the power-on state; do not reorder, the encoder is stable on order');
    expect(text).toContain("# the operator's start button, debounced in hardware");
    expect(text).toContain('# asserted only in RUN — safety-relevant, see review 2026-03');

    // The renamed identifiers land where they must.
    expect(text).toContain('  - ACTIVE');
    expect(text).toContain('- {from: IDLE, to: ACTIVE, when: "go"}');
    expect(text).toContain('busy: "state == ACTIVE"');

    // The styles of the collections are not reflowed: `states` stays a block
    // list, `transitions` stays flow, `output_logic` stays a block mapping.
    expect(text).toContain('states:\n  # IDLE is the power-on state');
    expect(text).toContain('  - {from: IDLE, to: ACTIVE, when: "go"}');
    expect(text).toContain('output_logic:\n  # asserted only in RUN');

    expect(parseDesignText(text).model).not.toBeNull();
  });

  it('changes exactly the lines that carry the name, and no others', () => {
    const before = ANNOTATED.split('\n');
    const after = renameState(ANNOTATED, 'RUN', 'ACTIVE').text.split('\n');
    expect(after).toHaveLength(before.length);
    const changed = before.filter((line, i) => line !== after[i]);
    expect(changed).toEqual([
      '  - RUN',
      '  - {from: IDLE, to: RUN, when: "go"}',
      '  busy: "state == RUN"',
    ]);
  });
});

describe('renameInput', () => {
  const DOC = [
    'name: renamer',
    'timing_model: synchronous',
    'clock: {signal: clk, freq_hz: 1000, source: OSC}',
    'reset: {signal: rst_n, active: low, source: "go button"}',
    'encoding: one_hot',
    'inputs:',
    '  # the start button, debounced in hardware',
    '  - {name: go, sync: false}',
    '  - {name: going, sync: false}',
    '  - {name: go_n, sync: false}',
    'outputs:',
    '  - {name: busy}',
    'expressions:',
    '  cond: "go & !going"',
    'states: [IDLE, RUN]',
    'initial: IDLE',
    'transitions:',
    '  - {from: IDLE, to: RUN, when: "go"}',
    '  - {from: RUN, to: IDLE, when: "!going"}',
    'output_logic:',
    '  busy: "go | state == RUN"',
    'properties:',
    '  - {name: p1, kind: invariant, expr: "go ^ going"}',
    'fundamental_mode:',
    '  mutually_exclusive:',
    '    - [go, going]',
    '',
  ].join('\n');

  it('rewrites a guard, an output expression, a property expression and a fundamental_mode group in one edit', () => {
    const { text, diagnostics } = renameInput(DOC, 'go', 'start');
    expect(diagnostics.filter((d) => d.severity === 'error')).toEqual([]);

    expect(text).toContain('{name: start');
    expect(text).toContain('when: "start"');
    expect(text).toContain('busy: "start | state == RUN"');
    expect(text).toContain('expr: "start ^ going"');
    expect(text).toContain('cond: "start & !going"');
    expect(text).toContain('- [start, going]');
    // `state == RUN` is a state reference, not the input being renamed.
    expect(text).toContain('state == RUN');
  });

  it('is identifier-aware: going, go_n and a quoted non-expression string are left alone', () => {
    const { text } = renameInput(DOC, 'go', 'start');
    expect(text).toContain('{name: going');
    expect(text).toContain('{name: go_n');
    expect(text).toContain('when: "!going"');
    // `reset.source` is a quoted string that is not an expression; a textual
    // rename would have rewritten it.
    expect(text).toContain('source: "go button"');
    // The comment is preserved, and it still reads "start button" only inside
    // the comment (not the input name, which moved).
    expect(text).toContain('# the start button, debounced in hardware');
  });

  it('refuses an invalid identifier and leaves the text byte-identical', () => {
    const { text, diagnostics } = renameInput(DOC, 'go', '1bad');
    expect(text).toBe(DOC);
    expect(diagnostics.some((d) => d.severity === 'error' && d.message.includes('not a valid Verilog identifier'))).toBe(true);
  });

  it('refuses a collision with an existing input, output, state or expression', () => {
    const collision = renameInput(DOC, 'go', 'going');
    expect(collision.text).toBe(DOC);
    expect(collision.diagnostics.some((d) => d.severity === 'error' && d.message.includes('already used'))).toBe(true);

    const outputCollision = renameInput(DOC, 'go', 'busy');
    expect(outputCollision.text).toBe(DOC);
    expect(outputCollision.diagnostics.some((d) => d.severity === 'error' && d.message.includes('already used'))).toBe(true);
  });

  it('refuses an unknown input, byte-identical', () => {
    const { text, diagnostics } = renameInput(DOC, 'nope', 'start');
    expect(text).toBe(DOC);
    expect(diagnostics.some((d) => d.severity === 'error' && d.message.includes('no input named'))).toBe(true);
  });
});

describe('model round-trip helpers', () => {
  it('applyTopLevelEdit with an unknown key throws', () => {
    expect(() => applyTopLevelEdit(XOR2, 'nope', (v: YValue) => v)).toThrow();
  });
});

describe('setTestPoints — a surgical splice, not a round-trip', () => {
  const COMMENTED = `# the sequence detector
name: seq
timing_model: synchronous
clock: {signal: clk, freq_hz: 1000, source: OSC}
# the reset chain (§9.3)
reset: {signal: rst_n, active: low, source: SUPERVISOR}
encoding: one_hot
inputs:
  - {name: a, sync: false}
  - {name: b, sync: false}
outputs:
  - {name: y}
states: [S0]
initial: S0
transitions:
  - {from: S0, to: S0, when: "1"}
output_logic:
  y: "a ^ b"
`;

  it('appends test_points when absent and leaves every comment and unrelated line alone', () => {
    const { text } = setTestPoints(COMMENTED, ['match']);
    expect(text).toContain('test_points:');
    expect(text).toContain('net: match');
    // The user's comments and unrelated formatting survive: only the one block
    // was added, so a round-trip through `modelToYaml` (which drops comments and
    // re-sorts keys) would have failed this.
    expect(text).toContain('# the sequence detector');
    expect(text).toContain('# the reset chain (§9.3)');
    expect(text.indexOf('name: seq')).toBeLessThan(text.indexOf('test_points:'));
    expect(parseDesignText(text).diagnostics).toEqual([]);
  });

  it('replaces the existing test_points block in place', () => {
    const withTp = `${COMMENTED}test_points:\n  - {net: old}\n`;
    const { text } = setTestPoints(withTp, ['a', 'b']);
    expect(text).toContain('net: a');
    expect(text).toContain('net: b');
    expect(text).not.toContain('net: old');
    expect(text).toContain('# the reset chain (§9.3)');
  });
});

describe('setInputSync — toggle one synchroniser', () => {
  it('flips one input and leaves the other untouched', () => {
    const { text } = setInputSync(XOR2, 'a', true);
    const { model } = parseDesignText(text);
    expect(model).not.toBeNull();
    const inputs = (model as DesignModel).inputs;
    expect(inputs.find((i) => i.name === 'a')?.sync).toBe(true);
    expect(inputs.find((i) => i.name === 'b')?.sync).toBe(false);
    expect(text).toContain('name: a, sync: true');
    expect(text).toContain('name: b, sync: false');
  });

  it('refuses an unknown input with a diagnostic and unchanged text', () => {
    const { text, diagnostics } = setInputSync(XOR2, 'nope', true);
    expect(text).toBe(XOR2);
    expect(diagnostics.some((d) => d.code === 'ED1024')).toBe(true);
  });
});

/**
 * These three pin data loss, not formatting taste. Each was reachable and each
 * silently deleted something the user wrote, with no diagnostic.
 */
describe('surgical edits do not destroy the block they edit', () => {
  const ANNOTATED = [
    '# Traffic controller — hand-tuned, do not reformat.',
    'name: probe',
    'timing_model: synchronous',
    'clock: {signal: clk, freq_hz: 1000, source: OSC}',
    'reset: {signal: rst_n, active: low, source: SUPERVISOR}',
    'encoding: one_hot',
    '',
    'inputs:',
    "  # the operator's push-button, debounced in hardware",
    '  - {name: a, sync: true}    # MUST stay synchronised — metastability',
    '  - {name: b, sync: false}',
    '',
    'outputs:',
    '  - {name: y}',
    'states: [S0]',
    'initial: S0',
    'transitions:',
    '  - {from: S0, to: S0, when: "1"}',
    'output_logic:',
    '  y: "a"',
    'test_points:',
    '  # probe pad next to U3, reachable with a scope hook',
    '  - {net: y}',
    '',
  ].join('\n');

  it('setInputSync keeps the comment on a DIFFERENT input', () => {
    // The failure this replaces: toggling `b` re-serialised the whole `inputs:`
    // block from the model and deleted a metastability note attached to `a`.
    const out = setInputSync(ANNOTATED, 'b', true);
    expect(out.text).toContain('# MUST stay synchronised');
    expect(out.text).toContain("# the operator's push-button");
    expect(out.text).toContain('- {name: b, sync: true}');
    // and `a` is untouched
    expect(out.text).toContain('- {name: a, sync: true}');
  });

  it('setInputSync changes exactly one line', () => {
    const out = setInputSync(ANNOTATED, 'b', true);
    const before = ANNOTATED.split('\n');
    const after = out.text.split('\n');
    expect(after).toHaveLength(before.length);
    const changed = before.filter((l, i) => l !== after[i]);
    expect(changed).toEqual(['  - {name: b, sync: false}']);
  });

  it('setTestPoints keeps comments in an EXISTING block', () => {
    const out = setTestPoints(ANNOTATED, ['y', 'a']);
    expect(out.text).toContain('# probe pad next to U3');
    expect(out.text).toContain('{net: a}');
    expect(out.text).toContain('{net: y}');
  });

  it('setTestPoints removes an entry without touching the rest', () => {
    const out = setTestPoints(ANNOTATED, []);
    expect(out.text).not.toContain('{net: y}');
    expect(out.text).toContain('# probe pad next to U3');
    expect(out.text).toContain('# MUST stay synchronised');
  });
});

// ---------------------------------------------------------------------------
// Reviewed addition: the two references a rename used to strand *silently*.
//
// `parseDesignText` diagnoses unknown states in transitions and output_logic
// (ED1014/ED1015/ED1022) and unknown signals in guards (ED1018), but measured
// 2026-08-23 it says nothing at all about `properties[].expr` or
// `macros[].enable`. So a rename that skips those blocks lands with no error,
// no diagnostic and no refusal — the user believes the rename was complete and
// the spec now asserts something about a name that does not exist. That is the
// silent-no-op failure the whole editing spine is built to avoid.
// ---------------------------------------------------------------------------

const RENAME_REFS_SPEC = `name: refs
timing_model: synchronous
clock: {net: clk, freq_hz: 1000}
reset: {net: rst_n, polarity: active_low}
inputs:
  - {name: go, sync: true}
outputs:
  - {name: busy}
states: [IDLE, RUN]
initial: IDLE
transitions:
  - {from: IDLE, to: RUN, when: "go"}
  - {from: RUN, to: IDLE, when: "!go"}
output_logic:
  busy: "state == RUN"
properties:
  - {name: p1, kind: invariant, expr: "state == RUN -> busy"}
  - {name: p2, kind: invariant, expr: "go -> busy"}
macros:
  - {instance: m1, cell: CNT4, clock: clk, enable: "go"}
`;

describe('renames leave no stranded reference', () => {
  it('renameState rewrites property expressions', () => {
    const out = renameState(RENAME_REFS_SPEC, 'RUN', 'ACTIVE');
    expect(out.diagnostics.filter((d) => d.severity === 'error')).toHaveLength(0);
    expect(out.text).toContain('expr: "state == ACTIVE -> busy"');
    expect(out.text).not.toContain('state == RUN');
  });

  it('renameInput rewrites a macro enable', () => {
    const out = renameInput(RENAME_REFS_SPEC, 'go', 'start');
    expect(out.diagnostics.filter((d) => d.severity === 'error')).toHaveLength(0);
    expect(out.text).toContain('enable: "start"');
    expect(out.text).toContain('expr: "start -> busy"');
    expect(out.text).not.toMatch(/\bgo\b/);
  });

  it('a state rename does not touch an input guard that reads like a state', () => {
    const out = renameState(RENAME_REFS_SPEC, 'RUN', 'ACTIVE');
    expect(out.text).toContain('when: "go"');
    expect(out.text).toContain('expr: "go -> busy"');
  });
});

// ---------------------------------------------------------------------------
// Reviewed addition: editing one list item must not rewrite the block.
//
// Measured 2026-08-23 on the spec below: editing the *first* transition's guard
// through `applyTopLevelEdit` — what the Inspector did — deleted both comments
// in the transitions block, including the one attached to the second
// transition, which the user had not touched. Fourth instance of this defect
// class in this file (setInputSync, setTestPoints, renameState were the others).
// ---------------------------------------------------------------------------

const ITEM_EDIT_SPEC = `name: p
timing_model: synchronous
clock: {net: clk, freq_hz: 1000}
reset: {net: rst_n, polarity: active_low}
inputs:
  - {name: go, sync: true}
  - {name: stop, sync: true}
outputs:
  - {name: busy}
states: [IDLE, RUN]
initial: IDLE
transitions:
  # the operator's start button — debounced in hardware, see review 2026-03
  - {from: IDLE, to: RUN, when: "go"}
  # deliberately unguarded: RUN must always fall back
  - {from: RUN, to: IDLE, when: "!go"}
output_logic:
  busy: "state == RUN"
properties:
  # the safety property the whole design exists for
  - {name: p1, kind: invariant, expr: "state == RUN -> busy"}
  - {name: p2, kind: invariant, expr: "go -> busy"}
`;

describe('editing one list item leaves the rest of the block alone', () => {
  it('setTransitionWhen keeps every comment in the block', () => {
    const out = setTransitionWhen(ITEM_EDIT_SPEC, 0, 'go & !stop');
    expect(out.diagnostics.filter((d) => d.severity === 'error')).toHaveLength(0);
    expect(out.text).toContain('# the operator\'s start button');
    expect(out.text).toContain('# deliberately unguarded');
    expect(out.text).toContain('when: "go & !stop"');
    // The untouched transition is byte-identical.
    expect(out.text).toContain('- {from: RUN, to: IDLE, when: "!go"}');
  });

  it('setPropertyExpr keeps every comment in the block', () => {
    const out = setPropertyExpr(ITEM_EDIT_SPEC, 1, 'go -> !busy');
    expect(out.diagnostics.filter((d) => d.severity === 'error')).toHaveLength(0);
    expect(out.text).toContain('# the safety property the whole design exists for');
    expect(out.text).toContain('expr: "go -> !busy"');
    expect(out.text).toContain('- {name: p1, kind: invariant, expr: "state == RUN -> busy"}');
  });

  it('an out-of-range item is refused, byte-identical', () => {
    const out = setTransitionWhen(ITEM_EDIT_SPEC, 9, 'go');
    expect(out.text).toBe(ITEM_EDIT_SPEC);
    expect(out.diagnostics.some((d) => d.code === 'ED1026')).toBe(true);
  });

  it('a guard with YAML-significant characters survives quoting', () => {
    const out = setTransitionWhen(ITEM_EDIT_SPEC, 0, '!go & (stop | go)');
    expect(out.diagnostics.filter((d) => d.severity === 'error')).toHaveLength(0);
    const back = parseDesignText(out.text).model;
    expect(back?.transitions[0].when).toBe('!go & (stop | go)');
  });

  it('a field that is absent is inserted, not silently dropped', () => {
    const noWhen = ITEM_EDIT_SPEC.replace('- {from: RUN, to: IDLE, when: "!go"}', '- {from: RUN, to: IDLE}');
    const out = setTransitionWhen(noWhen, 1, '!go');
    expect(out.diagnostics.filter((d) => d.severity === 'error')).toHaveLength(0);
    expect(parseDesignText(out.text).model?.transitions[1].when).toBe('!go');
    expect(out.text).toContain('# deliberately unguarded');
  });
});

// ---------------------------------------------------------------------------
// Package N: adding/removing list items must not destroy the comments they sit
// among. The fixture is the real bundled example — copied verbatim — because it
// is the one case that exercises all three losses at once: comments inside
// `transitions`, hand-aligned columns, and quoted scalars.
// ---------------------------------------------------------------------------

const EDGE_DETECTOR = `# ---------------------------------------------------------------------------
# A rising-edge detector — why "detect a change" needs memory.
#
# A purely combinational circuit cannot tell you the input *changed*: it can
# only tell you the input's current value. To notice the 0 -> 1 transition you
# must remember what the input was on the previous clock, and "remember" is
# exactly what a state is. This machine emits a one-cycle \`pulse\` immediately
# after the input rises, and holds it back while the input stays high or low.
#
# What it demonstrates:
#
#   memory is state      S0 means "the input was low", S1 "it was high"; the
#                        edge is the crossing between them
#   a one-cycle pulse     PULSE is entered once per rising edge and left on the
#                        next clock, so the pulse is exactly one cycle wide
#   sustained input       after the pulse the machine settles in S1 and does
#                        not re-pulse until the input falls and rises again
#   the registered form   the pulse appears one cycle after the raw edge, which
#                        is the usual synchronous (registered) edge detector
#
# This is the smallest genuinely sequential example in the set: one input, one
# output, three states, readable whole on screen.
#
# Synthetic, written for this project (§1.3). Not derived from any real product
# or datasheet application note.
# ---------------------------------------------------------------------------
name: edge_detector
timing_model: synchronous

clock: {signal: clk, freq_hz: 1000, source: OSC}

reset:
  signal: rst_n
  active: low
  source: SUPERVISOR

encoding: one_hot

inputs:
  # A clocked data bit, so no synchroniser (§9.3).
  - {name: din, sync: false}

outputs:
  - {name: pulse}

states: [S0, PULSE, S1]
initial: S0

transitions:
  # S0: the input was low. A rise is the edge we are looking for.
  - {from: S0,    to: PULSE, when: "din"}
  - {from: S0,    to: S0,    when: "!din"}
  # PULSE: the edge was just seen; emit for this cycle, then track the input.
  - {from: PULSE, to: S1,    when: "din"}
  - {from: PULSE, to: S0,    when: "!din"}
  # S1: the input is high; wait for it to fall before another edge can occur.
  - {from: S1,    to: S1,    when: "din"}
  - {from: S1,    to: S0,    when: "!din"}

output_logic:
  pulse: "state == PULSE"
`;

const TRANSITION_COMMENTS = [
  '# S0: the input was low. A rise is the edge we are looking for.',
  '# PULSE: the edge was just seen; emit for this cycle, then track the input.',
  '# S1: the input is high; wait for it to fall before another edge can occur.',
];

/** The changed region as a line diff: the lines removed from `before` and the
 * lines added in `after`, using a common prefix/suffix match. For a pure
 * splice exactly one side is non-empty, and everything outside the region is
 * byte-identical by construction. */
function lineDiff(before: string, after: string): { removed: string[]; added: string[] } {
  const b = before.split('\n');
  const a = after.split('\n');
  let prefix = 0;
  while (prefix < b.length && prefix < a.length && b[prefix] === a[prefix]) prefix += 1;
  let suffix = 0;
  while (
    suffix < b.length - prefix &&
    suffix < a.length - prefix &&
    b[b.length - 1 - suffix] === a[a.length - 1 - suffix]
  ) {
    suffix += 1;
  }
  return {
    removed: b.slice(prefix, b.length - suffix),
    added: a.slice(prefix, a.length - suffix),
  };
}

function noErrors(out: { diagnostics: { severity: string }[] }): boolean {
  return out.diagnostics.filter((d) => d.severity === 'error').length === 0;
}

describe('list-item edits preserve comments (real edge_detector fixture)', () => {
  it('add a transition: the block is spliced, not re-serialised', () => {
    const out = appendListItem(EDGE_DETECTOR, 'transitions', { from: 'S0', to: 'S0', when: '1' });
    expect(noErrors(out)).toBe(true);
    for (const c of TRANSITION_COMMENTS) expect(out.text).toContain(c);
    const diff = lineDiff(EDGE_DETECTOR, out.text);
    expect(diff.removed).toEqual([]);
    expect(diff.added).toEqual(['  - {from: S0, to: S0, when: "1"}']);
    expect(parseDesignText(out.text).model).not.toBeNull();
  });

  it("change a transition's `to`: only that line changes", () => {
    const out = setTransitionTo(EDGE_DETECTOR, 0, 'S1');
    expect(noErrors(out)).toBe(true);
    for (const c of TRANSITION_COMMENTS) expect(out.text).toContain(c);
    const diff = lineDiff(EDGE_DETECTOR, out.text);
    expect(diff.removed).toEqual(['  - {from: S0,    to: PULSE, when: "din"}']);
    expect(diff.added).toEqual(['  - {from: S0,    to: "S1", when: "din"}']);
  });

  it("change a transition's `from`: only that line changes", () => {
    const out = setTransitionFrom(EDGE_DETECTOR, 5, 'PULSE');
    expect(noErrors(out)).toBe(true);
    for (const c of TRANSITION_COMMENTS) expect(out.text).toContain(c);
    const diff = lineDiff(EDGE_DETECTOR, out.text);
    expect(diff.removed).toEqual(['  - {from: S1,    to: S0,    when: "!din"}']);
    expect(diff.added).toEqual(['  - {from: "PULSE",    to: S0,    when: "!din"}']);
  });

  it("change a transition's `when`: only that line changes", () => {
    const out = setTransitionWhen(EDGE_DETECTOR, 0, '!din');
    expect(noErrors(out)).toBe(true);
    for (const c of TRANSITION_COMMENTS) expect(out.text).toContain(c);
    const diff = lineDiff(EDGE_DETECTOR, out.text);
    expect(diff.removed).toEqual(['  - {from: S0,    to: PULSE, when: "din"}']);
    expect(diff.added).toEqual(['  - {from: S0,    to: PULSE, when: "!din"}']);
  });

  it('delete a transition: its glued comment goes with it, everything else is byte-identical', () => {
    const out = removeListItem(EDGE_DETECTOR, 'transitions', 2);
    expect(noErrors(out)).toBe(true);
    expect(out.text).toContain('# S0: the input was low. A rise is the edge we are looking for.');
    expect(out.text).toContain('# S1: the input is high; wait for it to fall before another edge can occur.');
    expect(out.text).not.toContain('# PULSE: the edge was just seen');
    const diff = lineDiff(EDGE_DETECTOR, out.text);
    expect(diff.added).toEqual([]);
    expect(diff.removed).toEqual([
      '  # PULSE: the edge was just seen; emit for this cycle, then track the input.',
      '  - {from: PULSE, to: S1,    when: "din"}',
    ]);
    expect(parseDesignText(out.text).model).not.toBeNull();
  });

  it('add a state: the flow sequence is extended in place', () => {
    const out = appendListItem(EDGE_DETECTOR, 'states', 'S3');
    expect(noErrors(out)).toBe(true);
    for (const c of TRANSITION_COMMENTS) expect(out.text).toContain(c);
    expect(out.text).toContain('# A clocked data bit, so no synchroniser (§9.3).');
    const diff = lineDiff(EDGE_DETECTOR, out.text);
    expect(diff.removed).toEqual(['states: [S0, PULSE, S1]']);
    expect(diff.added).toEqual(['states: [S0, PULSE, S1, S3]']);
  });

  it('add an input: the existing input and its comment are untouched', () => {
    const out = appendListItem(EDGE_DETECTOR, 'inputs', { name: 'din2', sync: false });
    expect(noErrors(out)).toBe(true);
    expect(out.text).toContain('# A clocked data bit, so no synchroniser (§9.3).');
    expect(out.text).toContain('- {name: din, sync: false}');
    const diff = lineDiff(EDGE_DETECTOR, out.text);
    expect(diff.removed).toEqual([]);
    expect(diff.added).toEqual(['  - {name: din2, sync: false}']);
  });
});

// The negative control: the re-serialisation this package replaces is lossy,
// and this test keeps the failure visible so a future revert is caught. If this
// test ever fails it means applyTopLevelEdit no longer canonicalises — which is
// a change of behaviour someone else depends on, not a green light to delete it.
describe('the re-serialisation this replaces loses the comments (canary)', () => {
  it('applyTopLevelEdit drops every comment and normalises quoting and alignment', () => {
    const model = parseDesignText(EDGE_DETECTOR).model as DesignModel;
    const out = applyTopLevelEdit(EDGE_DETECTOR, 'transitions', () =>
      [...model.transitions, { from: 'S0', to: 'S0', when: '1' }].map((t) => ({
        from: t.from,
        to: t.to,
        when: t.when,
      })),
    );
    expect(out.text).not.toContain('# S0: the input was low');
    expect(out.text).toContain('when: din'); // quoting normalised (was "din")
    expect(out.text).not.toContain('    to:'); // hand alignment collapsed
  });
});

describe('appendListItem / removeListItem edge cases', () => {
  const EMPTY_TRANSITIONS = `name: t
timing_model: synchronous
clock: {signal: clk, freq_hz: 1000, source: OSC}
reset: {signal: rst_n, active: low, source: SUPERVISOR}
encoding: one_hot
inputs:
  - {name: a, sync: false}
outputs:
  - {name: y}
states: [S0]
initial: S0
transitions:
output_logic:
  y: "a"
`;

  const BLOCK_STATES = `name: t
timing_model: synchronous
clock: {signal: clk, freq_hz: 1000, source: OSC}
reset: {signal: rst_n, active: low, source: SUPERVISOR}
encoding: one_hot
inputs:
  - {name: a, sync: false}
outputs:
  - {name: y}
states:
  # IDLE is the power-on state; do not reorder
  - IDLE
  - RUN
initial: IDLE
transitions:
  - {from: IDLE, to: RUN, when: "a"}
output_logic:
  y: "a"
`;

  it('appends to a key that is not present by adding a fresh block', () => {
    const out = appendListItem(EDGE_DETECTOR, 'macros', { instance: 'm0', cell: 'CNT4', clock: 'clk' });
    expect(noErrors(out)).toBe(true);
    expect(out.text).toContain('macros:');
    expect(out.text).toContain('instance: m0');
    expect(out.text).toContain('cell: CNT4');
    expect(out.text).toContain('# S0: the input was low. A rise is the edge we are looking for.');
  });

  it('appends to a block list that has no items yet', () => {
    const out = appendListItem(EMPTY_TRANSITIONS, 'transitions', { from: 'S0', to: 'S0', when: '1' });
    expect(noErrors(out)).toBe(true);
    expect(out.text).toContain('transitions:\n  - {from: S0, to: S0, when: "1"}');
    expect(out.text).toContain('output_logic:');
    expect(parseDesignText(out.text).model?.transitions).toEqual([
      { from: 'S0', to: 'S0', when: '1' },
    ]);
  });

  it('appends a state to a block-list `states` with a comment, keeping the style', () => {
    const out = appendListItem(BLOCK_STATES, 'states', 'ACTIVE');
    expect(noErrors(out)).toBe(true);
    expect(out.text).toContain('# IDLE is the power-on state; do not reorder');
    expect(out.text).toContain('  - ACTIVE');
    // Still a block list, not reflowed into a flow sequence.
    expect(out.text).not.toContain('states: [IDLE, RUN, ACTIVE]');
    expect(parseDesignText(out.text).model?.states).toEqual(['IDLE', 'RUN', 'ACTIVE']);
  });

  it('removes an item from a flow sequence', () => {
    const FLOW = `name: t
timing_model: synchronous
clock: {signal: clk, freq_hz: 1000, source: OSC}
reset: {signal: rst_n, active: low, source: SUPERVISOR}
encoding: one_hot
inputs:
  - {name: a, sync: false}
outputs:
  - {name: y}
states: [A, B, C]
initial: A
transitions:
  - {from: A, to: B, when: "a"}
output_logic:
  y: "a"
`;
    const out = removeListItem(FLOW, 'states', 2);
    expect(noErrors(out)).toBe(true);
    expect(out.text).toContain('states: [A, B]');
  });

  it('refuses to remove from an empty list, byte-identical', () => {
    const out = removeListItem(EMPTY_TRANSITIONS, 'transitions', 0);
    expect(out.text).toBe(EMPTY_TRANSITIONS);
    expect(out.diagnostics.some((d) => d.code === 'ED1031')).toBe(true);
  });

  it('refuses to remove from a missing key, byte-identical', () => {
    const out = removeListItem(EDGE_DETECTOR, 'macros', 0);
    expect(out.text).toBe(EDGE_DETECTOR);
    expect(out.diagnostics.some((d) => d.code === 'ED1031')).toBe(true);
  });

  it('refuses to append to a key whose value is not a list', () => {
    const out = appendListItem(EDGE_DETECTOR, 'name', 'x');
    expect(out.text).toBe(EDGE_DETECTOR);
    expect(out.diagnostics.some((d) => d.code === 'ED1030')).toBe(true);
  });

  it('a splice that would not re-parse is refused, not written', () => {
    // A state name with a newline would produce a broken flow sequence; the
    // edit must refuse (return the original text) rather than hand back text
    // that no longer parses.
    const out = appendListItem(EDGE_DETECTOR, 'states', 'A\nB');
    expect(out.text).toBe(EDGE_DETECTOR);
    expect(out.diagnostics.some((d) => d.severity === 'error')).toBe(true);
  });
});
