/**
 * DOM decoration of the rendered netlistsvg sheet (§C12).
 *
 * netlistsvg lays the schematic out once. Everything that changes afterwards —
 * the per-vector signal values (§24.2, M16), the refdes labels, the flow
 * animation — is applied by walking that one layout and setting attributes on
 * it, exactly as the §15.2 cross-highlight already does with `gp-sel`. Nothing
 * here re-runs layout, and nothing here calls `getBBox`, so it works under
 * jsdom as well as in the renderer.
 *
 * ## Why the labels are written here rather than by the skin
 *
 * netlistsvg's skin format has a `s:attribute` mechanism for exactly this, and
 * `prepareNetlist.ts` does supply `gp_refdes`/`gp_type`. It does not work on a
 * gatepack netlist, and the reason is a bug in the *shipped build* rather than
 * anything about our data: `Cell.render` resolves a label's attribute name with
 *
 *     label.id.split('.')[2]
 *
 * in `built/Cell.js` (the TypeScript source says `[length - 1]`; the published
 * `built/` tree is older than `lib/`). The label id is
 * `<instance>.label.<attribute>`, so index 2 is only the attribute name when
 * the instance name contains no dot. Post-`abc` instance names look like
 *
 *     $abc$133$auto$blifparse.cc:386:parse_blif$134
 *
 * — the `blifparse.cc` in Yosys's own generated name carries a dot, index 2
 * lands on the literal `label`, no text node matches it, and every gate kept
 * the skin's placeholder. Writing the labels here is a one-line DOM pass that
 * does not depend on netlistsvg's build, and it keeps the instance names
 * intact, which the packed layer and the §15.2 selection spine both key on.
 */

import type { Bit } from '../design/expr';
import type { NetValues } from '../mapped/sim';
import { netBitIndices } from '../worker/schematicOverlay';

export interface CellLabel {
  /** Package refdes (`U3`), or null when the cell is in no package. */
  refdes: string | null;
  /** Library cell type (`NAND2`). */
  type: string;
}

/**
 * Fill the `gp_refdes`/`gp_type` texts the skin left as placeholders.
 *
 * A cell with no refdes gets an empty label rather than a plausible one: an
 * unpacked gate is a real state (the packed view may not have loaded, or the
 * cell may genuinely be outside every package) and inventing `U?` in the sheet
 * would read as a designator.
 */
export function applyCellLabels(
  root: ParentNode,
  labels: Map<string, CellLabel>,
): number {
  let applied = 0;
  for (const group of Array.from(root.querySelectorAll('g[id^="cell_"]'))) {
    const id = group.getAttribute('id');
    if (id === null) continue;
    const instance = id.slice('cell_'.length);
    const label = labels.get(instance);
    for (const text of Array.from(group.querySelectorAll('text[s\\:attribute]'))) {
      const attribute = text.getAttribute('s:attribute');
      if (attribute === 'gp_refdes') {
        text.textContent = label?.refdes ?? '';
        applied += 1;
      } else if (attribute === 'gp_type') {
        text.textContent = label?.type ?? '';
        applied += 1;
      }
    }
  }
  return applied;
}

/**
 * Net value keyed by the `net_<bits>` class netlistsvg tags wires with.
 *
 * Several names can share one bit — `match`, `match_int` and `state_S3` are all
 * bit 5 in the sequence-detector netlist — so a known value always wins over an
 * `x` from an alias that the evaluator never reached. They cannot disagree on a
 * known bit: same bits, same wire.
 */
export function netValueClasses(
  netlist: unknown,
  values: NetValues,
): Map<string, Bit> {
  const out = new Map<string, Bit>();
  for (const [name, bits] of netBitIndices(netlist)) {
    if (bits.length === 0) continue;
    const value = values[name];
    if (value === undefined) continue;
    const cls = `net_${bits.join(',')}`;
    const held = out.get(cls);
    if (held === undefined || (held === 'x' && value !== 'x')) out.set(cls, value);
  }
  return out;
}

/** Net *name* per `net_<bits>` class, for the hover readout. */
export function netNameClasses(netlist: unknown): Map<string, string> {
  const out = new Map<string, string>();
  for (const [name, bits] of netBitIndices(netlist)) {
    if (bits.length === 0) continue;
    const cls = `net_${bits.join(',')}`;
    const held = out.get(cls);
    // Prefer the name an engineer wrote (`match`) over Yosys's generated ones
    // (`$abc$133$new_n12_`, `$0\state_S0[0:0]`), and the shorter of two written
    // names (`match` over `match_int`), so the readout names the signal the
    // spec names wherever one exists.
    if (held === undefined) {
      out.set(cls, name);
      continue;
    }
    const heldGenerated = held.startsWith('$');
    const nameGenerated = name.startsWith('$');
    if (heldGenerated && !nameGenerated) out.set(cls, name);
    else if (heldGenerated === nameGenerated && name.length < held.length) out.set(cls, name);
  }
  return out;
}

export interface ValueDecoration {
  /** `net_<bits>` -> the bit on that wire. */
  values: Map<string, Bit>;
  /** `net_<bits>` -> display name for the hover readout. */
  names: Map<string, string>;
  /** Net names carrying a clock; their wires never march. */
  clockClasses: Set<string>;
}

/**
 * Stamp `data-gp-value` (and `data-gp-net`) on every wire element.
 *
 * Wires are the `line`/`path`/`circle` elements netlistsvg tags `net_<bits>`;
 * the junction dots carry the same class, so a junction lights with its net.
 * Elements whose net has no value are stamped `x` rather than left bare, so the
 * CSS can distinguish "unknown" from "not part of a valued sheet" — a wire
 * drawn dim must mean *measured low*, never *not measured*.
 */
export function applyNetValues(root: ParentNode, decoration: ValueDecoration): number {
  let stamped = 0;
  for (const el of Array.from(root.querySelectorAll('[class*="net_"]'))) {
    const classes = (el.getAttribute('class') ?? '').split(/\s+/);
    const cls = classes.find((c) => c.startsWith('net_'));
    if (cls === undefined) continue;
    el.setAttribute('data-gp-value', decoration.values.get(cls) ?? 'x');
    const name = decoration.names.get(cls);
    if (name !== undefined) el.setAttribute('data-gp-net', name);
    if (decoration.clockClasses.has(cls)) el.setAttribute('data-gp-clock', '');
    else el.removeAttribute('data-gp-clock');
    stamped += 1;
  }
  return stamped;
}

/** Class marking an invisible click target, excluded from every visual pass. */
export const HIT_CLASS = 'gp-hit';

/** Layer holding the click targets, so one pass can remove them all. */
const HIT_LAYER = 'gp-hit-layer';

/**
 * Half-width, in SVG user units, of a wire's click target.
 *
 * Measured, not guessed: `hit-tolerance.probe.spec.ts` found netlistsvg wires
 * rendered at `stroke-width: 1px` with no wider hit region, so a click had to
 * land within **0.5 px** of the line's centre to select it. That is roughly a
 * quarter of the ~4 px of hand tremor a mouse user has at rest, so selecting a
 * wire was a game of patience rather than an interaction.
 *
 * 5 gives a 10 px-wide target, the low end of the usual 24-44 px touch
 * guidance scaled for a precise pointing device, and narrow enough that two
 * wires on netlistsvg's grid do not overlap into a coin toss.
 *
 * The width is also pinned in `views.css` with `!important`, because the value
 * overlay's `[data-gp-value]` rules out-rank a presentation attribute and were
 * silently shrinking every target back to 1 px. Change both together; the
 * stylesheet is what actually decides.
 */
export const HIT_HALF_WIDTH = 5;

/**
 * Give every wire an invisible, generously wide click target.
 *
 * A stroke's hit region is exactly the painted stroke, so a 1 px line is a 1 px
 * target and there is no CSS that widens one without widening the other. The
 * fix is a second copy of each wire, drawn with a fat transparent stroke and
 * `pointer-events: stroke`, which hit-tests the stroke area regardless of paint
 * or visibility.
 *
 * The copies carry the original's `net_<bits>` class so `netClassOf`, the
 * hover highlight and the §15.2 selection spine all resolve through them with
 * no change to the handlers. They are marked {@link HIT_CLASS} so the passes
 * that *draw* something — the flow dots — can skip them, and so the stylesheet
 * can hold them transparent even under the selection rules.
 *
 * They go in a layer appended last so they sit above the sheet: a target
 * underneath the drawing would be shadowed by whatever it is a target for.
 */
export function applyHitTargets(root: ParentNode): number {
  clearHitTargets(root);
  const svg = root.querySelector('svg');
  if (!svg) return 0;

  const wires = Array.from(svg.querySelectorAll('line[class*="net_"], path[class*="net_"]'));
  if (wires.length === 0) return 0;

  const layer = svg.ownerDocument.createElementNS('http://www.w3.org/2000/svg', 'g');
  layer.setAttribute('class', HIT_LAYER);
  // The layer must not swallow clicks in the gaps between wires.
  layer.setAttribute('pointer-events', 'none');

  let made = 0;
  for (const wire of wires) {
    if (wire.classList.contains(HIT_CLASS)) continue;
    const hit = wire.cloneNode(false) as Element;
    // A clone inherits the id; two elements with one id breaks `getElementById`
    // and the selection spine's `cell_<instance>` lookups.
    hit.removeAttribute('id');
    hit.setAttribute('class', `${wire.getAttribute('class') ?? ''} ${HIT_CLASS}`.trim());
    hit.setAttribute('stroke', 'transparent');
    hit.setAttribute('stroke-width', String(HIT_HALF_WIDTH * 2));
    hit.setAttribute('fill', 'none');
    hit.setAttribute('pointer-events', 'stroke');
    layer.appendChild(hit);
    made += 1;
  }
  svg.appendChild(layer);
  return made;
}

/** Remove the click-target layer. */
export function clearHitTargets(root: ParentNode): void {
  for (const layer of Array.from(root.querySelectorAll(`.${HIT_LAYER}`))) {
    layer.remove();
  }
}

/** Remove every value stamp, for when the overlay is switched off. */
export function clearNetValues(root: ParentNode): void {
  for (const el of Array.from(root.querySelectorAll('[data-gp-value]'))) {
    el.removeAttribute('data-gp-value');
    el.removeAttribute('data-gp-net');
    el.removeAttribute('data-gp-clock');
  }
  clearFlowDots(root);
}

/** Class of the generated group holding the travelling-dot copies. */
const FLOW_LAYER = 'gp-flow-layer';

/**
 * Falstad-style travelling dots along the wires that are carrying a one.
 *
 * The Circuit Simulator's most legible idea is that the *wire* stays a plain
 * solid line and the movement is carried by discrete dots running along it.
 * A dashed wire says "this connection is provisional"; a solid wire with dots
 * on it says "this connection is real and something is moving through it",
 * which is the thing worth showing. Dashes are kept for exactly one meaning
 * here — an unknown net — so the two never compete.
 *
 * Each high wire is *copied* into an overlay group and the copy is drawn with
 * `stroke-dasharray: 0 <gap>` and a round linecap: a zero-length dash with a
 * round cap is a dot, repeated every `gap` units along the path, and animating
 * the offset walks them. The original wire is untouched, so the layout, the
 * hit-testing and the §15.2 selection all still work on it.
 *
 * Two honest limits, both inherited rather than chosen:
 *
 *  - **Direction** is the order netlistsvg drew each segment in, which is
 *    source-to-sink for its orthogonal routing but is not a claim this module
 *    can verify per segment.
 *  - **Speed is constant.** Falstad varies dot speed with current magnitude;
 *    a logic netlist has no current to vary it by, and inventing a speed would
 *    be inventing a measurement.
 */
export function applyFlowDots(root: ParentNode): number {
  clearFlowDots(root);
  const svg = root.querySelector('svg');
  if (svg === null) return 0;

  const wires = Array.from(
    svg.querySelectorAll(
      'line[data-gp-value="1"]:not([data-gp-clock]):not(.gp-hit), ' +
        'path[data-gp-value="1"]:not([data-gp-clock]):not(.gp-hit)',
    ),
  );
  if (wires.length === 0) return 0;

  const layer = svg.ownerDocument.createElementNS('http://www.w3.org/2000/svg', 'g');
  layer.setAttribute('class', FLOW_LAYER);
  // The dots are decoration over a wire that is already hit-testable; letting
  // them swallow pointer events would break the hover readout on exactly the
  // nets most worth hovering.
  layer.setAttribute('pointer-events', 'none');
  layer.setAttribute('aria-hidden', 'true');

  for (const wire of wires) {
    const dot = wire.cloneNode(false) as Element;
    dot.removeAttribute('id');
    // No `net_…` class on the copy: the value pass finds wires by that class,
    // and a copy that answered to it would be re-stamped and re-copied.
    dot.setAttribute('class', 'gp-flow');
    dot.removeAttribute('data-gp-net');
    dot.removeAttribute('data-gp-value');
    dot.removeAttribute('style');
    layer.appendChild(dot);
  }
  svg.appendChild(layer);
  return wires.length;
}

/**
 * Light every segment of one net, the way Falstad highlights a whole node when
 * you point at any part of it.
 *
 * A schematic net is drawn as many disjoint segments plus its junction dots, so
 * highlighting only the element under the pointer tells you about a line, not
 * about a signal. Pass `null` to clear.
 */
export function highlightNet(root: ParentNode, netClass: string | null): number {
  for (const el of Array.from(root.querySelectorAll('[data-gp-hover]'))) {
    el.removeAttribute('data-gp-hover');
  }
  if (netClass === null) return 0;
  const peers = Array.from(root.querySelectorAll(`[class~="${netClass}"]`));
  for (const el of peers) el.setAttribute('data-gp-hover', '');
  return peers.length;
}

/** The `net_<bits>` class of an element, or null if it is not a wire. */
export function netClassOf(el: Element | null): string | null {
  const classes = (el?.getAttribute('class') ?? '').split(/\s+/);
  return classes.find((c) => c.startsWith('net_')) ?? null;
}

/** Remove the travelling-dot overlay. */
export function clearFlowDots(root: ParentNode): void {
  for (const layer of Array.from(root.querySelectorAll(`.${FLOW_LAYER}`))) {
    layer.remove();
  }
}

/**
 * The `net_<bits>` classes of the clock nets, so `applyNetValues` can exempt
 * them from the flow animation.
 */
export function clockNetClasses(netlist: unknown, clocks: Set<string>): Set<string> {
  const out = new Set<string>();
  for (const [name, bits] of netBitIndices(netlist)) {
    if (bits.length > 0 && clocks.has(name)) out.add(`net_${bits.join(',')}`);
  }
  return out;
}
