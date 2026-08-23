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
 *    line per node). This route is exact by construction, and it is widened to
 *    any construct (`resolveStructuralLine`) so an inferred fallback can also
 *    locate outputs/inputs.
 *
 * When a `cell`/`net` has no provenance entry, an explicitly `inferred`
 * fallback is attempted: a *net* whose name exactly matches a declared output
 * or input resolves to that construct, labelled `inferred` — never `exact`. A
 * `cell` gets no fallback; its `$abc$…` instance name never matches a spec
 * construct, and a cone/nearest-construct guess would be fabricated provenance.
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
/* Structural route                                                    */
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

/** The line of a named entry of the top-level mapping `key` (e.g. the
 * `expressions`/`output_logic`/`constraints`/`packing` entry named `entryKey`),
 * or null. */
function mappingEntryLine(root: YamlNode, key: string, entryKey: string): number | null {
  const value = topLevelValue(root, key);
  if (value === null || value.kind !== 'mapping') return null;
  const item = value.items.find((i) => i.key === entryKey);
  return item ? item.value.line : null;
}

/** A construct the structural route can locate, keyed by its identity rather
 * than by a `Selection` kind — the selection vocabulary only covers
 * state/transition/input/property, so the rest are addressed here directly. */
export type StructuralRef =
  | { kind: 'state'; name: string }
  | { kind: 'input'; name: string }
  | { kind: 'output'; name: string }
  | { kind: 'property'; name: string }
  | { kind: 'transition'; from: string; to: string }
  | { kind: 'expression'; name: string }
  | { kind: 'testPoint'; net: string }
  | { kind: 'macro'; instance: string }
  | { kind: 'constraint'; field: string }
  | { kind: 'packing'; field: string };

/**
 * The 1-based line of a construct in `specText`, located by parsing the YAML
 * (the `YamlNode` tree records a line per node), or null. Every match is keyed
 * on the construct's own identity — a name, a from/to pair, a net, an instance,
 * a field — never on "the first item" or "line 1".
 */
export function resolveStructuralLine(specText: string, ref: StructuralRef): number | null {
  let root: YamlNode;
  try {
    root = parse(specText).root;
  } catch {
    return null;
  }

  switch (ref.kind) {
    case 'state':
      return itemLine(root, 'states', (v) => v === ref.name);
    case 'input':
      return itemLine(root, 'inputs', (v) => isDict(v) && v.name === ref.name);
    case 'output':
      return itemLine(root, 'outputs', (v) => isDict(v) && v.name === ref.name);
    case 'property':
      return itemLine(root, 'properties', (v) => isDict(v) && v.name === ref.name);
    case 'transition':
      // Match on the from/to pair, NOT on the `when` guard text: two transitions
      // can carry identical guards, and locating the first line that contains
      // the guard string would point at the wrong transition.
      return itemLine(root, 'transitions', (v) => isDict(v) && v.from === ref.from && v.to === ref.to);
    case 'expression':
      return mappingEntryLine(root, 'expressions', ref.name);
    case 'testPoint':
      return itemLine(root, 'test_points', (v) => isDict(v) && v.net === ref.net);
    case 'macro':
      return itemLine(root, 'macros', (v) => isDict(v) && v.instance === ref.instance);
    case 'constraint':
      return mappingEntryLine(root, 'constraints', ref.field);
    case 'packing':
      return mappingEntryLine(root, 'packing', ref.field);
  }
}

/** Map the selections the structural route can answer to a `StructuralRef`. */
function selectionToRef(selection: Selection): StructuralRef | null {
  switch (selection.kind) {
    case 'state':
      return { kind: 'state', name: selection.id };
    case 'input':
      return { kind: 'input', name: selection.name };
    case 'property':
      return { kind: 'property', name: selection.name };
    case 'transition':
      return { kind: 'transition', from: selection.from, to: selection.to };
    default:
      return null;
  }
}

function structuralAnchor(selection: Selection, specText: string): SpecAnchor | null {
  const ref = selectionToRef(selection);
  if (ref === null) return null;
  const line = resolveStructuralLine(specText, ref);
  return line === null ? null : { line, route: 'structural', confidence: 'exact' };
}

/**
 * An explicitly `inferred` fallback for a `cell`/`net` whose provenance has no
 * surviving entry. It is limited to a *net* whose name is exactly a declared
 * output or input — that name is the net's identity in the mapped netlist, so
 * the link is a structural fact, not a guess — and it is always labelled
 * `inferred` (never `exact`). A `cell` gets no such fallback: its `$abc$…`
 * instance name never matches a spec construct, and inventing a cone or a
 * nearest-construct link would be fabricating provenance.
 */
function inferredAnchor(selection: Selection, specText: string): SpecAnchor | null {
  if (selection.kind !== 'net') return null;
  const output = resolveStructuralLine(specText, { kind: 'output', name: selection.name });
  if (output !== null) return { line: output, route: 'structural', confidence: 'inferred' };
  const input = resolveStructuralLine(specText, { kind: 'input', name: selection.name });
  if (input !== null) return { line: input, route: 'structural', confidence: 'inferred' };
  return null;
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
    return provenanceAnchor(selection, provenance) ?? inferredAnchor(selection, specText);
  }
  return structuralAnchor(selection, specText);
}
