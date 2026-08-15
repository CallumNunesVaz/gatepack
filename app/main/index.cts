/**
 * Electron main entry — window creation with the §5.2 security posture, the
 * application menu, and wiring of the C9 session manager + IPC bridge.
 */

import {
  app,
  BrowserWindow,
  dialog,
  Menu,
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
].join('; ');

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

  const indexPath = path.join(app.getAppPath(), 'dist', 'renderer', 'index.html');
  if (fs.existsSync(indexPath)) return pathToFileURL(indexPath).toString();

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

async function buildMenu(location: CoreLocation | null): Promise<void> {
  const examplesSubmenu = await fetchExamplesSubmenu(location);

  const fileMenu: MenuItemConstructorOptions[] = [
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

  const appRoot = app.getAppPath();
  const projectRoot = path.dirname(appRoot);
  const location = locateCore({ appRoot, projectRoot, env: process.env });
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
