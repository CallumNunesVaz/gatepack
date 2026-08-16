import { rationaleFor, type PackingGroup } from './packing';

export interface PackingCardsProps {
  groups: PackingGroup[];
  /** True when the library makes grouping inert (every part is one gate/package). */
  inert: boolean;
  /** The last rejected regroup's message, or null. */
  refusal: string | null;
  onRegroup: (cellName: string, targetGroupId: string) => void;
  onDragStart?: () => void;
}

const CELL_MIME = 'text/packing-cell';

/**
 * §C13 — package groupings as cards, with drag-to-regroup. Each card is one
 * group of mapped cells; dragging a cell chip onto another card asks the parent
 * to regroup it (which rejects mixed-function moves and otherwise persists the
 * override). The cards are a pure rendering + drag transport: all decisions
 * live in `packing.ts` and the parent view.
 */
export function PackingCards({ groups, inert, refusal, onRegroup, onDragStart }: PackingCardsProps) {
  return (
    <div className="packing" data-testid="packing-cards">
      {refusal ? (
        <div className="error-note" data-testid="packing-refusal" role="alert">
          {refusal}
        </div>
      ) : null}

      {inert ? (
        <div className="stale-note" data-testid="packing-inert">
          Grouping is inert for the shipped 74AUP library: every part is one gate
          per package, so packed = unpacked and a spare gate cannot exist.
          Regrouping records a <code>packing.force_groups</code> preference in
          design.yaml but changes no cost here.
        </div>
      ) : null}

      <div className="packing__cards">
        {groups.map((g) => (
          <article
            key={g.id}
            className="pack-group"
            data-testid={`packing-group-${g.id}`}
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => {
              e.preventDefault();
              const name = e.dataTransfer.getData(CELL_MIME);
              if (name) onRegroup(name, g.id);
            }}
          >
            <header className="pack-group__head">
              <span className="pack-group__func" data-testid={`packing-func-${g.id}`}>
                {g.func || '?'}
              </span>
              <span className="pack-group__count">{g.cells.length} gate{g.cells.length === 1 ? '' : 's'}</span>
              {g.forced ? (
                <span className="pack-group__forced" data-testid={`packing-forced-${g.id}`}>
                  forced group
                </span>
              ) : null}
            </header>
            <div className="pack-group__rationale">{rationaleFor(g)}</div>
            <div className="pack-group__cells">
              {g.cells.map((c) => (
                <span
                  key={c}
                  className="pack-cell"
                  draggable
                  data-testid={`packing-cell-${c}`}
                  onDragStart={(e) => {
                    e.dataTransfer.setData(CELL_MIME, c);
                    e.dataTransfer.effectAllowed = 'move';
                    onDragStart?.();
                  }}
                >
                  {c}
                </span>
              ))}
            </div>
          </article>
        ))}
      </div>
    </div>
  );
}
