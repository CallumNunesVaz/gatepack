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
  ExamplesList,
  LibraryCheckResult,
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
  ExamplesListSchema,
  LibraryCheckResultSchema,
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
  | 'doctor'
  | 'listExamples'
  | 'checkLibrary';

export interface ProgressEvent {
  token: string;
  stage: string;
  percent?: number;
}

/**
 * The OS shell seam (§GUI-1): reveal a path in the file manager. Kept as a
 * dependency rather than an `import { shell } from 'electron'` so a test can
 * stub the reveal without spawning a real file manager, and so this module
 * stays free of an Electron import (it runs under vitest in plain Node).
 */
export interface ShellSeam {
  /** Reveal `fullPath` in the OS file manager. Empty string = success. */
  openPath(fullPath: string): Promise<string>;
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
  /** Reveal the output directory in the OS file manager (Electron `shell`). */
  shell: ShellSeam;
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

/** The directory `build` writes its artefacts into, relative to the project root. */
export function outputDir(root: string): string {
  return path.join(root, '.gatepack', 'out');
}

/**
 * The build artefacts a person actually hands on (§GUI-1): the BOM, the KiCad
 * netlist and the report. The intermediates (`mapped.json`, `premap.json`,
 * `cells.lib`, `yosys.ys`, `generated.v`, `mapped.v`, `netlist.unpacked.net`,
 * `refdes.json`) are the core's own scratch for `analyse`/`provenance` and are
 * deliberately not copied — see docs/BUILD-NOTES-outputs.md.
 */
const EXPORT_ARTEFACTS = ['bom.csv', 'netlist.net', 'report.md'] as const;

/** What to say when there is nothing to reveal or export: say what to do. */
function noOutputsMessage(outDir: string): string {
  return `no build outputs at ${outDir} — run a build first`;
}

/** True when `outDir` exists, is a directory and holds at least one entry. */
function hasOutputs(outDir: string): boolean {
  let stat: fs.Stats;
  try {
    stat = fs.statSync(outDir);
  } catch {
    return false;
  }
  if (!stat.isDirectory()) return false;
  try {
    return fs.readdirSync(outDir).length > 0;
  } catch {
    return false;
  }
}

/** Build the argv (excluding the `--json` flag) for a core subcommand. */
export function buildCommandArgs(
  kind: CoreKind,
  project: ProjectState | null,
  arg?: string,
): string[] {
  const root = project === null ? '' : project.root;
  const design = path.join(root, 'design.yaml');
  const library = path.join(root, 'parts.csv');
  const hasLibrary = project !== null && fs.existsSync(library);
  const buildDir = path.join(root, '.gatepack', 'build');
  const outDir = outputDir(root);

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
    case 'listExamples':
      // Also project-independent: browsing examples is how a user gets a first
      // project, so it must not require one to already be open.
      return ['examples', 'list'];
    case 'checkLibrary':
      // `arg` is the absolute parts.csv path the renderer asked to validate.
      return ['lib', 'check', arg ?? ''];
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

  /* --- outputs (§GUI-1) ----------------------------------------------- */

  /**
   * Reveal the build output directory in the OS file manager.
   *
   * §GUI-1: `build` writes the BOM, netlist and report into `.gatepack/out`
   * and the application never offered them, so handing a netlist to a
   * fabricator meant leaving the app. Refusing to reveal when nothing has been
   * built is deliberate — an "outputs" command that opens an empty folder is a
   * small lie of the kind this project spends its effort not telling.
   */
  revealOutputs(): Promise<Envelope<{ path: string }>> {
    if (this.project === null) {
      return Promise.resolve(errorEnvelope('revealOutputs', 'GP4200', 'no project open'));
    }
    const outDir = outputDir(this.project.root);
    if (!hasOutputs(outDir)) {
      return Promise.resolve(errorEnvelope('revealOutputs', 'GP4113', noOutputsMessage(outDir)));
    }
    // `shell.openPath` resolves to a string (empty on success), it never
    // rejects — returning `ok` without checking it would be a silent failure.
    return this.deps.shell.openPath(outDir).then((result) => {
      if (result === '') return okEnvelope('revealOutputs', { path: outDir });
      return errorEnvelope('revealOutputs', 'GP4114', `cannot reveal ${outDir}: ${result}`);
    });
  }

  /**
   * Copy the build artefacts into `destination`, chosen by the user in a native
   * dialog (ipc.cts shows it). The destination is therefore never a path the
   * renderer supplied: writing outside the project root is acceptable only
   * because a native dialog picked it (§5.2).
   */
  async exportOutputs(destination: string): Promise<Envelope<{ path: string; files: string[] }>> {
    if (this.project === null) {
      return errorEnvelope('exportOutputs', 'GP4200', 'no project open');
    }
    const outDir = outputDir(this.project.root);
    if (!hasOutputs(outDir)) {
      return errorEnvelope('exportOutputs', 'GP4113', noOutputsMessage(outDir));
    }
    const missing = EXPORT_ARTEFACTS.filter((name) => !fs.existsSync(path.join(outDir, name)));
    if (missing.length > 0) {
      return errorEnvelope(
        'exportOutputs',
        'GP4113',
        `${noOutputsMessage(outDir)} (missing ${missing.join(', ')})`,
      );
    }

    const dest = path.resolve(destination);
    // Do not overwrite silently: refuse the whole export when any target file
    // already exists, rather than clobbering a file the user already had. The
    // policy is deliberate — see docs/BUILD-NOTES-outputs.md.
    const conflicts = EXPORT_ARTEFACTS.filter((name) => fs.existsSync(path.join(dest, name)));
    if (conflicts.length > 0) {
      return errorEnvelope(
        'exportOutputs',
        'GP4115',
        `refusing to overwrite ${conflicts.length} existing file(s) in ${dest}: ${conflicts.join(', ')}`,
      );
    }

    const written: string[] = [];
    try {
      fs.mkdirSync(dest, { recursive: true });
      for (const name of EXPORT_ARTEFACTS) {
        const target = path.join(dest, name);
        fs.copyFileSync(path.join(outDir, name), target);
        written.push(target);
      }
    } catch (err) {
      return errorEnvelope('exportOutputs', 'GP4116', `cannot export to ${dest}`, err);
    }
    return okEnvelope('exportOutputs', { path: dest, files: written });
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
  /** The open project, or a successful envelope carrying null. */
  currentProject(): Promise<Envelope<ProjectInfo | null>> {
    // `ok: true` with `data: null` — "nothing is open" is an answer, not a
    // failure, and must not be reported as one.
    return Promise.resolve({
      ok: true,
      command: 'currentProject',
      schema: 1,
      data: this.project === null ? null : this.info(this.project),
      warnings: [],
    });
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

  listExamples(): Promise<Envelope<ExamplesList>> {
    return this.invokeStandalone(ExamplesListSchema, 'listExamples', 'listExamples');
  }

  checkLibrary(input: string): Promise<Envelope<LibraryCheckResult>> {
    let abs: string;
    try {
      // An absolute path is the path the renderer already received from
      // `ProjectInfo.libraryPath`. A relative path comes straight from the
      // (untrusted) renderer and must be scoped to the project root (§5.2).
      abs = path.isAbsolute(input)
        ? path.resolve(input)
        : this.project !== null
          ? resolveWithin(this.project.root, input)
          : path.resolve(input);
    } catch (err) {
      return Promise.resolve(
        errorEnvelope(
          'checkLibrary',
          'GP4202',
          `refusing path outside project root: ${input}`,
          err,
        ),
      );
    }
    return this.invokeStandalone(
      LibraryCheckResultSchema,
      'checkLibrary',
      'checkLibrary',
      abs,
    );
  }

  /**
   * Open a bundled example into a new project (§18.1). This is the same
   * scratch-copy-and-open flow the showcase and the Examples menu use, so the
   * discovery from `listExamples()` and the open path stay one implementation.
   */
  openExample(name: string): Promise<Envelope<ProjectInfo>> {
    return this.openBundledExample(name);
  }

  /**
   * Scaffold a new project in `directory`, then open it (§18.1).
   *
   * The template comes from the core (`gatepack project new`), not from here.
   * "What a valid starting design looks like" and "which parts library it
   * ships with" are core knowledge, and this process is a view over artefacts
   * the CLI produces -- a template duplicated in the main process would drift
   * from the one `gatepack project new` writes, and only one of them would be
   * covered by the core's tests.
   *
   * The core refuses to overwrite an existing design.yaml, which matters here:
   * a user picking a directory in a file dialog can easily land on a project
   * they already have, and the refusal must not be second-guessed by opening
   * it silently instead.
   */
  async newProject(directory: string): Promise<Envelope<ProjectInfo>> {
    if (this.deps.location === null) {
      return errorEnvelope('newProject', 'GP9001', 'gatepack executable not found');
    }
    const abs = path.resolve(directory);
    const res = await runRaw(this.deps.location, ['project', 'new', abs]);
    if (res.code !== 0) {
      return errorEnvelope(
        'newProject',
        'GP4112',
        (res.stderr || res.stdout || `gatepack project new failed (exit ${res.code})`).trim(),
      );
    }
    return this.openProjectPath(abs);
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

  /**
   * A core invocation that does not need an open project (library validation,
   * example listing). `doctor` predates this helper and goes through `invoke`
   * today, which is why it only answers once a project is open; the new
   * project-independent commands use this instead.
   */
  private invokeStandalone<T>(
    schema: z.ZodType<T>,
    kind: CoreKind,
    command: string,
    arg?: string,
  ): Promise<Envelope<T>> {
    if (this.deps.location === null) {
      return Promise.resolve(errorEnvelope(command, 'GP9001', 'gatepack executable not found'));
    }
    const args = buildCommandArgs(kind, null, arg);
    return runEnvelope(this.deps.location, schema, command, args, {});
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
