import { useEffect, useState } from 'react';
import { useApi } from '../bridge/context';
import { setDoctorReport } from './doctorStore';
import type { Diagnostic, DoctorReport } from '../../shared/api';
import './panels.css';

/**
 * `inspect.doctor` — the toolchain status panel.
 *
 * The single most valuable diagnostic view: a user whose Build button fails
 * needs to see *which binary is missing and what it was for*, not a stack
 * trace. `DoctorReport` already carries `purpose` per tool; this panel shows
 * found tools with their version and path, missing tools with what breaks
 * without them, and the bundled-resource checks. Nothing here is recomputed —
 * every fact comes from `doctor()`, and the report is published to
 * `doctorStore` for the shell's status-bar indicator.
 */
export function ToolchainStatusPanel() {
  const api = useApi();
  const [status, setStatus] = useState<'loading' | 'success' | 'error'>('loading');
  const [report, setReport] = useState<DoctorReport | null>(null);
  const [error, setError] = useState<Diagnostic | null>(null);

  useEffect(() => {
    let cancelled = false;
    setStatus('loading');
    api.doctor().then((env) => {
      if (cancelled) return;
      if (env.ok) {
        setReport(env.data);
        setDoctorReport(env.data);
        setStatus('success');
      } else {
        setError(env.error);
        setDoctorReport(null);
        setStatus('error');
      }
    });
    return () => {
      cancelled = true;
    };
  }, [api]);

  return (
    <section className="gp-panel" data-testid="doctor-view">
      <header className="gp-panel__header">
        <h2 className="gp-panel__title">Toolchain status</h2>
      </header>

      {status === 'loading' ? (
        <p className="gp-loading" data-testid="doctor-loading">
          Checking toolchain…
        </p>
      ) : null}

      {status === 'error' ? (
        <div className="gp-error" data-testid="doctor-error">
          <strong>{error?.code ?? 'error'}:</strong> {error?.message}
        </div>
      ) : null}

      {status === 'success' && report ? (
        <>
          <div
            className={`gp-overall ${report.allToolsPresent ? 'gp-overall--ok' : 'gp-overall--fail'}`}
            data-testid="doctor-overall"
            data-all-present={String(report.allToolsPresent)}
          >
            {report.allToolsPresent
              ? 'All required tools present.'
              : 'Some required tools are missing — the commands that need them will refuse.'}
          </div>

          <ul className="gp-tool-list" data-testid="doctor-tools">
            {report.tools.map((tool) => (
              <li
                key={tool.name}
                className={`gp-tool ${tool.found ? '' : 'gp-tool--missing'}`}
                data-testid={`doctor-tool-${tool.name}`}
                data-found={String(tool.found)}
              >
                <div className="gp-tool__head">
                  <span className="gp-tool__name">{tool.name}</span>
                  {tool.found ? (
                    <span className="gp-badge gp-badge--found">found</span>
                  ) : (
                    <span className="gp-badge gp-badge--missing">missing</span>
                  )}
                  {tool.direct ? null : (
                    <span className="gp-tool__direct">reached indirectly</span>
                  )}
                  {tool.found && tool.version ? (
                    <span className="gp-tool__version">{tool.version}</span>
                  ) : null}
                </div>
                {tool.found && tool.path ? (
                  <span className="gp-tool__path">{tool.path}</span>
                ) : null}
                <span className="gp-tool__purpose">
                  {tool.found ? tool.purpose : `Missing — ${tool.purpose}`}
                </span>
              </li>
            ))}
          </ul>

          <div data-testid="doctor-resources">
            <h3>Bundled resources</h3>
            <ul className="gp-tool-list">
              <li
                className={`gp-tool ${report.resources.commonFrontendYs ? '' : 'gp-tool--missing'}`}
                data-testid="doctor-resource-frontend"
                data-present={String(report.resources.commonFrontendYs)}
              >
                <div className="gp-tool__head">
                  <span className="gp-tool__name">common_frontend.ys</span>
                  {report.resources.commonFrontendYs ? (
                    <span className="gp-badge gp-badge--found">present</span>
                  ) : (
                    <span className="gp-badge gp-badge--missing">missing</span>
                  )}
                </div>
                <span className="gp-tool__purpose">
                  {report.resources.commonFrontendYs
                    ? 'The shared synthesis script the pipeline loads.'
                    : 'Missing — synthesis cannot generate its script.'}
                </span>
              </li>
              <li
                className={`gp-tool ${report.resources.mcellModels ? '' : 'gp-tool--missing'}`}
                data-testid="doctor-resource-mcell"
                data-present={String(report.resources.mcellModels)}
              >
                <div className="gp-tool__head">
                  <span className="gp-tool__name">M-cell models</span>
                  {report.resources.mcellModels ? (
                    <span className="gp-badge gp-badge--found">
                      present ({report.resources.mcellCount})
                    </span>
                  ) : (
                    <span className="gp-badge gp-badge--missing">missing</span>
                  )}
                </div>
                <span className="gp-tool__purpose">
                  {report.resources.mcellModels
                    ? `${report.resources.mcellCount} macro model(s) available.`
                    : 'Missing — macro-cell simulation models are not bundled.'}
                </span>
              </li>
            </ul>
          </div>
        </>
      ) : null}
    </section>
  );
}
