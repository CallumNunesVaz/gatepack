import type { ReactElement } from 'react';
import { describe, expect, it } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { ApiProvider } from '../bridge/context';
import { ProjectProvider } from '../state/project';
import { setApi } from '../api';
import { FakeGatepack } from '../bridge/fake';
import {
  ExamplesPanel,
  LibraryPanel,
  MappedNetlistPanel,
  PackedNetlistPanel,
  ProvenancePanel,
  ToolchainStatusPanel,
} from './index';
import type {
  DoctorReport,
  LibraryCheckResult,
  PackedView,
  ProvenanceMap,
} from '../../shared/api';

function renderPanel(fake: FakeGatepack, ui: ReactElement) {
  setApi(fake);
  return render(
    <ApiProvider>
      <ProjectProvider>{ui}</ProjectProvider>
    </ApiProvider>,
  );
}

/* ------------------------------------------------------------------ */
/* fixtures                                                            */
/* ------------------------------------------------------------------ */

function doctorReport(over: Partial<DoctorReport>): DoctorReport {
  return {
    allToolsPresent: true,
    tools: [
      {
        name: 'yosys',
        direct: true,
        found: true,
        path: '/usr/bin/yosys',
        version: 'Yosys 0.23',
        purpose: 'logic synthesis (C3): behavioural Verilog -> mapped netlist',
      },
      {
        name: 'sby',
        direct: true,
        found: true,
        path: '/usr/bin/sby',
        version: 'SymbiYosys',
        purpose: 'formal property checking + equivalence fallback',
      },
    ],
    resources: { commonFrontendYs: true, mcellModels: true, mcellCount: 4 },
    ...over,
  };
}

function provenance(over: Partial<ProvenanceMap>): ProvenanceMap {
  return {
    entries: [
      {
        pointer: 'design.yaml:12:transitions[3]',
        nets: ['n1'],
        cells: ['$abc$1$2'],
        confidence: 'exact',
      },
      {
        pointer: 'design.yaml:9:output_logic[y]',
        nets: ['y'],
        cells: [],
        confidence: 'inferred',
      },
    ],
    coverage: 0.5,
    ...over,
  };
}

function packedView(): PackedView {
  return {
    packages: [
      {
        refdes: 'U1',
        partNumber: '74AUP1G00',
        cells: ['NAND2_abc123'],
        instanceCells: ['$abc$148$99$154'],
        capacity: 1,
        spare: 0,
        rationale: 'single NAND2',
      },
    ],
  };
}

function libraryCheck(over: Partial<LibraryCheckResult>): LibraryCheckResult {
  return {
    path: '/tmp/project/parts.csv',
    refsPath: '/tmp/project/parts.refs.md',
    refsPresent: true,
    cellCount: 3,
    includedCount: 2,
    excludedCount: 1,
    missingCitations: [],
    parts: [
      {
        cell: 'INV',
        tier: 'G',
        family: 'AUP',
        partNumber: '74AUP1G04',
        function: '!A',
        inputs: 1,
        gatesPerPackage: 1,
        package: 'SOT-353',
        manufacturers: ['TI'],
        equivalents: 0,
        secondSourceCount: 2,
        citation: 'verified — TI datasheet rev 1',
        unverified: false,
        excluded: false,
        exclusionReason: null,
      },
      {
        cell: 'NAND2',
        tier: 'G',
        family: 'AUP',
        partNumber: '74AUP1G00',
        function: '!(A&B)',
        inputs: 2,
        gatesPerPackage: 1,
        package: 'SOT-353',
        manufacturers: ['TI'],
        equivalents: 0,
        secondSourceCount: 2,
        citation: 'placeholder — unverified',
        unverified: true,
        excluded: false,
        exclusionReason: null,
      },
      {
        cell: 'DFF_S',
        tier: 'F',
        family: 'AUP',
        partNumber: '',
        function: null,
        inputs: 3,
        gatesPerPackage: 1,
        package: 'SOT-353',
        manufacturers: [],
        equivalents: 0,
        secondSourceCount: 0,
        citation: null,
        unverified: false,
        excluded: true,
        exclusionReason: 'single-sourced',
      },
    ],
    ...over,
  };
}

/* ------------------------------------------------------------------ */
/* Toolchain status                                                    */
/* ------------------------------------------------------------------ */

describe('ToolchainStatusPanel', () => {
  it('shows found tools with version and path, missing tools with their purpose', async () => {
    const fake = new FakeGatepack();
    fake.setOk(
      'doctor',
      doctorReport({
        allToolsPresent: false,
        tools: [
          {
            name: 'yosys',
            direct: true,
            found: true,
            path: '/usr/bin/yosys',
            version: 'Yosys 0.23',
            purpose: 'logic synthesis',
          },
          {
            name: 'sby',
            direct: true,
            found: false,
            path: null,
            version: null,
            purpose: 'formal property checking',
          },
        ],
      }),
    );

    renderPanel(fake, <ToolchainStatusPanel />);

    await waitFor(() => expect(screen.getByTestId('doctor-tool-yosys')).toBeTruthy());
    expect(screen.getByTestId('doctor-tool-yosys')).toHaveAttribute('data-found', 'true');
    expect(screen.getByTestId('doctor-tool-yosys').textContent).toContain('Yosys 0.23');
    expect(screen.getByTestId('doctor-tool-yosys').textContent).toContain('/usr/bin/yosys');

    expect(screen.getByTestId('doctor-tool-sby')).toHaveAttribute('data-found', 'false');
    // the missing tool names what breaks without it
    expect(screen.getByTestId('doctor-tool-sby').textContent).toContain(
      'Missing — formal property checking',
    );

    expect(screen.getByTestId('doctor-overall')).toHaveAttribute('data-all-present', 'false');
  });

  it('surfaces a failure envelope as a clear error, never an empty panel', async () => {
    const fake = new FakeGatepack();
    fake.setError('doctor', {
      severity: 'error',
      code: 'GP9001',
      message: 'gatepack executable not found',
    });

    renderPanel(fake, <ToolchainStatusPanel />);

    await waitFor(() => expect(screen.getByTestId('doctor-error')).toBeTruthy());
    expect(screen.getByTestId('doctor-error').textContent).toContain('gatepack executable not found');
    // no fabricated tools list
    expect(screen.queryByTestId('doctor-tools')).toBeNull();
  });

  it('reports bundled resources, including a missing one as missing', async () => {
    const fake = new FakeGatepack();
    fake.setOk(
      'doctor',
      doctorReport({ resources: { commonFrontendYs: false, mcellModels: true, mcellCount: 4 } }),
    );

    renderPanel(fake, <ToolchainStatusPanel />);

    await waitFor(() => expect(screen.getByTestId('doctor-resource-frontend')).toBeTruthy());
    expect(screen.getByTestId('doctor-resource-frontend')).toHaveAttribute('data-present', 'false');
    expect(screen.getByTestId('doctor-resource-mcell')).toHaveAttribute('data-present', 'true');
  });
});

/* ------------------------------------------------------------------ */
/* Provenance                                                          */
/* ------------------------------------------------------------------ */

describe('ProvenancePanel', () => {
  it('reports coverage measured by the core, without recomputing it', async () => {
    const fake = new FakeGatepack();
    fake.setOk('provenance', provenance({ coverage: 0.5 }));

    renderPanel(fake, <ProvenancePanel />);

    await waitFor(() => expect(screen.getByTestId('provenance-coverage')).toBeTruthy());
    expect(screen.getByTestId('provenance-coverage').textContent).toContain('50.0%');
    expect(screen.getByTestId('provenance-entries')).toBeTruthy();
    expect(screen.getAllByTestId('provenance-entry')).toHaveLength(2);
  });

  it('labels each entry exact or inferred', async () => {
    const fake = new FakeGatepack();
    fake.setOk('provenance', provenance({}));

    renderPanel(fake, <ProvenancePanel />);

    await waitFor(() => expect(screen.getAllByTestId('provenance-entry')).toHaveLength(2));
    const badges = screen.getAllByTestId('provenance-entry').map((el) => {
      const b = el.querySelector('[data-confidence]');
      return b?.getAttribute('data-confidence');
    });
    expect(badges).toContain('exact');
    expect(badges).toContain('inferred');
  });

  it('shows an honest error when nothing was measured', async () => {
    const fake = new FakeGatepack();
    fake.setError('provenance', {
      severity: 'error',
      code: 'GP1003',
      message: 'no captured netlists: run `gatepack build` first',
    });

    renderPanel(fake, <ProvenancePanel />);

    await waitFor(() => expect(screen.getByTestId('provenance-error')).toBeTruthy());
    expect(screen.getByTestId('provenance-error').textContent).toContain('run `gatepack build` first');
  });
});

/* ------------------------------------------------------------------ */
/* Mapped netlist                                                      */
/* ------------------------------------------------------------------ */

describe('MappedNetlistPanel', () => {
  const NETLIST = {
    modules: {
      top: {
        ports: { x: { direction: 'input', bits: [2] }, y: { direction: 'output', bits: [4] } },
        cells: {
          '$abc$148$99$154': {
            type: 'NAND2',
            port_directions: { A: 'input', B: 'input', Y: 'output' },
            connections: { A: [2], B: [3], Y: [4] },
          },
        },
        netnames: { x: { bits: [2] }, n1: { bits: [3] }, y: { bits: [4] } },
      },
    },
  };

  it('labels cell keys as instance names, distinct from stable names', async () => {
    const fake = new FakeGatepack();
    fake.setOk('mappedNetlist', NETLIST);

    renderPanel(fake, <MappedNetlistPanel />);

    await waitFor(() => expect(screen.getByTestId('mapped-netlist-cells')).toBeTruthy());
    // the instance name is shown, and the note names both spaces
    expect(screen.getByText('$abc$148$99$154')).toBeTruthy();
    expect(screen.getByTestId('mapped-netlist-view').textContent).toContain('instance names');
    expect(screen.getByTestId('mapped-netlist-view').textContent).toContain('stable');
  });

  it('shows an honest error when no mapped netlist exists', async () => {
    const fake = new FakeGatepack();
    fake.setError('mappedNetlist', {
      severity: 'error',
      code: 'GP1003',
      message: 'no mapped netlist: run `gatepack build` first',
    });

    renderPanel(fake, <MappedNetlistPanel />);

    await waitFor(() => expect(screen.getByTestId('mapped-netlist-error')).toBeTruthy());
    expect(screen.getByTestId('mapped-netlist-error').textContent).toContain('run `gatepack build` first');
  });
});

/* ------------------------------------------------------------------ */
/* Packed netlist                                                      */
/* ------------------------------------------------------------------ */

describe('PackedNetlistPanel', () => {
  it('keeps stable and instance name spaces visibly distinct', async () => {
    const fake = new FakeGatepack();
    fake.setOk('packedNetlist', packedView());

    renderPanel(fake, <PackedNetlistPanel />);

    await waitFor(() => expect(screen.getByTestId('packed-netlist-packages')).toBeTruthy());

    const panel = screen.getByTestId('packed-netlist-view');
    // both labels exist, and each is followed by the value from the right space
    expect(panel.textContent).toContain('stable cell names');
    expect(panel.textContent).toContain('instance cell names');
    expect(panel.textContent).toContain('NAND2_abc123');
    expect(panel.textContent).toContain('$abc$148$99$154');
  });

  it('shows an honest error when no packed view exists', async () => {
    const fake = new FakeGatepack();
    fake.setError('packedNetlist', {
      severity: 'error',
      code: 'GP1003',
      message: 'no packed view: run `gatepack build` first',
    });

    renderPanel(fake, <PackedNetlistPanel />);

    await waitFor(() => expect(screen.getByTestId('packed-netlist-error')).toBeTruthy());
    expect(screen.getByTestId('packed-netlist-error').textContent).toContain('run `gatepack build` first');
  });
});

/* ------------------------------------------------------------------ */
/* Library                                                             */
/* ------------------------------------------------------------------ */

describe('LibraryPanel', () => {
  it('shows an honest empty state when no library is loaded', async () => {
    const fake = new FakeGatepack({ project: { libraryPath: null } });
    renderPanel(fake, <LibraryPanel />);
    await waitFor(() => expect(screen.getByTestId('library-empty')).toBeTruthy());
  });

  it('checks the loaded library and surfaces citation status per part', async () => {
    const fake = new FakeGatepack({ project: { libraryPath: '/tmp/project/parts.csv' } });
    fake.setOk('checkLibrary', libraryCheck({}));

    renderPanel(fake, <LibraryPanel />);

    await waitFor(() => expect(screen.getByTestId('library-part-INV')).toBeTruthy());

    // the path checked is exactly the one the project loaded
    expect(fake.checkedLibraries).toEqual(['/tmp/project/parts.csv']);

    const status = (cell: string) =>
      screen.getByTestId(`library-part-${cell}`).querySelector('[data-citation]');

    expect(status('INV')?.getAttribute('data-citation')).toBe('verified');
    expect(status('NAND2')?.getAttribute('data-citation')).toBe('unverified');
    expect(status('DFF_S')?.getAttribute('data-citation')).toBe('uncited');
  });

  it('shows a missing citation as a finding, not a hard error', async () => {
    const fake = new FakeGatepack({ project: { libraryPath: '/tmp/project/parts.csv' } });
    fake.setOk('checkLibrary', libraryCheck({ missingCitations: ['DFF_S'], refsPresent: false }));

    renderPanel(fake, <LibraryPanel />);

    await waitFor(() => expect(screen.getByTestId('library-missing-citations')).toBeTruthy());
    expect(screen.getByTestId('library-missing-citations').textContent).toContain('DFF_S');
  });

  it('shows a clear error when the core cannot run the check', async () => {
    const fake = new FakeGatepack({ project: { libraryPath: '/tmp/project/parts.csv' } });
    fake.setError('checkLibrary', {
      severity: 'error',
      code: 'GP9001',
      message: 'gatepack executable not found',
    });

    renderPanel(fake, <LibraryPanel />);

    await waitFor(() => expect(screen.getByTestId('library-error')).toBeTruthy());
    expect(screen.getByTestId('library-error').textContent).toContain('gatepack executable not found');
  });
});

/* ------------------------------------------------------------------ */
/* Examples                                                            */
/* ------------------------------------------------------------------ */

describe('ExamplesPanel', () => {
  it('lists examples with the showcase marked', async () => {
    const fake = new FakeGatepack();
    fake.setOk('listExamples', {
      examples: [
        { name: 'pelican', summary: 'Pelican crossing controller', isShowcase: true },
        { name: 'sync_interlock', summary: 'A synchronised interlock', isShowcase: false },
      ],
    });

    renderPanel(fake, <ExamplesPanel />);

    await waitFor(() => expect(screen.getByTestId('example-pelican')).toBeTruthy());
    expect(screen.getByTestId('example-pelican')).toHaveAttribute('data-showcase', 'true');
    expect(screen.getByTestId('example-sync_interlock')).not.toHaveAttribute('data-showcase');
  });

  it('opens an example through openExample', async () => {
    const fake = new FakeGatepack();
    fake.setOk('listExamples', {
      examples: [{ name: 'pelican', summary: 'Pelican crossing controller', isShowcase: true }],
    });

    renderPanel(fake, <ExamplesPanel />);

    await waitFor(() => expect(screen.getByTestId('example-open-pelican')).toBeTruthy());
    fireEvent.click(screen.getByTestId('example-open-pelican'));

    await waitFor(() => expect(screen.getByTestId('examples-opened')).toBeTruthy());
    expect(fake.openedExamples).toEqual(['pelican']);
  });

  it('shows a clear error when opening an example fails', async () => {
    const fake = new FakeGatepack();
    fake.setOk('listExamples', {
      examples: [{ name: 'pelican', summary: 'Pelican crossing controller', isShowcase: true }],
    });
    fake.setError('openExample', {
      severity: 'error',
      code: 'GP4111',
      message: 'bundled example pelican is not available in this installation',
    });

    renderPanel(fake, <ExamplesPanel />);

    await waitFor(() => expect(screen.getByTestId('example-open-pelican')).toBeTruthy());
    fireEvent.click(screen.getByTestId('example-open-pelican'));

    await waitFor(() => expect(screen.getByTestId('examples-open-error')).toBeTruthy());
    expect(screen.getByTestId('examples-open-error').textContent).toContain('not available');
  });

  it('shows a clear error when the example list cannot be fetched', async () => {
    const fake = new FakeGatepack();
    fake.setError('listExamples', {
      severity: 'error',
      code: 'GP9001',
      message: 'gatepack executable not found',
    });

    renderPanel(fake, <ExamplesPanel />);

    await waitFor(() => expect(screen.getByTestId('examples-error')).toBeTruthy());
    expect(screen.getByTestId('examples-error').textContent).toContain('gatepack executable not found');
  });
});
