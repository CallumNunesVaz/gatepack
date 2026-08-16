import { describe, expect, it } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { ApiProvider } from '../bridge/context';
import { ProjectProvider } from '../state/project';
import { setApi } from '../api';
import { FakeGatepack } from '../bridge/fake';
import { AnalysisView } from './AnalysisView';
import type { AnalysisSummary, EstimateResult } from '../../shared/api';

function summary(over: Partial<AnalysisSummary>): AnalysisSummary {
  return {
    metrics: [],
    scoap: [],
    faults: { detected: 0, undetected: 0, redundant: 0, untestable: 0 },
    cpldBlockers: [],
    ...over,
  };
}

function estimateResult(verdict: EstimateResult['verdict']): EstimateResult {
  return {
    verdict,
    reasons: verdict === 'red' ? ['package count is red'] : [],
    packageCount: 3,
    flopCount: 2,
    cellCounts: { NOR2: 3 },
    alternative: verdict === 'red' ? 'flash CPLD (e.g. MAX V)' : null,
  };
}

function renderAnalysis(fake: FakeGatepack) {
  setApi(fake);
  return render(
    <ApiProvider>
      <ProjectProvider>
        <AnalysisView />
      </ProjectProvider>
    </ApiProvider>,
  );
}

describe('AnalysisView — C14 dashboard', () => {
  it('renders a violated constraint red and a met one not', async () => {
    const fake = new FakeGatepack();
    fake.setOk(
      'analyse',
      summary({
        metrics: [
          { name: 'package count', value: 12, unit: 'packages', limit: 10, violated: true },
          { name: 'flop count', value: 2, unit: 'flops', limit: 8, violated: false },
        ],
      }),
    );
    fake.setOk('estimate', estimateResult('green'));

    renderAnalysis(fake);
    fireEvent.click(screen.getByText('Run analysis'));

    await waitFor(() => expect(screen.getByTestId('metric-package count')).toBeTruthy());

    const violated = screen.getByTestId('metric-package count');
    expect(violated).toHaveAttribute('data-violated', 'true');
    expect(violated.className).toContain('metric--violated');

    const met = screen.getByTestId('metric-flop count');
    expect(met).not.toHaveAttribute('data-violated');
    expect(met.className).not.toContain('metric--violated');
  });

  it('renders the four fault classes distinguishably, not as a percentage', async () => {
    const fake = new FakeGatepack();
    fake.setOk(
      'analyse',
      summary({ faults: { detected: 3, undetected: 1, redundant: 0, untestable: 2 } }),
    );
    fake.setOk('estimate', estimateResult('green'));

    renderAnalysis(fake);
    fireEvent.click(screen.getByText('Run analysis'));

    await waitFor(() => expect(screen.getByTestId('fault-detected')).toBeTruthy());

    expect(screen.getByTestId('fault-detected').textContent).toContain('3');
    expect(screen.getByTestId('fault-undetected').textContent).toContain('1');
    expect(screen.getByTestId('fault-redundant').textContent).toContain('0');
    expect(screen.getByTestId('fault-untestable').textContent).toContain('2');

    // The four are distinct findings, each carrying its own label and note.
    const keys = ['detected', 'undetected', 'redundant', 'untestable'];
    for (const key of keys) {
      expect(screen.getByTestId(`fault-${key}`)).toHaveAttribute('data-fault', key);
    }
    expect(screen.getByTestId('fault-redundant').textContent).toContain('no test can exist');
    expect(screen.getByTestId('fault-undetected').textContent).toContain('gap in the vectors');
    // no single percentage collapsing the four
    expect(screen.queryByText(/%/)).toBeNull();
  });

  it('renders the §6 verdict with its alternative on red', async () => {
    const fake = new FakeGatepack();
    fake.setOk('analyse', summary({}));
    fake.setOk('estimate', estimateResult('red'));

    renderAnalysis(fake);
    fireEvent.click(screen.getByText('Run analysis'));

    await waitFor(() => expect(screen.getByTestId('verdict')).toBeTruthy());
    expect(screen.getByTestId('verdict')).toHaveAttribute('data-verdict', 'red');
    expect(screen.getByTestId('verdict-alternative').textContent).toContain('CPLD');
  });

  it('shows an honest empty state for SCOAP when no netlist produced it', async () => {
    const fake = new FakeGatepack();
    fake.setOk('analyse', summary({ scoap: [] }));
    fake.setOk('estimate', estimateResult('green'));

    renderAnalysis(fake);
    fireEvent.click(screen.getByText('Run analysis'));

    await waitFor(() => expect(screen.getByText(/No SCOAP data/)).toBeTruthy());
  });

  it('labels each metric band from the core violated flag, never a recomputed verdict', async () => {
    const fake = new FakeGatepack();
    fake.setOk(
      'analyse',
      summary({
        metrics: [
          { name: 'package count', value: 12, unit: 'packages', limit: 10, violated: true },
          { name: 'flop count', value: 2, unit: 'flops', limit: 8, violated: false },
        ],
      }),
    );
    fake.setOk('estimate', estimateResult('green'));

    renderAnalysis(fake);
    fireEvent.click(screen.getByText('Run analysis'));

    await waitFor(() => expect(screen.getByTestId('metric-package count')).toBeTruthy());
    expect(screen.getByTestId('metric-package count')).toHaveTextContent('violated');
    expect(screen.getByTestId('metric-flop count')).toHaveTextContent('met');
  });
});
