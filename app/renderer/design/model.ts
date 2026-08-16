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

/** Rename a state everywhere it appears (states, initial, transitions, output_logic, macros). */
export function renameState(text: string, oldName: string, newName: string): EditOutcome {
  if (!isIdentifier(newName)) {
    const outcome = parseDesignText(text);
    return {
      text,
      diagnostics: [...outcome.diagnostics, diag('error', 'ED1023', `state name ${JSON.stringify(newName)} is not a valid Verilog identifier`)],
    };
  }
  const { value } = parseToJs(text);
  const root = asDict(value) ?? {};

  const renameExprState = (expr: string): string =>
    expr.replace(new RegExp(`\\bstate\\s*==\\s*${escapeRegExp(oldName)}\\b`, 'g'), `state == ${newName}`);

  const edits = new Map<string, YValue>();

  const states = (asList(root['states']) ?? []).map((s) => (asString(s) === oldName ? newName : s));
  edits.set('states', states);

  if (asString(root['initial']) === oldName) edits.set('initial', newName);

  const transitions = (asList(root['transitions']) ?? []).map((item) => {
    const m = asDict(item);
    if (!m) return item;
    const out: Record<string, YValue> = { ...m };
    if (asString(m['from']) === oldName) out['from'] = newName;
    if (asString(m['to']) === oldName) out['to'] = newName;
    return out;
  });
  edits.set('transitions', transitions);

  const outputLogic = { ...(asDict(root['output_logic']) ?? {}) };
  for (const [k, v] of Object.entries(outputLogic)) {
    if (asString(v) !== null) outputLogic[k] = renameExprState(asString(v) as string);
  }
  edits.set('output_logic', outputLogic);

  const macros = (asList(root['macros']) ?? []).map((item) => {
    const m = asDict(item);
    if (!m) return item;
    const out: Record<string, YValue> = { ...m };
    const enable = asString(m['enable']);
    if (enable !== null) out['enable'] = renameExprState(enable);
    return out;
  });
  edits.set('macros', macros);

  return applyEdits(text, edits);
}

function applyEdits(text: string, edits: Map<string, YValue>): EditOutcome {
  const { ranges } = parseToJs(text);
  const replacements: Array<{ start: number; end: number; value: string }> = [];
  for (const [key, value] of edits) {
    const range = ranges.get(key);
    if (!range) continue;
    replacements.push({
      start: range.valueStart,
      end: range.valueEnd,
      value: serializeTopLevelValue(value),
    });
  }
  replacements.sort((a, b) => b.start - a.start);
  let newText = text;
  for (const r of replacements) {
    newText = spliceText(newText, r.start, r.end, r.value);
  }
  const outcome = parseDesignText(newText);
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

function constraintsToYaml(c: Constraints): Record<string, YValue> {
  const out: Record<string, YValue> = { vcc: c.vcc };
  if (c.maxFlops !== undefined) out.max_flops = c.maxFlops;
  if (c.maxPackages !== undefined) out.max_packages = c.maxPackages;
  if (c.maxStaticUa !== undefined) out.max_static_ua = c.maxStaticUa;
  return out;
}
