/**
 * In-memory fake of the `window.gatepack` bridge, used by every test and by the
 * dev harness (where `app/main/` does not exist yet). It mirrors the IPC
 * contract in `app/shared/api.ts` exactly; nothing here talks to a real process.
 */

import type {
  AnalysisSummary,
  BuildResult,
  CompileResult,
  Diagnostic,
  Envelope,
  EstimateResult,
  GatepackApi,
  ProjectInfo,
  ProvenanceMap,
  SimulationTable,
  VerifyResult,
} from '../../shared/api';

export type Command =
  | 'compile'
  | 'estimate'
  | 'verify'
  | 'build'
  | 'analyse'
  | 'mappedNetlist'
  | 'provenance'
  | 'simulate';

type ResultFactory<T> = Envelope<T> | ((token?: string) => Envelope<T>);
type Hook = (token?: string) => Promise<void>;

export interface FakeGatepackOptions {
  specText?: string;
  project?: Partial<ProjectInfo>;
  delayMs?: number;
}

const DEFAULT_SPEC = `name: xor2
timing_model: synchronous
clock: {signal: clk, freq_hz: 1000, source: OSC}
reset: {signal: rst_n, active: low, source: SUPERVISOR}
encoding: one_hot
inputs:
  - {name: a, sync: false}
  - {name: b, sync: false}
outputs:
  - {name: y}
states: [S0]
initial: S0
transitions:
  - {from: S0, to: S0, when: "1"}
output_logic:
  y: "a ^ b"
`;

const DEFAULT_PROJECT: ProjectInfo = {
  path: '/tmp/project',
  form: 'directory',
  designPath: '/tmp/project/design.yaml',
  libraryPath: null,
  dirty: false,
  git: null,
};

function ok<T>(command: string, data: T, warnings: Diagnostic[] = []): Envelope<T> {
  return { ok: true, command, schema: 1, data, warnings };
}

function err(command: string, error: Diagnostic, warnings: Diagnostic[] = []): Envelope<never> {
  return { ok: false, command, schema: 1, error, warnings };
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export class FakeGatepack implements GatepackApi {
  specText: string;
  project: ProjectInfo;

  results: Partial<Record<Command, ResultFactory<unknown>>> = {};
  hooks: Partial<Record<Command, Hook>> = {};

  calls: Array<{ command: Command; token?: string }> = [];
  cancelled: string[] = [];
  writes: string[] = [];
  delayMs: number;

  private projectChangedHandlers: Array<(info: ProjectInfo) => void> = [];
  private fileChangedHandlers: Array<(paths: string[]) => void> = [];
  private progressHandlers: Array<(p: { token: string; stage: string; percent?: number }) => void> = [];

  constructor(options: FakeGatepackOptions = {}) {
    this.specText = options.specText ?? DEFAULT_SPEC;
    this.project = { ...DEFAULT_PROJECT, ...options.project };
    this.delayMs = options.delayMs ?? 0;
  }

  /* ---- result seeding helpers ---- */

  setOk<T>(command: Command, data: T): void {
    this.results[command] = ok(command, data);
  }

  setOkFactory<T>(command: Command, factory: (token?: string) => T): void {
    this.results[command] = (token?: string) => ok(command, factory(token));
  }

  setError(command: Command, error: Diagnostic): void {
    this.results[command] = err(command, error);
  }

  setHook(command: Command, hook: Hook): void {
    this.hooks[command] = hook;
  }

  /** Fire the onProjectChanged event (used to simulate a file watch). */
  emitProjectChanged(info?: ProjectInfo): void {
    const next = info ?? this.project;
    this.project = next;
    for (const cb of this.projectChangedHandlers) cb(next);
  }

  emitFileChanged(paths: string[]): void {
    for (const cb of this.fileChangedHandlers) cb(paths);
  }

  /* ---- private plumbing ---- */

  private async invoke<T>(command: Command, token?: string): Promise<Envelope<T>> {
    this.calls.push({ command, token });
    const hook = this.hooks[command];
    if (hook) {
      await hook(token);
    } else if (this.delayMs > 0) {
      await sleep(this.delayMs);
    }
    const factory = this.results[command];
    if (factory === undefined) {
      return ok(command, null as unknown as T);
    }
    const envelope = typeof factory === 'function' ? factory(token) : factory;
    return envelope as Envelope<T>;
  }

  /* ---- GatepackApi ---- */

  async openProject(): Promise<Envelope<ProjectInfo>> {
    return ok('openProject', { ...this.project });
  }

  async openProjectPath(_path: string): Promise<Envelope<ProjectInfo>> {
    return ok('openProjectPath', { ...this.project });
  }

  async closeProject(): Promise<void> {
    // no-op in the fake
  }

  async saveProject(): Promise<Envelope<ProjectInfo>> {
    return ok('saveProject', { ...this.project, dirty: false });
  }

  async saveProjectAs(_gpkPath: string): Promise<Envelope<ProjectInfo>> {
    return ok('saveProjectAs', { ...this.project, dirty: false });
  }

  async readSpec(): Promise<Envelope<{ text: string; path: string }>> {
    return ok('readSpec', { text: this.specText, path: this.project.designPath });
  }

  async writeSpec(text: string): Promise<Envelope<{ path: string }>> {
    this.specText = text;
    this.writes.push(text);
    return ok('writeSpec', { path: this.project.designPath });
  }

  compile(token?: string): Promise<Envelope<CompileResult>> {
    return this.invoke<CompileResult>('compile', token);
  }

  estimate(token?: string): Promise<Envelope<EstimateResult>> {
    return this.invoke<EstimateResult>('estimate', token);
  }

  verify(token?: string): Promise<Envelope<VerifyResult>> {
    return this.invoke<VerifyResult>('verify', token);
  }

  build(token?: string): Promise<Envelope<BuildResult>> {
    return this.invoke<BuildResult>('build', token);
  }

  analyse(token?: string): Promise<Envelope<AnalysisSummary>> {
    return this.invoke<AnalysisSummary>('analyse', token);
  }

  provenance(): Promise<Envelope<ProvenanceMap>> {
    return this.invoke<ProvenanceMap>('provenance');
  }

  simulate(token?: string): Promise<Envelope<SimulationTable>> {
    return this.invoke<SimulationTable>('simulate', token);
  }

  mappedNetlist(): Promise<Envelope<unknown>> {
    return this.invoke<unknown>('mappedNetlist');
  }

  async cancel(token: string): Promise<void> {
    this.cancelled.push(token);
  }

  onProjectChanged(cb: (info: ProjectInfo) => void): () => void {
    this.projectChangedHandlers.push(cb);
    return () => {
      this.projectChangedHandlers = this.projectChangedHandlers.filter((h) => h !== cb);
    };
  }

  onFileChanged(cb: (paths: string[]) => void): () => void {
    this.fileChangedHandlers.push(cb);
    return () => {
      this.fileChangedHandlers = this.fileChangedHandlers.filter((h) => h !== cb);
    };
  }

  onProgress(cb: (p: { token: string; stage: string; percent?: number }) => void): () => void {
    this.progressHandlers.push(cb);
    return () => {
      this.progressHandlers = this.progressHandlers.filter((h) => h !== cb);
    };
  }
}
