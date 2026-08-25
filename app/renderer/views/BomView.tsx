import { useCallback, useEffect, useMemo, useState } from 'react';
import { useApi } from '../bridge/context';
import { useProject } from '../state/project';
import { useRevisionedTask } from '../hooks/useRevisionedTask';
import { useRunRequest } from '../shell/runRequests';
import { setPackingForceGroups } from '../design/model';
import { parseWriteJson } from '../mapped/sim';
import { useLinkContext } from '../selection/useLinkContext';
import { useHighlights, useSelection } from '../selection/bus';
import {
  buildGroups,
  groupsToForceGroups,
  regroup,
  type PackingCell,
} from '../components/packing';
import { PackingCards } from '../components/PackingCards';
import { Icon, Tooltip } from '../ui';
import { ActionButton } from './kit';
import { nextDir, sortBomLines, type BomSortKey, type SortDir } from './bomSort';
import {
  requestBuildStateReload,
  setBuildRevision,
  setBuildRunning,
} from '../state/buildState';
import { VIEW_BLOCKS } from '../shell/pipeline';
import type { BuildResult } from '../../shared/api';
import './views.css';

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
 * regroup is refused with a message rather than silently dropped. The BOM table
 * is sortable; the sort only re-orders rows the core produced, it never
 * recomputes a value.
 */
export function BomView() {
  const { model, specText, editSpec, revision } = useProject();
  const api = useApi();
  const build = useRevisionedTask<BuildResult>(revision, (t) => api.build(t));
  useRunRequest('run.build', build.run);
  const ctx = useLinkContext();
  const { setSelection } = useSelection();
  const highlights = useHighlights(ctx);

  const [cells, setCells] = useState<PackingCell[] | null>(null);
  const [refusal, setRefusal] = useState<string | null>(null);
  const [netlistVersion, setNetlistVersion] = useState(0);
  const [sort, setSort] = useState<{ key: BomSortKey; dir: SortDir }>({
    key: 'partNumber',
    dir: 'asc',
  });

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

  // Publish the build's progress to the pipeline strip. The build-finished
  // reload signal is what keeps the strip from lying for the rest of the
  // session; every site that runs `api.build()` must fire it.
  useEffect(() => {
    setBuildRunning(build.state.status === 'running');
    if (build.state.status === 'success') {
      requestBuildStateReload();
      if (build.state.revision !== null) setBuildRevision(build.state.revision);
    }
  }, [build.state.status, build.state.revision]);

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

      // The same rule, applied per cell rather than to the map as a whole. An
      // empty map was already refused above; a *partial* one fell through here
      // and `?? name` wrote the instance name for whichever cell was missing —
      // the exact outcome the comment above says is not an option. Proven
      // reachable with a map covering one of two gates.
      const next: string[][] = [];
      for (const group of groupsToForceGroups(result.groups)) {
        const mapped: string[] = [];
        for (const name of group) {
          const stableName = stable[name];
          if (stableName === undefined) {
            setRefusal(
              `${name} is not in this build's cell map, so it has no stable ` +
                'name to record — rebuild before regrouping.',
            );
            return;
          }
          mapped.push(stableName);
        }
        next.push(mapped);
      }
      editSpec((current) => setPackingForceGroups(current, next).text);
    },
    [groups, specText, editSpec, build.state],
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

  const sortedBom = useMemo(
    () => (data ? sortBomLines(data.bom, sort.key, sort.dir) : []),
    [data, sort],
  );

  const onSort = (key: BomSortKey) =>
    setSort((s) =>
      s.key === key ? { key, dir: nextDir(s.dir) } : { key, dir: 'asc' },
    );

  return (
    <section className="pane" data-testid="bom-view">
      <header className="pane__header">
        <h2>Packing &amp; BOM</h2>
        <ActionButton
          icon="build"
          label="Run build"
          busyLabel="Building"
          busy={build.state.status === 'running'}
          onClick={build.run}
          primary
        />
      </header>
      {build.isStale ? <div className="stale-note">Stale — the source has changed.</div> : null}

      {cells === null ? (
        <div className="gp-empty" data-testid="bom-empty">
          <Icon name="packing" size={30} decorative />
          <p className="gp-empty__title">{VIEW_BLOCKS.packing.note}</p>
        </div>
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
          <div className="bom-stats" data-testid="packing-stats">
            <div className="bom-stat">
              <span className="bom-stat__label">
                <Tooltip content="Physical packages the packer produced">
                  <span>Packages</span>
                </Tooltip>
              </span>
              <strong className="bom-stat__value">{data.packageCount}</strong>
            </div>
            <div className="bom-stat">
              <span className="bom-stat__label">
                <Tooltip content="Unused gates across all packages">
                  <span>Spares</span>
                </Tooltip>
              </span>
              <strong className="bom-stat__value">{data.spareCount}</strong>
            </div>
            <div className="bom-stat">
              <span className="bom-stat__label">
                <Tooltip content="Package cost reported by the core">
                  <span>pack_cost</span>
                </Tooltip>
              </span>
              <strong className="bom-stat__value">{data.packCost}</strong>
            </div>
          </div>

          <div className="view-grid">
            <table>
              <thead>
                <tr>
                  <SortableTh label="Part" sortKey="partNumber" sort={sort} onSort={onSort} />
                  <SortableTh label="Qty" sortKey="quantity" sort={sort} onSort={onSort} />
                  <SortableTh label="Package" sortKey="package" sort={sort} onSort={onSort} />
                  <th scope="col">Refdes</th>
                  <SortableTh
                    label="Gates/pkg"
                    sortKey="gatesPerPackage"
                    sort={sort}
                    onSort={onSort}
                    tooltip="Gates one package holds — whether packing can spare a gate"
                  />
                  <SortableTh label="Mfrs" sortKey="manufacturers" sort={sort} onSort={onSort} />
                </tr>
              </thead>
              <tbody>
                {sortedBom.map((line) => (
                  <tr
                    key={line.partNumber}
                    className={line.singleSourced ? 'row--single-sourced' : ''}
                    data-single-sourced={line.singleSourced || undefined}
                  >
                    <td className="mono">
                      {line.partNumber}
                      {line.singleSourced ? (
                        <span className="single-source-marker" data-testid="single-source-marker">
                          <Icon name="warning" size={12} decorative />
                          SINGLE-SOURCE
                        </span>
                      ) : null}
                    </td>
                    <td className="num">{line.quantity}</td>
                    <td className="mono">{line.package}</td>
                    <td>
                      {line.refdes.map((ref) => (
                        <button
                          key={ref}
                          type="button"
                          className={highlights.packages.includes(ref) ? 'refdes refdes--highlight' : 'refdes'}
                          data-refdes={ref}
                          data-highlight={highlights.packages.includes(ref) || undefined}
                          onClick={() => setSelection({ kind: 'package', refdes: ref })}
                        >
                          {ref}
                        </button>
                      ))}
                    </td>
                    <td className="num">{line.gatesPerPackage}</td>
                    <td>{line.manufacturers.join('; ')}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : null}
    </section>
  );
}

function SortableTh({
  label,
  sortKey,
  sort,
  onSort,
  tooltip,
}: {
  label: string;
  sortKey: BomSortKey;
  sort: { key: BomSortKey; dir: SortDir };
  onSort: (key: BomSortKey) => void;
  tooltip?: string;
}) {
  const active = sort.key === sortKey;
  return (
    <th
      scope="col"
      className="sortable"
      aria-sort={active ? (sort.dir === 'asc' ? 'ascending' : 'descending') : 'none'}
    >
      <button type="button" className="view-sort" onClick={() => onSort(sortKey)}>
        {label}
        <span className="sort-indicator">
          <Icon name="chevronDown" size={12} decorative />
        </span>
      </button>
      {tooltip ? (
        <Tooltip content={tooltip}>
          <span className="th-info" tabIndex={0} role="img" aria-label={tooltip}>
            <Icon name="info" size={12} decorative />
          </span>
        </Tooltip>
      ) : null}
    </th>
  );
}
