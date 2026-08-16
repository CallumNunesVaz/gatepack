/**
 * C9 session manager (§16): open/close a project scoped to a directory or a
 * single `.gpk` file, file watching with debounce, git status, and read/write
 * of the spec. A `.gpk` is exploded into a temporary working directory on open
 * and re-bundled deterministically on save via the core's `project` verbs —
 * never re-implemented here.
 */

import { randomUUID } from 'node:crypto';
import * as fs from 'node:fs';
import * as os from 'node:os';
import * as path from 'node:path';

import type { z } from 'zod';

import type {
  AnalysisSummary,
  BuildResult,
  CompileResult,
  Envelope,
  EstimateResult,
  ProjectInfo,
  DoctorReport,
  PackedView,
  ProvenanceMap,
  SimulationTable,
  VerifyResult,
} from '../shared/api';
import { CancelRegistry } from './cancel.cjs';
import { type CoreLocation, runEnvelope, runRaw } from './core.cjs';
import { debounce, type Debounced } from './debounce.cjs';
import {
  AnalysisSummarySchema,
  BuildResultSchema,
  CompileResultSchema,
  EstimateResultSchema,
  MappedNetlistSchema,
  DoctorReportSchema,
  PackedViewSchema,
  ProvenanceMapSchema,
  SimulationTableSchema,
  VerifyResultSchema,
  errorEnvelope,
  okEnvelope,
} from './envelope.cjs';
import { readGitStatus, type Exec, type GitStatus } from './git.cjs';
import { resolveWithin } from './paths.cjs';

export type CoreKind =
  | 'compile'
  | 'estimate'
  | 'verify'
  | 'build'
  | 'analyse'
  | 'provenance'
  | 'simulate'
  | 'mappedNetlist'
  | 'packedNetlist'
  | 'doctor';

export interface ProgressEvent {
  token: string;
  stage: string;
  percent?: number;
}

export interface SessionDeps {
  location: CoreLocation | null;
  registry: CancelRegistry;
  /** Root of the bundled examples directory (contains `<name>/design.yaml`). */
  examplesRoot: string | null;
  /** Called after a successful non-showcase open, to persist the session. */
  onProjectOpened?: (info: ProjectInfo) => void;
  onProjectChanged: (info: ProjectInfo) => void;
  onFileChanged: (paths: string[]) => void;
  onProgress: (p: ProgressEvent) => void;
  gitExec?: Exec;
}

interface ProjectState {
  form: 'directory' | 'gpk';
  /** The directory root, or the original `.gpk` path when opened in file form. */
  openedPath: string;
  /** Working directory the core reads/writes. A temp dir for `.gpk` form. */
  root: string;
  /** The original `.gpk` path (file form only). */
  gpkPath: string | null;
  dirty: boolean;
  git: GitStatus | null;
  /** True for a bundled example opened read-only-ish into a scratch copy (§18.1). */
  showcase: boolean;
}

/** The bundled example opened on first launch (§18.1). */
export const SHOWCASE_NAME = 'pelican';

const WATCH_DEBOUNCE_MS = 250;
const IGNORED_SEGMENTS = new Set([
  '.git',
  '.gatepack',
  'node_modules',
  'dist',
  'out',
  'build',
  '__pycache__',
]);

function genToken(): string {
  return randomUUID();
}

/** Build the argv (excluding the `--json` flag) for a core subcommand. */
export function buildCommandArgs(kind: CoreKind, project: ProjectState): string[] {
  const design = path.join(project.root, 'design.yaml');
  const library = path.join(project.root, 'parts.csv');
  const hasLibrary = fs.existsSync(library);
  const buildDir = path.join(project.root, '.gatepack', 'build');
  const outDir = path.join(project.root, '.gatepack', 'out');

  switch (kind) {
    case 'compile':
      return ['compile', design, '-o', buildDir];
    case 'estimate':
      return ['estimate', design, ...(hasLibrary ? ['--library', library] : []), '--build', buildDir];
    case 'verify':
      return ['verify', design, ...(hasLibrary ? ['--library', library] : []), '--build', buildDir];
    case 'build':
      return ['build', design, ...(hasLibrary ? ['--library', library] : []), '--out', outDir];
    case 'analyse':
      return ['analyse', outDir];
    case 'provenance':
      return ['provenance', outDir];
    case 'simulate':
      // §C11 divergence data. Needs the library to evaluate the mapped
      // netlist; without it the core still returns the `expected` column and
      // omits `actual`, which the UI renders as "not synthesised" rather than
      // as agreement.
      return ['simulate', design, ...(hasLibrary ? ['--library', library] : []), '--build', buildDir];
    case 'mappedNetlist':
      return ['mapped-netlist', outDir];
    case 'packedNetlist':
      return ['packed-netlist', outDir];
    case 'doctor':
      // Takes no project paths: it reports on the core's environment, so it
      // must stay answerable with no project open and no build present.
      return ['doctor'];
  }
}

function isGpk(p: string): boolean {
  return p.toLowerCase().endsWith('.gpk');
}

function ignorePath(p: string): boolean {
  const segments = p.split(path.sep);
  return segments.some((seg) => IGNORED_SEGMENTS.has(seg));
}

export class SessionManager {
  private project: ProjectState | null = null;
  private watcher: fs.FSWatcher | null = null;
  private debounced: Debounced<[]> | null = null;

  constructor(private readonly deps: SessionDeps) {}

  get current(): ProjectInfo | null {
    return this.project ? this.info(this.project) : null;
  }

  /** True when the open project is a bundled showcase copy (§18.1). */
  isShowcase(): boolean {
    return this.project !== null && this.project.showcase;
  }

  private info(project: ProjectState): ProjectInfo {
    return {
      path: project.form === 'gpk' ? project.openedPath : project.root,
      form: project.form,
      designPath: path.join(project.root, 'design.yaml'),
      libraryPath: fs.existsSync(path.join(project.root, 'parts.csv'))
        ? path.join(project.root, 'parts.csv')
        : null,
      dirty: project.dirty,
      git: project.git,
    };
  }

  private requireProject(): ProjectState {
    if (this.project === null) throw new Error('no project open');
    return this.project;
  }

  /* --- open / close --------------------------------------------------- */

  async openProjectPath(input: string): Promise<Envelope<ProjectInfo>> {
    const abs = path.resolve(input);
    let stat: fs.Stats;
    try {
      stat = fs.statSync(abs);
    } catch (err) {
      return errorEnvelope('openProject', 'GP4100', `cannot open ${abs}`, err);
    }

    this.closeProject();

    let state: ProjectState;
    if (stat.isDirectory()) {
      if (!fs.existsSync(path.join(abs, 'design.yaml'))) {
        return errorEnvelope(
          'openProject',
          'GP4101',
          `project directory has no design.yaml: ${abs}`,
        );
      }
      state = { form: 'directory', openedPath: abs, root: abs, gpkPath: null, dirty: false, git: null, showcase: false };
    } else if (isGpk(abs)) {
      if (this.deps.location === null) {
        return errorEnvelope('openProject', 'GP9001', 'gatepack executable not found (needed to explode .gpk)');
      }
      let exploded: string;
      try {
        exploded = await this.explode(abs);
      } catch (err) {
        return errorEnvelope('openProject', 'GP4102', `cannot explode ${abs}`, err);
      }
      state = { form: 'gpk', openedPath: abs, root: exploded, gpkPath: abs, dirty: false, git: null, showcase: false };
    } else {
      return errorEnvelope('openProject', 'GP4103', `not a directory or .gpk file: ${abs}`);
    }

    state.git = await this.readGitFor(state);
    this.project = state;
    this.startWatching();
    this.deps.onProjectChanged(this.info(state));
    this.deps.onProjectOpened?.(this.info(state));
    return okEnvelope('openProject', this.info(state));
  }

  /**
   * Open a bundled example into a scratch working copy (§18.1).
   *
   * The bundled copy is never modified in place: it is copied to a fresh temp
   * directory first, so a user exploring it cannot destroy the shipped copy.
   * `showcase` marks the §18.1 showcase (read-only-ish — Save prompts for a
   * location rather than writing over the bundled copy).
   */
  async openBundledExample(name: string): Promise<Envelope<ProjectInfo>> {
    const root = this.copyExampleToScratch(name);
    if (root === null) {
      return errorEnvelope(
        'openProject',
        'GP4111',
        `bundled example ${name} is not available in this installation`,
      );
    }

    this.closeProject();

    const state: ProjectState = {
      form: 'directory',
      openedPath: root,
      root,
      gpkPath: null,
      dirty: false,
      git: null,
      showcase: name === SHOWCASE_NAME,
    };
    state.git = await this.readGitFor(state);
    this.project = state;
    this.startWatching();
    this.deps.onProjectChanged(this.info(state));
    return okEnvelope('openProject', this.info(state));
  }

  /** Copy a bundled example directory into a scratch working directory. */
  private copyExampleToScratch(name: string): string | null {
    const examplesRoot = this.deps.examplesRoot;
    if (examplesRoot === null) return null;
    const src = path.join(examplesRoot, name);
    if (!fs.existsSync(path.join(src, 'design.yaml'))) return null;
    try {
      const dst = fs.mkdtempSync(path.join(os.tmpdir(), 'gatepack-example-'));
      for (const entry of fs.readdirSync(src)) {
        const from = path.join(src, entry);
        if (fs.statSync(from).isFile()) {
          fs.copyFileSync(from, path.join(dst, entry));
        }
      }
      return dst;
    } catch {
      return null;
    }
  }

  private async explode(gpkPath: string): Promise<string> {
    const tmp = await fs.promises.mkdtemp(path.join(os.tmpdir(), 'gatepack-'));
    const res = await runRaw(this.deps.location as CoreLocation, [
      'project',
      'explode',
      gpkPath,
      '-o',
      tmp,
    ]);
    if (res.code !== 0) {
      await fs.promises.rm(tmp, { recursive: true, force: true }).catch(() => {});
      throw new Error(`gatepack project explode failed (exit ${res.code}): ${res.stderr || res.stdout}`);
    }
    if (!fs.existsSync(path.join(tmp, 'design.yaml'))) {
      await fs.promises.rm(tmp, { recursive: true, force: true }).catch(() => {});
      throw new Error('gatepack project explode produced no design.yaml');
    }
    return tmp;
  }

  closeProject(): void {
    this.stopWatching();
    if (this.project !== null) {
      const { form, gpkPath, showcase, root } = this.project;
      // Both a `.gpk` and a showcase are exploded/copied into a temp working
      // directory that should not outlive the session.
      if ((form === 'gpk' && gpkPath !== null) || showcase) {
        fs.promises.rm(root, { recursive: true, force: true }).catch(() => {});
      }
    }
    this.project = null;
  }

  /* --- save ----------------------------------------------------------- */

  async saveProject(): Promise<Envelope<ProjectInfo>> {
    const project = this.requireProject();
    // §18.1(4): the showcase is read-only-ish. "Save" on it must prompt for a
    // new location rather than write over the bundled copy; the copy lives in
    // a scratch dir, so the bundled copy is safe, but saving should still not
    // pretend to succeed against the scratch copy.
    if (project.showcase) {
      return errorEnvelope(
        'saveProject',
        'GP4109',
        'the showcase is read-only; use Save As… to keep your changes',
      );
    }
    if (project.form === 'gpk') {
      if (this.deps.location === null) {
        return errorEnvelope('saveProject', 'GP9001', 'gatepack executable not found (needed to bundle .gpk)');
      }
      try {
        await this.bundle(project.root, project.gpkPath as string);
      } catch (err) {
        return errorEnvelope('saveProject', 'GP4104', `cannot bundle ${project.gpkPath}`, err);
      }
    }
    project.dirty = false;
    project.git = await this.readGitFor(project);
    this.deps.onProjectChanged(this.info(project));
    return okEnvelope('saveProject', this.info(project));
  }

  async saveProjectAs(gpkPath: string): Promise<Envelope<ProjectInfo>> {
    const project = this.requireProject();
    if (this.deps.location === null) {
      return errorEnvelope('saveProjectAs', 'GP9001', 'gatepack executable not found (needed to bundle .gpk)');
    }
    // An absolute path is the user's explicit save-dialog choice. A relative
    // path comes straight from the (untrusted) renderer and must be scoped to
    // the opened project directory (§5.2).
    let abs: string;
    try {
      abs = path.isAbsolute(gpkPath) ? path.resolve(gpkPath) : resolveWithin(project.root, gpkPath);
    } catch (err) {
      return errorEnvelope('saveProjectAs', 'GP4108', `refusing path outside project root: ${gpkPath}`, err);
    }
    try {
      await this.bundle(project.root, abs);
    } catch (err) {
      return errorEnvelope('saveProjectAs', 'GP4105', `cannot bundle to ${abs}`, err);
    }
    this.deps.onProjectChanged(this.info(project));
    return okEnvelope('saveProjectAs', this.info(project));
  }

  private async bundle(dir: string, out: string): Promise<void> {
    const res = await runRaw(this.deps.location as CoreLocation, [
      'project',
      'bundle',
      dir,
      '-o',
      out,
    ]);
    if (res.code !== 0) {
      throw new Error(`gatepack project bundle failed (exit ${res.code}): ${res.stderr || res.stdout}`);
    }
  }

  /* --- spec read/write ------------------------------------------------ */

  readSpec(): Envelope<{ text: string; path: string }> {
    const project = this.requireProject();
    const designPath = path.join(project.root, 'design.yaml');
    try {
      const text = fs.readFileSync(designPath, 'utf8');
      return okEnvelope('readSpec', { text, path: designPath });
    } catch (err) {
      return errorEnvelope('readSpec', 'GP4106', `cannot read ${designPath}`, err);
    }
  }

  writeSpec(text: string): Envelope<{ path: string }> {
    const project = this.requireProject();
    const designPath = path.join(project.root, 'design.yaml');
    try {
      fs.writeFileSync(designPath, text);
    } catch (err) {
      return errorEnvelope('writeSpec', 'GP4107', `cannot write ${designPath}`, err);
    }
    project.dirty = true;
    return okEnvelope('writeSpec', { path: designPath });
  }

  /* --- core invocations ---------------------------------------------- */

  compile(token?: string): Promise<Envelope<CompileResult>> {
    return this.invoke(CompileResultSchema, 'compile', 'compile', token);
  }
  estimate(token?: string): Promise<Envelope<EstimateResult>> {
    return this.invoke(EstimateResultSchema, 'estimate', 'estimate', token);
  }
  verify(token?: string): Promise<Envelope<VerifyResult>> {
    return this.invoke(VerifyResultSchema, 'verify', 'verify', token);
  }
  build(token?: string): Promise<Envelope<BuildResult>> {
    return this.invoke(BuildResultSchema, 'build', 'build', token);
  }
  analyse(token?: string): Promise<Envelope<AnalysisSummary>> {
    return this.invoke(AnalysisSummarySchema, 'analyse', 'analyse', token);
  }
  simulate(token?: string): Promise<Envelope<SimulationTable>> {
    return this.invoke(SimulationTableSchema, 'simulate', 'simulate', token);
  }

  provenance(): Promise<Envelope<ProvenanceMap>> {
    return this.invoke(ProvenanceMapSchema, 'provenance', 'provenance');
  }
  doctor(): Promise<Envelope<DoctorReport>> {
    return this.invoke(DoctorReportSchema, 'doctor', 'doctor');
  }

  packedNetlist(): Promise<Envelope<PackedView>> {
    return this.invoke(PackedViewSchema, 'packedNetlist', 'packedNetlist');
  }

  mappedNetlist(): Promise<Envelope<unknown>> {
    return this.invoke(MappedNetlistSchema, 'mappedNetlist', 'mappedNetlist');
  }

  private invoke<T>(
    schema: z.ZodType<T>,
    kind: CoreKind,
    command: string,
    token?: string,
  ): Promise<Envelope<T>> {
    const project = this.project;
    if (project === null) {
      return Promise.resolve(errorEnvelope(command, 'GP4200', 'no project open'));
    }
    if (this.deps.location === null) {
      return Promise.resolve(errorEnvelope(command, 'GP9001', 'gatepack executable not found'));
    }

    const tok = token ?? genToken();
    const args = buildCommandArgs(kind, project);
    return runEnvelope(this.deps.location, schema, command, args, {
      cwd: project.root,
      token: tok,
      registry: this.deps.registry,
      onProgress: (stage, percent) => this.deps.onProgress({ token: tok, stage, percent }),
    });
  }

  /* --- git ------------------------------------------------------------ */

  private async readGitFor(project: ProjectState): Promise<GitStatus | null> {
    const baseDir = project.form === 'gpk' ? path.dirname(project.openedPath) : project.root;
    return readGitStatus(baseDir, this.deps.gitExec);
  }

  /* --- file watching --------------------------------------------------- */

  private startWatching(): void {
    if (this.project === null) return;
    const root = this.project.root;
    const pending = new Set<string>();
    this.debounced = debounce(() => {
      const paths = [...pending];
      pending.clear();
      if (paths.length === 0) return;
      this.deps.onFileChanged(paths);
      if (this.project !== null) {
        const baseDir =
          this.project.form === 'gpk' ? path.dirname(this.project.openedPath) : this.project.root;
        readGitStatus(baseDir, this.deps.gitExec).then((git) => {
          if (this.project !== null) this.project.git = git;
        });
      }
    }, WATCH_DEBOUNCE_MS);

    try {
      this.watcher = fs.watch(root, { recursive: true }, (_event, filename) => {
        if (typeof filename !== 'string' || filename === '') return;
        if (ignorePath(filename)) return;
        const abs = path.join(root, filename);
        pending.add(abs);
        if (this.debounced !== null) this.debounced();
      });
    } catch {
      this.watcher = null;
    }
  }

  private stopWatching(): void {
    if (this.watcher !== null) {
      this.watcher.close();
      this.watcher = null;
    }
    if (this.debounced !== null) {
      this.debounced.cancel();
      this.debounced = null;
    }
  }

  /** Called on app quit: release OS resources. */
  dispose(): void {
    this.stopWatching();
    this.deps.registry.cancelAll();
    this.closeProject();
  }
}
