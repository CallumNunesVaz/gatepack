import { describe, expect, it } from 'vitest';
import { modelToYaml, parseDesignText, setPackingForceGroups, type DesignModel } from './model';

const SPEC = `name: xor2
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
  - {from: S0, to: S0, when: "1"}
output_logic:
  y: "a"
`;

describe('packing.force_groups round-trips through the design text', () => {
  it('parses an existing packing block', () => {
    const withPacking = SPEC.replace(
      'output_logic:\n  y: "a"\n',
      'output_logic:\n  y: "a"\npacking:\n  force_groups:\n    - [g0, g1]\n',
    );
    const { model, diagnostics } = parseDesignText(withPacking);
    expect(diagnostics).toEqual([]);
    expect((model as DesignModel).packing.forceGroups).toEqual([['g0', 'g1']]);
  });

  it('setPackingForceGroups writes force_groups without disturbing positions/layout', () => {
    const { text, diagnostics } = setPackingForceGroups(SPEC, [
      ['g0', 'g1'],
      ['g3'],
    ]);
    expect(diagnostics).toEqual([]);
    expect(text).toContain('packing:');
    expect(text).toContain('force_groups');
    expect(text).toContain('g0');
    expect(text).toContain('g1');
    expect(text).not.toContain('position');
    expect(text).not.toContain('layout');
    expect(text).not.toContain('"x"');
    // The edited text still parses to a model with the override.
    const { model } = parseDesignText(text);
    expect((model as DesignModel).packing.forceGroups).toEqual([['g0', 'g1'], ['g3']]);
  });

  it('clears the block when no groups remain', () => {
    const withPacking = setPackingForceGroups(SPEC, [['g0', 'g1']]).text;
    const { text } = setPackingForceGroups(withPacking, []);
    expect(parseDesignText(text).model).not.toBeNull();
    expect((parseDesignText(text).model as DesignModel).packing.forceGroups).toEqual([]);
  });

  it('modelToYaml emits the packing block when groups exist', () => {
    const { model } = parseDesignText(SPEC);
    const withGroups: DesignModel = { ...(model as DesignModel), packing: { forceGroups: [['g0', 'g1']] } };
    expect(modelToYaml(withGroups)).toContain('force_groups');
    // and omits it when empty
    expect(modelToYaml(model as DesignModel)).not.toContain('force_groups');
  });
});
