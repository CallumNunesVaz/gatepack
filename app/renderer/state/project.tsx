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
  /** Bumped on every spec edit; results carry the revision they were computed at. */
  revision: number;
  model: DesignModel | null;
  diagnostics: Diagnostic[];
  project: ProjectInfo | null;
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
  const [revision, setRevision] = useState(0);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pendingRef = useRef<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    api.openProject().then((env) => {
      if (cancelled || !env.ok) return;
      setProject(env.data);
    });
    api.readSpec().then((env) => {
      if (cancelled || !env.ok) return;
      setSpecTextState(env.data.text);
    });
    return () => {
      cancelled = true;
    };
  }, [api]);

  const setSpecText = useCallback((text: string) => {
    setSpecTextState(text);
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
      setSpecText,
      save,
    }),
    [specText, revision, model, diagnostics, project, setSpecText, save],
  );

  return <ProjectContext.Provider value={value}>{children}</ProjectContext.Provider>;
}

export function useProject(): ProjectContextValue {
  const ctx = useContext(ProjectContext);
  if (!ctx) throw new Error('useProject must be used inside <ProjectProvider>');
  return ctx;
}
