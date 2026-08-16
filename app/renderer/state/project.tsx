import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react';
import type { Diagnostic, ProjectInfo } from '../../shared/api';
import { useApi } from '../bridge/context';
import { parseDesignText, type DesignModel } from '../design/model';

export interface ProjectContextValue {
  specText: string;
  /** Bumped on every spec change (local edit or external re-read); results carry the revision they were computed at. */
  revision: number;
  model: DesignModel | null;
  diagnostics: Diagnostic[];
  project: ProjectInfo | null;
  /**
   * True when the spec changed on disk but unsaved local edits were kept
   * rather than overwritten. The editor should mark the document stale.
   */
  specStale: boolean;
  setSpecText: (text: string) => void;
  /** Flush the pending write to the bridge (the explicit-save path). */
  save: () => Promise<void>;
}

const ProjectContext = createContext<ProjectContextValue | null>(null);

const WRITE_DEBOUNCE_MS = 400;

export function ProjectProvider({ children }: { children: ReactNode }) {
  const api = useApi();
  const [project, setProject] = useState<ProjectInfo | null>(null);
  const [specText, setSpecTextState] = useState('');
  const [specStale, setSpecStale] = useState(false);
  const [revision, setRevision] = useState(0);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pendingRef = useRef<string | null>(null);
  const readSeqRef = useRef(0);

  // Apply spec text that is already authoritative (from disk) without
  // scheduling a write, and clear the stale marker. Bumps the revision so a
  // revisioned result computed against the old text is flagged stale.
  const applySpecText = useCallback((text: string) => {
    setSpecTextState(text);
    setSpecStale(false);
    setRevision((r) => r + 1);
  }, []);

  // Read the spec from disk. Only the latest read wins: an out-of-order
  // response (an earlier read resolving after a later one) must never clobber
  // the current text with stale content.
  const readSpecFromDisk = useCallback(
    (markChanged: boolean) => {
      const seq = ++readSeqRef.current;
      api.readSpec().then((env) => {
        if (seq !== readSeqRef.current) return;
        if (!env.ok) return;
        // The initial load is not a "change" — nothing could have computed
        // against the empty text yet, and bumping the revision here races an
        // in-flight task started just after mount (cancelling it). A project
        // switch or external edit is a real change and must invalidate prior
        // results, so those bump.
        if (markChanged) applySpecText(env.data.text);
        else setSpecTextState(env.data.text);
      });
    },
    [api, applySpecText],
  );

  useEffect(() => {
    let cancelled = false;

    // `onProjectChanged` is how the renderer learns which project is open —
    // NOT `openProject()`, which shows a native file picker and is the user's
    // "Open…" action. Calling that on mount popped a dialog at every launch,
    // and because it reports a cancelled dialog as an error the project stayed
    // null, so the status bar read "no project" while the showcase was open.
    //
    // Main deliberately re-broadcasts after the page loads (see index.cts:
    // "so a renderer that subscribes after load still sees the project"), and
    // nothing was subscribing to it. Subscribe before the first await so the
    // re-broadcast cannot land in the gap.
    const unsubscribe = api.onProjectChanged((info) => {
      if (cancelled) return;
      setProject(info);
      // A new (or reopened) project means a different spec on disk. Drop any
      // pending local write — it belonged to the previous project — and read
      // the new spec so `model.name` (and the status bar) follow the project.
      if (timerRef.current) clearTimeout(timerRef.current);
      pendingRef.current = null;
      readSpecFromDisk(true);
    });

    // Subscribing is not enough on first launch: main broadcasts once, right
    // after `loadURL` resolves, which is before React has run this effect. So
    // also *ask*. The subscription then keeps it current.
    api.currentProject().then((env) => {
      if (cancelled || !env.ok || env.data === null) return;
      setProject(env.data);
    });

    readSpecFromDisk(false);

    return () => {
      cancelled = true;
      unsubscribe();
    };
  }, [api, readSpecFromDisk]);

  // External file change (C9 broadcasts debounced file-change events). Re-read,
  // unless the user has unsaved local edits — silently overwriting what they
  // typed because a file changed on disk is a worse bug than a stale editor.
  // Policy: keep local edits and mark the spec stale. The marker clears when
  // the text is next applied authoritatively (a fresh local edit, or a re-read
  // once nothing is pending).
  useEffect(() => {
    let cancelled = false;
    const unsubscribe = api.onFileChanged(() => {
      if (cancelled) return;
      if (pendingRef.current !== null) {
        setSpecStale(true);
        return;
      }
      readSpecFromDisk(true);
    });
    return () => {
      cancelled = true;
      unsubscribe();
    };
  }, [api, readSpecFromDisk]);

  const setSpecText = useCallback((text: string) => {
    setSpecTextState(text);
    setSpecStale(false);
    setRevision((r) => r + 1);
    pendingRef.current = text;
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => {
      const value = pendingRef.current;
      pendingRef.current = null;
      if (value !== null) void api.writeSpec(value);
    }, WRITE_DEBOUNCE_MS);
  }, [api]);

  const save = useCallback(async () => {
    if (timerRef.current) clearTimeout(timerRef.current);
    const value = pendingRef.current ?? specText;
    pendingRef.current = null;
    await api.writeSpec(value);
  }, [api, specText]);

  useEffect(() => {
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, []);

  const { model, diagnostics } = useMemo(() => parseDesignText(specText), [specText]);

  const value = useMemo<ProjectContextValue>(
    () => ({
      specText,
      revision,
      model,
      diagnostics,
      project,
      specStale,
      setSpecText,
      save,
    }),
    [specText, revision, model, diagnostics, project, specStale, setSpecText, save],
  );

  return <ProjectContext.Provider value={value}>{children}</ProjectContext.Provider>;
}

export function useProject(): ProjectContextValue {
  const ctx = useContext(ProjectContext);
  if (!ctx) throw new Error('useProject must be used inside <ProjectProvider>');
  return ctx;
}
