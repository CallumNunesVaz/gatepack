import { describe, expect, it } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { ApiProvider } from '../bridge/context';
import { ProjectProvider } from '../state/project';
import { SelectionProvider } from '../selection/bus';
import { setApi } from '../api';
import { FakeGatepack } from '../bridge/fake';
import { BomView } from './BomView';
import type { BuildResult, PackedView } from '../../shared/api';

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
    // As a real build returns: instance name -> stable cone-hash name.
    stableCellNames: {
      g0: 'NOR2__a1b2c3',
      g1: 'NOR2__d4e5f6',
      g2: 'NAND2__99aabb',
    },
    bom: [
      {
        partNumber: '74AUP1G02',
        manufacturers: ['TI', 'Nexperia'],
        package: 'SOT-353',
        quantity: 2,
        refdes: ['U1', 'U2'],
        tier: 'G',
        singleSourced: false,
      gatesPerPackage: 2,
      },
      {
        partNumber: '74AUP1G00',
        manufacturers: ['TI'],
        package: 'SOT-353',
        quantity: 1,
        refdes: ['U3'],
        tier: 'G',
        singleSourced: true,
      gatesPerPackage: 1,
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

function packedView(): PackedView {
  return {
    packages: [
      {
        refdes: 'U1',
        partNumber: '74AUP1G02',
        cells: ['NOR2__a1b2c3', 'NOR2__d4e5f6'],
        instanceCells: ['g0', 'g1'],
        capacity: 2,
        spare: 0,
        rationale: '',
      },
      {
        refdes: 'U2',
        partNumber: '74AUP1G02',
        cells: ['NOR2__a1b2c3'],
        instanceCells: ['g2'],
        capacity: 1,
        spare: 0,
        rationale: '',
      },
    ],
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
        <SelectionProvider>
          <BomView />
        </SelectionProvider>
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

    // A build must have run: it is what supplies the stable-name map.
    fireEvent.click(screen.getByText('Run build'));
    await waitFor(() => expect(screen.getByTestId('single-source-marker')).toBeTruthy());

    fireEvent.dragStart(screen.getByTestId('packing-cell-g0'), {
      dataTransfer: fakeDataTransfer('g0'),
    } as never);
    fireEvent.drop(screen.getByTestId('packing-group-g1'), {
      dataTransfer: fakeDataTransfer('g0'),
    } as never);

    await waitFor(() => expect(fake.specText).toContain('force_groups'));
    // STABLE names must be persisted, never the mapped-netlist instance names:
    // the packer resolves force_groups against stable names, and ABC renumbers
    // instance names on every synthesis, so a persisted `g0` is both refused
    // now and pointing at a different gate later.
    expect(fake.specText).toContain('NOR2__a1b2c3');
    expect(fake.specText).toContain('NOR2__d4e5f6');
    expect(fake.specText).not.toMatch(/force_groups[\s\S]*\bg0\b/);
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

  it('says grouping is inert only when every package holds one gate', async () => {
    // Derived from the BOM the build actually produced, never hardcoded: the
    // library gained multi-gate parts once, and a fixed claim here became a
    // false statement about the user's own design.
    const fake = new FakeGatepack();
    fake.setOk('mappedNetlist', mappedJson());
    const single = buildResult();
    single.bom = single.bom.map((l) => ({ ...l, gatesPerPackage: 1 }));
    fake.setOk('build', single);

    renderBom(fake);

    fireEvent.click(screen.getByText('Run build'));
    await waitFor(() => expect(screen.getByTestId('packing-inert')).toBeTruthy());
    expect(screen.getByTestId('packing-inert').textContent).toContain('inert');
  });

  it('does NOT claim inert when the library offers a multi-gate package', async () => {
    const fake = new FakeGatepack();
    fake.setOk('mappedNetlist', mappedJson());
    fake.setOk('build', buildResult()); // fixture carries a 2-gate part

    renderBom(fake);

    fireEvent.click(screen.getByText('Run build'));
    await waitFor(() => expect(screen.getByTestId('single-source-marker')).toBeTruthy());
    expect(screen.queryByTestId('packing-inert')).toBeNull();
  });

  it('refuses to record an override before a build, rather than writing a name that will be rejected', async () => {
    // The stable-name map comes from the build. Without it the only thing the
    // renderer knows is the ABC instance name, which the packer refuses and
    // which points at a different gate after the next synthesis.
    const fake = new FakeGatepack();
    fake.setOk('mappedNetlist', mappedJson());
    fake.setOk('build', buildResult());

    renderBom(fake);
    await waitFor(() => expect(screen.getByTestId('packing-cell-g0')).toBeTruthy());

    fireEvent.dragStart(screen.getByTestId('packing-cell-g0'), {
      dataTransfer: fakeDataTransfer('g0'),
    } as never);
    fireEvent.drop(screen.getByTestId('packing-group-g1'), {
      dataTransfer: fakeDataTransfer('g0'),
    } as never);

    await waitFor(() => expect(screen.getByTestId('packing-refusal')).toBeTruthy());
    expect(screen.getByTestId('packing-refusal').textContent).toMatch(/run a build/i);
    expect(fake.specText).not.toContain('force_groups');
    expect(fake.specText).not.toContain('g0');
  });

  it('selecting a package refdes highlights it (and it resolves to its cells)', async () => {
    const fake = new FakeGatepack();
    fake.setOk('mappedNetlist', mappedJson());
    fake.setOk('build', buildResult());
    fake.setOk('packedNetlist', packedView());

    renderBom(fake);
    fireEvent.click(screen.getByText('Run build'));
    await waitFor(() => expect(screen.getByTestId('single-source-marker')).toBeTruthy());

    const u1 = screen.getByText('U1');
    expect(u1).not.toHaveAttribute('data-highlight', 'true');

    fireEvent.click(u1);
    await waitFor(() => expect(u1).toHaveAttribute('data-highlight', 'true'));
    // The selection is a refdes token, not a cell: the highlight comes back as
    // the package itself, and the schematic's cells are the instance cells g0/g1.
    expect(u1).toHaveAttribute('data-refdes', 'U1');
  });
});
