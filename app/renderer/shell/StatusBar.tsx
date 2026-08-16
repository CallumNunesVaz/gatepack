/**
 * The status bar — project path, design name, diagnostics count, toolchain
 * state, and a pulsing indicator for whatever command is running right now.
 *
 * "Toolchain state" is the core's own `doctor()` answer, fetched once here and
 * never recomputed by the renderer: a missing binary is a legitimate visible
 * state ("N tools missing"), not something to paper over. The running indicator
 * comes from the bridge's `onProgress` events, so the shell reports the truth
 * it is handed rather than guessing whether a command is still alive.
 */

import { useEffect, useState } from 'react';
import { useApi } from '../bridge/context';
import { useProject } from '../state/project';
import type { DoctorReport } from '../../shared/api';

const PROGRESS_FADE_MS = 1600;

export function StatusBar() {
  const { project, model, diagnostics, specStale } = useProject();
  const api = useApi();
  const [doctor, setDoctor] = useState<DoctorReport | null>(null);
  const [doctorFailed, setDoctorFailed] = useState(false);
  const [progress, setProgress] = useState<{ stage: string; percent?: number } | null>(null);
  const [pulse, setPulse] = useState(false);

  useEffect(() => {
    let cancelled = false;
    api.doctor().then((env) => {
      if (cancelled) return;
      if (env.ok) setDoctor(env.data);
      else setDoctorFailed(true);
    });
    return () => {
      cancelled = true;
    };
  }, [api]);

  useEffect(() => {
    let timer: ReturnType<typeof setTimeout> | null = null;
    const unsubscribe = api.onProgress((p) => {
      setProgress(p);
      setPulse(true);
      if (timer) clearTimeout(timer);
      timer = setTimeout(() => setPulse(false), PROGRESS_FADE_MS);
    });
    return () => {
      if (timer) clearTimeout(timer);
      unsubscribe();
    };
  }, [api]);

  const errorCount = diagnostics.filter((d) => d.severity === 'error').length;
  const missingTools = doctor ? doctor.tools.filter((t) => t.direct && !t.found).length : null;

  let toolchain = 'checking tools…';
  if (doctor !== null) {
    toolchain = missingTools === 0 ? 'tools ready' : `${missingTools} tool${missingTools === 1 ? '' : 's'} missing`;
  } else if (doctorFailed) {
    toolchain = 'tools unknown';
  }

  return (
    <footer className="gp-statusbar" data-testid="status-bar">
      <span className="gp-statusbar__item gp-statusbar__project" data-testid="status-project" title={project?.designPath}>
        {project ? project.designPath : 'no project'}
      </span>
      <span className="gp-statusbar__item" data-testid="status-design">
        {model ? model.name : '—'}
      </span>
      <span
        className={
          errorCount > 0
            ? 'gp-statusbar__item gp-statusbar__diag gp-statusbar__diag--error'
            : 'gp-statusbar__item gp-statusbar__diag'
        }
        data-testid="status-diagnostics"
      >
        {errorCount} error{errorCount === 1 ? '' : 's'}
      </span>
      {specStale ? (
        <span
          className="gp-statusbar__item gp-statusbar__diag"
          data-testid="status-stale"
          title="The spec changed on disk; your unsaved edits were kept."
        >
          spec changed on disk
        </span>
      ) : null}
      <span className="gp-statusbar__spacer" />
      {progress ? (
        <span className="gp-statusbar__item gp-statusbar__progress" data-testid="status-progress">
          <span className={pulse ? 'gp-pulse gp-pulse--active' : 'gp-pulse'} aria-hidden="true" />
          {progress.stage}
          {progress.percent !== undefined ? ` ${progress.percent}%` : ''}
        </span>
      ) : null}
      <span className="gp-statusbar__item" data-testid="status-toolchain">
        {toolchain}
      </span>
    </footer>
  );
}
