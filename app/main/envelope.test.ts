import { describe, expect, it } from 'vitest';

import {
  CheckSchema,
  CompileResultSchema,
  DiagnosticSchema,
  envelopeSchema,
  errorEnvelope,
  ExamplesListSchema,
  LibraryCheckResultSchema,
  okEnvelope,
  parseEnvelope,
  VerifyResultSchema,
  NativeThemeSchema,
} from './envelope.cjs';

const validCompile = {
  verilogPath: '/tmp/build/generated.v',
  propertiesPath: null,
  flopCount: 4,
  stateCount: 4,
  encoding: 'one_hot',
  johnsonSuggestion: null,
};

describe('parseEnvelope', () => {
  it('parses a well-formed ok envelope', () => {
    const stdout = JSON.stringify({
      ok: true,
      command: 'compile',
      schema: 1,
      data: validCompile,
      warnings: [],
    });
    const env = parseEnvelope(CompileResultSchema, stdout, 'compile');
    expect(env.ok).toBe(true);
    if (env.ok) {
      expect(env.data.flopCount).toBe(4);
      expect(env.data.encoding).toBe('one_hot');
    }
  });

  it('parses a well-formed error envelope', () => {
    const stdout = JSON.stringify({
      ok: false,
      command: 'compile',
      schema: 1,
      error: { severity: 'error', code: 'GP1003', message: 'bad guard' },
      warnings: [],
    });
    const env = parseEnvelope(CompileResultSchema, stdout, 'compile');
    expect(env.ok).toBe(false);
    if (!env.ok) expect(env.error.code).toBe('GP1003');
  });

  it('rejects non-JSON stdout with a visible error envelope', () => {
    const env = parseEnvelope(CompileResultSchema, 'not json at all', 'compile');
    expect(env.ok).toBe(false);
    if (!env.ok) expect(env.error.code).toBe('GP9002');
  });

  it('rejects an envelope that fails schema validation', () => {
    const stdout = JSON.stringify({
      ok: true,
      command: 'compile',
      schema: 1,
      data: { ...validCompile, encoding: 'not_an_encoding' },
      warnings: [],
    });
    const env = parseEnvelope(CompileResultSchema, stdout, 'compile');
    expect(env.ok).toBe(false);
    if (!env.ok) expect(env.error.code).toBe('GP9003');
  });

  it('rejects a schema version other than 1', () => {
    const stdout = JSON.stringify({
      ok: true,
      command: 'compile',
      schema: 2,
      data: validCompile,
      warnings: [],
    });
    const env = parseEnvelope(CompileResultSchema, stdout, 'compile');
    expect(env.ok).toBe(false);
  });
});

describe('envelope schemas', () => {
  it('validates a diagnostic with provenance', () => {
    const d = DiagnosticSchema.parse({
      severity: 'error',
      code: 'GP1003',
      message: 'nope',
      path: 'design.yaml',
      line: 12,
      column: 3,
      pointer: 'design.yaml:12:transitions[3]',
    });
    expect(d.pointer).toBe('design.yaml:12:transitions[3]');
  });

  it('the ok envelope helper and schema agree', () => {
    const env = okEnvelope('compile', validCompile);
    expect(envelopeSchema(CompileResultSchema).parse(env).ok).toBe(true);
  });

  it('the error envelope helper is a valid envelope', () => {
    const env = errorEnvelope<typeof validCompile>('compile', 'GP9001', 'missing core');
    const parsed = envelopeSchema(CompileResultSchema).parse(env);
    expect(parsed.ok).toBe(false);
  });

  it('library check: "not cited" is an explicit null, never an absent key', () => {
    // `.nullable()` must accept null and must still *require* the key — the
    // trap this repo has hit is `z.unknown()`/`z.any()` inferring optional, so
    // a field silently becomes droppable.
    const withNullCitation = LibraryCheckResultSchema.parse({
      path: '/tmp/parts.csv',
      refsPath: '/tmp/parts.refs.md',
      refsPresent: false,
      cellCount: 1,
      includedCount: 1,
      excludedCount: 0,
      missingCitations: ['FOO'],
      parts: [
        {
          cell: 'FOO',
          tier: 'G',
          family: 'AUP',
          partNumber: '',
          function: null,
          inputs: 1,
          gatesPerPackage: 1,
          package: 'SOT-353',
          manufacturers: [],
          equivalents: 0,
          secondSourceCount: 0,
          citation: null,
          unverified: false,
          excluded: false,
          exclusionReason: null,
        },
      ],
    });
    expect(withNullCitation.parts[0].citation).toBeNull();

    // Dropping a nullable field must fail — it is required, not optional.
    const droppingCitation = (() => {
      const obj = withNullCitation as unknown as Record<string, unknown>;
      const part = obj.parts as unknown as Record<string, unknown>[];
      const stripped = { ...part[0] } as Record<string, unknown>;
      delete stripped.citation;
      return LibraryCheckResultSchema.parse({ ...obj, parts: [stripped] });
    });
    expect(() => droppingCitation()).toThrow();
  });

  it('examples list schema accepts the core payload', () => {
    const parsed = ExamplesListSchema.parse({
      examples: [{ name: 'pelican', summary: 'Pelican crossing', isShowcase: true }],
    });
    expect(parsed.examples[0].isShowcase).toBe(true);
  });

  it('a failed check\'s `detail` is accepted and preserved, not stripped', () => {
    const parsed = CheckSchema.parse({
      name: 'property never_both',
      kind: 'property',
      status: 'failed',
      detail: 'ERROR: engine returned 2\nTraceback (most recent call last):',
      durationMs: 1,
    });
    expect(parsed.detail).toBe('ERROR: engine returned 2\nTraceback (most recent call last):');
  });

  it('a failed check\'s `detail` survives the envelope parse round-trip', () => {
    const stdout = JSON.stringify({
      ok: true,
      command: 'verify',
      schema: 1,
      data: {
        checks: [
          {
            name: 'property never_both',
            kind: 'property',
            status: 'failed',
            detail: 'ERROR: engine returned 2',
            durationMs: 1,
          },
        ],
        allPassed: false,
      },
      warnings: [],
    });
    const env = parseEnvelope(VerifyResultSchema, stdout, 'verify');
    expect(env.ok).toBe(true);
    if (env.ok) {
      expect(env.data.checks[0].detail).toBe('ERROR: engine returned 2');
    }
  });
});

describe('NativeThemeSchema', () => {
  // The renderer is untrusted (§5.2), and this payload is handed straight to
  // `nativeTheme.themeSource`. Only the two themes the app has may pass.
  it('accepts the two themes and nothing else', () => {
    expect(NativeThemeSchema.safeParse({ theme: 'dark' }).success).toBe(true);
    expect(NativeThemeSchema.safeParse({ theme: 'light' }).success).toBe(true);
    expect(NativeThemeSchema.safeParse({ theme: 'system' }).success).toBe(false);
    expect(NativeThemeSchema.safeParse({ theme: 42 }).success).toBe(false);
    expect(NativeThemeSchema.safeParse({}).success).toBe(false);
  });
});
