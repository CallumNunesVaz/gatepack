import { describe, expect, it } from 'vitest';
import {
  applyTopLevelEdit,
  parseDesignText,
  renameInput,
  renameState,
  setInputSync,
  setTestPoints,
  type DesignModel,
  type Transition,
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
