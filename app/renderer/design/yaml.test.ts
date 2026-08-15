import { describe, expect, it } from 'vitest';
import {
  isDict,
  parseToJs,
  serializeDocument,
  serializeTopLevelValue,
  spliceText,
  YamlError,
  type YValue,
} from './yaml';

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

describe('yaml subset parser', () => {
  it('parses the xor2 golden and interprets scalars', () => {
    const { value } = parseToJs(XOR2);
    expect(isDict(value)).toBe(true);
    const root = value as Record<string, YValue>;
    expect(root['name']).toBe('xor2');
    expect(root['encoding']).toBe('one_hot');
    expect(root['initial']).toBe('S0');
    expect(root['states']).toEqual(['S0']);
    const inputs = root['inputs'] as YValue[];
    expect(inputs[0]).toEqual({ name: 'a', sync: false });
    expect(root['output_logic']).toEqual({ y: 'a ^ b' });
    // "1" is a quoted string, not the integer 1
    const transitions = root['transitions'] as YValue[];
    expect(transitions[0]).toEqual({ from: 'S0', to: 'S0', when: '1' });
  });

  it('records top-level value ranges for surgical edits', () => {
    const { ranges } = parseToJs(XOR2);
    const states = ranges.get('states');
    expect(states).toBeDefined();
    if (!states) return;
    // "states: [S0]" — value starts right after the colon.
    const slice = XOR2.slice(states.valueStart, states.valueEnd);
    expect(slice).toBe(' [S0]');
  });

  it('splices a list edit without disturbing the rest', () => {
    const { ranges } = parseToJs(XOR2);
    const states = ranges.get('states');
    expect(states).toBeDefined();
    if (!states) return;
    const replacement = serializeTopLevelValue(['S0', 'S1']);
    const text = spliceText(XOR2, states.valueStart, states.valueEnd, replacement);
    expect(text).toContain('states: [S0, S1]');
    expect(text).toContain('output_logic:');
    expect(parseToJs(text).value).toMatchObject({ states: ['S0', 'S1'] });
  });

  it('serialises a block sequence for a list of mappings', () => {
    const text = serializeTopLevelValue([
      { from: 'S0', to: 'S1', when: 'x' },
      { from: 'S1', to: 'S0', when: '1' },
    ]);
    expect(text).toContain('- {from: S0, to: S1, when: x}');
    expect(text).toContain('- {from: S1, to: S0, when: "1"}');
  });

  it('quotes scalars that would not round-trip as plain text', () => {
    const doc = serializeDocument({ name: 'xor2', when: 'a ^ b', one: '1', empty: '' });
    expect(doc).toContain('when: "a ^ b"');
    expect(doc).toContain('one: "1"');
    expect(doc).toContain('empty: ""');
    expect(doc).toContain('name: xor2');
  });

  it('treats on/off/yes/no as plain strings (YAML 1.1 footgun)', () => {
    const { value } = parseToJs('states: [ON, OFF, yes, no]');
    expect(value).toEqual({ states: ['ON', 'OFF', 'yes', 'no'] });
  });

  it('rejects duplicate mapping keys', () => {
    expect(() => parseToJs('name: a\nname: b')).toThrow(YamlError);
  });

  it('rejects block scalars', () => {
    expect(() => parseToJs('doc: |\n  hello')).toThrow(/block scalar/);
  });

  it('rejects tab indentation', () => {
    expect(() => parseToJs('a:\n\tb: c')).toThrow(/tab/);
  });

  it('round-trips the full xor2 document through serialise', () => {
    const { value } = parseToJs(XOR2);
    const doc = serializeDocument(value as Record<string, YValue>);
    const reparsed = parseToJs(doc).value;
    expect(reparsed).toEqual(value);
  });
});
