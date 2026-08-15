import { describe, expect, it } from 'vitest';
import {
  evaluate,
  expand,
  freeVars,
  parse,
  statesReferenced,
  ExprError,
  type Bit,
} from './expr';

function ev(text: string, env: Record<string, Bit>, state?: string): Bit {
  return evaluate(parse(text), env, state);
}

describe('boolean expression parser / evaluator', () => {
  it('evaluates xor', () => {
    expect(ev('a ^ b', { a: '1', b: '0' })).toBe('1');
    expect(ev('a ^ b', { a: '1', b: '1' })).toBe('0');
  });

  it('honours precedence ! > & > ^ > |', () => {
    // a | b & c  ===  a | (b & c)
    expect(ev('a | b & c', { a: '1', b: '0', c: '0' })).toBe('1');
    // a ^ b & c  ===  a ^ (b & c)
    expect(ev('a ^ b & c', { a: '1', b: '1', c: '0' })).toBe('1');
    // a ^ b | c  ===  (a ^ b) | c
    expect(ev('a ^ b | c', { a: '1', b: '0', c: '1' })).toBe('1');
    // !a & b  ===  (!a) & b
    expect(ev('!a & b', { a: '0', b: '1' })).toBe('1');
  });

  it('matches the core on the xor2 golden expression', () => {
    // y: "a ^ b"  — full truth table
    const cases: Array<[string, string, string]> = [
      ['0', '0', '0'],
      ['0', '1', '1'],
      ['1', '0', '1'],
      ['1', '1', '0'],
    ];
    for (const [a, b, y] of cases) {
      expect(ev('a ^ b', { a: a as Bit, b: b as Bit })).toBe(y);
    }
  });

  it('evaluates the decoder minterm expressions', () => {
    expect(ev('!s0 & !s1 & !s2', { s0: '0', s1: '0', s2: '0' })).toBe('1');
    expect(ev('!s0 & !s1 & !s2', { s0: '1', s1: '0', s2: '0' })).toBe('0');
    expect(ev('s0 & !s1 & s2', { s0: '1', s1: '0', s2: '1' })).toBe('1');
  });

  it('returns x for an unknown (don\'t-care) input', () => {
    expect(ev('a & b', { a: '1' })).toBe('x');
    expect(ev('a | b', { a: '0' })).toBe('x');
    expect(ev('a ^ b', { a: '1' })).toBe('x');
    expect(ev('!a', {})).toBe('x');
    // short-circuit: a & b with a=0 is 0 even if b unknown
    expect(ev('a & b', { a: '0' })).toBe('0');
    expect(ev('a | b', { a: '1' })).toBe('1');
  });

  it('handles state == NAME', () => {
    const expr = parse('state == RUNNING');
    expect(evaluate(expr, {}, 'RUNNING')).toBe('1');
    expect(evaluate(expr, {}, 'IDLE')).toBe('0');
    expect(evaluate(expr, {})).toBe('x');
  });

  it('evaluates a Moore output_logic expression with state context', () => {
    expect(ev('state == GREEN', {}, 'GREEN')).toBe('1');
    expect(ev('state == GREEN', {}, 'RED')).toBe('0');
  });

  it('reports free variables', () => {
    expect([...freeVars(parse('a & !b | c ^ d'))].sort()).toEqual(['a', 'b', 'c', 'd']);
    expect([...freeVars(parse('state == X'))]).toEqual([]);
  });

  it('reports referenced states', () => {
    expect([...statesReferenced(parse('a & (state == X)'))]).toEqual(['X']);
    expect([...statesReferenced(parse('a & b'))]).toEqual([]);
  });

  it('expands named expressions and detects cycles', () => {
    const defs = { f: parse('a | b'), g: parse('f & c') };
    const expanded = expand(parse('g ^ d'), defs);
    expect([...freeVars(expanded)].sort()).toEqual(['a', 'b', 'c', 'd']);

    expect(() => expand(parse('x'), { x: parse('y'), y: parse('x') })).toThrow(ExprError);
  });

  it('rejects malformed expressions', () => {
    expect(() => parse('')).toThrow(ExprError);
    expect(() => parse('a = b')).toThrow(ExprError);
    expect(() => parse('a &')).toThrow(ExprError);
    expect(() => parse('(a | b')).toThrow(ExprError);
    expect(() => parse('2')).toThrow(/constant/);
    expect(() => parse('state ==')).toThrow(ExprError);
    expect(() => parse('a b')).toThrow(ExprError);
  });
});
