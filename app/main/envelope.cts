/**
 * Envelope parsing and the zod schemas that pin the IPC contract at runtime.
 *
 * The Python core (`gatepack <cmd> --json`) prints exactly one JSON envelope to
 * stdout; the main process parses it and validates it with these schemas before
 * it is allowed to cross IPC. The renderer is treated as untrusted, so the
 * request *payloads* it sends are also validated with zod (in main/ipc.cts).
 *
 * These schemas are the runtime twin of the hand-written TypeScript contract in
 * shared/api.ts. They must track it field-for-field; a silent divergence is the
 * one bug that costs all three work packages at once.
 */

import { z } from 'zod';

import type { Envelope } from '../shared/api';

/* ------------------------------------------------------------------ */
/* Diagnostic                                                          */
/* ------------------------------------------------------------------ */

export const DiagnosticSchema = z.object({
  severity: z.enum(['error', 'warning', 'info']),
  code: z.string(),
  message: z.string(),
  path: z.string().optional(),
  line: z.number().optional(),
  column: z.number().optional(),
  pointer: z.string().optional(),
});
export type Diagnostic = z.infer<typeof DiagnosticSchema>;

/* ------------------------------------------------------------------ */
/* Per-command payloads                                                */
/* ------------------------------------------------------------------ */

export const CompileResultSchema = z.object({
  verilogPath: z.string(),
  propertiesPath: z.string().nullable(),
  flopCount: z.number(),
  stateCount: z.number(),
  encoding: z.enum(['one_hot', 'binary', 'gray', 'johnson']),
  johnsonSuggestion: z.string().nullable(),
});

export const EstimateResultSchema = z.object({
  verdict: z.enum(['green', 'amber', 'red']),
  reasons: z.array(z.string()),
  packageCount: z.number(),
  flopCount: z.number(),
  cellCounts: z.record(z.string(), z.number()),
  alternative: z.string().nullable(),
});

export const CheckStatusSchema = z.enum(['passed', 'bounded', 'failed', 'not_run']);

export const CounterexampleSchema = z.object({
  steps: z.array(z.record(z.string(), z.string())),
  pointers: z.array(z.string()),
});

export const NativeThemeSchema = z.object({
  theme: z.enum(['light', 'dark']),
});

export const CheckSchema = z.object({
  name: z.string(),
  kind: z.enum(['equivalence', 'simulation', 'mutation', 'property', 'hazard']),
  status: CheckStatusSchema,
  bound: z.number().optional(),
  skippedReason: z.string().optional(),
  detail: z.string().optional(),
  durationMs: z.number(),
  counterexample: CounterexampleSchema.optional(),
});

export const VerifyResultSchema = z.object({
  checks: z.array(CheckSchema),
  allPassed: z.boolean(),
});

export const BomLineSchema = z.object({
  partNumber: z.string(),
  manufacturers: z.array(z.string()),
  package: z.string(),
  quantity: z.number(),
  refdes: z.array(z.string()),
  tier: z.string(),
  singleSourced: z.boolean(),
  gatesPerPackage: z.number(),
});

export const MetricSchema = z.object({
  name: z.string(),
  value: z.number(),
  unit: z.string(),
  limit: z.number().nullable(),
  violated: z.boolean(),
});

export const AnalysisSummarySchema = z.object({
  metrics: z.array(MetricSchema),
  scoap: z.array(
    z.object({
      net: z.string(),
      controllability0: z.number(),
      controllability1: z.number(),
      observability: z.number(),
    }),
  ),
  faults: z.object({
    detected: z.number(),
    undetected: z.number(),
    redundant: z.number(),
    untestable: z.number(),
  }),
  cpldBlockers: z.array(DiagnosticSchema),
});

export const BuildResultSchema = z.object({
  bomPath: z.string(),
  netlistPath: z.string(),
  reportPath: z.string(),
  mappedJsonPath: z.string(),
  packageCount: z.number(),
  spareCount: z.number(),
  packCost: z.number(),
  bom: z.array(BomLineSchema),
  analysis: AnalysisSummarySchema,
  stableCellNames: z.record(z.string()),
});

export const PackedViewSchema = z.object({
  packages: z.array(
    z.object({
      refdes: z.string(),
      partNumber: z.string(),
      cells: z.array(z.string()),
      instanceCells: z.array(z.string()),
      capacity: z.number(),
      spare: z.number(),
      rationale: z.string(),
    }),
  ),
});

export const DoctorReportSchema = z.object({
  allToolsPresent: z.boolean(),
  tools: z.array(
    z.object({
      name: z.string(),
      direct: z.boolean(),
      found: z.boolean(),
      // `.nullable()` and not `.optional()`: the core always emits the key, and
      // "not found" must be an explicit null rather than an absent field that a
      // reader could mistake for "not checked".
      path: z.string().nullable(),
      version: z.string().nullable(),
      purpose: z.string(),
    }),
  ),
  resources: z.object({
    commonFrontendYs: z.boolean(),
    mcellModels: z.boolean(),
    mcellCount: z.number(),
  }),
});

export const ProvenanceMapSchema = z.object({
  entries: z.array(
    z.object({
      pointer: z.string(),
      nets: z.array(z.string()),
      cells: z.array(z.string()),
      confidence: z.enum(['exact', 'inferred']),
    }),
  ),
  coverage: z.number(),
});

export const LibraryPartSchema = z.object({
  cell: z.string(),
  tier: z.string(),
  family: z.string(),
  partNumber: z.string(),
  // `.nullable()` and not `.optional()`: the core always emits the key, and
  // "no function"/"uncited"/"included" must be an explicit null rather than an
  // absent field a reader could mistake for "not checked".
  function: z.string().nullable(),
  inputs: z.number(),
  gatesPerPackage: z.number(),
  package: z.string(),
  manufacturers: z.array(z.string()),
  equivalents: z.number(),
  secondSourceCount: z.number(),
  citation: z.string().nullable(),
  unverified: z.boolean(),
  excluded: z.boolean(),
  exclusionReason: z.string().nullable(),
});

export const LibraryCheckResultSchema = z.object({
  path: z.string(),
  refsPath: z.string(),
  refsPresent: z.boolean(),
  cellCount: z.number(),
  includedCount: z.number(),
  excludedCount: z.number(),
  missingCitations: z.array(z.string()),
  parts: z.array(LibraryPartSchema),
});

export const ExamplesListSchema = z.object({
  examples: z.array(
    z.object({
      name: z.string(),
      summary: z.string(),
      isShowcase: z.boolean(),
    }),
  ),
});

export const SimulationTableSchema = z.object({
  inputNames: z.array(z.string()),
  outputNames: z.array(z.string()),
  rows: z.array(
    z.object({
      inputs: z.record(z.string()),
      state: z.string().optional(),
      expected: z.record(z.string()),
      actual: z.record(z.string()).optional(),
      diverges: z.boolean(),
    }),
  ),
  dontCareCount: z.number(),
  unreachableCount: z.number(),
  exhaustive: z.boolean(),
});

/** `mappedNetlist()` — Yosys `write_json` output; shape not pinned, `unknown`. */
export const MappedNetlistSchema = z.unknown();

/* ------------------------------------------------------------------ */
/* Envelope                                                            */
/* ------------------------------------------------------------------ */

export function envelopeSchema<T>(data: z.ZodType<T>) {
  return z.union([
    z.object({
      ok: z.literal(true),
      command: z.string(),
      schema: z.literal(1),
      data,
      warnings: z.array(DiagnosticSchema),
    }),
    z.object({
      ok: z.literal(false),
      command: z.string(),
      schema: z.literal(1),
      error: DiagnosticSchema,
      warnings: z.array(DiagnosticSchema),
    }),
  ]);
}

/* ------------------------------------------------------------------ */
/* Request payloads (renderer -> main)                                 */
/* ------------------------------------------------------------------ */

export const OpenProjectPathSchema = z.object({ path: z.string().min(1) });
export const NewProjectSchema = z.object({ directory: z.string().min(1) });
export const SaveProjectAsSchema = z.object({ gpkPath: z.string().min(1) });
export const WriteSpecSchema = z.object({ text: z.string() });
export const InvokeTokenSchema = z.object({ token: z.string().min(1).optional() });
export const CancelTokenSchema = z.object({ token: z.string().min(1) });
export const CheckLibrarySchema = z.object({ path: z.string().min(1) });
export const OpenExampleSchema = z.object({ name: z.string().min(1) });

/* ------------------------------------------------------------------ */
/* Parsing                                                             */
/* ------------------------------------------------------------------ */

export class EnvelopeParseError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'EnvelopeParseError';
  }
}

/**
 * Parse stdout as exactly one JSON envelope and validate it. Diagnostics and
 * the exit code are handled by the caller; this never throws on malformed
 * input — it returns an `ok: false` envelope, because faking a result is worse
 * than reporting a failure.
 */
export function parseEnvelope<T>(
  schema: z.ZodType<T>,
  stdout: string,
  command: string,
): Envelope<T> {
  let raw: unknown;
  try {
    raw = JSON.parse(stdout);
  } catch (err) {
    return errorEnvelope(
      command,
      'GP9002',
      'core emitted no parseable JSON envelope',
      err,
    );
  }

  const parsed = envelopeSchema(schema).safeParse(raw);
  if (!parsed.success) {
    return errorEnvelope(
      command,
      'GP9003',
      'core envelope failed schema validation',
      parsed.error,
    );
  }
  return parsed.data as Envelope<T>;
}

/** Build a well-formed `ok: false` envelope without inventing a result. */
export function errorEnvelope<T>(
  command: string,
  code: string,
  message: string,
  cause?: unknown,
): Envelope<T> {
  const detail = describe(cause);
  return {
    ok: false,
    command,
    schema: 1,
    error: {
      severity: 'error',
      code,
      message: detail ? `${message}: ${detail}` : message,
    },
    warnings: [],
  };
}

/** Build a well-formed `ok: true` envelope. */
export function okEnvelope<T>(
  command: string,
  data: T,
  warnings: Diagnostic[] = [],
): Envelope<T> {
  return { ok: true, command, schema: 1, data, warnings };
}

/** Turn an arbitrary thrown value into a single-line, stable description. */
export function describe(cause: unknown): string {
  if (cause === undefined || cause === null) return '';
  if (cause instanceof z.ZodError) {
    return cause.issues
      .map((issue) => `${issue.path.join('.') || '(root)'}: ${issue.message}`)
      .join('; ');
  }
  if (cause instanceof Error) return cause.message;
  return String(cause);
}
