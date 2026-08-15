/**
 * Client-side boolean expression language for `design.yaml` (§10.2).
 *
 * This mirrors `gatepack/frontend/expr.py` exactly — the *same* language the
 * core parses — so the live truth-table column (the sanctioned client-side
 * exception) evaluates identically to the core:
 *
 *   - identifiers reference inputs or named expressions,
 *   - `!` (not), `&` (and), `|` (or), `^` (xor), parentheses,
 *   - constants `0` / `1`,
 *   - `state == NAME` (Moore-style).
 *
 * Precedence (tightest first): `!`, `&`, `^`, `|`.
 *
 * Evaluation is tri-valued: `'0'`, `'1'`, or `'x'` for unknown (a don't-care
 * input, or a `state ==` test with no state context). This is what lets the
 * truth table render don't-cares honestly instead of guessing.
 */

export class ExprError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'ExprError';
  }
}

export type Bit = '0' | '1' | 'x';

export type Expr =
  | { kind: 'var'; name: string }
  | { kind: 'const'; value: boolean }
  | { kind: 'not'; x: Expr }
  | { kind: 'bin'; op: '&' | '|' | '^'; left: Expr; right: Expr }
  | { kind: 'stateEq'; state: string };

export type Env = Record<string, Bit>;

/* ------------------------------------------------------------------ */
/* Tokeniser                                                           */
/* ------------------------------------------------------------------ */

function tokenize(text: string): string[] {
  const tokens: string[] = [];
  let i = 0;
  const n = text.length;
  while (i < n) {
    const c = text[i];
    if (/\s/.test(c)) {
      i += 1;
      continue;
    }
    if ('&|^!()'.includes(c)) {
      tokens.push(c);
      i += 1;
      continue;
    }
    if (c === '=') {
      if (i + 1 < n && text[i + 1] === '=') {
        tokens.push('==');
        i += 2;
        continue;
      }
      throw new ExprError(`unexpected '=' in expression ${JSON.stringify(text)} (use '==')`);
    }
    if (c >= '0' && c <= '9') {
      let j = i;
      while (j < n && text[j] >= '0' && text[j] <= '9') j += 1;
      tokens.push(text.slice(i, j));
      i = j;
      continue;
    }
    if (/[A-Za-z_]/.test(c)) {
      let j = i;
      while (j < n && /[A-Za-z0-9_]/.test(text[j])) j += 1;
      tokens.push(text.slice(i, j));
      i = j;
      continue;
    }
    throw new ExprError(`unexpected character ${JSON.stringify(c)} in expression ${JSON.stringify(text)}`);
  }
  return tokens;
}

/* ------------------------------------------------------------------ */
/* Parser (recursive descent, precedence ! > & > ^ > |)                */
/* ------------------------------------------------------------------ */

function parseOr(tokens: string[], pos: number): [Expr, number] {
  let [node, p] = parseXor(tokens, pos);
  while (p < tokens.length && tokens[p] === '|') {
    const [rhs, q] = parseXor(tokens, p + 1);
    node = { kind: 'bin', op: '|', left: node, right: rhs };
    p = q;
  }
  return [node, p];
}

function parseXor(tokens: string[], pos: number): [Expr, number] {
  let [node, p] = parseAnd(tokens, pos);
  while (p < tokens.length && tokens[p] === '^') {
    const [rhs, q] = parseAnd(tokens, p + 1);
    node = { kind: 'bin', op: '^', left: node, right: rhs };
    p = q;
  }
  return [node, p];
}

function parseAnd(tokens: string[], pos: number): [Expr, number] {
  let [node, p] = parseNot(tokens, pos);
  while (p < tokens.length && tokens[p] === '&') {
    const [rhs, q] = parseNot(tokens, p + 1);
    node = { kind: 'bin', op: '&', left: node, right: rhs };
    p = q;
  }
  return [node, p];
}

function parseNot(tokens: string[], pos: number): [Expr, number] {
  if (pos < tokens.length && tokens[pos] === '!') {
    const [node, p] = parseNot(tokens, pos + 1);
    return [{ kind: 'not', x: node }, p];
  }
  return parseAtom(tokens, pos);
}

function parseAtom(tokens: string[], pos: number): [Expr, number] {
  if (pos >= tokens.length) {
    throw new ExprError('unexpected end of expression');
  }
  const token = tokens[pos];
  if (token === '(') {
    const [node, p] = parseOr(tokens, pos + 1);
    if (p >= tokens.length || tokens[p] !== ')') {
      throw new ExprError("missing ')' in expression");
    }
    return [node, p + 1];
  }
  if ('&|^!()=='.includes(token)) {
    throw new ExprError(`unexpected ${JSON.stringify(token)} in expression`);
  }
  if (/^[0-9]+$/.test(token)) {
    if (token !== '0' && token !== '1') {
      throw new ExprError(`constant ${JSON.stringify(token)} must be 0 or 1`);
    }
    return [{ kind: 'const', value: token === '1' }, pos + 1];
  }
  if (token === 'state') {
    if (pos + 2 < tokens.length && tokens[pos + 1] === '==' && /^[A-Za-z_][A-Za-z0-9_]*$/.test(tokens[pos + 2])) {
      return [{ kind: 'stateEq', state: tokens[pos + 2] }, pos + 3];
    }
    throw new ExprError("'state' may only appear as 'state == NAME'");
  }
  return [{ kind: 'var', name: token }, pos + 1];
}

export function parse(text: string): Expr {
  const tokens = tokenize(text);
  if (tokens.length === 0) {
    throw new ExprError('empty expression');
  }
  const [node, pos] = parseOr(tokens, 0);
  if (pos !== tokens.length) {
    throw new ExprError(`unexpected trailing tokens ${JSON.stringify(tokens.slice(pos))} in ${JSON.stringify(text)}`);
  }
  return node;
}

/* ------------------------------------------------------------------ */
/* Analysis                                                            */
/* ------------------------------------------------------------------ */

export function freeVars(expr: Expr): Set<string> {
  switch (expr.kind) {
    case 'var':
      return new Set([expr.name]);
    case 'const':
      return new Set();
    case 'not':
      return freeVars(expr.x);
    case 'bin':
      return new Set([...freeVars(expr.left), ...freeVars(expr.right)]);
    case 'stateEq':
      return new Set();
  }
}

export function statesReferenced(expr: Expr): Set<string> {
  switch (expr.kind) {
    case 'stateEq':
      return new Set([expr.state]);
    case 'var':
    case 'const':
      return new Set();
    case 'not':
      return statesReferenced(expr.x);
    case 'bin':
      return new Set([...statesReferenced(expr.left), ...statesReferenced(expr.right)]);
  }
}

/**
 * Substitute named-expression references with their definitions, detecting
 * cycles (an expression defined in terms of itself, directly or transitively).
 */
export function expand(expr: Expr, definitions: Record<string, Expr>): Expr {
  function go(e: Expr, seen: string[]): Expr {
    switch (e.kind) {
      case 'var': {
        if (e.name in definitions) {
          if (seen.includes(e.name)) {
            throw new ExprError(`cyclic expression definition: ${[...seen, e.name].join(' -> ')}`);
          }
          return go(definitions[e.name], [...seen, e.name]);
        }
        return e;
      }
      case 'const':
      case 'stateEq':
        return e;
      case 'not':
        return { kind: 'not', x: go(e.x, seen) };
      case 'bin':
        return { kind: 'bin', op: e.op, left: go(e.left, seen), right: go(e.right, seen) };
    }
  }
  return go(expr, []);
}

/* ------------------------------------------------------------------ */
/* Evaluation (tri-valued)                                             */
/* ------------------------------------------------------------------ */

function not(b: Bit): Bit {
  if (b === 'x') return 'x';
  return b === '1' ? '0' : '1';
}

function and(a: Bit, b: Bit): Bit {
  if (a === '0' || b === '0') return '0';
  if (a === 'x' || b === 'x') return 'x';
  return '1';
}

function or(a: Bit, b: Bit): Bit {
  if (a === '1' || b === '1') return '1';
  if (a === 'x' || b === 'x') return 'x';
  return '0';
}

function xor(a: Bit, b: Bit): Bit {
  if (a === 'x' || b === 'x') return 'x';
  return a === b ? '0' : '1';
}

/**
 * Evaluate an expression under an input assignment. `state` is the optional
 * state context for `state == NAME` tests; when omitted such a test is `'x'`.
 */
export function evaluate(expr: Expr, env: Env, state?: string): Bit {
  switch (expr.kind) {
    case 'var':
      return expr.name in env ? env[expr.name] : 'x';
    case 'const':
      return expr.value ? '1' : '0';
    case 'not':
      return not(evaluate(expr.x, env, state));
    case 'bin': {
      const left = evaluate(expr.left, env, state);
      const right = evaluate(expr.right, env, state);
      if (expr.op === '&') return and(left, right);
      if (expr.op === '|') return or(left, right);
      return xor(left, right);
    }
    case 'stateEq':
      return state === undefined ? 'x' : state === expr.state ? '1' : '0';
  }
}
