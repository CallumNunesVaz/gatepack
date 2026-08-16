/**
 * Loads the pieces linked selection needs from the bridge: `provenance()`,
 * `mappedNetlist()`, `simulate()` and `packedNetlist()`. The first three are
 * optional in the contract and may be absent before a build; an absent result
 * is null, and views render that state honestly rather than fabricating a link
 * context. The `verify()` result is published by the VerificationPanel into
 * `./linkData` (it owns the expensive, revisioned sby run); this hook reads it
 * back so a property selection resolves against the same result the panel
 * showed.
 */

import { useEffect, useMemo, useState } from 'react';
import type { PackedView, ProvenanceMap, SimulationTable, VerifyResult } from '../../shared/api';
import { useApi } from '../bridge/context';
import { useProject } from '../state/project';
import { parseWriteJson, type ParsedNetlist } from '../mapped/sim';
import { getVerifyResult, subscribeVerifyResult } from './linkData';
import type { LinkContext } from './types';

const EMPTY_PROVENANCE: ProvenanceMap = { entries: [], coverage: 0 };

export function useLinkContext(): LinkContext | null {
  const { model } = useProject();
  const api = useApi();
  const [provenance, setProvenance] = useState<ProvenanceMap>(EMPTY_PROVENANCE);
  const [netlist, setNetlist] = useState<ParsedNetlist | null>(null);
  const [simulation, setSimulation] = useState<SimulationTable | null>(null);
  const [packed, setPacked] = useState<PackedView | null>(null);
  const [verify, setVerify] = useState<VerifyResult | null>(getVerifyResult);

  useEffect(() => {
    let cancelled = false;
    api.provenance().then((env) => {
      if (!cancelled && env.ok && env.data) setProvenance(env.data);
    });
    api.mappedNetlist().then((env) => {
      if (!cancelled && env.ok && env.data) setNetlist(parseWriteJson(env.data));
    });
    api.simulate().then((env) => {
      if (!cancelled && env.ok && env.data) setSimulation(env.data);
    });
    api.packedNetlist().then((env) => {
      if (!cancelled && env.ok && env.data) setPacked(env.data);
    });
    const unsubscribe = subscribeVerifyResult(() => setVerify(getVerifyResult()));
    return () => {
      cancelled = true;
      unsubscribe();
    };
  }, [api]);

  const linkContext = useMemo<LinkContext | null>(
    () => (model ? { model, provenance, netlist, simulation, packed, verify } : null),
    [model, provenance, netlist, simulation, packed, verify],
  );
  return linkContext;
}
