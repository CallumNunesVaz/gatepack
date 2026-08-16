import { useCallback, useEffect, useMemo, useState } from 'react';
import { useApi } from '../bridge/context';
import { useProject } from '../state/project';
import { useRevisionedTask } from '../hooks/useRevisionedTask';
import { setPackingForceGroups } from '../design/model';
import { parseWriteJson } from '../mapped/sim';
import {
  buildGroups,
  groupsToForceGroups,
  regroup,
  type PackingCell,
} from '../components/packing';
import { PackingCards } from '../components/PackingCards';
import type { BuildResult } from '../../shared/api';

/**
 * C13 — packing and BOM.
 *
 * Package groupings as cards with drag-to-regroup; live (honestly inert) cost
 * readout; the adjacent BOM table with a hard marker on single-sourced parts.
 * Overrides persist to `design.yaml` via `packing.force_groups` — the text is
 * authoritative, as everywhere else.
 *
 * Two honesty requirements are honoured here: grouping is inert for the shipped
 * 74AUP library (every part is one gate per package), and a mixed-function
 * regroup is refused with a message rather than silently dropped.
 */
export function BomView() {
  const { model, specText, setSpecText, revision } = useProject();
  const api = useApi();
  const build = useRevisionedTask<BuildResult>(revision, (t) => api.build(t));

  const [cells, setCells] = useState<PackingCell[] | null>(null);
  const [refusal, setRefusal] = useState<string | null>(null);
  const [netlistVersion, setNetlistVersion] = useState(0);

  useEffect(() => {
    let cancelled = false;
    api.mappedNetlist().then((env) => {
      if (cancelled || !env.ok) return;
      const parsed = parseWriteJson(env.data);
      if (parsed.top === '') {
        setCells(null);
      } else {
        setCells(parsed.cells.map((c) => ({ name: c.name, func: c.type })));
      }
    });
    return () => {
      cancelled = true;
    };
  }, [api, netlistVersion]);

  // The mapped netlist only exists after a build; refetch once one lands.
  useEffect(() => {
    if (build.state.status === 'success') setNetlistVersion((v) => v + 1);
  }, [build.state.status]);

  const forceGroups = model?.packing.forceGroups ?? [];
  const groups = useMemo(
    () => (cells ? buildGroups(cells, forceGroups) : []),
    [cells, forceGroups],
  );

  const handleRegroup = useCallback(
    (cellName: string, targetGroupId: string) => {
      const result = regroup(groups, cellName, targetGroupId);
      if (result.error) {
        setRefusal(result.error);
        return;
      }
      setRefusal(null);

      // Translate to STABLE names before persisting. `force_groups` is
      // resolved by the packer against stable cone-hash names; everything the
      // renderer sees from `mappedNetlist()` is an ABC instance name
      // (`$abc$148$...$154`) which is renumbered by every synthesis. Writing
      // one into design.yaml is refused on the next build — and would point at
      // a *different gate* if it were not.
      const stable: Record<string, string> =
        build.state.status === 'success' && build.state.data
          ? build.state.data.stableCellNames
          : {};

      // Without the map there is nothing safe to write. Persisting the
      // instance name is not a lesser option: the packer refuses it on the
      // next build, and if it did not it would name a different gate. Say so
      // rather than writing something that quietly fails later.
      if (Object.keys(stable).length === 0) {
        setRefusal(
          'Run a build before regrouping — an override recorded now would name ' +
            'gates that do not survive the next synthesis.',
        );
        return;
      }

      const next = groupsToForceGroups(result.groups).map((group) =>
        group.map((name) => stable[name] ?? name),
      );
      const { text } = setPackingForceGroups(specText, next);
      setSpecText(text);
    },
    [groups, specText, setSpecText, build.state],
  );

  const data = build.state.status === 'success' ? build.state.data : null;

  // Whether grouping can achieve anything at all, derived from the library the
  // build actually used rather than asserted. Every part being one gate per
  // package makes packed === unpacked by construction; the moment the library
  // gains a dual-gate part that stops being true, and a hardcoded claim here
  // becomes a false statement about the user's own design.
  const inert =
    data !== null && data.bom.length > 0
      ? data.bom.every((line) => line.gatesPerPackage <= 1)
      : false;

  return (
    <section className="pane" data-testid="bom-view">
      <header className="pane__header">
        <h2>Packing &amp; BOM</h2>
        <button onClick={build.run} disabled={build.state.status === 'running'}>
          {build.state.status === 'running' ? 'Building…' : 'Run build'}
        </button>
      </header>
      {build.isStale ? <div className="stale-note">Stale — the source has changed.</div> : null}

      {cells === null ? (
        <p className="pane__empty">Run a build to see the mapped cells and BOM.</p>
      ) : (
        <PackingCards
          groups={groups}
          inert={inert}
          refusal={refusal}
          onRegroup={handleRegroup}
          onDragStart={() => setRefusal(null)}
        />
      )}

      {data ? (
        <div className="bom">
          <div className="stat-row" data-testid="packing-stats">
            <span>Packages</span>
            <strong>{data.packageCount}</strong>
            <span>Spares</span>
            <strong>{data.spareCount}</strong>
            <span>pack_cost</span>
            <strong>{data.packCost}</strong>
          </div>
          <table className="data-table">
            <thead>
              <tr>
                <th>Part</th>
                <th>Qty</th>
                <th>Package</th>
                <th>Refdes</th>
                <th>Mfrs</th>
              </tr>
            </thead>
            <tbody>
              {data.bom.map((line) => (
                <tr
                  key={line.partNumber}
                  className={line.singleSourced ? 'row--single-sourced' : ''}
                  data-single-sourced={line.singleSourced || undefined}
                >
                  <td>
                    {line.partNumber}
                    {line.singleSourced ? (
                      <span className="single-source-marker" data-testid="single-source-marker">
                        SINGLE-SOURCE
                      </span>
                    ) : null}
                  </td>
                  <td>{line.quantity}</td>
                  <td>{line.package}</td>
                  <td>{line.refdes.join(', ')}</td>
                  <td>{line.manufacturers.join('; ')}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </section>
  );
}
