/**
 * Loads the pieces linked selection needs from the bridge: `provenance()`,
 * `mappedNetlist()` and `simulate()`. All three are optional in the contract
 * and may be absent before a build; an absent result is null, and views render
 * that state honestly rather than fabricating a link context.
 */

import { useEffect, useMemo, useState } from 'react';
import type { ProvenanceMap, SimulationTable } from '../../shared/api';
import { useApi } from '../bridge/context';
import { useProject } from '../state/project';
import { parseWriteJson, type ParsedNetlist } from '../mapped/sim';
import type { LinkContext } from './types';

const EMPTY_PROVENANCE: ProvenanceMap = { entries: [], coverage: 0 };

export function useLinkContext(): LinkContext | null {
  const { model } = useProject();
  const api = useApi();
  const [provenance, setProvenance] = useState<ProvenanceMap>(EMPTY_PROVENANCE);
  const [netlist, setNetlist] = useState<ParsedNetlist | null>(null);
  const [simulation, setSimulation] = useState<SimulationTable | null>(null);

  useEffect(() => {
    let cancelled = false;
    api.provenance().then((env) => {
      if (!cancelled && env.ok) setProvenance(env.data);
    });
    api.mappedNetlist().then((env) => {
      if (!cancelled && env.ok) setNetlist(parseWriteJson(env.data));
    });
    api.simulate().then((env) => {
      if (!cancelled && env.ok) setSimulation(env.data);
    });
    return () => {
      cancelled = true;
    };
  }, [api]);

  const linkContext = useMemo<LinkContext | null>(
    () => (model ? { model, provenance, netlist, simulation } : null),
    [model, provenance, netlist, simulation],
  );
  return linkContext;
}
