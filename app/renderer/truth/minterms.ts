/**
 * Pure helpers for the truth-table grid: input-minterm enumeration, live output
 * evaluation from the spec (the sanctioned client-side exception), and
 * reachability for the coverage indicator. No synthesis, no core call.
 */

import { expand, evaluate, parse as parseExpr, type Bit } from '../design/expr';
import type { DesignModel } from '../design/model';

export const MAX_MINTERM_INPUTS = 12;

/** All 2^n input assignments, bit n-1 as the most-significant column. */
export function allMinterms(inputs: string[]): Array<Record<string, Bit>> {
  const n = inputs.length;
  const out: Array<Record<string, Bit>> = [];
  for (let code = 0; code < 1 << n; code += 1) {
    const env: Record<string, Bit> = {};
    for (let i = 0; i < n; i += 1) {
      env[inputs[i]] = (code >> (n - 1 - i)) & 1 ? '1' : '0';
    }
    out.push(env);
  }
  return out;
}

/**
 * Evaluate every output's `output_logic` (with named expressions expanded) under
 * an input assignment and an optional state context. `state == NAME` yields 'x'
 * when no state context is supplied.
 */
export function computeLiveOutputs(
  model: DesignModel,
  env: Record<string, Bit>,
  state?: string,
): Record<string, Bit> {
  const expressionAsts: Record<string, ReturnType<typeof parseExpr>> = {};
  for (const [name, text] of Object.entries(model.expressions)) {
    try {
      expressionAsts[name] = parseExpr(text);
    } catch {
      // invalid expressions are surfaced by the editor; skip here
    }
  }
  const out: Record<string, Bit> = {};
  for (const [name, text] of Object.entries(model.outputLogic)) {
    try {
      const ast = expand(parseExpr(text), expressionAsts);
      out[name] = evaluate(ast, env, state);
    } catch {
      out[name] = 'x';
    }
  }
  return out;
}

/** States reachable from the initial state (adjacency only, mirrors the core). */
export function reachableStates(model: DesignModel): Set<string> {
  const graph = new Map<string, string[]>();
  for (const s of model.states) graph.set(s, []);
  for (const t of model.transitions) {
    graph.get(t.from)?.push(t.to);
  }
  const seen = new Set<string>();
  const stack = [model.initial];
  while (stack.length) {
    const node = stack.pop()!;
    if (seen.has(node)) continue;
    seen.add(node);
    for (const nxt of graph.get(node) ?? []) {
      if (!seen.has(nxt)) stack.push(nxt);
    }
  }
  return seen;
}

/** Whether the design's outputs are purely combinational (no `state ==`). */
export function isCombinational(model: DesignModel): boolean {
  return Object.values(model.outputLogic).every((text) => {
    try {
      return !text.includes('state');
    } catch {
      return false;
    }
  });
}
