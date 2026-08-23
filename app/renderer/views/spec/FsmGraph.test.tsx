import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { ApiProvider } from '../../bridge/context';
import { ProjectProvider } from '../../state/project';
import { SelectionProvider } from '../../selection/bus';
import { setApi } from '../../api';
import { FakeGatepack } from '../../bridge/fake';
import { FsmGraph } from './FsmGraph';

// React Flow subscribes to a ResizeObserver, which jsdom does not provide. A
// minimal stub is enough for the mount/passive-effect paths this test exercises.
class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}

beforeAll(() => {
  (globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = ResizeObserverStub;
});

afterAll(() => {
  delete (globalThis as unknown as { ResizeObserver?: unknown }).ResizeObserver;
});

const SPEC = `name: fsm
timing_model: synchronous
clock: {signal: clk, freq_hz: 1000, source: OSC}
reset: {signal: rst_n, active: low, source: SUPERVISOR}
encoding: one_hot
inputs:
  - {name: go, sync: false}
outputs:
  - {name: out}
states: [A, B]
initial: A
transitions:
  - {from: A, to: B, when: "go"}
output_logic:
  out: "state == B"
`;

describe('FsmGraph — mounts while the spec is still loading', () => {
  it('renders once the spec parses, without a hooks-mismatch crash', async () => {
    // The spec is empty on the first render (model null), then `readSpec`
    // resolves. A `useCallback` that ran *after* the early return used to make
    // the second render run more hooks than the first and React threw
    // "Rendered more hooks than during the previous render".
    const fake = new FakeGatepack({ specText: SPEC });
    setApi(fake);
    render(
      <ApiProvider>
        <ProjectProvider>
          <SelectionProvider>
            <FsmGraph />
          </SelectionProvider>
        </ProjectProvider>
      </ApiProvider>,
    );
    await waitFor(() => expect(screen.getByTestId('fsm-graph')).toBeTruthy());
  });
});
