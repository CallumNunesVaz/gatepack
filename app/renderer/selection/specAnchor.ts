/**
 * §15.2 selection -> spec line. Given a `Selection`, the `ProvenanceMap` and the
 * spec text, return the 1-based line of `design.yaml` the selection came from,
 * or `null`.
 *
 * Two independent routes, kept visibly distinct so the Inspector can tell the
 * user *how* it knows where the selection lives:
 *
 *  - **provenance** — a `cell`/`net` selection matches provenance entries whose
 *    `§15.1` pointer carries a line number (`design.yaml:42:transitions[2]`).
 *    Confidence is `exact` or `inferred` and is carried through, never
 *    flattened.
 *  - **structural** — a `state`/`transition`/`input`/`property` selection is
 *    located directly in the YAML by parsing it (the `YamlNode` tree records a
 *    line per node). This route is exact by construction.
 *
 * `null` is a real answer ("no link"), never line 1.
 */

import type { ProvenanceMap } from '../../shared/api';
import { isDict, parse, toJs, type YamlNode, type YValue } from '../design/yaml';
import { parsePointer } from './map';
import type { Selection } from './types';

export type SpecAnchorRoute = 'provenance' | 'structural';

export type AnchorConfidence = 'exact' | 'inferred';

export interface SpecAnchor {
  /** 1-based line number in `design.yaml`. */
  line: number;
  route: SpecAnchorRoute;
  confidence: AnchorConfidence;
}

/* ------------------------------------------------------------------ */
/* Provenance route (cell / net)                                       */
/* ------------------------------------------------------------------ */

function provenanceAnchor(selection: Selection, provenance: ProvenanceMap): SpecAnchor | null {
  let isCell: boolean;
  let name: string;
  if (selection.kind === 'cell') {
    isCell = true;
    name = selection.name;
  } else if (selection.kind === 'net') {
    isCell = false;
    name = selection.name;
  } else {
    return null;
  }

  const matches = provenance.entries.filter((entry) =>
    isCell ? entry.cells.includes(name) : entry.nets.includes(name),
  );

  // Pick the strongest, most specific pointer: an `exact` entry beats an
  // `inferred` one, and among entries of equal confidence the lowest line wins
  // (deterministic). Entries whose pointer carries no line are skipped — a
  // pointer that cannot locate a line is not a link to one.
  let best: SpecAnchor | null = null;
  for (const entry of matches) {
    const line = parsePointer(entry.pointer).line;
    if (line === null) continue;
    if (
      best === null ||
      (entry.confidence === 'exact' && best.confidence !== 'exact') ||
      (entry.confidence === best.confidence && line < best.line)
    ) {
      best = { line, route: 'provenance', confidence: entry.confidence };
    }
  }
  return best;
}

/* ------------------------------------------------------------------ */
/* Structural route (state / transition / input / property)            */
/* ------------------------------------------------------------------ */

function topLevelValue(root: YamlNode, key: string): YamlNode | null {
  if (root.kind !== 'mapping') return null;
  const item = root.items.find((i) => i.key === key);
  return item ? item.value : null;
}

/**
 * The line of the first item of the top-level `key` sequence whose parsed value
 * satisfies `predicate`, or `null` when the key is absent/not a sequence or no
 * item matches. Matching is done on the *parsed* value so quoted and plain
 * scalars (and flow vs block items) compare identically.
 */
function itemLine(root: YamlNode, key: string, predicate: (value: YValue) => boolean): number | null {
  const value = topLevelValue(root, key);
  if (value === null || value.kind !== 'sequence') return null;
  for (const item of value.items) {
    if (predicate(toJs(item))) return item.line;
  }
  return null;
}

function structuralAnchor(selection: Selection, specText: string): SpecAnchor | null {
  let root: YamlNode;
  try {
    root = parse(specText).root;
  } catch {
    // Unparseable spec: no construct can be located. The editor's own
    // diagnostics report *why* it does not parse; here the honest answer is
    // "no link".
    return null;
  }

  let line: number | null = null;
  if (selection.kind === 'state') {
    line = itemLine(root, 'states', (v) => v === selection.id);
  } else if (selection.kind === 'input') {
    line = itemLine(root, 'inputs', (v) => isDict(v) && v.name === selection.name);
  } else if (selection.kind === 'property') {
    line = itemLine(root, 'properties', (v) => isDict(v) && v.name === selection.name);
  } else if (selection.kind === 'transition') {
    // Match on the from/to pair, NOT on the `when` guard text: two transitions
    // can carry identical guards, and locating the first line that contains the
    // guard string would point at the wrong transition.
    line = itemLine(
      root,
      'transitions',
      (v) => isDict(v) && v.from === selection.from && v.to === selection.to,
    );
  }

  return line === null ? null : { line, route: 'structural', confidence: 'exact' };
}

/* ------------------------------------------------------------------ */
/* Public entry point                                                  */
/* ------------------------------------------------------------------ */

export function resolveSpecAnchor(
  selection: Selection,
  provenance: ProvenanceMap,
  specText: string,
): SpecAnchor | null {
  if (selection.kind === 'cell' || selection.kind === 'net') {
    return provenanceAnchor(selection, provenance);
  }
  return structuralAnchor(selection, specText);
}
