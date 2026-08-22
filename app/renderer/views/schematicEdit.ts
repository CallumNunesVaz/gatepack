/**
 * Pure edit decisions for the schematic's §C12 spec-editing surface.
 *
 * The schematic renders a post-`abc` synthesised netlist, and the map from
 * gates back to the FSM spec is not invertible. So the only edits it offers are
 * *spec facts* that already have a home in `design.yaml` — test points, an
 * input's synchroniser, and a packing override — and every one of them is
 * written through the same `model.ts` text-splice editors the other views use.
 *
 * This module holds the decisions (and the refusals) separately from the DOM so
 * they are unit-testable without a render cycle. The two name spaces matter
 * here and are deliberately NOT re-derived:
 *
 *  - net/instance names the rendered SVG is keyed by (`data-gp-net`,
 *    `id="cell_<instance>"`) are what Yosys emitted — `$abc$…` instance names
 *    are renumbered by every synthesis;
 *  - `test_points[].net` and `packing.force_groups` are resolved against names
 *    that survive synthesis (written net names, stable cone-hash names).
 *
 * A generated name is refused with a visible reason, never written, and never
 * replaced by something weaker.
 */

import { buildGroups, groupsToForceGroups, regroup, type PackingCell, type PackingGroup } from '../components/packing';
import { setPackingForceGroups } from '../design/model';
import type { PackedView } from '../../shared/api';

/** The refusal BomView's `handleRegroup` emits when no build has supplied the
 * instance -> stable name map. Kept identical so the two surfaces agree. */
export const NO_BUILD_REFUSAL =
  'Run a build before regrouping — an override recorded now would name ' +
  'gates that do not survive the next synthesis.';

/**
 * True when a net name is Yosys-generated and therefore not a stable identifier
 * worth writing into `design.yaml`. Generated names start with `$`
 * (`$abc$133$new_n12_`, `$0\state_S0[0:0]`); written names (`match`, `a`) do not.
 */
export function isGeneratedNetName(name: string): boolean {
  return name.startsWith('$');
}

export function generatedNetRefusal(name: string): string {
  return (
    `${JSON.stringify(name)} is a Yosys-generated net name, renumbered by every ` +
    `synthesis — it cannot be recorded as a test point in design.yaml.`
  );
}

export interface TestPointEdit {
  /** The new test-point list to write, or null when the edit was refused. */
  nets: string[] | null;
  refusal: string | null;
}

/**
 * Toggle one net's membership in the test-point list. A generated name is
 * refused (the membership is computed against the *display* name the hover
 * readout chose, which is a written name wherever one exists — so refusing the
 * `$` fallback never loses a legitimate edit).
 */
export function toggleTestPoint(current: string[], net: string): TestPointEdit {
  if (isGeneratedNetName(net)) {
    return { nets: null, refusal: generatedNetRefusal(net) };
  }
  const nets = current.includes(net)
    ? current.filter((n) => n !== net)
    : [...current, net];
  return { nets, refusal: null };
}

export interface RegroupEdit {
  /** The edited text to write, or null when the edit was refused. */
  text: string | null;
  refusal: string | null;
}

/**
 * Rebuild the instance -> stable cell-name map from the packed view.
 *
 * `PackedView.packages[].cells` are STABLE names and `.instanceCells` are the
 * corresponding mapped-netlist instance names, in the same order (see
 * `gatepack/api.py::packed_view_payload`). The build's `stableCellNames` field
 * is the same map keyed by instance; deriving it from the packed layer here
 * keeps the schematic from needing a second build task. A design with no
 * packed view therefore yields an empty map — which is exactly the "no build
 * result" state the regroup guard refuses on.
 */
export function stableNamesFromPacked(packages: PackedView['packages']): Record<string, string> {
  const out: Record<string, string> = {};
  for (const pkg of packages) {
    const n = Math.min(pkg.cells.length, pkg.instanceCells.length);
    for (let i = 0; i < n; i += 1) {
      out[pkg.instanceCells[i]] = pkg.cells[i];
    }
  }
  return out;
}

/** The group id (in BomView's `buildGroups` model) holding a package's gates. */
function groupIdForPackage(groups: PackingGroup[], instanceCells: string[]): string | null {
  const target = new Set(instanceCells);
  for (const g of groups) {
    if (g.cells.some((c) => target.has(c))) return g.id;
  }
  return null;
}

/**
 * Regroup a gate into the package holding `targetInstanceCells`, and return the
 * edited `design.yaml` text. Mirrors `BomView.handleRegroup`: the same
 * `buildGroups`/`regroup`/`groupsToForceGroups` pipeline, the same stable-name
 * translation, and the same refusal when no build has supplied the map.
 *
 * `sourceInstance` and `targetInstanceCells` are mapped-netlist instance names
 * (what the rendered SVG is keyed by); `stableNames` is instance -> stable.
 */
export function regroupToPackage(
  specText: string,
  cells: PackingCell[],
  forceGroups: string[][],
  stableNames: Record<string, string>,
  sourceInstance: string,
  targetInstanceCells: string[],
): RegroupEdit {
  const groups = buildGroups(cells, forceGroups);
  const targetGroupId = groupIdForPackage(groups, targetInstanceCells);
  if (targetGroupId === null) {
    return { text: null, refusal: 'that package holds no gate that can be grouped here' };
  }
  const result = regroup(groups, sourceInstance, targetGroupId);
  if (result.error) {
    return { text: null, refusal: result.error };
  }
  if (Object.keys(stableNames).length === 0) {
    return { text: null, refusal: NO_BUILD_REFUSAL };
  }
  // Every name must translate. A partial map is not a lesser version of a whole
  // one: falling back to the instance name writes `$abc$148$…` into
  // `packing.force_groups`, which the packer refuses on the next build — and if
  // it did not, ABC renumbers those every synthesis, so it would name a
  // *different gate*. Refuse and say which cell, rather than write a group that
  // is half right.
  const next: string[][] = [];
  for (const group of groupsToForceGroups(result.groups)) {
    const mapped: string[] = [];
    for (const name of group) {
      const stable = stableNames[name];
      if (stable === undefined) {
        return {
          text: null,
          refusal:
            `${name} is not in the packed view, so it has no stable name to ` +
            'record — rebuild before regrouping.',
        };
      }
      mapped.push(stable);
    }
    next.push(mapped);
  }
  return { text: setPackingForceGroups(specText, next).text, refusal: null };
}

export interface EditAffordances {
  /** Editing is on; off removes every stamp. */
  active: boolean;
  /** Current test-point net names (for the add/remove preview). */
  testPoints: string[];
  /** Current inputs (name + sync), for the synchroniser preview. */
  inputs: Array<{ name: string; sync: boolean }>;
  /** Gate instance names — the gates a drag can move. */
  gates: Set<string>;
  /** Whether the packed layer is on (gates are only draggable then). */
  showPacked: boolean;
}

/**
 * Stamp the rendered sheet with the §C12 edit affordances, the way
 * `schematicDecorate.ts` stamps values: attributes only, no re-layout.
 *
 *  - every wire (`[data-gp-net]`) gets a `title` naming the test-point entry a
 *    click writes (or the generated-name refusal), plus `data-gp-edit`;
 *  - every input port (`cell_<port>`) gets a `title` naming the `inputs.sync`
 *    flip, plus `data-gp-edit`;
 *  - every gate gets a drag title when the packed layer is on.
 *
 * With `active: false` every stamp is removed, so the sheet is byte-for-byte
 * the read-only view it was before editing was turned on.
 */
export function applyEditAffordances(root: ParentNode, opts: EditAffordances): void {
  const testPointSet = new Set(opts.testPoints);
  const syncByName = new Map(opts.inputs.map((i) => [i.name, i.sync]));
  const inputNames = new Set(opts.inputs.map((i) => i.name));

  for (const el of Array.from(root.querySelectorAll('[data-gp-net]'))) {
    if (!opts.active) {
      el.removeAttribute('data-gp-edit');
      el.removeAttribute('title');
      continue;
    }
    const net = el.getAttribute('data-gp-net');
    if (net === null) continue;
    el.setAttribute('data-gp-edit', '');
    if (isGeneratedNetName(net)) {
      el.setAttribute('title', generatedNetRefusal(net));
    } else {
      el.setAttribute(
        'title',
        testPointSet.has(net)
          ? `test_points: remove {net: ${net}}`
          : `test_points: add {net: ${net}}`,
      );
    }
  }

  for (const g of Array.from(root.querySelectorAll('g[id^="cell_"]'))) {
    const id = g.getAttribute('id');
    if (id === null) continue;
    const name = id.slice('cell_'.length);
    if (!opts.active) {
      if (inputNames.has(name) || opts.gates.has(name)) {
        g.removeAttribute('data-gp-edit');
        g.removeAttribute('title');
      }
      continue;
    }
    if (inputNames.has(name)) {
      const sync = syncByName.get(name) ?? false;
      g.setAttribute('data-gp-edit', '');
      g.setAttribute('title', `inputs[${name}].sync: ${sync} → ${!sync}`);
    } else if (opts.gates.has(name) && opts.showPacked) {
      g.setAttribute('data-gp-edit', '');
      g.setAttribute('title', `drag into a package to record packing.force_groups`);
    }
  }
}
