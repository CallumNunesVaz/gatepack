/**
 * A minimal YAML-subset parser/serialiser for `design.yaml`, mirroring
 * `gatepack/frontend/yaml_subset.py` (parse) and `gatepack/project/serialize.py`
 * (emit) so that the renderer accepts exactly the subset the core accepts and
 * re-emits it canonically.
 *
 * Deliberate subset (identical to the core):
 *   - block mappings and sequences, flow mappings and sequences (nestable),
 *   - single/double-quoted and plain scalars, ints, floats, true/false/null,
 *   - only `true`/`false`/`null` are special (a state named `ON` stays a string),
 *   - block scalars (`|`/`>`), anchors/aliases and tags are rejected,
 *   - tab indentation is rejected, duplicate mapping keys are rejected.
 *
 * In addition the parser records, for every top-level key, the exact character
 * range of its value so the spec editor can apply a *surgical* text edit
 * (replace one block) without disturbing the rest of the document.
 */

export class YamlError extends Error {
  line: number;
  constructor(line: number, message: string) {
    super(`line ${line}: ${message}`);
    this.line = line;
    this.name = 'YamlError';
  }
}

export type YValue = null | boolean | number | string | YValue[] | { [key: string]: YValue };

export type YamlNode =
  | { kind: 'scalar'; raw: string; value: string; line: number }
  | { kind: 'mapping'; items: Array<{ key: string; value: YamlNode }>; line: number }
  | { kind: 'sequence'; items: YamlNode[]; line: number };

export interface Range {
  /** Offset immediately after the `:` that ends the key. */
  valueStart: number;
  /** Offset at the end of the value (exclusive). */
  valueEnd: number;
  line: number;
}

export interface ParseResult {
  root: YamlNode;
  ranges: Map<string, Range>;
}

interface Line {
  content: string;
  start: number;
  lineno: number;
}

/* ------------------------------------------------------------------ */
/* Preprocessing                                                       */
/* ------------------------------------------------------------------ */

function stripComment(line: string): string {
  let quote: string | null = null;
  let i = 0;
  const n = line.length;
  while (i < n) {
    const c = line[i];
    if (quote) {
      if (c === '\\' && i + 1 < n) {
        i += 2;
        continue;
      }
      if (c === quote) quote = null;
    } else {
      if (c === '"' || c === "'") quote = c;
      else if (c === '#' && (i === 0 || line[i - 1] === ' ' || line[i - 1] === '\t')) {
        return line.slice(0, i);
      }
    }
    i += 1;
  }
  return line;
}

function preprocess(text: string): Line[] {
  const lines: Line[] = [];
  let offset = 0;
  for (const raw of text.split('\n')) {
    const content = stripComment(raw).replace(/\s+$/, '');
    lines.push({ content, start: offset, lineno: lines.length + 1 });
    offset += raw.length + 1;
  }
  return lines;
}

function indent(content: string): number {
  let count = 0;
  for (const c of content) {
    if (c === ' ') count += 1;
    else if (c === '\t') throw new YamlError(0, 'tab characters are not allowed in indentation');
    else break;
  }
  return count;
}

function isSeqItem(content: string): boolean {
  const s = content.replace(/^\s+/, '');
  return s === '-' || s.startsWith('- ');
}

function seqItemRest(content: string): string {
  const s = content.replace(/^\s+/, '');
  return s.slice(1).trim();
}

/* ------------------------------------------------------------------ */
/* Parser                                                              */
/* ------------------------------------------------------------------ */

class Parser {
  lines: Line[];
  pos = 0;
  topRanges: Map<string, Range>;
  /** End offset of the last line actually consumed (blank lines excluded). */
  lastEnd = 0;

  constructor(lines: Line[]) {
    this.lines = lines;
    this.topRanges = new Map();
  }

  peek(): Line | null {
    while (this.pos < this.lines.length) {
      const line = this.lines[this.pos];
      if (line.content.trim()) return line;
      this.pos += 1;
    }
    return null;
  }

  parseBlockNode(ind: number): YamlNode {
    const entry = this.peek();
    if (entry === null) return { kind: 'scalar', raw: '', value: '', line: 0 };
    if (isSeqItem(entry.content)) return this.parseSequence(ind, entry.lineno);
    return this.parseMapping(ind, entry.lineno);
  }

  parseMapping(ind: number, startLine: number): YamlNode {
    const items: Array<{ key: string; value: YamlNode }> = [];
    const seen = new Set<string>();
    for (;;) {
      const entry = this.peek();
      if (entry === null) break;
      const cur = indent(entry.content);
      if (cur < ind) break;
      if (cur > ind) throw new YamlError(entry.lineno, 'unexpected indentation');
      if (isSeqItem(entry.content)) {
        throw new YamlError(entry.lineno, 'sequence item where mapping key expected');
      }
      const { key, rest } = splitMappingLine(entry.content, entry.lineno);
      if (seen.has(key)) {
        throw new YamlError(
          entry.lineno,
          `duplicate mapping key ${JSON.stringify(key)} (text is canonical; a duplicate is a silent wrong build)`,
        );
      }
      seen.add(key);
      const colonOffset = entry.content.indexOf(':');
      // valueStart: right after the colon (the inline space/newline is part of
      // the replacement text we splice back in).
      const valueStart = entry.start + colonOffset + 1;
      this.pos += 1;
      this.lastEnd = entry.start + entry.content.length;
      let value: YamlNode;
      let valueEnd: number;
      if (rest === null) {
        const nxt = this.peek();
        if (nxt === null || indent(nxt.content) <= ind) {
          value = { kind: 'scalar', raw: '', value: '', line: entry.lineno };
          valueEnd = entry.start + entry.content.length;
        } else {
          value = this.parseBlockNode(indent(nxt.content));
          valueEnd = this.lastEnd;
        }
      } else {
        value = parseInlineValue(rest, entry.lineno);
        valueEnd = entry.start + entry.content.length;
      }
      items.push({ key, value });
      if (ind === 0) {
        this.topRanges.set(key, { valueStart, valueEnd, line: entry.lineno });
      }
    }
    return { kind: 'mapping', items, line: startLine };
  }

  parseSequence(ind: number, startLine: number): YamlNode {
    const items: YamlNode[] = [];
    for (;;) {
      const entry = this.peek();
      if (entry === null) break;
      const cur = indent(entry.content);
      if (cur < ind) break;
      if (cur > ind) throw new YamlError(entry.lineno, 'unexpected indentation');
      if (!isSeqItem(entry.content)) break;
      const rest = seqItemRest(entry.content);
      this.pos += 1;
      this.lastEnd = entry.start + entry.content.length;
      if (rest === '') {
        const nxt = this.peek();
        if (nxt !== null && indent(nxt.content) > ind) {
          items.push(this.parseBlockNode(indent(nxt.content)));
        } else {
          items.push({ kind: 'scalar', raw: '', value: '', line: entry.lineno });
        }
      } else {
        items.push(parseInlineValue(rest, entry.lineno));
      }
    }
    return { kind: 'sequence', items, line: startLine };
  }
}

function splitMappingLine(content: string, lineno: number): { key: string; rest: string | null } {
  let quote: string | null = null;
  let i = 0;
  const n = content.length;
  while (i < n) {
    const c = content[i];
    if (quote) {
      if (c === '\\' && i + 1 < n) {
        i += 2;
        continue;
      }
      if (c === quote) quote = null;
    } else {
      if (c === '"' || c === "'") quote = c;
      else if (c === ':') {
        const key = stripQuotes(content.slice(0, i).trim());
        if (!key) throw new YamlError(lineno, 'empty mapping key');
        const rest = content.slice(i + 1).trim();
        return { key, rest: rest ? rest : null };
      }
    }
    i += 1;
  }
  throw new YamlError(lineno, `expected 'key: value', got ${JSON.stringify(content)}`);
}

function stripQuotes(s: string): string {
  if (s.length >= 2 && s[0] === '"' && s[s.length - 1] === '"') return unquote(s.slice(1, -1), '"');
  if (s.length >= 2 && s[0] === "'" && s[s.length - 1] === "'") return s.slice(1, -1).replace(/''/g, "'");
  return s;
}

/* ------------------------------------------------------------------ */
/* Flow parser                                                         */
/* ------------------------------------------------------------------ */

function parseInlineValue(text: string, lineno: number): YamlNode {
  const t = text.trim();
  if (!t) return { kind: 'scalar', raw: '', value: '', line: lineno };
  if (t.startsWith('{')) {
    if (!t.endsWith('}')) throw new YamlError(lineno, `unterminated flow mapping: ${JSON.stringify(t)}`);
    return parseFlowMapping(t, lineno);
  }
  if (t.startsWith('[')) {
    if (!t.endsWith(']')) throw new YamlError(lineno, `unterminated flow sequence: ${JSON.stringify(t)}`);
    return parseFlowSequence(t, lineno);
  }
  if (t === '|' || t === '>' || t.startsWith('|') || t.startsWith('>')) {
    throw new YamlError(lineno, 'block scalars (|/ >) are not supported');
  }
  return { kind: 'scalar', raw: t, value: t, line: lineno };
}

function parseFlowMapping(text: string, lineno: number): YamlNode {
  const inner = text.slice(1, -1).trim();
  const items: Array<{ key: string; value: YamlNode }> = [];
  const seen = new Set<string>();
  if (inner) {
    for (const part of splitTopLevel(inner, ',')) {
      const p = part.trim();
      if (!p) continue;
      const { key, value } = splitFlowKv(p, lineno);
      if (seen.has(key)) {
        throw new YamlError(lineno, `duplicate mapping key ${JSON.stringify(key)}`);
      }
      seen.add(key);
      items.push({ key, value: parseInlineValue(value, lineno) });
    }
  }
  return { kind: 'mapping', items, line: lineno };
}

function parseFlowSequence(text: string, lineno: number): YamlNode {
  const inner = text.slice(1, -1).trim();
  const items: YamlNode[] = [];
  if (inner) {
    for (const part of splitTopLevel(inner, ',')) {
      const p = part.trim();
      if (p === '') continue;
      items.push(parseInlineValue(p, lineno));
    }
  }
  return { kind: 'sequence', items, line: lineno };
}

function splitTopLevel(text: string, sep: string): string[] {
  const parts: string[] = [];
  let depth = 0;
  let quote: string | null = null;
  let cur = '';
  let i = 0;
  const n = text.length;
  while (i < n) {
    const c = text[i];
    if (quote) {
      cur += c;
      if (c === '\\' && i + 1 < n) {
        cur += text[i + 1];
        i += 2;
        continue;
      }
      if (c === quote) quote = null;
      i += 1;
      continue;
    }
    if (c === '"' || c === "'") {
      quote = c;
      cur += c;
      i += 1;
      continue;
    }
    if (c === '{' || c === '[') depth += 1;
    else if (c === '}' || c === ']') depth -= 1;
    if (c === sep && depth === 0) {
      parts.push(cur);
      cur = '';
      i += 1;
      continue;
    }
    cur += c;
    i += 1;
  }
  parts.push(cur);
  return parts;
}

function splitFlowKv(part: string, lineno: number): { key: string; value: string } {
  let quote: string | null = null;
  let depth = 0;
  let i = 0;
  const n = part.length;
  while (i < n) {
    const c = part[i];
    if (quote) {
      if (c === '\\' && i + 1 < n) {
        i += 2;
        continue;
      }
      if (c === quote) quote = null;
      i += 1;
      continue;
    }
    if (c === '"' || c === "'") {
      quote = c;
      i += 1;
      continue;
    }
    if (c === '{' || c === '[') depth += 1;
    else if (c === '}' || c === ']') depth -= 1;
    else if (c === ':' && depth === 0) {
      const key = stripQuotes(part.slice(0, i).trim());
      if (!key) throw new YamlError(lineno, `empty key in flow mapping: ${JSON.stringify(part)}`);
      return { key, value: part.slice(i + 1).trim() };
    }
    i += 1;
  }
  throw new YamlError(lineno, `expected 'key: value' in flow mapping, got ${JSON.stringify(part)}`);
}

/* ------------------------------------------------------------------ */
/* Scalar interpretation                                               */
/* ------------------------------------------------------------------ */

function unquote(s: string, quote: string): string {
  let out = '';
  let i = 0;
  const n = s.length;
  while (i < n) {
    const c = s[i];
    if (c === '\\' && i + 1 < n) {
      const nxt = s[i + 1];
      const escapes: Record<string, string> = {
        n: '\n', t: '\t', r: '\r', '0': '\0', '\\': '\\', '"': '"', "'": "'",
      };
      out += nxt in escapes ? escapes[nxt] : nxt;
      i += 2;
      continue;
    }
    out += c;
    i += 1;
  }
  void quote;
  return out;
}

function isInt(s: string): boolean {
  if (!s) return false;
  const body = s[0] === '+' || s[0] === '-' ? s.slice(1) : s;
  return body.length > 0 && /^[0-9]+$/.test(body);
}

function isFloat(s: string): boolean {
  if (!s || !/[0-9]/.test(s)) return false;
  if (!/[.eE]/.test(s)) return false;
  return Number.isFinite(Number(s));
}

function scalarValue(raw: string): YValue {
  const s = raw;
  if (s.length >= 2 && s[0] === '"' && s[s.length - 1] === '"') return unquote(s.slice(1, -1), '"');
  if (s.length >= 2 && s[0] === "'" && s[s.length - 1] === "'") return s.slice(1, -1).replace(/''/g, "'");
  if (s === 'true') return true;
  if (s === 'false') return false;
  if (s === 'null' || s === '~' || s === '') return null;
  if (isInt(s)) return parseInt(s, 10);
  if (isFloat(s)) return parseFloat(s);
  return s;
}

/* ------------------------------------------------------------------ */
/* Conversion to plain JS                                              */
/* ------------------------------------------------------------------ */

export function toJs(node: YamlNode): YValue {
  if (node.kind === 'scalar') return scalarValue(node.value);
  if (node.kind === 'mapping') {
    const out: Record<string, YValue> = {};
    for (const { key, value } of node.items) out[key] = toJs(value);
    return out;
  }
  return node.items.map(toJs);
}

/* ------------------------------------------------------------------ */
/* Public parse                                                        */
/* ------------------------------------------------------------------ */

export function parse(text: string): ParseResult {
  const lines = preprocess(text);
  if (lines.length === 0) throw new YamlError(1, 'empty document');
  const parser = new Parser(lines);
  const root = parser.parseBlockNode(0);
  return { root, ranges: parser.topRanges };
}

export function parseToJs(text: string): { value: YValue; ranges: Map<string, Range> } {
  const { root, ranges } = parse(text);
  return { value: toJs(root), ranges };
}

/* ------------------------------------------------------------------ */
/* Serialiser (mirrors gatepack/project/serialize.py)                  */
/* ------------------------------------------------------------------ */

const SAFE_PLAIN = /^[A-Za-z0-9_][A-Za-z0-9_./-]*$/;
const RESERVED = new Set(['true', 'false', 'null', '~']);
const ESCAPES: Record<string, string> = {
  '\\': '\\\\', '"': '\\"', '\n': '\\n', '\t': '\\t', '\r': '\\r', '\0': '\\0',
};

function looksNumeric(s: string): boolean {
  if (s === '') return false;
  if (Number.isFinite(Number(s))) return true;
  return false;
}

function dumpString(s: string): string {
  if (s === '') return '""';
  if (SAFE_PLAIN.test(s) && !RESERVED.has(s) && !looksNumeric(s)) return s;
  let out = '"';
  for (const c of s) out += c in ESCAPES ? ESCAPES[c] : c;
  return out + '"';
}

function scalarToken(value: YValue): string {
  if (value === null) return '~';
  if (value === true) return 'true';
  if (value === false) return 'false';
  if (typeof value === 'number') return String(value);
  if (typeof value === 'string') return dumpString(value);
  throw new Error(`cannot emit YAML for ${typeof value}`);
}

export function isDict(v: YValue | undefined): v is Record<string, YValue> {
  return typeof v === 'object' && v !== null && !Array.isArray(v);
}

export function isList(v: YValue | undefined): v is YValue[] {
  return Array.isArray(v);
}

function allScalars(value: YValue): boolean {
  if (isDict(value)) return Object.values(value).every((v) => isScalar(v));
  if (isList(value)) return value.every((v) => isScalar(v));
  return true;
}

function isScalar(v: YValue | undefined): v is null | boolean | number | string {
  return v === null || typeof v === 'boolean' || typeof v === 'number' || typeof v === 'string';
}

function flowMapping(mapping: Record<string, YValue>): string {
  const inner = Object.keys(mapping)
    .sort()
    .map((k) => `${dumpString(k)}: ${scalarToken(mapping[k])}`)
    .join(', ');
  return `{${inner}}`;
}

function flowSequence(items: YValue[]): string {
  return `[${items.map(scalarToken).join(', ')}]`;
}

function inline(value: YValue): string {
  if (isScalar(value)) return scalarToken(value);
  if (isDict(value)) return flowMapping(value);
  if (isList(value)) return flowSequence(value);
  throw new Error(`cannot emit YAML for ${typeof value}`);
}

function blockMappingLines(mapping: Record<string, YValue>, level: number): string[] {
  const pad = '  '.repeat(level);
  const lines: string[] = [];
  for (const key of Object.keys(mapping).sort()) {
    const value = mapping[key];
    if (isDict(value) && !allScalars(value)) {
      lines.push(`${pad}${dumpString(key)}:`);
      lines.push(...blockMappingLines(value, level + 1));
    } else if (isList(value) && !allScalars(value)) {
      lines.push(`${pad}${dumpString(key)}:`);
      lines.push(...blockSequenceLines(value, level + 1));
    } else {
      lines.push(`${pad}${dumpString(key)}: ${inline(value)}`);
    }
  }
  return lines;
}

function blockSequenceLines(items: YValue[], level: number): string[] {
  const pad = '  '.repeat(level);
  const lines: string[] = [];
  for (const item of items) {
    if (isDict(item) && !allScalars(item)) {
      lines.push(`${pad}-`);
      lines.push(...blockMappingLines(item, level + 1));
    } else if (isList(item) && !allScalars(item)) {
      lines.push(`${pad}-`);
      lines.push(...blockSequenceLines(item, level + 1));
    } else {
      lines.push(`${pad}- ${inline(item)}`);
    }
  }
  return lines;
}

/**
 * The text to splice between a top-level key's `valueStart`/`valueEnd`. Scalars
 * are prefixed with a single space; blocks are prefixed with a newline and
 * emitted at indent level 1 (two spaces, the top-level value indent).
 */
export function serializeTopLevelValue(value: YValue): string {
  if (isScalar(value)) return ` ${scalarToken(value)}`;
  if (isDict(value) && !allScalars(value)) return `\n${blockMappingLines(value, 1).join('\n')}`;
  if (isList(value) && !allScalars(value)) return `\n${blockSequenceLines(value, 1).join('\n')}`;
  return ` ${inline(value)}`;
}

/** Serialise a complete design document (canonical, sorted keys). */
export function serializeDocument(mapping: Record<string, YValue>): string {
  return `${blockMappingLines(mapping, 0).join('\n')}\n`;
}

export function spliceText(text: string, start: number, end: number, replacement: string): string {
  return text.slice(0, start) + replacement + text.slice(end);
}
