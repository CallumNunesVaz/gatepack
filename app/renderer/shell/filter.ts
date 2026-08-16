/**
 * Palette fuzzy filtering — pure, so the ranking is testable without a render.
 *
 * The filter matches a query against a command's title, hint, id, group and
 * cli tag. Scoring favours whole-field substrings (earlier match ranks higher),
 * then subsequence matches with a penalty for gaps. An empty query returns
 * every command in registry order; a query that matches nothing returns [].
 */

import type { CommandDef } from '../keys/registry';

const HINT_PENALTY = 50;
const META_PENALTY = 100;

function scoreField(query: string, field: string): number {
  const q = query.toLowerCase();
  const f = field.toLowerCase();
  if (q.length === 0) return 0;

  const idx = f.indexOf(q);
  if (idx !== -1) return 1000 - idx;

  // Subsequence match (e.g. "sv" matches "Save as…"): contiguous and early
  // matches score higher, gaps are penalised.
  let qi = 0;
  let first = -1;
  let last = -1;
  for (let i = 0; i < f.length && qi < q.length; i += 1) {
    if (f[i] === q[qi]) {
      if (first === -1) first = i;
      last = i;
      qi += 1;
    }
  }
  if (qi !== q.length) return -1;
  const gap = last - first - (q.length - 1);
  return 500 - first - gap * 10;
}

export function filterCommands(query: string, commands: CommandDef[]): CommandDef[] {
  const q = query.trim();
  if (q === '') return commands.slice();

  interface Scored {
    command: CommandDef;
    score: number;
  }
  const scored: Scored[] = [];
  for (const c of commands) {
    let best = scoreField(q, c.title);
    if (c.hint) best = Math.max(best, scoreField(q, c.hint) - HINT_PENALTY);
    best = Math.max(best, scoreField(q, c.id) - META_PENALTY);
    best = Math.max(best, scoreField(q, c.group) - META_PENALTY);
    if (c.cli) best = Math.max(best, scoreField(q, c.cli) - META_PENALTY);
    if (best >= 0) scored.push({ command: c, score: best });
  }
  scored.sort((a, b) => b.score - a.score);
  return scored.map((s) => s.command);
}
