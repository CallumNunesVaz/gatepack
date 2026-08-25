/**
 * Preload bridge (§5.2): expose exactly the `GatepackApi` interface on
 * `window.gatepack` via `contextBridge`, and nothing else. The renderer never
 * sees `fs`, `child_process`, `ipcRenderer`, or any path it did not receive
 * from the main process.
 *
 * This file must stay self-contained: under `sandbox: true` the preload can
 * only `require('electron')` (and a handful of Node built-ins), so all runtime
 * imports here are from 'electron'. Types from shared/api.ts are erased.
 */

import { contextBridge, ipcRenderer, type IpcRendererEvent } from 'electron';

import type {
  AnalysisSummary,
  BuildResult,
  BuildState,
  CompileResult,
  Envelope,
  EstimateResult,
  ExamplesList,
  GatepackApi,
  LibraryCheckResult,
  ProjectInfo,
  DoctorReport,
  PackedView,
  ProvenanceMap,
  SimulationTable,
  VerifyResult,
} from '../shared/api';

function on<T>(channel: string, cb: (payload: T) => void): () => void {
  const listener = (_event: IpcRendererEvent, payload: T) => cb(payload);
  ipcRenderer.on(channel, listener);
  return () => ipcRenderer.removeListener(channel, listener);
}

const api: GatepackApi = {
  openProject: () => ipcRenderer.invoke('gatepack:openProject') as Promise<Envelope<ProjectInfo>>,

  openProjectPath: (path: string) =>
    ipcRenderer.invoke('gatepack:openProjectPath', { path }) as Promise<Envelope<ProjectInfo>>,

  newProject: (directory: string) =>
    ipcRenderer.invoke('gatepack:newProject', { directory }) as Promise<Envelope<ProjectInfo>>,

  newProjectDialog: () =>
    ipcRenderer.invoke('gatepack:newProjectDialog') as Promise<Envelope<ProjectInfo>>,

  closeProject: () => ipcRenderer.invoke('gatepack:closeProject') as Promise<void>,

  saveProject: () =>
    ipcRenderer.invoke('gatepack:saveProject') as Promise<Envelope<ProjectInfo>>,

  saveProjectAs: (gpkPath: string) =>
    ipcRenderer.invoke('gatepack:saveProjectAs', { gpkPath }) as Promise<Envelope<ProjectInfo>>,

  buildState: () =>
    ipcRenderer.invoke('gatepack:buildState') as Promise<Envelope<BuildState>>,

  revealOutputs: () =>
    ipcRenderer.invoke('gatepack:revealOutputs') as Promise<Envelope<{ path: string }>>,

  exportOutputs: () =>
    ipcRenderer.invoke('gatepack:exportOutputs') as Promise<Envelope<{ path: string; files: string[] }>>,

  setNativeTheme: (theme: 'light' | 'dark') =>
    ipcRenderer.invoke('gatepack:setNativeTheme', { theme }) as Promise<void>,

  readSpec: () =>
    ipcRenderer.invoke('gatepack:readSpec') as Promise<Envelope<{ text: string; path: string }>>,

  writeSpec: (text: string) =>
    ipcRenderer.invoke('gatepack:writeSpec', { text }) as Promise<Envelope<{ path: string }>>,

  compile: (token?: string) =>
    ipcRenderer.invoke('gatepack:compile', { token }) as Promise<Envelope<CompileResult>>,

  estimate: (token?: string) =>
    ipcRenderer.invoke('gatepack:estimate', { token }) as Promise<Envelope<EstimateResult>>,

  verify: (token?: string) =>
    ipcRenderer.invoke('gatepack:verify', { token }) as Promise<Envelope<VerifyResult>>,

  build: (token?: string) =>
    ipcRenderer.invoke('gatepack:build', { token }) as Promise<Envelope<BuildResult>>,

  analyse: (token?: string) =>
    ipcRenderer.invoke('gatepack:analyse', { token }) as Promise<Envelope<AnalysisSummary>>,

  provenance: () =>
    ipcRenderer.invoke('gatepack:provenance') as Promise<Envelope<ProvenanceMap>>,
  simulate: (token?: string) =>
    ipcRenderer.invoke('gatepack:simulate', { token }) as Promise<Envelope<SimulationTable>>,

  mappedNetlist: () =>
    ipcRenderer.invoke('gatepack:mappedNetlist') as Promise<Envelope<unknown>>,
  packedNetlist: () =>
    ipcRenderer.invoke('gatepack:packedNetlist') as Promise<Envelope<PackedView>>,
  doctor: () => ipcRenderer.invoke('gatepack:doctor') as Promise<Envelope<DoctorReport>>,
  currentProject: () =>
    ipcRenderer.invoke('gatepack:currentProject') as Promise<Envelope<ProjectInfo | null>>,

  checkLibrary: (path: string) =>
    ipcRenderer.invoke('gatepack:checkLibrary', { path }) as Promise<Envelope<LibraryCheckResult>>,

  listExamples: () =>
    ipcRenderer.invoke('gatepack:listExamples') as Promise<Envelope<ExamplesList>>,

  openExample: (name: string) =>
    ipcRenderer.invoke('gatepack:openExample', { name }) as Promise<Envelope<ProjectInfo>>,

  cancel: (token: string) => ipcRenderer.invoke('gatepack:cancel', { token }) as Promise<void>,

  onProjectChanged: (cb: (info: ProjectInfo) => void) =>
    on<ProjectInfo>('gatepack:projectChanged', cb),

  onFileChanged: (cb: (paths: string[]) => void) => on<string[]>('gatepack:fileChanged', cb),

  onProgress: (cb: (p: { token: string; stage: string; percent?: number }) => void) =>
    on<{ token: string; stage: string; percent?: number }>('gatepack:progress', cb),
};

contextBridge.exposeInMainWorld('gatepack', api);
