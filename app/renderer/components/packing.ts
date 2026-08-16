/**
 * Pure packing-group model for the C13 view (§12 C5, §C13).
 *
 * The core owns packing: it groups mapped cells into physical packages and
 * refuses a group whose cells are not the same function. This module is the
 * renderer's *editing* model of that — the same rule, mirrored, so a drag that
 * the core would reject is rejected here with the same message rather than
 * silently persisted as an override.
 *
 * The renderer's only cell identity is the mapped-netlist instance name
 * (`write_json` cell key), which is what `packing.force_groups` names. The
 * function identity of a cell is its Liberty cell `type` (e.g. `NOR2`): two
 * mapped cells are the same function iff they share a `type`, which is exactly
 * the packer's `_pack_key` for this library.
 */

export interface PackingCell {
  name: string;
  /** Function identity — the mapped cell's Liberty `type`. */
  func: string;
}

export interface PackingGroup {
  id: string;
  func: string;
  /** Sorted deterministically. */
  cells: string[];
  /** True when this group is (or should be) a persisted `force_group`. */
  forced: boolean;
}

export interface RegroupResult {
  groups: PackingGroup[];
  error: string | null;
}

/** A refusal message that mirrors the packer's "mixes functions" rejection. */
export function mixedFunctionError(cellName: string, cellFunc: string, targetFunc: string): string {
  return (
    `cannot group ${cellName} (${cellFunc}) with ${targetFunc}: ` +
    `the packer refuses a group whose cells are not the same function`
  );
}

/**
 * Build the group model from the mapped cells and any persisted `force_groups`.
 * Force groups are kept verbatim; every mapped cell not named by a force group
 * becomes its own singleton group.
 */
export function buildGroups(cells: PackingCell[], forceGroups: string[][]): PackingGroup[] {
  const funcByName = new Map(cells.map((c) => [c.name, c.func]));
  const inGroup = new Set<string>();
  const groups: PackingGroup[] = [];
  let idx = 0;

  for (const names of forceGroups) {
    const sorted = [...new Set(names)].sort();
    if (sorted.length === 0) continue;
    const funcs = new Set(
      sorted.map((n) => funcByName.get(n)).filter((f): f is string => f !== undefined && f !== ''),
    );
    const func = funcs.size === 1 ? [...funcs][0] : '';
    groups.push({ id: `g${idx++}`, func, cells: sorted, forced: sorted.length > 1 });
    for (const n of sorted) inGroup.add(n);
  }

  const rest = cells
    .filter((c) => !inGroup.has(c.name))
    .map((c) => c.name)
    .sort();
  for (const name of rest) {
    groups.push({ id: `g${idx++}`, func: funcByName.get(name) ?? '', cells: [name], forced: false });
  }

  return groups;
}

/**
 * Move `cellName` into `targetGroupId`. Refuses (returns `error`) when the
 * move would put two different functions in one group — the same refusal the
 * packer makes, surfaced rather than dropped.
 */
export function regroup(
  groups: PackingGroup[],
  cellName: string,
  targetGroupId: string,
): RegroupResult {
  const source = groups.find((g) => g.cells.includes(cellName));
  const target = groups.find((g) => g.id === targetGroupId);

  if (!source) {
    return { groups, error: `unknown cell ${cellName}` };
  }
  if (!target) {
    return { groups, error: `unknown group ${targetGroupId}` };
  }
  if (source.id === target.id) {
    return { groups, error: null };
  }

  const cellFunc = source.func;
  if (target.func && cellFunc && target.func !== cellFunc) {
    return {
      groups,
      error: mixedFunctionError(cellName, cellFunc, target.func),
    };
  }

  const sourceCells = source.cells.filter((c) => c !== cellName);
  const targetCells = [...target.cells, cellName].sort();

  const next: PackingGroup[] = [];
  for (const g of groups) {
    if (g.id === source.id) {
      if (sourceCells.length > 0) {
        next.push({
          id: g.id,
          func: g.func,
          cells: sourceCells,
          forced: sourceCells.length > 1,
        });
      }
    } else if (g.id === target.id) {
      next.push({
        id: g.id,
        func: target.func || cellFunc,
        cells: targetCells,
        forced: targetCells.length > 1,
      });
    } else {
      next.push(g);
    }
  }

  return { groups: next, error: null };
}

/**
 * The persisted `packing.force_groups` for a set of groups: only the groups with
 * two or more cells, in a deterministic order.
 */
export function groupsToForceGroups(groups: PackingGroup[]): string[][] {
  return groups
    .filter((g) => g.cells.length > 1)
    .map((g) => [...g.cells])
    .sort((a, b) => {
      const ka = a.join('\u0000');
      const kb = b.join('\u0000');
      return ka < kb ? -1 : ka > kb ? 1 : 0;
    });
}

/**
 * A per-group rationale line. This mirrors the *shape* of the core's rationale
 * (`forced group: …`, `unpacked: one … per package`) but is derived locally:
 * the exact rationale string is emitted by the core in `report.md`, not on the
 * IPC contract (§C13 gap — see BUILD-NOTES).
 */
export function rationaleFor(group: PackingGroup): string {
  if (group.cells.length > 1) {
    return `forced group: ${group.func || '?'} holds ${group.cells.length} gates`;
  }
  return `unpacked: one ${group.func || '?'} per package`;
}
