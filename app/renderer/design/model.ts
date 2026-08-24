/**
 * Typed model of a `design.yaml` document plus the edit operations that mutate
 * the *text* (the text is authoritative; the model is derived). Mirrors the
 * structural rules of `gatepack/frontend/schema.py` for immediate editor
 * feedback; the *semantic* checks (reachability, guard overlap/exhaustiveness)
 * are deliberately NOT reimplemented here — those arrive from the core's
 * `compile`/`estimate` diagnostics.
 */

import type { Diagnostic } from '../../shared/api';
import { expand, parse as parseExpr, freeVars, statesReferenced, ExprError, type Expr } from './expr';
import {
  isDict,
  isList,
  parseToJs,
  serializeDocument,
  serializeTopLevelValue,
  spliceText,
  type Range,
  type YValue,
} from './yaml';

/* ------------------------------------------------------------------ */
/* Types                                                               */
/* ------------------------------------------------------------------ */

export interface Clock {
  signal: string;
  freqHz: number;
  source: string;
}

export interface Reset {
  signal: string;
  active: 'low' | 'high';
  asyncAssert: boolean;
  syncDeassert: boolean;
  source: string;
}

export interface InputPort {
  name: string;
  sync: boolean;
}

export interface OutputPort {
  name: string;
}

export interface Transition {
  from: string;
  to: string;
  when: string;
}

export interface PropertySpec {
  name: string;
  kind: 'invariant' | 'reachability' | 'liveness' | 'mutex';
  expr?: string;
  from?: string;
  to?: string;
}

export interface TestPoint {
  net: string;
}

export interface MacroSpec {
  instance: string;
  cell: string;
  clock: string;
  enable?: string;
}

export interface FundamentalMode {
  mutuallyExclusive: string[][];
}

export interface Constraints {
  maxFlops?: number;
  maxPackages?: number;
  vcc: number;
  maxStaticUa?: number;
}

/**
 * §12 C5 packing overrides, persisted in `design.yaml` (§C13). Each group names
 * mapped cells that must share a package. Mirrors `schema.py` `Packing`; the
 * packer still refuses a mixed-function group, so the renderer enforces the same
 * rule client-side before writing.
 */
export interface Packing {
  forceGroups: string[][];
}

export interface DesignModel {
  name: string;
  timingModel: 'synchronous' | 'asynchronous';
  clock: Clock | null;
  reset: Reset;
  encoding: 'one_hot' | 'binary' | 'gray';
  inputs: InputPort[];
  outputs: OutputPort[];
  expressions: Record<string, string>;
  states: string[];
  initial: string;
  transitions: Transition[];
  outputLogic: Record<string, string>;
  properties: PropertySpec[];
  safeState: Record<string, string>;
  testPoints: TestPoint[];
  macros: MacroSpec[];
  fundamentalMode: FundamentalMode | null;
  constraints: Constraints;
  packing: Packing;
}

export interface ParseOutcome {
  model: DesignModel | null;
  diagnostics: Diagnostic[];
}

export interface EditOutcome {
  text: string;
  diagnostics: Diagnostic[];
}

const VERILOG_KEYWORDS = new Set([
  'module', 'endmodule', 'input', 'output', 'inout', 'wire', 'reg', 'assign',
  'always', 'initial', 'begin', 'end', 'if', 'else', 'case', 'endcase',
  'default', 'parameter', 'localparam', 'posedge', 'negedge', 'or', 'and',
  'not', 'nand', 'nor', 'xor', 'xnor', 'buf', 'genvar', 'generate',
  'endgenerate', 'function', 'endfunction', 'task', 'endtask', 'integer',
  'real', 'signed', 'unsigned', 'supply0', 'supply1', 'tri', 'wand', 'wor',
  'for', 'while', 'repeat', 'forever', 'wait', 'event', 'struct', 'union',
  'typedef', 'enum', 'logic', 'bit', 'byte', 'shortint', 'int', 'longint',
  'time', 'generate', 'specify', 'endspecify',
]);

const IDENTIFIER = /^[A-Za-z_][A-Za-z0-9_]*$/;

function isIdentifier(name: string): boolean {
  return IDENTIFIER.test(name) && !VERILOG_KEYWORDS.has(name);
}

/* ------------------------------------------------------------------ */
/* Coercion helpers                                                    */
/* ------------------------------------------------------------------ */

function asDict(v: YValue | undefined): Record<string, YValue> | null {
  return isDict(v) ? v : null;
}

function asList(v: YValue | undefined): YValue[] | null {
  return isList(v) ? v : null;
}

function asString(v: YValue | undefined): string | null {
  return typeof v === 'string' ? v : null;
}

function asBool(v: YValue | undefined, fallback: boolean): boolean {
  return typeof v === 'boolean' ? v : fallback;
}

function asNumber(v: YValue | undefined): number | null {
  return typeof v === 'number' ? v : null;
}

function diag(severity: Diagnostic['severity'], code: string, message: string, line?: number): Diagnostic {
  const d: Diagnostic = { severity, code, message };
  if (line !== undefined) d.line = line;
  return d;
}

/* ------------------------------------------------------------------ */
/* Parse                                                               */
/* ------------------------------------------------------------------ */

export function parseDesignText(text: string): ParseOutcome {
  let value: YValue;
  try {
    value = parseToJs(text).value;
  } catch (e) {
    return {
      model: null,
      diagnostics: [diag('error', 'ED1000', e instanceof Error ? e.message : String(e))],
    };
  }
  const diagnostics: Diagnostic[] = [];
  const root = asDict(value);
  if (root === null) {
    return { model: null, diagnostics: [diag('error', 'ED1001', 'design.yaml must be a mapping')] };
  }

  const name = asString(root['name']) ?? '';
  if (name && !isIdentifier(name)) {
    diagnostics.push(diag('error', 'ED1002', `design name ${JSON.stringify(name)} is not a valid Verilog identifier`));
  }

  const timingModel = root['timing_model'] === 'asynchronous' ? 'asynchronous' : 'synchronous';

  const clockRaw = asDict(root['clock']) ?? null;
  const clock: Clock | null = clockRaw
    ? {
        signal: asString(clockRaw['signal']) ?? '',
        freqHz: asNumber(clockRaw['freq_hz']) ?? 0,
        source: asString(clockRaw['source']) ?? '',
      }
    : null;

  const resetRaw = asDict(root['reset']) ?? {};
  const resetActive = resetRaw['active'] === 'high' ? 'high' : 'low';
  const reset: Reset = {
    signal: asString(resetRaw['signal']) ?? '',
    active: resetActive,
    asyncAssert: asBool(resetRaw['async_assert'], true),
    syncDeassert: asBool(resetRaw['sync_deassert'], true),
    source: asString(resetRaw['source']) ?? '',
  };

  const encodingRaw = asString(root['encoding']) ?? 'one_hot';
  const encoding: DesignModel['encoding'] =
    encodingRaw === 'binary' || encodingRaw === 'gray' ? encodingRaw : 'one_hot';

  const inputs: InputPort[] = [];
  for (const item of asList(root['inputs']) ?? []) {
    const m = asDict(item);
    inputs.push({ name: asString(m?.['name']) ?? '', sync: asBool(m?.['sync'], false) });
  }

  const outputs: OutputPort[] = [];
  for (const item of asList(root['outputs']) ?? []) {
    const m = asDict(item);
    outputs.push({ name: asString(m?.['name']) ?? '' });
  }

  const expressions: Record<string, string> = {};
  const exprRaw = asDict(root['expressions']) ?? {};
  for (const [k, v] of Object.entries(exprRaw)) {
    const s = asString(v);
    if (s !== null) expressions[k] = s;
  }

  const states = (asList(root['states']) ?? [])
    .map((s) => asString(s))
    .filter((s): s is string => s !== null);
  const initial = asString(root['initial']) ?? '';

  const transitions: Transition[] = [];
  for (const item of asList(root['transitions']) ?? []) {
    const m = asDict(item);
    transitions.push({
      from: asString(m?.['from']) ?? '',
      to: asString(m?.['to']) ?? '',
      when: asString(m?.['when']) ?? '',
    });
  }

  const outputLogic: Record<string, string> = {};
  const olRaw = asDict(root['output_logic']) ?? {};
  for (const [k, v] of Object.entries(olRaw)) {
    const s = asString(v);
    if (s !== null) outputLogic[k] = s;
  }

  const properties: PropertySpec[] = [];
  for (const item of asList(root['properties']) ?? []) {
    const m = asDict(item);
    const kind = asString(m?.['kind']) ?? 'invariant';
    const p: PropertySpec = {
      name: asString(m?.['name']) ?? '',
      kind: kind === 'reachability' || kind === 'liveness' || kind === 'mutex' ? kind : 'invariant',
    };
    const expr = asString(m?.['expr']);
    if (expr !== null) p.expr = expr;
    const from = asString(m?.['from']);
    if (from !== null) p.from = from;
    const to = asString(m?.['to']);
    if (to !== null) p.to = to;
    properties.push(p);
  }

  const safeState: Record<string, string> = {};
  const ssRaw = asDict(root['safe_state']) ?? {};
  for (const [k, v] of Object.entries(ssRaw)) {
    const s = asString(v);
    if (s !== null) safeState[k] = s;
  }

  const testPoints: TestPoint[] = [];
  for (const item of asList(root['test_points']) ?? []) {
    const m = asDict(item);
    testPoints.push({ net: asString(m?.['net']) ?? '' });
  }

  const macros: MacroSpec[] = [];
  for (const item of asList(root['macros']) ?? []) {
    const m = asDict(item);
    const macro: MacroSpec = {
      instance: asString(m?.['instance']) ?? '',
      cell: asString(m?.['cell']) ?? '',
      clock: asString(m?.['clock']) ?? '',
    };
    const enable = asString(m?.['enable']);
    if (enable !== null) macro.enable = enable;
    macros.push(macro);
  }

  const fmRaw = asDict(root['fundamental_mode']) ?? null;
  const fundamentalMode: FundamentalMode | null = fmRaw
    ? {
        mutuallyExclusive: (asList(fmRaw['mutually_exclusive']) ?? [])
          .map((grp) =>
            (asList(grp) ?? []).map((s) => asString(s)).filter((s): s is string => s !== null),
          )
          .filter((grp) => grp.length > 0),
      }
    : null;

  const cRaw = asDict(root['constraints']) ?? {};
  const constraints: Constraints = { vcc: asNumber(cRaw['vcc']) ?? 3.3 };
  const maxFlops = asNumber(cRaw['max_flops']);
  if (maxFlops !== null) constraints.maxFlops = maxFlops;
  const maxPackages = asNumber(cRaw['max_packages']);
  if (maxPackages !== null) constraints.maxPackages = maxPackages;
  const maxStaticUa = asNumber(cRaw['max_static_ua']);
  if (maxStaticUa !== null) constraints.maxStaticUa = maxStaticUa;

  const pRaw = asDict(root['packing']) ?? {};
  const forceGroups: string[][] = [];
  for (const item of asList(pRaw['force_groups']) ?? []) {
    const names = (asList(item) ?? [])
      .map((s) => asString(s))
      .filter((s): s is string => s !== null);
    if (names.length > 0) forceGroups.push(names);
  }

  const model: DesignModel = {
    name,
    timingModel,
    clock,
    reset,
    encoding,
    inputs,
    outputs,
    expressions,
    states,
    initial,
    transitions,
    outputLogic,
    properties,
    safeState,
    testPoints,
    macros,
    fundamentalMode,
    constraints,
    packing: { forceGroups },
  };

  validateStructure(model, diagnostics);
  validateExpressions(model, diagnostics);

  return { model, diagnostics };
}

/* ------------------------------------------------------------------ */
/* Structural validation (mirrors schema.py §structural_checks)        */
/* ------------------------------------------------------------------ */

function validateStructure(model: DesignModel, diagnostics: Diagnostic[]): void {
  const inputNames = model.inputs.map((i) => i.name);
  const outputNames = model.outputs.map((o) => o.name);
  const stateSet = new Set(model.states);

  for (const name of inputNames) {
    if (!isIdentifier(name)) diagnostics.push(diag('error', 'ED1003', `input name ${JSON.stringify(name)} is not a valid Verilog identifier`));
  }
  for (const name of outputNames) {
    if (!isIdentifier(name)) diagnostics.push(diag('error', 'ED1004', `output name ${JSON.stringify(name)} is not a valid Verilog identifier`));
  }
  for (const name of model.states) {
    if (!isIdentifier(name)) diagnostics.push(diag('error', 'ED1005', `state ${JSON.stringify(name)} is not a valid Verilog identifier`));
  }
  reportDuplicates(inputNames, 'input', 'ED1006', diagnostics);
  reportDuplicates(outputNames, 'output', 'ED1007', diagnostics);
  reportDuplicates(model.states, 'state', 'ED1008', diagnostics);
  reportDuplicates(Object.keys(model.expressions), 'expression', 'ED1009', diagnostics);

  if (model.states.length > 0 && !stateSet.has(model.initial)) {
    diagnostics.push(diag('error', 'ED1010', `initial state ${JSON.stringify(model.initial)} is not in states`));
  }

  const outputSet = new Set(outputNames);
  for (const name of Object.keys(model.outputLogic)) {
    if (!outputSet.has(name)) {
      diagnostics.push(diag('error', 'ED1011', `output_logic[${JSON.stringify(name)}] is not a declared output`));
    }
  }
  for (const name of Object.keys(model.safeState)) {
    if (!outputSet.has(name)) {
      diagnostics.push(diag('error', 'ED1012', `safe_state[${JSON.stringify(name)}] is not a declared output`));
    } else if (!['0', '1', 'any'].includes(model.safeState[name])) {
      diagnostics.push(diag('error', 'ED1013', `safe_state[${JSON.stringify(name)}] must be 0, 1 or 'any'`));
    }
  }

  model.transitions.forEach((tr, index) => {
    if (model.states.length > 0 && !stateSet.has(tr.from)) {
      diagnostics.push(diag('error', 'ED1014', `transitions[${index}] 'from' state ${JSON.stringify(tr.from)} is not declared`));
    }
    if (model.states.length > 0 && !stateSet.has(tr.to)) {
      diagnostics.push(diag('error', 'ED1015', `transitions[${index}] 'to' state ${JSON.stringify(tr.to)} is not declared`));
    }
  });
}

function reportDuplicates(names: string[], kind: string, code: string, diagnostics: Diagnostic[]): void {
  const seen = new Set<string>();
  for (const name of names) {
    if (name && seen.has(name)) {
      diagnostics.push(diag('error', code, `duplicate ${kind} name ${JSON.stringify(name)}`));
    }
    seen.add(name);
  }
}

/* ------------------------------------------------------------------ */
/* Expression validation (mirrors model.py reference checks)           */
/* ------------------------------------------------------------------ */

function validateExpressions(model: DesignModel, diagnostics: Diagnostic[]): void {
  const inputSet = new Set(model.inputs.map((i) => i.name));
  const stateSet = new Set(model.states);

  const expressionAsts: Record<string, Expr> = {};
  for (const [name, text] of Object.entries(model.expressions)) {
    try {
      expressionAsts[name] = parseExpr(text);
    } catch (e) {
      diagnostics.push(diag('error', 'ED1016', `expression ${JSON.stringify(name)}: ${messageOf(e)}`));
    }
  }

  const checkRefs = (
    ast: Expr | null,
    where: string,
  ): void => {
    if (ast === null) return;
    let expanded: Expr;
    try {
      expanded = expand(ast, expressionAsts);
    } catch (e) {
      diagnostics.push(diag('error', 'ED1017', `${where}: ${messageOf(e)}`));
      return;
    }
    const unknown = [...freeVars(expanded)].filter((v) => !inputSet.has(v));
    if (unknown.length) {
      diagnostics.push(diag('error', 'ED1018', `${where} references unknown signals ${JSON.stringify(unknown.sort())}`));
    }
  };

  model.transitions.forEach((tr, index) => {
    let ast: Expr | null = null;
    try {
      ast = parseExpr(tr.when);
    } catch (e) {
      diagnostics.push(diag('error', 'ED1019', `transitions[${index}] when ${JSON.stringify(tr.when)}: ${messageOf(e)}`));
      return;
    }
    const stateRefs = statesReferenced(ast);
    if (stateRefs.size) {
      diagnostics.push(diag('error', 'ED1020', `transitions[${index}] guard must not reference 'state =='`));
    }
    checkRefs(ast, `transitions[${index}] guard ${JSON.stringify(tr.when)}`);
  });

  for (const [name, text] of Object.entries(model.outputLogic)) {
    let ast: Expr | null = null;
    try {
      ast = parseExpr(text);
    } catch (e) {
      diagnostics.push(diag('error', 'ED1021', `output_logic[${JSON.stringify(name)}]: ${messageOf(e)}`));
      continue;
    }
    const badStates = [...statesReferenced(ast)].filter((s) => !stateSet.has(s));
    if (badStates.length) {
      diagnostics.push(diag('error', 'ED1022', `output_logic[${JSON.stringify(name)}] references unknown states ${JSON.stringify(badStates.sort())}`));
    }
    checkRefs(ast, `output_logic[${JSON.stringify(name)}]`);
  }
}

function messageOf(e: unknown): string {
  return e instanceof ExprError || e instanceof Error ? e.message : String(e);
}

/* ------------------------------------------------------------------ */
/* Edit operations (mutate the text, re-parse, re-validate)            */
/* ------------------------------------------------------------------ */

export function applyTopLevelEdit(
  text: string,
  key: string,
  transform: (current: YValue) => YValue,
): EditOutcome {
  const { value, ranges } = parseToJs(text);
  const range = ranges.get(key);
  if (!range) {
    throw new Error(`key ${JSON.stringify(key)} not found in document`);
  }
  const root = asDict(value) ?? {};
  const current = key in root ? root[key] : null;
  const next = transform(current);
  const replacement = serializeTopLevelValue(next);
  const newText = spliceText(text, range.valueStart, range.valueEnd, replacement);
  const outcome = parseDesignText(newText);
  return { text: newText, diagnostics: outcome.diagnostics };
}

/** Set a top-level field, appending it (canonically) when it is not present. */
export function setField(text: string, key: string, value: YValue): EditOutcome {
  try {
    return applyTopLevelEdit(text, key, () => value);
  } catch {
    const block = serializeDocument({ [key]: value });
    const newText = text.endsWith('\n') ? text + block : `${text}\n${block}`;
    return { text: newText, diagnostics: parseDesignText(newText).diagnostics };
  }
}

/* ------------------------------------------------------------------ */
/* Identifier-aware, comment-preserving splices                        */
/* ------------------------------------------------------------------ */

/** The characters that continue an identifier: a rename matches a name only as
 * a whole identifier, so `RUN` matches `- RUN` and `state == RUN` but never
 * `RUNNING` or `go_RUN`. */
const IDENTIFIER_CHARS = 'A-Za-z0-9_';

function identifierPattern(name: string): string {
  return `(?<![${IDENTIFIER_CHARS}])${escapeRegExp(name)}(?![${IDENTIFIER_CHARS}])`;
}

/** Replace every whole-identifier occurrence of `name` in a string. */
function replaceIdentifier(text: string, name: string, replacement: string): string {
  return text.replace(new RegExp(identifierPattern(name), 'g'), replacement);
}

/** Apply `transform` to the code part of every line inside a block's value,
 * preserving each line's trailing comment and every line that does not change.
 * Returns null when no line changed, so an absent block (or a rename that
 * matches nothing) leaves the document byte-identical. */
function spliceBlockLines(
  text: string,
  range: Range,
  transform: (code: string) => string,
): { start: number; end: number; value: string } | null {
  const body = text.slice(range.valueStart, range.valueEnd);
  let changed = false;
  const lines = body.split('\n').map((line) => {
    const hash = line.indexOf('#');
    const code = hash === -1 ? line : line.slice(0, hash);
    const next = transform(code);
    if (next === code) return line;
    changed = true;
    return hash === -1 ? next : next + line.slice(hash);
  });
  if (!changed) return null;
  return { start: range.valueStart, end: range.valueEnd, value: lines.join('\n') };
}

/** Apply disjoint character-range edits, newest-first so earlier offsets stay
 * valid. */
function applyRangeEdits(
  text: string,
  edits: Array<{ start: number; end: number; value: string }>,
): string {
  const sorted = [...edits].sort((a, b) => b.start - a.start);
  let out = text;
  for (const edit of sorted) out = spliceText(out, edit.start, edit.end, edit.value);
  return out;
}

/** Rename the *input* identifier `oldName` in an expression, leaving
 * `state == oldName` (a state reference) untouched. */
function renameInputInExpr(expr: string, oldName: string, newName: string): string {
  const stateEq = `\\bstate\\s*==\\s*${identifierPattern(oldName)}`;
  const bare = identifierPattern(oldName);
  return expr.replace(new RegExp(`${stateEq}|${bare}`, 'g'), (match) =>
    match === oldName ? newName : match,
  );
}

/** Rename the input identifier inside a quoted or plain scalar expression. */
function renameInputInScalar(raw: string, oldName: string, newName: string): string {
  const first = raw[0];
  if ((first === '"' || first === "'") && raw.length >= 2 && raw[raw.length - 1] === first) {
    return first + renameInputInExpr(raw.slice(1, -1), oldName, newName) + first;
  }
  return renameInputInExpr(raw, oldName, newName);
}

/** Rename `oldName` in the value of one named field (quoted or plain). */
function renameInField(code: string, field: string, oldName: string, newName: string): string {
  const fieldRe = new RegExp(`(\\b${field}\\s*:\\s*)("([^"]*)"|'([^']*)'|([^,}]+))`, 'g');
  return code.replace(fieldRe, (_match, prefix, _whole, dq, sq, bare) => {
    if (dq !== undefined) return `${prefix}"${renameInputInExpr(dq, oldName, newName)}"`;
    if (sq !== undefined) return `${prefix}'${renameInputInExpr(sq, oldName, newName)}'`;
    return `${prefix}${renameInputInExpr(bare, oldName, newName)}`;
  });
}

/** Rename `oldName` in the *values* of a mapping block (keys are left alone). */
function renameInMappingValues(code: string, oldName: string, newName: string): string {
  const kvRe = /([A-Za-z_][A-Za-z0-9_]*\s*:\s*)("(?:\\.|[^"])*"|'(?:\\.|[^'])*'|[^,}]+)/g;
  return code.replace(kvRe, (_match, keyPart, valuePart) =>
    keyPart + renameInputInScalar(valuePart, oldName, newName),
  );
}

/* ------------------------------------------------------------------ */
/* One field of one list item, spliced                                  */
/* ------------------------------------------------------------------ */

/** Quote a scalar for YAML, double-quoted so an expression's `!`, `&` and `|`
 * cannot be read as YAML syntax. */
function quoteScalar(value: string): string {
  return '"' + value.replace(/\\/g, '\\\\').replace(/"/g, '\\"') + '"';
}

interface BlockLine {
  /** The whole line, comment included. */
  raw: string;
  /** The line up to any `#`, which is the only part an edit may touch. */
  code: string;
  /** The `#` onwards, or ''. */
  comment: string;
}

function splitBlockLine(raw: string): BlockLine {
  const hash = raw.indexOf('#');
  return hash === -1
    ? { raw, code: raw, comment: '' }
    : { raw, code: raw.slice(0, hash), comment: raw.slice(hash) };
}

/** The line indices in `lines` at which each `- ` list item starts. */
function itemStartLines(lines: BlockLine[]): number[] {
  const starts: number[] = [];
  for (let i = 0; i < lines.length; i += 1) {
    if (/^\s*-\s/.test(lines[i].code)) starts.push(i);
  }
  return starts;
}

/**
 * Set one field of one list item, touching only the line that carries it.
 *
 * The alternative — the `applyTopLevelEdit` path every list editor used before
 * this — re-serialises the whole block from the model, which deletes every
 * comment in it. Measured 2026-08-23 on a two-transition spec: editing the
 * *first* transition's guard from the Inspector deleted both comments in the
 * block, including one attached to the transition the user had not touched.
 *
 * Returns `null` when the item or a place to put the field cannot be found, so
 * the caller refuses rather than falling back to a rewrite.
 */
function spliceItemField(
  text: string,
  range: Range,
  index: number,
  field: string,
  value: string,
): { start: number; end: number; value: string } | null {
  const lines = text.slice(range.valueStart, range.valueEnd).split('\n').map(splitBlockLine);
  const starts = itemStartLines(lines);
  if (index < 0 || index >= starts.length) return null;

  const from = starts[index];
  const to = index + 1 < starts.length ? starts[index + 1] : lines.length;
  const quoted = quoteScalar(value);
  const fieldRe = new RegExp(`(\\b${field}\\s*:\\s*)("(?:\\\\.|[^"])*"|'(?:\\\\.|[^'])*'|[^,}\\n]*)`);

  for (let i = from; i < to; i += 1) {
    if (!fieldRe.test(lines[i].code)) continue;
    lines[i] = {
      ...lines[i],
      code: lines[i].code.replace(fieldRe, (_m, prefix) => `${prefix}${quoted}`),
    };
    lines[i].raw = lines[i].code + lines[i].comment;
    return {
      start: range.valueStart,
      end: range.valueEnd,
      value: lines.map((l) => l.raw).join('\n'),
    };
  }

  // The field is absent. A flow mapping takes it before the closing brace; a
  // block mapping takes a new line at the item's key indentation.
  const head = lines[from];
  const brace = head.code.lastIndexOf('}');
  if (brace !== -1) {
    const before = head.code.slice(0, brace).trimEnd();
    const sep = before.endsWith('{') ? '' : ', ';
    head.code = `${before}${sep}${field}: ${quoted}${head.code.slice(brace)}`;
    head.raw = head.code + head.comment;
  } else {
    const dash = head.code.indexOf('- ');
    if (dash === -1) return null;
    const indent = ' '.repeat(dash + 2);
    lines.splice(from + 1, 0, splitBlockLine(`${indent}${field}: ${quoted}`));
  }
  return {
    start: range.valueStart,
    end: range.valueEnd,
    value: lines.map((l) => l.raw).join('\n'),
  };
}

function setItemField(
  text: string,
  blockKey: string,
  index: number,
  field: string,
  value: string,
  code: string,
): EditOutcome {
  const { ranges } = parseToJs(text);
  const range = ranges.get(blockKey);
  const refuse = (reason: string): EditOutcome => ({
    text,
    diagnostics: [...parseDesignText(text).diagnostics, diag('error', code, reason)],
  });
  if (!range) return refuse(`there is no ${blockKey} block to edit`);
  const edit = spliceItemField(text, range, index, field, value);
  if (!edit) return refuse(`${blockKey}[${index}] could not be located to set ${field}`);
  const newText = applyRangeEdits(text, [edit]);
  return { text: newText, diagnostics: parseDesignText(newText).diagnostics };
}

/** §C10: set one transition's `when` guard, preserving every comment in the
 * transitions block — including comments on transitions the user did not edit. */
export function setTransitionWhen(text: string, index: number, when: string): EditOutcome {
  return setItemField(text, 'transitions', index, 'when', when, 'ED1026');
}

/** §11: set one property's `expr`, preserving every comment in the properties
 * block. */
export function setPropertyExpr(text: string, index: number, expr: string): EditOutcome {
  return setItemField(text, 'properties', index, 'expr', expr, 'ED1027');
}

/** §C10: set one transition's `from` state, preserving every comment in the
 * transitions block — the same line-splice `setTransitionWhen` uses. */
export function setTransitionFrom(text: string, index: number, from: string): EditOutcome {
  return setItemField(text, 'transitions', index, 'from', from, 'ED1028');
}

/** §C10: set one transition's `to` state, preserving every comment in the
 * transitions block. */
export function setTransitionTo(text: string, index: number, to: string): EditOutcome {
  return setItemField(text, 'transitions', index, 'to', to, 'ED1029');
}

/** §C12: set one input's `name`, preserving every comment in the inputs block. */
export function setInputName(text: string, index: number, name: string): EditOutcome {
  return setItemField(text, 'inputs', index, 'name', name, 'ED1032');
}

/** §C12: set one output's `name`, preserving every comment in the outputs block. */
export function setOutputName(text: string, index: number, name: string): EditOutcome {
  return setItemField(text, 'outputs', index, 'name', name, 'ED1033');
}

/** §11: set one property's `name`, preserving every comment in the properties block. */
export function setPropertyName(text: string, index: number, name: string): EditOutcome {
  return setItemField(text, 'properties', index, 'name', name, 'ED1034');
}

/** §11: set one property's `kind`, preserving every comment in the properties block. */
export function setPropertyKind(text: string, index: number, kind: string): EditOutcome {
  return setItemField(text, 'properties', index, 'kind', kind, 'ED1035');
}

/* ------------------------------------------------------------------ */
/* Adding and removing list items, spliced                              */
/* ------------------------------------------------------------------ */

const SAFE_PLAIN = /^[A-Za-z_][A-Za-z0-9_./-]*$/;
const RESERVED_INLINE = new Set(['true', 'false', 'null', '~']);

function looksNumeric(s: string): boolean {
  if (s === '') return false;
  return Number.isFinite(Number(s));
}

/** Inline YAML for one value, quoting anything that would not round-trip as a
 * plain scalar: empty, reserved words, numeric-looking strings, and anything
 * with a character outside `SAFE_PLAIN`. */
function inlineScalar(v: YValue): string {
  if (v === null) return '~';
  if (typeof v === 'boolean') return v ? 'true' : 'false';
  if (typeof v === 'number') return String(v);
  if (typeof v === 'string') {
    if (v !== '' && SAFE_PLAIN.test(v) && !RESERVED_INLINE.has(v) && !looksNumeric(v)) return v;
    return quoteScalar(v);
  }
  if (Array.isArray(v)) return `[${v.map(inlineScalar).join(', ')}]`;
  if (isDict(v)) return `{${Object.keys(v).map((k) => `${k}: ${inlineScalar(v[k])}`).join(', ')}}`;
  throw new Error(`cannot emit YAML for ${typeof v}`);
}

/** Render one list item as `- ` line(s) at `indent`, in the flow-mapping,
 * block-mapping or scalar style the surrounding list already uses. */
function renderListItemLines(item: YValue, indent: string, flow: boolean): string[] {
  if (isDict(item)) {
    if (flow) {
      const inner = Object.keys(item).map((k) => `${k}: ${inlineScalar(item[k])}`).join(', ');
      return [`${indent}- {${inner}}`];
    }
    const keys = Object.keys(item);
    const lines = [`${indent}- ${keys[0]}: ${inlineScalar(item[keys[0]])}`];
    for (const k of keys.slice(1)) lines.push(`${indent}  ${k}: ${inlineScalar(item[k])}`);
    return lines;
  }
  if (Array.isArray(item)) return [`${indent}- [${item.map(inlineScalar).join(', ')}]`];
  return [`${indent}- ${inlineScalar(item)}`];
}

/** Split a flow-sequence body on top-level commas, honouring quotes and nested
 * `{}`/`[]`. */
function splitTopLevelCommas(text: string): string[] {
  const parts: string[] = [];
  let depth = 0;
  let quote: string | null = null;
  let cur = '';
  for (let i = 0; i < text.length; i += 1) {
    const c = text[i];
    if (quote) {
      cur += c;
      if (c === '\\' && i + 1 < text.length) {
        cur += text[i + 1];
        i += 1;
        continue;
      }
      if (c === quote) quote = null;
      continue;
    }
    if (c === '"' || c === "'") {
      quote = c;
      cur += c;
      continue;
    }
    if (c === '{' || c === '[') depth += 1;
    else if (c === '}' || c === ']') depth -= 1;
    if (c === ',' && depth === 0) {
      parts.push(cur.trim());
      cur = '';
      continue;
    }
    cur += c;
  }
  parts.push(cur.trim());
  return parts.filter((p) => p !== '');
}

/** True for a line that is *only* a comment (no code, not blank). */
function isAttachedComment(line: BlockLine): boolean {
  return line.code.trim() === '' && line.comment !== '';
}

/**
 * Append one item to a top-level list, spliced into the block rather than
 * re-serialised. Re-serialising a list from the model deletes every comment in
 * it (the same defect `setInputSync` documents for `inputs`); appending only
 * touches the end of the block.
 *
 * The new item is written in the style the list already uses: a flow sequence
 * (`states: [S0, PULSE]`) gets an inline item; a block list of flow mappings
 * (`- {from: S0, to: PULSE, when: "din"}`) gets another flow mapping; a block
 * list of block mappings (`- name: a`) gets another block mapping. When the key
 * is absent the whole block is appended canonically (there is nothing to
 * destroy). An empty list becomes a one-item list.
 */
export function appendListItem(text: string, key: string, item: YValue): EditOutcome {
  const refuse = (reason: string): EditOutcome => ({
    text,
    diagnostics: [...parseDesignText(text).diagnostics, diag('error', 'ED1030', reason)],
  });

  let value: YValue;
  let ranges: Map<string, Range>;
  try {
    const parsed = parseToJs(text);
    value = parsed.value;
    ranges = parsed.ranges;
  } catch (e) {
    return refuse(messageOf(e));
  }

  const range = ranges.get(key);
  if (!range) {
    // The key is not there at all: append a fresh block. Nothing exists to
    // destroy, so the canonical serialiser is correct and safe.
    return setField(text, key, [item]);
  }
  const root = asDict(value) ?? {};
  // A list key with no items parses to `null` (`transitions:` with nothing after
  // it), so `null` counts as an empty list, not as a type mismatch.
  const current = root[key];
  if (current !== null && !isList(current)) {
    return refuse(`cannot append to ${JSON.stringify(key)}: it is not a list`);
  }

  const body = text.slice(range.valueStart, range.valueEnd);
  const trimmed = body.trimStart();

  let next: string;

  if (trimmed.startsWith('[')) {
    // Flow sequence: insert the new item inside the brackets, before any
    // trailing comment.
    const open = body.indexOf('[');
    const close = body.lastIndexOf(']');
    if (open === -1 || close === -1 || close < open) {
      return refuse(`malformed flow sequence for ${JSON.stringify(key)}`);
    }
    const inner = body.slice(open + 1, close).trim();
    const token = inlineScalar(item);
    const nextInner = inner === '' ? token : `${inner}, ${token}`;
    next = spliceText(text, range.valueStart + open + 1, range.valueStart + close, nextInner);
  } else {
    const lines = body.split('\n').map(splitBlockLine);
    const starts = itemStartLines(lines);
    if (starts.length > 0) {
      const lastStart = starts[starts.length - 1];
      const indent = /^\s*/.exec(lines[lastStart].code)?.[0] ?? '';
      const flow = lines[lastStart].code.replace(/^\s*-\s*/, '').startsWith('{');
      const newLines = renderListItemLines(item, indent, flow);
      lines.splice(lines.length, 0, ...newLines.map(splitBlockLine));
      next = spliceText(text, range.valueStart, range.valueEnd, lines.map((l) => l.raw).join('\n'));
    } else {
      // An empty block list: the first item goes on a new line after the key.
      const newLines = renderListItemLines(item, '  ', isDict(item));
      next = spliceText(text, range.valueStart, range.valueEnd, `\n${newLines.join('\n')}`);
    }
  }

  // A splice that produced unparseable YAML must not be handed back as an edit.
  const reparsed = parseDesignText(next);
  if (reparsed.model === null) {
    return { text, diagnostics: reparsed.diagnostics };
  }
  return { text: next, diagnostics: reparsed.diagnostics };
}

/**
 * Remove one item from a top-level list, spliced so only the removed item's
 * own lines change.
 *
 * The comment rule is a deliberate judgement call, not an accident of the line
 * arithmetic: a comment line sitting *directly* above the item — no blank line
 * between — is read as that item's annotation and goes with it; a comment
 * separated from the item by a blank line, or sitting above a blank line at the
 * top of the block, is a block header and stays. A single blank line is the
 * only boundary we can reason about without trying to understand what the
 * comment says.
 */
export function removeListItem(text: string, key: string, index: number): EditOutcome {
  const refuse = (reason: string): EditOutcome => ({
    text,
    diagnostics: [...parseDesignText(text).diagnostics, diag('error', 'ED1031', reason)],
  });

  let ranges: Map<string, Range>;
  try {
    ranges = parseToJs(text).ranges;
  } catch (e) {
    return refuse(messageOf(e));
  }
  const range = ranges.get(key);
  if (!range) {
    return refuse(`there is no ${JSON.stringify(key)} block to remove from`);
  }

  const body = text.slice(range.valueStart, range.valueEnd);
  const trimmed = body.trimStart();

  let next: string;

  if (trimmed.startsWith('[')) {
    const open = body.indexOf('[');
    const close = body.lastIndexOf(']');
    if (open === -1 || close === -1 || close < open) {
      return refuse(`malformed flow sequence for ${JSON.stringify(key)}`);
    }
    const parts = splitTopLevelCommas(body.slice(open + 1, close));
    if (index < 0 || index >= parts.length) {
      return refuse(`${JSON.stringify(key)}[${index}] does not exist to remove`);
    }
    parts.splice(index, 1);
    next = spliceText(text, range.valueStart + open + 1, range.valueStart + close, parts.join(', '));
  } else {
    const lines = body.split('\n').map(splitBlockLine);
    const starts = itemStartLines(lines);
    if (index < 0 || index >= starts.length) {
      return refuse(`${JSON.stringify(key)}[${index}] does not exist to remove`);
    }
    const from = starts[index];
    const to = index + 1 < starts.length ? starts[index + 1] : lines.length;
    // Extend upward over comment lines glued to the item (see the judgement
    // documented on the function).
    let head = from;
    while (head > 0 && isAttachedComment(lines[head - 1])) {
      head -= 1;
    }
    lines.splice(head, to - head);
    next = spliceText(text, range.valueStart, range.valueEnd, lines.map((l) => l.raw).join('\n'));
  }

  const reparsed = parseDesignText(next);
  if (reparsed.model === null) {
    return { text, diagnostics: reparsed.diagnostics };
  }
  return { text: next, diagnostics: reparsed.diagnostics };
}

/* ------------------------------------------------------------------ */
/* Renames                                                             */
/* ------------------------------------------------------------------ */

/** Rename a state everywhere it appears (states, initial, transitions,
 * output_logic, macros). A line-level splice: only the lines that actually
 * carry the name change, so every comment and the block/flow style of every
 * collection the rename does not touch survive byte-identical. */
export function renameState(text: string, oldName: string, newName: string): EditOutcome {
  if (!isIdentifier(newName)) {
    const outcome = parseDesignText(text);
    return {
      text,
      diagnostics: [...outcome.diagnostics, diag('error', 'ED1023', `state name ${JSON.stringify(newName)} is not a valid Verilog identifier`)],
    };
  }

  const { value, ranges } = parseToJs(text);
  const root = asDict(value) ?? {};

  // `state == NAME` in output_logic / macros `enable` (a state reference).
  const stateEqRe = new RegExp(`\\bstate\\s*==\\s*${identifierPattern(oldName)}`, 'g');
  const renameStateExpr = (code: string): string =>
    code.replace(stateEqRe, `state == ${newName}`);

  // `from:` / `to:` in transitions (state references); `when:` is an input guard
  // and must never be touched by a state rename.
  const fromToRe = new RegExp(
    `(\\b(?:from|to)\\s*:\\s*)("?)${identifierPattern(oldName)}\\2`,
    'g',
  );
  const renameFromTo = (code: string): string =>
    code.replace(fromToRe, (_match, prefix, quote) => `${prefix}${quote}${newName}${quote}`);

  const edits: Array<{ start: number; end: number; value: string }> = [];

  const statesRange = ranges.get('states');
  if (statesRange) {
    const edit = spliceBlockLines(text, statesRange, (code) =>
      replaceIdentifier(code, oldName, newName),
    );
    if (edit) edits.push(edit);
  }

  if (asString(root['initial']) === oldName) {
    const initialRange = ranges.get('initial');
    if (initialRange) {
      edits.push({
        start: initialRange.valueStart,
        end: initialRange.valueEnd,
        value: ` ${newName}`,
      });
    }
  }

  const transitionsRange = ranges.get('transitions');
  if (transitionsRange) {
    const edit = spliceBlockLines(text, transitionsRange, renameFromTo);
    if (edit) edits.push(edit);
  }

  const outputLogicRange = ranges.get('output_logic');
  if (outputLogicRange) {
    const edit = spliceBlockLines(text, outputLogicRange, renameStateExpr);
    if (edit) edits.push(edit);
  }

  const macrosRange = ranges.get('macros');
  if (macrosRange) {
    const edit = spliceBlockLines(text, macrosRange, renameStateExpr);
    if (edit) edits.push(edit);
  }

  // Property expressions reference states the same way output_logic does
  // (`state == NAME`). Nothing diagnoses a stranded reference here — measured:
  // `parseDesignText` reports unknown states in transitions and output_logic
  // but says nothing about `properties[].expr` — so a rename that skipped this
  // block would leave a property asserting something about a state that no
  // longer exists, with no error anywhere. Silent, and the user believes the
  // rename was complete.
  const propertiesRange = ranges.get('properties');
  if (propertiesRange) {
    const edit = spliceBlockLines(text, propertiesRange, renameStateExpr);
    if (edit) edits.push(edit);
  }

  if (edits.length === 0) {
    return { text, diagnostics: parseDesignText(text).diagnostics };
  }
  const newText = applyRangeEdits(text, edits);
  return { text: newText, diagnostics: parseDesignText(newText).diagnostics };
}

/** §C12: rename an input everywhere it is referenced — identifier-aware and
 * line-spliced so the lines that do not name the input are untouched. Refuses
 * (byte-identical) when the new name is not a valid identifier, collides with
 * an input/output/state/expression name, or the result does not parse. */
export function renameInput(text: string, oldName: string, newName: string): EditOutcome {
  const refuse = (reason: string): EditOutcome => {
    const outcome = parseDesignText(text);
    return {
      text,
      diagnostics: [...outcome.diagnostics, diag('error', 'ED1025', reason)],
    };
  };

  if (!isIdentifier(newName)) {
    return refuse(`input name ${JSON.stringify(newName)} is not a valid Verilog identifier`);
  }

  const parsed = parseDesignText(text);
  if (parsed.model === null) {
    return { text, diagnostics: parsed.diagnostics };
  }
  const model = parsed.model;

  if (!model.inputs.some((i) => i.name === oldName)) {
    return refuse(`no input named ${JSON.stringify(oldName)} to rename`);
  }

  const reserved = new Set<string>();
  for (const i of model.inputs) if (i.name !== oldName) reserved.add(i.name);
  for (const o of model.outputs) reserved.add(o.name);
  for (const s of model.states) reserved.add(s);
  for (const k of Object.keys(model.expressions)) reserved.add(k);
  if (reserved.has(newName)) {
    return refuse(
      `name ${JSON.stringify(newName)} is already used by an input, output, state or expression`,
    );
  }

  const { ranges } = parseToJs(text);
  const edits: Array<{ start: number; end: number; value: string }> = [];

  const inputsRange = ranges.get('inputs');
  if (inputsRange) {
    const edit = spliceBlockLines(text, inputsRange, (code) =>
      renameInField(code, 'name', oldName, newName),
    );
    if (edit) edits.push(edit);
  }

  const transitionsRange = ranges.get('transitions');
  if (transitionsRange) {
    const edit = spliceBlockLines(text, transitionsRange, (code) =>
      renameInField(code, 'when', oldName, newName),
    );
    if (edit) edits.push(edit);
  }

  const outputLogicRange = ranges.get('output_logic');
  if (outputLogicRange) {
    const edit = spliceBlockLines(text, outputLogicRange, (code) =>
      renameInMappingValues(code, oldName, newName),
    );
    if (edit) edits.push(edit);
  }

  const propertiesRange = ranges.get('properties');
  if (propertiesRange) {
    const edit = spliceBlockLines(text, propertiesRange, (code) =>
      renameInField(code, 'expr', oldName, newName),
    );
    if (edit) edits.push(edit);
  }

  const expressionsRange = ranges.get('expressions');
  if (expressionsRange) {
    const edit = spliceBlockLines(text, expressionsRange, (code) =>
      renameInMappingValues(code, oldName, newName),
    );
    if (edit) edits.push(edit);
  }

  const fmRange = ranges.get('fundamental_mode');
  if (fmRange) {
    const edit = spliceBlockLines(text, fmRange, (code) =>
      replaceIdentifier(code, oldName, newName),
    );
    if (edit) edits.push(edit);
  }

  // A macro's `enable` is an expression over inputs, so it is renamed too.
  // Same reason as `properties[].expr` above: nothing diagnoses the stranded
  // reference, so skipping it strands `enable` silently.
  const macrosRange = ranges.get('macros');
  if (macrosRange) {
    const edit = spliceBlockLines(text, macrosRange, (code) =>
      renameInField(code, 'enable', oldName, newName),
    );
    if (edit) edits.push(edit);
  }

  // `safe_state` keys are output names and its values are 0/1/any, so an input
  // name can never legitimately appear there; it is deliberately left untouched
  // (see BUILD-NOTES-spine.md).

  if (edits.length === 0) {
    return { text, diagnostics: parsed.diagnostics };
  }
  const newText = applyRangeEdits(text, edits);
  const outcome = parseDesignText(newText);
  if (outcome.model === null) {
    return { text, diagnostics: outcome.diagnostics };
  }
  return { text: newText, diagnostics: outcome.diagnostics };
}

function escapeRegExp(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

/* ------------------------------------------------------------------ */
/* Serialisation of a model back to a document (rare, whole-document)  */
/* ------------------------------------------------------------------ */

export function modelToYaml(model: DesignModel): string {
  const root: Record<string, YValue> = {
    name: model.name,
    timing_model: model.timingModel,
    encoding: model.encoding,
    states: model.states,
    initial: model.initial,
    inputs: model.inputs.map((i) => ({ name: i.name, sync: i.sync })),
    outputs: model.outputs.map((o) => ({ name: o.name })),
    expressions: model.expressions,
    transitions: model.transitions.map((t) => ({ from: t.from, to: t.to, when: t.when })),
    output_logic: model.outputLogic,
    properties: model.properties.map((p) => {
      const m: Record<string, YValue> = { name: p.name, kind: p.kind };
      if (p.expr !== undefined) m.expr = p.expr;
      if (p.from !== undefined) m.from = p.from;
      if (p.to !== undefined) m.to = p.to;
      return m;
    }),
    safe_state: model.safeState,
    test_points: model.testPoints.map((t) => ({ net: t.net })),
    macros: model.macros.map((m) => {
      const mm: Record<string, YValue> = { instance: m.instance, cell: m.cell, clock: m.clock };
      if (m.enable !== undefined) mm.enable = m.enable;
      return mm;
    }),
    constraints: constraintsToYaml(model.constraints),
  };
  if (model.clock) {
    root.clock = { signal: model.clock.signal, freq_hz: model.clock.freqHz, source: model.clock.source };
  }
  root.reset = {
    signal: model.reset.signal,
    active: model.reset.active,
    async_assert: model.reset.asyncAssert,
    sync_deassert: model.reset.syncDeassert,
    source: model.reset.source,
  };
  if (model.fundamentalMode) {
    root.fundamental_mode = { mutually_exclusive: model.fundamentalMode.mutuallyExclusive };
  }
  if (model.packing.forceGroups.length > 0) {
    root.packing = { force_groups: model.packing.forceGroups.map((g) => [...g]) };
  }
  return serializeDocument(root);
}

/** §C13: replace the persisted packing overrides (force_groups) in the text. */
export function setPackingForceGroups(text: string, forceGroups: string[][]): EditOutcome {
  return setField(text, 'packing', { force_groups: forceGroups.map((g) => [...g]) });
}

/**
 * §C12: replace the persisted test points in the text.
 *
 * This is the same surgical splice as `setField` — only the `test_points`
 * value block is rewritten, so comments and formatting elsewhere in the
 * document survive untouched. The *caller* is responsible for the stable-name
 * guard: a Yosys-generated net name must be refused before it reaches here.
 */
export function setTestPoints(text: string, nets: string[]): EditOutcome {
  const { ranges } = parseToJs(text);
  const block = ranges.get('test_points');

  // No block yet: appending a fresh one cannot destroy anything.
  if (block === undefined) {
    return setField(text, 'test_points', nets.map((net) => ({ net })));
  }

  // A block that already exists is edited line by line, for the same reason
  // `setInputSync` is: re-serialising it from the model drops every comment
  // inside it. Measured — adding a second test point deleted
  // `# probe pad next to U3, reachable with a scope hook` from the first.
  const wanted = new Set(nets);
  const before = text.slice(0, block.valueStart);
  const body = text.slice(block.valueStart, block.valueEnd);
  const after = text.slice(block.valueEnd);

  const entry = /(^|[{,\s])net\s*:\s*["']?([^"',}\s]+)["']?/;
  const lines = body.split('\n');
  const kept: string[] = [];
  const present = new Set<string>();
  let lastEntry = -1;
  let indent = '  - ';

  for (const line of lines) {
    const code = line.indexOf('#') === -1 ? line : line.slice(0, line.indexOf('#'));
    const match = entry.exec(code);
    if (match === null) {
      kept.push(line);
      continue;
    }
    const net = match[2];
    indent = /^\s*-\s*/.exec(line)?.[0] ?? indent;
    if (!wanted.has(net)) continue; // removed: drop this entry's line
    present.add(net);
    lastEntry = kept.length;
    kept.push(line);
  }

  const added = nets.filter((net) => !present.has(net)).map((net) => `${indent}{net: ${net}}`);
  if (added.length > 0) {
    const at = lastEntry === -1 ? kept.length : lastEntry + 1;
    kept.splice(at, 0, ...added);
  }

  const next = before + kept.join('\n') + after;
  const reparsed = parseDesignText(next);
  if (reparsed.model === null) {
    return { text, diagnostics: reparsed.diagnostics };
  }
  return { text: next, diagnostics: reparsed.diagnostics };
}

/**
 * §C12: set one input's `sync` flag in the text, leaving every other input's
 * value (and the rest of the document) untouched.
 *
 * An unknown input is not a silent no-op: it returns the text unchanged plus a
 * diagnostic, so the caller can surface the refusal instead of writing nothing
 * and letting the user believe the synchroniser changed.
 */
export function setInputSync(text: string, name: string, sync: boolean): EditOutcome {
  const outcome = parseDesignText(text);
  if (outcome.model === null) {
    return { text, diagnostics: outcome.diagnostics };
  }
  if (!outcome.model.inputs.some((i) => i.name === name)) {
    return {
      text,
      diagnostics: [
        ...outcome.diagnostics,
        diag('error', 'ED1024', `no input named ${JSON.stringify(name)} to set sync on`),
      ],
    };
  }

  // Rewrite ONE input's `sync` token in place rather than re-serialising the
  // `inputs:` block from the model.
  //
  // Re-serialising is what `setField` does, and it is right for a scalar like
  // `encoding`. For a list it destroys everything inside the block that the
  // model does not carry — which is every comment in it. Measured: toggling
  // input `b` deleted `# MUST stay synchronised — metastability` from input
  // `a`. That is a safety note about metastability, removed by editing an
  // unrelated field, and the user is never told.
  const { ranges } = parseToJs(text);
  const block = ranges.get('inputs');
  if (block === undefined) {
    return { text, diagnostics: outcome.diagnostics };
  }

  const before = text.slice(0, block.valueStart);
  const body = text.slice(block.valueStart, block.valueEnd);
  const after = text.slice(block.valueEnd);
  const lines = body.split('\n');

  // The line that declares this input. `name:` may be flow (`- {name: a, …}`)
  // or block (`- name: a`); both put it on the item's first line.
  const declares = new RegExp(`(^|[{,\\s])name\\s*:\\s*["']?${escapeRegExp(name)}["']?(\\s*[,}]|\\s*$)`);
  const index = lines.findIndex((line) => declares.test(stripComment(line)));
  if (index === -1) {
    return { text, diagnostics: outcome.diagnostics };
  }

  const value = sync ? 'true' : 'false';
  const line = lines[index];
  const code = stripComment(line);

  if (/\bsync\s*:/.test(code)) {
    // Replace the existing token, leaving any trailing comment untouched.
    lines[index] = replaceOutsideComment(line, /(\bsync\s*:\s*)(true|false)/, `$1${value}`);
  } else if (code.includes('{')) {
    lines[index] = replaceOutsideComment(line, /\}/, `, sync: ${value}}`);
  } else {
    // Block style: `sync` may be on a later line of the same item, else insert
    // one after the name with the item's own indent.
    let target = -1;
    for (let i = index + 1; i < lines.length; i += 1) {
      if (/^\s*-/.test(lines[i])) break; // next item
      if (/\bsync\s*:/.test(stripComment(lines[i]))) {
        target = i;
        break;
      }
    }
    if (target !== -1) {
      lines[target] = replaceOutsideComment(lines[target], /(\bsync\s*:\s*)(true|false)/, `$1${value}`);
    } else {
      const indent = (/^\s*-\s*/.exec(lines[index])?.[0] ?? '  - ').replace(/-/, ' ');
      lines.splice(index + 1, 0, `${indent}sync: ${value}`);
    }
  }

  const next = before + lines.join('\n') + after;
  const reparsed = parseDesignText(next);
  // A splice that produced something unparseable must not be handed back as an
  // edit; the caller would write it to disk.
  if (reparsed.model === null) {
    return { text, diagnostics: reparsed.diagnostics };
  }
  return { text: next, diagnostics: reparsed.diagnostics };
}

/** The part of a YAML line before any `#` comment. */
function stripComment(line: string): string {
  const hash = line.indexOf('#');
  return hash === -1 ? line : line.slice(0, hash);
}

/** Apply a replacement to the code part of a line, preserving its comment. */
function replaceOutsideComment(line: string, pattern: RegExp, replacement: string): string {
  const hash = line.indexOf('#');
  if (hash === -1) return line.replace(pattern, replacement);
  return line.slice(0, hash).replace(pattern, replacement) + line.slice(hash);
}

function constraintsToYaml(c: Constraints): Record<string, YValue> {
  const out: Record<string, YValue> = { vcc: c.vcc };
  if (c.maxFlops !== undefined) out.max_flops = c.maxFlops;
  if (c.maxPackages !== undefined) out.max_packages = c.maxPackages;
  if (c.maxStaticUa !== undefined) out.max_static_ua = c.maxStaticUa;
  return out;
}
