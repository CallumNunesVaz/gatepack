import { useState } from 'react';
import { ProjectProvider, useProject } from './state/project';
import { SelectionProvider } from './selection/bus';
import { SpecEditor } from './views/SpecEditor';
import { TruthTable } from './views/TruthTable';
import { Schematic } from './views/Schematic';
import { BomView } from './views/BomView';
import { AnalysisView } from './views/AnalysisView';
import { VerificationPanel } from './views/VerificationPanel';

type PaneId = 'spec' | 'truthtable' | 'schematic' | 'packing' | 'analysis' | 'verify';

const PANES: Array<{ id: PaneId; label: string }> = [
  { id: 'spec', label: 'Spec editor' },
  { id: 'truthtable', label: 'Truth table' },
  { id: 'schematic', label: 'Schematic' },
  { id: 'packing', label: 'Packing & BOM' },
  { id: 'analysis', label: 'Analysis' },
  { id: 'verify', label: 'Verification' },
];

function Shell() {
  const { model, diagnostics, project } = useProject();
  const [active, setActive] = useState<PaneId>('spec');

  const errorCount = diagnostics.filter((d) => d.severity === 'error').length;

  return (
    <div className="app">
      <header className="app__topbar">
        <span className="app__title">gatepack</span>
        {project ? <span className="app__project">{project.designPath}</span> : null}
        {model ? <span className="app__design">{model.name}</span> : null}
        {errorCount > 0 ? (
          <span className="app__errors" data-testid="diagnostics-count">
            {errorCount} error{errorCount === 1 ? '' : 's'}
          </span>
        ) : null}
      </header>
      <div className="app__body">
        <nav className="app__nav">
          {PANES.map((p) => (
            <button
              key={p.id}
              className={p.id === active ? 'nav-btn nav-btn--active' : 'nav-btn'}
              onClick={() => setActive(p.id)}
            >
              {p.label}
            </button>
          ))}
        </nav>
        <main className="app__content">
          {active === 'spec' ? <SpecEditor /> : null}
          {active === 'truthtable' ? <TruthTable /> : null}
          {active === 'schematic' ? <Schematic /> : null}
          {active === 'packing' ? <BomView /> : null}
          {active === 'analysis' ? <AnalysisView /> : null}
          {active === 'verify' ? <VerificationPanel /> : null}
        </main>
      </div>
    </div>
  );
}

export function App() {
  return (
    <ProjectProvider>
      <SelectionProvider>
        <Shell />
      </SelectionProvider>
    </ProjectProvider>
  );
}
