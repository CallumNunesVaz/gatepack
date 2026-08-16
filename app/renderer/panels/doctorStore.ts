/**
 * A tiny module-scoped store for the `doctor()` report, published by the
 * Toolchain Status panel and read by the shell's status-bar toolchain
 * indicator (a slot the shell agent owns — this is the hand-off, so the shell
 * never has to spawn the core a second time).
 *
 * Mirrors `selection/linkData.ts`: no provider wrapper, so a panel can publish
 * without touching App.tsx.
 */

import type { DoctorReport } from '../../shared/api';

type Listener = () => void;

let report: DoctorReport | null = null;
const listeners = new Set<Listener>();

export function getDoctorReport(): DoctorReport | null {
  return report;
}

export function setDoctorReport(next: DoctorReport | null): void {
  report = next;
  for (const listener of listeners) listener();
}

export function subscribeDoctorReport(listener: Listener): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}
