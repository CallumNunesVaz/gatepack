import { describe, expect, it } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { ApiProvider } from '../bridge/context';
import { ProjectProvider } from '../state/project';
import { setApi } from '../api';
import { FakeGatepack } from '../bridge/fake';
import { BomView } from './BomView';
import type { BuildResult } from '../../shared/api';

function mappedJson(): Record<string, unknown> {
  const cell = (type: string) => ({
    type,
    port_directions: { A: 'input', B: 'input', Y: 'output' },
    connections: {},
  });
  return {
    modules: {
      xor2: {
        cells: { g0: cell('NOR2'), g1: cell('NOR2'), g2: cell('NAND2') },
        netnames: {},
        ports: {},
      },
    },
  };
}

function buildResult(): BuildResult {
  return {
    bomPath: '/out/bom.csv',
    netlistPath: '/out/netlist.net',
    reportPath: '/out/report.md',
    mappedJsonPath: '/out/mapped.json',
    packageCount: 3,
    spareCount: 0,
    packCost: 3,
    bom: [
      {
        partNumber: '74AUP1G02',
        manufacturers: ['TI', 'Nexperia'],
        package: 'SOT-353',
        quantity: 2,
        refdes: ['U1', 'U2'],
        tier: 'G',
        singleSourced: false,
      },
      {
        partNumber: '74AUP1G00',
        manufacturers: ['TI'],
        package: 'SOT-353',
        quantity: 1,
        refdes: ['U3'],
        tier: 'G',
        singleSourced: true,
      },
    ],
    analysis: {
      metrics: [],
      scoap: [],
      faults: { detected: 0, undetected: 0, redundant: 0, untestable: 0 },
      cpldBlockers: [],
    },
  };
}

function fakeDataTransfer(cellName: string) {
  return {
    effectAllowed: 'move',
    dropEffect: 'none',
    getData: () => cellName,
    setData: () => {},
    clearData: () => {},
    types: [],
  } as unknown as DataTransfer;
}

function renderBom(fake: FakeGatepack) {
  setApi(fake);
  return render(
    <ApiProvider>
      <ProjectProvider>
        <BomView />
      </ProjectProvider>
    </ApiProvider>,
  );
}

describe('BomView — C13 packing and BOM', () => {
  it('a drag-regroup writes packing.force_groups and never node positions', async () => {
    const fake = new FakeGatepack();
    fake.setOk('mappedNetlist', mappedJson());
    fake.setOk('build', buildResult());

    renderBom(fake);

    await waitFor(() => expect(screen.getByTestId('packing-cell-g0')).toBeTruthy());
    expect(fake.specText).not.toContain('force_groups');

    fireEvent.dragStart(screen.getByTestId('packing-cell-g0'), {
      dataTransfer: fakeDataTransfer('g0'),
    } as never);
    fireEvent.drop(screen.getByTestId('packing-group-g1'), {
      dataTransfer: fakeDataTransfer('g0'),
    } as never);

    await waitFor(() => expect(fake.specText).toContain('force_groups'));
    expect(fake.specText).toContain('g0');
    expect(fake.specText).toContain('g1');
    expect(fake.specText).not.toContain('position');
    expect(fake.specText).not.toContain('layout');
  });

  it('surfaces a mixed-function refusal and does not write an override', async () => {
    const fake = new FakeGatepack();
    fake.setOk('mappedNetlist', mappedJson());
    fake.setOk('build', buildResult());

    renderBom(fake);

    await waitFor(() => expect(screen.getByTestId('packing-cell-g0')).toBeTruthy());

    fireEvent.dragStart(screen.getByTestId('packing-cell-g0'), {
      dataTransfer: fakeDataTransfer('g0'),
    } as never);
    fireEvent.drop(screen.getByTestId('packing-group-g2'), {
      dataTransfer: fakeDataTransfer('g0'),
    } as never);

    await waitFor(() => expect(screen.getByTestId('packing-refusal')).toBeTruthy());
    expect(screen.getByTestId('packing-refusal').textContent).toContain('not the same function');
    expect(fake.specText).not.toContain('force_groups');
  });

  it('marks exactly the single-sourced parts, and not the dual-sourced ones', async () => {
    const fake = new FakeGatepack();
    fake.setOk('mappedNetlist', mappedJson());
    fake.setOk('build', buildResult());

    renderBom(fake);

    fireEvent.click(screen.getByText('Run build'));
    await waitFor(() => expect(screen.getByTestId('single-source-marker')).toBeTruthy());

    const markers = screen.getAllByTestId('single-source-marker');
    expect(markers).toHaveLength(1);
    expect(markers[0].textContent).toContain('SINGLE-SOURCE');

    const rows = screen.getAllByRole('row').filter((r) => r.querySelector('td'));
    const singleRows = rows.filter((r) => r.getAttribute('data-single-sourced') === 'true');
    expect(singleRows).toHaveLength(1);
    expect(singleRows[0].textContent).toContain('74AUP1G00');
  });

  it('says plainly that grouping is inert for this library', async () => {
    const fake = new FakeGatepack();
    fake.setOk('mappedNetlist', mappedJson());
    fake.setOk('build', buildResult());

    renderBom(fake);

    await waitFor(() => expect(screen.getByTestId('packing-inert')).toBeTruthy());
    expect(screen.getByTestId('packing-inert').textContent).toContain('inert');
  });
});
