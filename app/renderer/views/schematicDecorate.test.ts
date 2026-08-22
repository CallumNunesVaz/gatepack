import { describe, expect, it } from 'vitest';
import {
  applyCellLabels,
  applyFlowDots,
  applyNetValues,
  clearNetValues,
  highlightNet,
  netClassOf,
  clockNetClasses,
  netNameClasses,
  netValueClasses,
} from './schematicDecorate';
import type { Bit } from '../design/expr';

const NETLIST = {
  modules: {
    top: {
      ports: {
        a: { direction: 'input', bits: [0] },
        match: { direction: 'output', bits: [5] },
      },
      netnames: {
        a: { bits: [0] },
        $abc$1$new_n7_: { bits: [7] },
        match: { bits: [5] },
        match_int: { bits: [5] },
        state_S3: { bits: [5] },
        clk: { bits: [9] },
      },
    },
  },
};

function sheet(html: string): HTMLElement {
  const root = document.createElement('div');
  root.innerHTML = html;
  return root;
}

describe('applyCellLabels', () => {
  it('fills the skin placeholders that netlistsvg could not substitute', () => {
    // The instance name carries a dot (Yosys writes `blifparse.cc:386`), which
    // is exactly what defeats netlistsvg's own `label.id.split('.')[2]`.
    const root = sheet(`
      <g id="cell_$abc$1$auto$blifparse.cc:386:parse_blif$10">
        <text s:attribute="gp_refdes">U?</text>
        <text s:attribute="gp_type">AND2</text>
      </g>`);
    const applied = applyCellLabels(
      root,
      new Map([['$abc$1$auto$blifparse.cc:386:parse_blif$10', { refdes: 'U3', type: 'NAND2' }]]),
    );
    expect(applied).toBe(2);
    const texts = Array.from(root.querySelectorAll('text')).map((t) => t.textContent);
    expect(texts).toEqual(['U3', 'NAND2']);
  });

  it('leaves an unpacked cell with an empty refdes, never an invented one', () => {
    const root = sheet(`
      <g id="cell_g1">
        <text s:attribute="gp_refdes">U?</text>
        <text s:attribute="gp_type">AND2</text>
      </g>`);
    applyCellLabels(root, new Map([['g1', { refdes: null, type: 'AND2' }]]));
    const texts = Array.from(root.querySelectorAll('text')).map((t) => t.textContent);
    expect(texts).toEqual(['', 'AND2']);
  });

  it('blanks the labels of a cell it has no entry for', () => {
    const root = sheet(`
      <g id="cell_ghost"><text s:attribute="gp_refdes">U?</text></g>`);
    applyCellLabels(root, new Map());
    expect(root.querySelector('text')?.textContent).toBe('');
  });
});

describe('netValueClasses', () => {
  it('keys values by the net_<bits> class netlistsvg tags wires with', () => {
    const values: Record<string, Bit> = { a: '1', $abc$1$new_n7_: '0' };
    const classes = netValueClasses(NETLIST, values);
    expect(classes.get('net_0')).toBe('1');
    expect(classes.get('net_7')).toBe('0');
  });

  it('lets a known value win over an alias the evaluator never reached', () => {
    // `match`, `match_int` and `state_S3` are all bit 5. Whichever name the
    // evaluator resolved is the value of that one wire; they cannot disagree.
    expect(netValueClasses(NETLIST, { match: 'x', state_S3: '1' } as Record<string, Bit>).get('net_5')).toBe('1');
    expect(netValueClasses(NETLIST, { state_S3: '1', match: 'x' } as Record<string, Bit>).get('net_5')).toBe('1');
  });
});

describe('netNameClasses', () => {
  it('prefers a written name over a Yosys-generated one', () => {
    expect(netNameClasses(NETLIST).get('net_7')).toBe('$abc$1$new_n7_');
    // Three written names share bit 5; the shortest is the one the spec uses.
    expect(netNameClasses(NETLIST).get('net_5')).toBe('match');
  });
});

describe('applyNetValues / clearNetValues', () => {
  const decoration = {
    values: new Map<string, Bit>([['net_0', '1'], ['net_5', '0']]),
    names: new Map([['net_0', 'a'], ['net_5', 'match']]),
    clockClasses: new Set(['net_9']),
  };

  it('stamps every wire, including one whose net has no value', () => {
    const root = sheet(`
      <line class="net_0"></line>
      <circle class="net_0"></circle>
      <line class="net_5"></line>
      <line class="net_7"></line>`);
    expect(applyNetValues(root, decoration)).toBe(4);
    const stamps = Array.from(root.querySelectorAll('[data-gp-value]')).map((el) =>
      el.getAttribute('data-gp-value'),
    );
    // A wire with no value is an explicit `x`, never left bare — "not measured"
    // must be distinguishable from "measured low".
    expect(stamps).toEqual(['1', '1', '0', 'x']);
    expect(root.querySelector('.net_0')?.getAttribute('data-gp-net')).toBe('a');
  });

  it('marks clock wires so the flow animation can skip them', () => {
    const root = sheet('<line class="net_9"></line><line class="net_0"></line>');
    applyNetValues(root, decoration);
    expect(root.querySelector('.net_9')?.hasAttribute('data-gp-clock')).toBe(true);
    expect(root.querySelector('.net_0')?.hasAttribute('data-gp-clock')).toBe(false);
  });

  it('removes every stamp when the layer is switched off', () => {
    const root = sheet('<line class="net_0"></line>');
    applyNetValues(root, decoration);
    clearNetValues(root);
    expect(root.querySelectorAll('[data-gp-value]')).toHaveLength(0);
    expect(root.querySelectorAll('[data-gp-net]')).toHaveLength(0);
  });
});

describe('clockNetClasses', () => {
  it('resolves clock net names to their wire classes', () => {
    expect([...clockNetClasses(NETLIST, new Set(['clk']))]).toEqual(['net_9']);
  });
});

describe('applyFlowDots', () => {
  const decoration = {
    values: new Map<string, Bit>([['net_0', '1'], ['net_5', '0'], ['net_9', '1']]),
    names: new Map([['net_0', 'a'], ['net_5', 'match'], ['net_9', 'clk']]),
    clockClasses: new Set(['net_9']),
  };

  function svgSheet(): HTMLElement {
    return sheet(`<svg>
      <line class="net_0"></line>
      <path class="net_0"></path>
      <line class="net_5"></line>
      <line class="net_9"></line>
    </svg>`);
  }

  it('copies each high wire into an overlay rather than restyling it', () => {
    const root = svgSheet();
    applyNetValues(root, decoration);
    expect(applyFlowDots(root)).toBe(2);
    const layer = root.querySelector('.gp-flow-layer');
    expect(layer?.children).toHaveLength(2);
    // The originals keep their value stamp, their net name and their class, so
    // hit-testing and the §15.2 selection still work on them.
    expect(root.querySelector('line.net_0')?.getAttribute('data-gp-value')).toBe('1');
  });

  it('leaves clock wires and low wires alone', () => {
    const root = svgSheet();
    applyNetValues(root, decoration);
    applyFlowDots(root);
    const copies = Array.from(root.querySelectorAll('.gp-flow-layer > *'));
    expect(copies).toHaveLength(2);
    // `net_9` is high but is the clock; `net_5` is low.
    expect(copies.some((c) => c.getAttribute('class')?.includes('net_'))).toBe(false);
  });

  it('does not let its copies be re-stamped or re-copied', () => {
    const root = svgSheet();
    applyNetValues(root, decoration);
    applyFlowDots(root);
    // A second full pass must be idempotent: the copies carry no `net_…` class,
    // so the value pass cannot find them and the flow pass rebuilds from the
    // real wires only.
    expect(applyNetValues(root, decoration)).toBe(4);
    expect(applyFlowDots(root)).toBe(2);
    expect(root.querySelectorAll('.gp-flow-layer')).toHaveLength(1);
  });

  it('is removed when the value layer is cleared', () => {
    const root = svgSheet();
    applyNetValues(root, decoration);
    applyFlowDots(root);
    clearNetValues(root);
    expect(root.querySelectorAll('.gp-flow-layer')).toHaveLength(0);
  });
});

describe('highlightNet', () => {
  it('lights every segment of the net, not the one under the pointer', () => {
    const root = sheet(`
      <line class="net_3"></line>
      <line class="net_3"></line>
      <circle class="net_3"></circle>
      <line class="net_4"></line>`);
    expect(highlightNet(root, 'net_3')).toBe(3);
    expect(root.querySelectorAll('[data-gp-hover]')).toHaveLength(3);
    expect(root.querySelector('.net_4')?.hasAttribute('data-gp-hover')).toBe(false);
  });

  it('clears on null', () => {
    const root = sheet('<line class="net_3"></line>');
    highlightNet(root, 'net_3');
    expect(highlightNet(root, null)).toBe(0);
    expect(root.querySelectorAll('[data-gp-hover]')).toHaveLength(0);
  });

  it('reads a wire class off an element, and nothing off a gate body', () => {
    const root = sheet('<line class="net_3 gp-sel"></line><rect class="cell_g1"></rect>');
    expect(netClassOf(root.querySelector('line'))).toBe('net_3');
    expect(netClassOf(root.querySelector('rect'))).toBeNull();
    expect(netClassOf(null)).toBeNull();
  });
});
