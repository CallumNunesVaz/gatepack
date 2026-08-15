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
import { locateCore } from './core.cjs';
import { registerIpc } from './ipc.cjs';
import { SessionManager } from './session.cjs';

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

function buildMenu(): void {
  const template: MenuItemConstructorOptions[] = [
    {
      label: 'File',
      submenu: [
        { label: 'Open Project…', accelerator: 'CmdOrCtrl+O', click: () => openViaDialog('any') },
        { label: 'Open .gpk…', accelerator: 'CmdOrCtrl+Shift+O', click: () => openViaDialog('gpk') },
        { type: 'separator' },
        { label: 'Save', accelerator: 'CmdOrCtrl+S', click: () => void sessionManager?.saveProject() },
        { label: 'Save As…', accelerator: 'CmdOrCtrl+Shift+S', click: () => saveAsDialog() },
        { label: 'Close Project', click: () => sessionManager?.closeProject() },
        { type: 'separator' },
        { label: 'Quit', accelerator: 'CmdOrCtrl+Q', click: () => app.quit() },
      ],
    },
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

function bootstrap(): void {
  applySecurityPosture();

  const appRoot = app.getAppPath();
  const projectRoot = path.dirname(appRoot);
  const location = locateCore({ appRoot, projectRoot, env: process.env });
  const registry = new CancelRegistry();

  sessionManager = new SessionManager({
    location,
    registry,
    onProjectChanged: (info: ProjectInfo) => broadcast('gatepack:projectChanged', info),
    onFileChanged: (paths: string[]) => broadcast('gatepack:fileChanged', paths),
    onProgress: (p) => broadcast('gatepack:progress', p),
  });

  registerIpc({ session: sessionManager, registry });

  buildMenu();

  mainWindow = createWindow();
  void mainWindow.loadURL(rendererUrl());
}

app.whenReady().then(() => {
  bootstrap();

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
