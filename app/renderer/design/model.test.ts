import { describe, expect, it } from 'vitest';
import {
  applyTopLevelEdit,
  parseDesignText,
  renameState,
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
});

describe('model round-trip helpers', () => {
  it('applyTopLevelEdit with an unknown key throws', () => {
    expect(() => applyTopLevelEdit(XOR2, 'nope', (v: YValue) => v)).toThrow();
  });
});
