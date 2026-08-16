/**
 * The panel host — the seam that makes `inspect.*` and `project.examples`
 * reachable. These tests pin that the handlers are actually *mounted* (a
 * command that dispatches to nothing fails here), and that the dialog is
 * keyboard-dismissible and returns focus to the element that invoked it.
 */

import { describe, expect, it } from 'vitest';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { ApiProvider } from '../bridge/context';
import { setApi } from '../api';
import { FakeGatepack } from '../bridge/fake';
import { createCommandBus, CommandBusProvider } from './commands';
import { PanelHost } from './PanelHost';
import { PANEL_COMMANDS } from '../panels';
import type { DoctorReport } from '../../shared/api';

function doctorReport(): DoctorReport {
  return {
    allToolsPresent: true,
    tools: [
      {
        name: 'yosys',
        direct: true,
        found: true,
        path: '/usr/bin/yosys',
        version: 'Yosys 0.23',
        purpose: 'logic synthesis',
      },
    ],
    resources: { commonFrontendYs: true, mcellModels: true, mcellCount: 4 },
  };
}

function renderHost(fake: FakeGatepack) {
  const bus = createCommandBus();
  setApi(fake);
  render(
    <ApiProvider>
      <CommandBusProvider bus={bus}>
        <button data-testid="origin">origin</button>
        <PanelHost />
      </CommandBusProvider>
    </ApiProvider>,
  );
  return bus;
}

describe('PanelHost', () => {
  it('registers a mounted handler for every panel command', () => {
    const bus = createCommandBus();
    render(
      <CommandBusProvider bus={bus}>
        <PanelHost />
      </CommandBusProvider>,
    );
    for (const { id } of PANEL_COMMANDS) {
      expect(bus.isRegistered(id), `${id} is registered`).toBe(true);
    }
  });

  it('opens a panel on dispatch instead of reporting "not wired"', async () => {
    const fake = new FakeGatepack();
    fake.setOk('doctor', doctorReport());
    const bus = renderHost(fake);

    act(() => {
      bus.dispatch('inspect.doctor');
    });

    await waitFor(() => expect(screen.getByTestId('doctor-view')).toBeTruthy());
    expect(screen.getByTestId('panel-host')).toBeTruthy();
  });

  it('is keyboard-dismissible and returns focus to the invoking element', async () => {
    const fake = new FakeGatepack();
    fake.setOk('doctor', doctorReport());
    const bus = renderHost(fake);
    const origin = screen.getByTestId('origin');
    origin.focus();
    expect(document.activeElement).toBe(origin);

    act(() => {
      bus.dispatch('inspect.doctor');
    });
    await waitFor(() => expect(screen.getByTestId('doctor-view')).toBeTruthy());
    expect(document.activeElement).toBe(screen.getByTestId('panel-host'));

    fireEvent.keyDown(screen.getByTestId('panel-host'), { key: 'Escape' });
    expect(screen.queryByTestId('panel-host')).toBeNull();
    expect(document.activeElement).toBe(origin);
  });

  it('dismisses via the close button', async () => {
    const fake = new FakeGatepack();
    fake.setOk('doctor', doctorReport());
    const bus = renderHost(fake);

    act(() => {
      bus.dispatch('inspect.doctor');
    });
    await waitFor(() => expect(screen.getByTestId('doctor-view')).toBeTruthy());

    fireEvent.click(screen.getByTestId('panel-host-close'));
    expect(screen.queryByTestId('panel-host')).toBeNull();
  });
});
