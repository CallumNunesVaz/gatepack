/**
 * IPC registration (§5.2: "every IPC payload schema-validated in the main
 * process — treat the renderer as untrusted"). Each channel is registered once;
 * a handler never lets a thrown error escape as a raw reject — it is converted
 * to a well-formed error envelope.
 */

import { dialog, ipcMain, nativeTheme, type OpenDialogOptions } from 'electron';

import { z } from 'zod';

import type { Envelope, ProjectInfo } from '../shared/api';
import { CancelRegistry, CancelledError } from './cancel.cjs';
import {
  CancelTokenSchema,
  CheckLibrarySchema,
  InvokeTokenSchema,
  NativeThemeSchema,
  OpenExampleSchema,
  NewProjectSchema,
  OpenProjectPathSchema,
  SaveProjectAsSchema,
  WriteSpecSchema,
  errorEnvelope,
} from './envelope.cjs';
import { SessionManager } from './session.cjs';

const NoPayloadSchema = z.object({}).passthrough();

export interface IpcDeps {
  session: SessionManager;
  registry: CancelRegistry;
}

function handle<P, R>(
  channel: string,
  schema: z.ZodType<P>,
  fn: (payload: P) => Promise<R> | R,
): void {
  ipcMain.handle(channel, async (_event, raw: unknown) => {
    const parsed = schema.safeParse(raw ?? {});
    if (!parsed.success) {
      return errorEnvelope(channel, 'GP4001', 'invalid IPC payload', parsed.error);
    }
    try {
      return await fn(parsed.data);
    } catch (err) {
      // A cancelled call must never resolve into the renderer — not even as an
      // error envelope — so cancellation propagates as a reject (§16.1).
      if (err instanceof CancelledError) throw err;
      return errorEnvelope(channel, 'GP4002', err instanceof Error ? err.message : String(err), err);
    }
  });
}

function handleVoid(channel: string, schema: z.ZodType<unknown>, fn: () => void): void {
  ipcMain.handle(channel, async (_event, raw: unknown) => {
    const parsed = schema.safeParse(raw ?? {});
    if (!parsed.success) return;
    try {
      fn();
    } catch {
      // Cleanup handlers are best-effort; nothing to return.
    }
  });
}

export function registerIpc(deps: IpcDeps): void {
  const { session, registry } = deps;

  handle<Record<string, unknown>, Envelope<ProjectInfo>>('gatepack:openProject', NoPayloadSchema, () =>
    openViaDialog(session, 'any'),
  );

  handle('gatepack:openProjectPath', OpenProjectPathSchema, (p) =>
    session.openProjectPath(p.path),
  );

  handle('gatepack:newProject', NewProjectSchema, (p) => session.newProject(p.directory));

  handle<Record<string, unknown>, Envelope<ProjectInfo>>('gatepack:newProjectDialog', NoPayloadSchema, () =>
    newViaDialog(session),
  );

  handleVoid('gatepack:closeProject', NoPayloadSchema, () => session.closeProject());

  handle('gatepack:saveProject', NoPayloadSchema, () => session.saveProject());

  handle('gatepack:saveProjectAs', SaveProjectAsSchema, (p) =>
    session.saveProjectAs(p.gpkPath),
  );

  // §GUI-1: reveal the build outputs, and copy them out. Neither takes a path
  // from the renderer — the destination is chosen by a native dialog, which is
  // the trust boundary for writing outside the project root (§5.2).
  handle('gatepack:buildState', NoPayloadSchema, () => session.buildState());

  handle('gatepack:revealOutputs', NoPayloadSchema, () => session.revealOutputs());

  handle<Record<string, unknown>, Envelope<{ path: string; files: string[] }>>(
    'gatepack:exportOutputs',
    NoPayloadSchema,
    () => exportViaDialog(session),
  );

  // Chrome, not project state: the renderer reports the theme it is showing so
  // Electron's own menu bar matches it. Fire-and-forget — there is no result to
  // report, and a host whose chrome does not follow `nativeTheme` is not an
  // error.
  ipcMain.handle('gatepack:setNativeTheme', async (_event, raw: unknown) => {
    const parsed = NativeThemeSchema.safeParse(raw ?? {});
    if (parsed.success) nativeTheme.themeSource = parsed.data.theme;
  });

  handle('gatepack:readSpec', NoPayloadSchema, () => session.readSpec());

  handle('gatepack:writeSpec', WriteSpecSchema, (p) => session.writeSpec(p.text));

  handle('gatepack:compile', InvokeTokenSchema, (p) => session.compile(p.token));
  handle('gatepack:estimate', InvokeTokenSchema, (p) => session.estimate(p.token));
  handle('gatepack:verify', InvokeTokenSchema, (p) => session.verify(p.token));
  handle('gatepack:build', InvokeTokenSchema, (p) => session.build(p.token));
  handle('gatepack:analyse', InvokeTokenSchema, (p) => session.analyse(p.token));
  handle('gatepack:provenance', NoPayloadSchema, () => session.provenance());
  handle('gatepack:simulate', InvokeTokenSchema, (p) => session.simulate(p.token));
  handle('gatepack:mappedNetlist', NoPayloadSchema, () => session.mappedNetlist());
  handle('gatepack:packedNetlist', NoPayloadSchema, () => session.packedNetlist());

  handle('gatepack:doctor', NoPayloadSchema, () => session.doctor());

  handle('gatepack:currentProject', NoPayloadSchema, () => session.currentProject());

  handle('gatepack:checkLibrary', CheckLibrarySchema, (p) => session.checkLibrary(p.path));
  handle('gatepack:listExamples', NoPayloadSchema, () => session.listExamples());
  handle('gatepack:openExample', OpenExampleSchema, (p) => session.openExample(p.name));

  ipcMain.handle('gatepack:cancel', async (_event, raw: unknown) => {
    const parsed = CancelTokenSchema.safeParse(raw ?? {});
    if (parsed.success) registry.cancel(parsed.data.token);
  });
}

async function openViaDialog(
  session: SessionManager,
  kind: 'any' | 'gpk',
): Promise<Envelope<ProjectInfo>> {
  const options: OpenDialogOptions =
    kind === 'gpk'
      ? {
          properties: ['openFile'],
          filters: [{ name: 'gatepack project', extensions: ['gpk'] }],
        }
      : { properties: ['openFile', 'openDirectory'] };

  const result = await dialog.showOpenDialog(options);
  if (result.canceled || result.filePaths.length === 0) {
    return errorEnvelope('openProject', 'GP4201', 'open cancelled');
  }
  return session.openProjectPath(result.filePaths[0]);
}

/**
 * Ask for a directory to scaffold a new project into.
 *
 * `createDirectory` is what makes this usable: the natural gesture is to make
 * a folder for the design at the moment you decide to start it, and without
 * that property the user has to leave the application to create one first --
 * which is the very thing having a New Project command is meant to end.
 */
async function newViaDialog(session: SessionManager): Promise<Envelope<ProjectInfo>> {
  const result = await dialog.showOpenDialog({
    title: 'New gatepack project',
    buttonLabel: 'Create project here',
    properties: ['openDirectory', 'createDirectory'],
  });
  if (result.canceled || result.filePaths.length === 0) {
    return errorEnvelope('newProject', 'GP4201', 'new project cancelled');
  }
  return session.newProject(result.filePaths[0]);
}

/**
 * Ask for a directory to copy the build outputs into (§GUI-1).
 *
 * The destination always comes from this native dialog, never from the
 * renderer: writing outside the project root is acceptable only because a
 * native dialog picked it (§5.2). Cancelled is a visible, legitimate state
 * (`GP4201`), the same shape the other dialogs return for a cancelled open.
 */
async function exportViaDialog(
  session: SessionManager,
): Promise<Envelope<{ path: string; files: string[] }>> {
  const result = await dialog.showOpenDialog({
    title: 'Export build outputs',
    buttonLabel: 'Export here',
    properties: ['openDirectory', 'createDirectory'],
  });
  if (result.canceled || result.filePaths.length === 0) {
    return errorEnvelope('exportOutputs', 'GP4201', 'export cancelled');
  }
  return session.exportOutputs(result.filePaths[0]);
}
