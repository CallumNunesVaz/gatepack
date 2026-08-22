import { describe, expect, it } from 'vitest';
import {
  applyEditAffordances,
  generatedNetRefusal,
  isGeneratedNetName,
  NO_BUILD_REFUSAL,
  regroupToPackage,
  stableNamesFromPacked,
  toggleTestPoint,
} from './schematicEdit';
import type { PackingCell } from '../components/packing';
import type { PackedView } from '../../shared/api';

const SPEC = `name: xor2
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

const CELLS: PackingCell[] = [
  { name: 'g0', func: 'NOR2' },
  { name: 'g1', func: 'NOR2' },
  { name: 'g2', func: 'NAND2' },
];

const STABLE: Record<string, string> = {
  g0: 'NOR2__a1b2c3',
  g1: 'NOR2__d4e5f6',
  g2: 'NAND2__99aabb',
};

function sheet(html: string): HTMLElement {
  const root = document.createElement('div');
  root.innerHTML = html;
  return root;
}

describe('isGeneratedNetName', () => {
  it('rejects $abc generated names and accepts written names', () => {
    expect(isGeneratedNetName('$abc$133$new_n12_')).toBe(true);
    expect(isGeneratedNetName('$0\\state_S0[0:0]')).toBe(true);
    expect(isGeneratedNetName('match')).toBe(false);
    expect(isGeneratedNetName('a')).toBe(false);
  });
});

describe('toggleTestPoint', () => {
  it('adds a net that is not present', () => {
    const r = toggleTestPoint(['a'], 'n1');
    expect(r.refusal).toBeNull();
    expect(r.nets).toEqual(['a', 'n1']);
  });

  it('removes a net that is present', () => {
    const r = toggleTestPoint(['a', 'n1'], 'a');
    expect(r.refusal).toBeNull();
    expect(r.nets).toEqual(['n1']);
  });

  it('refuses a generated net name without touching the list', () => {
    const r = toggleTestPoint(['a'], '$abc$133$new_n12_');
    expect(r.nets).toBeNull();
    expect(r.refusal).toBe(generatedNetRefusal('$abc$133$new_n12_'));
    expect(r.refusal).toContain('cannot be recorded');
  });
});

describe('stableNamesFromPacked', () => {
  it('rebuilds the instance -> stable map from the packed view', () => {
    const map = stableNamesFromPacked([
      { refdes: 'U1', partNumber: 'p', cells: ['NOR2__a1b2c3', 'NOR2__d4e5f6'], instanceCells: ['g0', 'g1'], capacity: 2, spare: 0, rationale: '' },
      { refdes: 'U2', partNumber: 'p', cells: ['NAND2__99aabb'], instanceCells: ['g2'], capacity: 1, spare: 0, rationale: '' },
    ]);
    expect(map).toEqual(STABLE);
  });
});

describe('regroupToPackage', () => {
  it('refuses when no build supplied the stable-name map, writing nothing', () => {
    const r = regroupToPackage(SPEC, CELLS, [], {}, 'g0', ['g1']);
    expect(r.text).toBeNull();
    expect(r.refusal).toBe(NO_BUILD_REFUSAL);
  });

  it('refuses a mixed-function regroup rather than writing an override', () => {
    const r = regroupToPackage(SPEC, CELLS, [], STABLE, 'g0', ['g2']);
    expect(r.text).toBeNull();
    expect(r.refusal).toContain('not the same function');
  });

  it('writes stable names, never the instance names', () => {
    const r = regroupToPackage(SPEC, CELLS, [], STABLE, 'g0', ['g1']);
    expect(r.refusal).toBeNull();
    expect(r.text).not.toBeNull();
    expect(r.text).toContain('force_groups');
    expect(r.text).toContain('NOR2__a1b2c3');
    expect(r.text).toContain('NOR2__d4e5f6');
    // The rendered SVG is keyed by instance names; persisting one is the bug
    // this guard exists to prevent.
    expect(r.text).not.toMatch(/force_groups[\s\S]*\bg0\b/);
    expect(r.text).not.toMatch(/force_groups[\s\S]*\bg1\b/);
  });
});

describe('applyEditAffordances', () => {
  it('stamps a wire with the field and value a click will write', () => {
    const root = sheet(
      `<line data-gp-net="a"></line>` +
        `<g id="cell_a"></g>` +
        `<g id="cell_$g1"></g>`,
    );
    applyEditAffordances(root, {
      active: true,
      testPoints: ['n1'],
      inputs: [{ name: 'a', sync: false }],
      gates: new Set(['$g1']),
      showPacked: true,
    });
    expect(root.querySelector('[data-gp-net="a"]')?.getAttribute('title')).toBe(
      'test_points: add {net: a}',
    );
    expect(root.querySelector('#cell_a')?.getAttribute('title')).toBe(
      'inputs[a].sync: false → true',
    );
    expect(root.querySelector('[id="cell_$g1"]')?.getAttribute('title')).toContain('force_groups');
  });

  it('names the generated-net refusal in the title rather than offering a write', () => {
    const root = sheet(`<line data-gp-net="$abc$133$new_n12_"></line>`);
    applyEditAffordances(root, {
      active: true,
      testPoints: [],
      inputs: [],
      gates: new Set(),
      showPacked: false,
    });
    const title = root.querySelector('[data-gp-net]')?.getAttribute('title') ?? '';
    expect(title).toContain('cannot be recorded');
  });

  it('removes every stamp when editing is off', () => {
    const root = sheet(`<line data-gp-net="a"></line><g id="cell_a"></g>`);
    applyEditAffordances(root, {
      active: true,
      testPoints: [],
      inputs: [{ name: 'a', sync: false }],
      gates: new Set(),
      showPacked: false,
    });
    expect(root.querySelector('[data-gp-net]')?.hasAttribute('data-gp-edit')).toBe(true);

    applyEditAffordances(root, {
      active: false,
      testPoints: [],
      inputs: [{ name: 'a', sync: false }],
      gates: new Set(),
      showPacked: false,
    });
    expect(root.querySelector('[data-gp-net]')?.hasAttribute('data-gp-edit')).toBe(false);
    expect(root.querySelector('[data-gp-net]')?.hasAttribute('title')).toBe(false);
    expect(root.querySelector('#cell_a')?.hasAttribute('title')).toBe(false);
  });
});

describe('regroupToPackage — a partial stable-name map is refused, not patched', () => {
  const SPEC = 'name: p\ntiming_model: synchronous\nencoding: one_hot\ninitial: S0\n';
  const CELLS = [
    { name: '$abc$148$aaa', func: 'NAND2' },
    { name: '$abc$148$bbb', func: 'NAND2' },
  ];

  function packed(): PackedView['packages'] {
    return [
      { refdes: 'U1', partNumber: '74AUP2G00', cells: ['NAND2__stable_a'],
        instanceCells: ['$abc$148$aaa'], capacity: 2, spare: 1, rationale: '' },
      { refdes: 'U2', partNumber: '74AUP1G00', cells: ['NAND2__stable_b'],
        instanceCells: ['$abc$148$bbb'], capacity: 1, spare: 0, rationale: '' },
    ];
  }

  it('never writes an ABC instance name when one cell is unmapped', () => {
    // A packed view that does not cover every gate in the mapped netlist —
    // a stale overlay, or a gate in no package. The map is NOT empty, so the
    // all-or-nothing guard passes and the old `?? name` fallback wrote
    //     - [NAND2__stable_a, "$abc$148$bbb"]
    // straight into design.yaml. The packer refuses that on the next build,
    // and ABC renumbers instance names every synthesis, so if it did not it
    // would name a different gate.
    const stable = stableNamesFromPacked(packed());
    delete stable['$abc$148$bbb'];

    const out = regroupToPackage(SPEC, CELLS, [], stable, '$abc$148$aaa', ['$abc$148$bbb']);

    expect(out.text).toBeNull();
    expect(out.refusal).toContain('$abc$148$bbb');
    expect(out.refusal).toMatch(/stable name/);
  });

  it('writes stable names only when every cell maps', () => {
    const out = regroupToPackage(SPEC, CELLS, [], stableNamesFromPacked(packed()),
      '$abc$148$aaa', ['$abc$148$bbb']);
    expect(out.refusal).toBeNull();
    expect(out.text ?? '').not.toMatch(/\$abc\$/);
    expect(out.text ?? '').toContain('NAND2__stable_a');
  });
});
