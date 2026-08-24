/**
 * Electron main entry — window creation with the §5.2 security posture, the
 * application menu, and wiring of the C9 session manager + IPC bridge.
 */

import {
  app,
  BrowserWindow,
  dialog,
  Menu,
  net,
  protocol,
  shell,
  type MenuItemConstructorOptions,
  type OpenDialogOptions,
  session as electronSession,
} from 'electron';
import * as fs from 'node:fs';
import * as path from 'node:path';
import { pathToFileURL } from 'node:url';

import type { ProjectInfo } from '../shared/api';
import { CancelRegistry } from './cancel.cjs';
import { locateCore, runRaw, type CoreLocation } from './core.cjs';
import { findExamplesRoot, parseExamplesList } from './examples.cjs';
import { registerIpc } from './ipc.cjs';
import { SessionManager, SHOWCASE_NAME } from './session.cjs';
import { readStoredSession, writeStoredSession } from './session-store.cjs';

const FALLBACK_HTML = `<!DOCTYPE html>
<html>
  <head>
    <meta charset="utf-8" />
    <meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'" />
    <title>gatepack</title>
  </head>
  <body>
    <p>gatepack renderer is not built yet (app/renderer/).</p>
  </body>
</html>
`;

const STRICT_CSP = [
  "default-src 'none'",
  "script-src 'self'",
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data:",
  "font-src 'self'",
  "connect-src 'self'",
  // Stated rather than inherited. Without it `worker-src` falls back through
  // `child-src` to `script-src`, which happens to be the same value — but the
  // schematic's layout worker is load-bearing and should not depend on a
  // fallback chain someone could shorten later.
  "worker-src 'self'",
].join('; ');

/**
 * The renderer is served from `app://renderer/…`, not from `file://`.
 *
 * Chromium gives a `file://` document an opaque origin, and an opaque origin
 * may not construct a `Worker` at all — the constructor fails with an
 * ErrorEvent carrying no message, which is exactly what the schematic view
 * reported as "schematic worker failed". The netlistsvg + elkjs layout runs in
 * a worker precisely so a large netlist cannot freeze the UI, so the answer is
 * to give the page a real origin rather than to give up the worker.
 *
 * A custom scheme registered as `standard` + `secure` does that, and it tightens
 * the security posture as a side effect: `'self'` in the CSP now names an
 * actual origin, and the handler below serves the bundle directory and nothing
 * outside it.
 */
const APP_SCHEME = 'app';
const APP_ORIGIN = `${APP_SCHEME}://renderer`;

protocol.registerSchemesAsPrivileged([
  {
    scheme: APP_SCHEME,
    privileges: { standard: true, secure: true, supportFetchAPI: true, stream: true },
  },
]);

function rendererRoot(): string {
  return path.join(app.getAppPath(), 'dist', 'renderer');
}

/** Resolve a request path inside the bundle, or null if it escapes it. */
export function resolveBundlePath(root: string, urlPath: string): string | null {
  const rel = decodeURIComponent(urlPath).replace(/^\/+/, '');
  const target = path.normalize(path.join(root, rel === '' ? 'index.html' : rel));
  const prefix = root.endsWith(path.sep) ? root : root + path.sep;
  return target === root || target.startsWith(prefix) ? target : null;
}

function registerAppProtocol(): void {
  const root = rendererRoot();
  protocol.handle(APP_SCHEME, async (request) => {
    const target = resolveBundlePath(root, new URL(request.url).pathname);
    // A traversal attempt is refused here rather than being resolved and then
    // regretted: the handler is the only thing standing between a URL and the
    // filesystem.
    if (target === null) return new Response('forbidden', { status: 403 });
    if (!fs.existsSync(target)) return new Response('not found', { status: 404 });

    const response = await net.fetch(pathToFileURL(target).toString());
    const headers = new Headers(response.headers);
    headers.set('Content-Security-Policy', STRICT_CSP);
    return new Response(response.body, { status: response.status, headers });
  });
}

let mainWindow: BrowserWindow | null = null;
let sessionManager: SessionManager | null = null;

function broadcast(channel: string, payload: unknown): void {
  for (const win of BrowserWindow.getAllWindows()) {
    if (!win.isDestroyed()) win.webContents.send(channel, payload);
  }
}

function fallbackHtmlPath(): string {
  const dir = path.join(app.getPath('temp'), 'gatepack-stub');
  fs.mkdirSync(dir, { recursive: true });
  const p = path.join(dir, 'index.html');
  fs.writeFileSync(p, FALLBACK_HTML);
  return p;
}

function rendererUrl(): string {
  const dev = process.env.GATEPACK_DEV_SERVER;
  if (dev && dev.length > 0) return dev;

  const indexPath = path.join(rendererRoot(), 'index.html');
  if (fs.existsSync(indexPath)) return `${APP_ORIGIN}/index.html`;

  return pathToFileURL(fallbackHtmlPath()).toString();
}

function applySecurityPosture(): void {
  // Strict CSP on every response. For the local renderer this is belt-and-
  // braces on top of the `<meta>` CSP the renderer ships; for a (disabled)
  // remote load it would be the only defence.
  electronSession.defaultSession.webRequest.onHeadersReceived((details, callback) => {
    callback({
      responseHeaders: {
        ...details.responseHeaders,
        'Content-Security-Policy': [STRICT_CSP],
      },
    });
  });

  // No remote content, ever; deny every permission request.
  electronSession.defaultSession.setPermissionRequestHandler((_wc, _permission, cb) => cb(false));
}

function createWindow(): BrowserWindow {
  const win = new BrowserWindow({
    width: 1280,
    height: 860,
    show: false,
    webPreferences: {
      preload: path.join(__dirname, '../preload/index.cjs'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      webSecurity: true,
      allowRunningInsecureContent: false,
      nodeIntegrationInSubFrames: false,
    },
  });

  // Deny every new window and all navigation away from the renderer bundle.
  win.webContents.setWindowOpenHandler(() => ({ action: 'deny' }));
  win.webContents.on('will-navigate', (event) => event.preventDefault());
  win.webContents.on('will-redirect', (event) => event.preventDefault());
  win.webContents.on('will-attach-webview', (event) => event.preventDefault());

  win.once('ready-to-show', () => win.show());
  win.on('closed', () => {
    if (mainWindow === win) mainWindow = null;
  });

  return win;
}

function openViaDialog(kind: 'any' | 'gpk'): void {
  const options: OpenDialogOptions =
    kind === 'gpk'
      ? {
          properties: ['openFile'],
          filters: [{ name: 'gatepack project', extensions: ['gpk'] }],
        }
      : { properties: ['openFile', 'openDirectory'] };

  dialog
    .showOpenDialog(options)
    .then((result) => {
      if (result.canceled || result.filePaths.length === 0) return;
      void sessionManager?.openProjectPath(result.filePaths[0]);
    })
    .catch(() => {});
}

/**
 * File > New Project.
 *
 * `createDirectory` lets the user make the folder inside the dialog, at the
 * moment they decide to start a design. Without it they would have to leave
 * the application to create a directory first — which is exactly the gap this
 * command exists to close.
 */
function newProjectDialog(): void {
  dialog
    .showOpenDialog({
      title: 'New gatepack project',
      buttonLabel: 'Create project here',
      properties: ['openDirectory', 'createDirectory'],
    })
    .then((result) => {
      if (result.canceled || result.filePaths.length === 0) return;
      void sessionManager?.newProject(result.filePaths[0]);
    })
    .catch(() => {});
}

function saveAsDialog(): void {
  if (!mainWindow) return;
  dialog
    .showSaveDialog(mainWindow, {
      filters: [{ name: 'gatepack project', extensions: ['gpk'] }],
    })
    .then((result) => {
      if (result.canceled || !result.filePath) return;
      void sessionManager?.saveProjectAs(result.filePath);
    })
    .catch(() => {});
}

/**
 * File > Export Outputs… (§GUI-1): copy the build outputs to a directory the
 * user picks. The destination comes from this native dialog — the trust
 * boundary for writing outside the project root (§5.2) — never from the
 * renderer.
 */
function exportOutputsDialog(): void {
  dialog
    .showOpenDialog({
      title: 'Export build outputs',
      buttonLabel: 'Export here',
      properties: ['openDirectory', 'createDirectory'],
    })
    .then((result) => {
      if (result.canceled || result.filePaths.length === 0) return;
      const sm = sessionManager;
      if (!sm) return;
      void sm.exportOutputs(result.filePaths[0]).then((env) => {
        if (!env.ok) dialog.showErrorBox('Export Outputs', env.error.message);
      });
    })
    .catch(() => {});
}

/**
 * File > Reveal Outputs (§GUI-1). The menu action is fire-and-forget, but the
 * refusal (nothing built) must not be silent: an "outputs" command that does
 * nothing at all is the exact lie this project exists to avoid, so the error
 * is surfaced in a native box rather than swallowed.
 */
function revealOutputsMenu(): void {
  const sm = sessionManager;
  if (!sm) return;
  void sm.revealOutputs().then((env) => {
    if (!env.ok) dialog.showErrorBox('Reveal Outputs', env.error.message);
  });
}

async function buildMenu(location: CoreLocation | null): Promise<void> {
  const examplesSubmenu = await fetchExamplesSubmenu(location);

  const fileMenu: MenuItemConstructorOptions[] = [
    { label: 'New Project…', accelerator: 'CmdOrCtrl+N', click: () => newProjectDialog() },
    { type: 'separator' },
    { label: 'Open Project…', accelerator: 'CmdOrCtrl+O', click: () => openViaDialog('any') },
    { label: 'Open .gpk…', accelerator: 'CmdOrCtrl+Shift+O', click: () => openViaDialog('gpk') },
    { type: 'separator' },
    {
      label: 'Open Showcase',
      click: () => void sessionManager?.openBundledExample(SHOWCASE_NAME),
    },
    {
      label: 'Examples',
      submenu: examplesSubmenu,
    },
    { type: 'separator' },
    {
      label: 'Save',
      accelerator: 'CmdOrCtrl+S',
      click: () => {
        // §18.1(4): saving the showcase prompts for a new location.
        if (sessionManager?.isShowcase()) {
          saveAsDialog();
          return;
        }
        void sessionManager?.saveProject();
      },
    },
    { label: 'Save As…', accelerator: 'CmdOrCtrl+Shift+S', click: () => saveAsDialog() },
    { type: 'separator' },
    { label: 'Reveal Outputs', click: () => revealOutputsMenu() },
    { label: 'Export Outputs…', click: () => exportOutputsDialog() },
    { type: 'separator' },
    { label: 'Close Project', click: () => sessionManager?.closeProject() },
    { type: 'separator' },
    { label: 'Quit', accelerator: 'CmdOrCtrl+Q', click: () => app.quit() },
  ];

  const template: MenuItemConstructorOptions[] = [
    { label: 'File', submenu: fileMenu },
    {
      label: 'Edit',
      submenu: [
        { role: 'undo' },
        { role: 'redo' },
        { type: 'separator' },
        { role: 'cut' },
        { role: 'copy' },
        { role: 'paste' },
        { role: 'selectAll' },
      ],
    },
  ];
  Menu.setApplicationMenu(Menu.buildFromTemplate(template));
}

/**
 * The Examples submenu, populated from `gatepack examples list` (§18.1). The
 * list is fetched via the core rather than re-derived from the filesystem, so
 * discovery and ordering stay the core's responsibility. When the core is
 * missing the submenu is simply empty.
 */
async function fetchExamplesSubmenu(
  location: CoreLocation | null,
): Promise<MenuItemConstructorOptions[]> {
  if (location === null) return [];
  try {
    const res = await runRaw(location, ['examples', 'list']);
    if (res.code !== 0) return [];
    return parseExamplesList(res.stdout).map((entry) => ({
      label: entry.isShowcase ? `${entry.name} (showcase)` : entry.name,
      click: () => void sessionManager?.openBundledExample(entry.name),
    }));
  } catch {
    return [];
  }
}

function sessionDirFromEnv(): string | null {
  const dir = process.env.GATEPACK_SESSION_DIR;
  return dir && dir.length > 0 ? dir : null;
}

/**
 * Open the initial project: the last-opened project when one is stored, falling
 * back to the bundled showcase (§18.1) when there is no prior session (or the
 * stored path no longer opens).
 */
async function openInitialProject(sessionDir: string): Promise<void> {
  const stored = readStoredSession(sessionDir);
  if (stored.lastProjectPath !== null) {
    const env = await sessionManager?.openProjectPath(stored.lastProjectPath);
    if (env && env.ok) return;
  }
  await sessionManager?.openBundledExample(SHOWCASE_NAME);
}

async function bootstrap(): Promise<void> {
  applySecurityPosture();
  registerAppProtocol();

  const appRoot = app.getAppPath();
  const projectRoot = path.dirname(appRoot);
  const location = locateCore({
    appRoot,
    projectRoot,
    env: process.env,
    resourcesPath: process.resourcesPath,
  });
  const registry = new CancelRegistry();
  const sessionDir = sessionDirFromEnv() ?? app.getPath('userData');
  const examplesRoot = findExamplesRoot(appRoot, projectRoot);

  sessionManager = new SessionManager({
    location,
    registry,
    examplesRoot,
    onProjectOpened: (info: ProjectInfo) =>
      writeStoredSession(sessionDir, { lastProjectPath: info.path }),
    onProjectChanged: (info: ProjectInfo) => broadcast('gatepack:projectChanged', info),
    onFileChanged: (paths: string[]) => broadcast('gatepack:fileChanged', paths),
    onProgress: (p) => broadcast('gatepack:progress', p),
    shell: { openPath: (fullPath) => shell.openPath(fullPath) },
  });

  registerIpc({ session: sessionManager, registry });

  await buildMenu(location);

  mainWindow = createWindow();

  // Open the initial project before the renderer loads, so the renderer's first
  // readSpec() sees a real project (the showcase, or the last-opened one)
  // rather than an empty editor (§18.1).
  await openInitialProject(sessionDir);

  await mainWindow.loadURL(rendererUrl());

  // The onProjectChanged fired above happened before the page could listen; re-
  // broadcast so a renderer that subscribes after load still sees the project.
  if (sessionManager?.current) {
    broadcast('gatepack:projectChanged', sessionManager.current);
  }
}

app.whenReady().then(() => {
  void bootstrap();

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      mainWindow = createWindow();
      void mainWindow.loadURL(rendererUrl());
    }
  });
});

app.on('window-all-closed', () => {
  app.quit();
});

app.on('before-quit', () => {
  sessionManager?.dispose();
});
