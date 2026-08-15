import { useMemo, useState } from 'react';
import ReactFlow, {
  Background,
  Controls,
  MarkerType,
  type Edge,
  type Node,
} from 'reactflow';
import { useProject } from '../../state/project';
import { createLocalStorageLayoutStore, type LayoutMap } from '../../design/layout';
import { applyTopLevelEdit, renameState, type Transition } from '../../design/model';
import { useHighlights, useSelection } from '../../selection/bus';
import { useLinkContext } from '../../selection/useLinkContext';
import { SelectionBadge } from '../../selection/SelectionBadge';

/**
 * FSM graph (React Flow): states are nodes, transitions are labelled edges. A
 * graph edit is a *document mutation* — it produces new YAML text, which is what
 * is saved. Node positions are cosmetic and live in the gitignored sidecar
 * store, never in the YAML.
 *
 * Selecting a node/edge emits a §15.2 selection; the same selection reflected
 * back from another view (a truth-table row, a schematic gate) highlights the
 * matching nodes/edges here. A transition whose provenance has no surviving
 * link renders its "no exact link" state instead of silently highlighting
 * nothing.
 */
export function FsmGraph() {
  const { specText, model, setSpecText, project } = useProject();
  const { selection, setSelection } = useSelection();
  const ctx = useLinkContext();
  const highlights = useHighlights(ctx);
  const [positions, setPositions] = useState<LayoutMap>(() => {
    const store = createLocalStorageLayoutStore(project?.path ?? '');
    return store.load();
  });

  const store = useMemo(
    () => createLocalStorageLayoutStore(project?.path ?? ''),
    [project?.path],
  );

  if (!model) {
    return <div className="pane__empty">The spec does not parse yet.</div>;
  }

  const nodes: Node[] = model.states.map((state, i) => ({
    id: state,
    position: positions[state] ?? { x: i * 180, y: 0 },
    data: { label: state },
    className: highlights.states.includes(state) ? 'fsm-node--highlight' : undefined,
    style:
      state === model.initial
        ? { border: '2px solid #4c9ffe' }
        : highlights.states.includes(state)
          ? { border: '2px solid #23a55a' }
          : undefined,
  }));

  const edges: Edge[] = model.transitions.map((t, i) => ({
    id: `e${i}`,
    source: t.from,
    target: t.to,
    label: t.when,
    type: 'default',
    markerEnd: { type: MarkerType.ArrowClosed },
    className: highlights.transitions.includes(i) ? 'fsm-edge--highlight' : undefined,
    style: highlights.transitions.includes(i) ? { stroke: '#23a55a', strokeWidth: 2 } : undefined,
  }));

  const onNodeDragStop = (_event: unknown, node: Node) => {
    const next = { ...positions, [node.id]: { x: node.position.x, y: node.position.y } };
    setPositions(next);
    store.save(next);
  };

  const setTransitions = (transitions: Transition[]) => {
    const { text } = applyTopLevelEdit(specText, 'transitions', () =>
      transitions.map((t) => ({ from: t.from, to: t.to, when: t.when })),
    );
    setSpecText(text);
  };

  const updateEdge = (index: number, patch: Partial<Transition>) => {
    setTransitions(model.transitions.map((t, i) => (i === index ? { ...t, ...patch } : t)));
  };

  const addState = () => {
    const name = `S${model.states.length}`;
    const { text } = applyTopLevelEdit(specText, 'states', () => [...model!.states, name]);
    setSpecText(text);
  };

  const addTransition = () => {
    const from = model.initial ?? model.states[0];
    const to = model.states[0] ?? from;
    setTransitions([...model.transitions, { from, to, when: '1' }]);
  };

  const selectedTransitionIndex =
    selection?.kind === 'transition'
      ? model.transitions.findIndex((t) => t.from === selection.from && t.to === selection.to)
      : -1;
  const selectedTransition = selectedTransitionIndex >= 0 ? model.transitions[selectedTransitionIndex] : null;
  const selectedState = selection?.kind === 'state' ? selection.id : null;

  return (
    <div className="fsm" data-testid="fsm-graph">
      <div className="fsm__toolbar">
        <button onClick={addState}>+ state</button>
        <button onClick={addTransition}>+ transition</button>
      </div>
      <div className="fsm-graph">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodeClick={(_e, node) => setSelection({ kind: 'state', id: node.id })}
          onEdgeClick={(_e, edge) => {
            const index = Number(edge.id.slice(1));
            const t = model.transitions[index];
            if (t) setSelection({ kind: 'transition', from: t.from, to: t.to });
          }}
          onPaneClick={() => setSelection(null)}
          onNodeDragStop={onNodeDragStop}
          fitView
        >
          <Background />
          <Controls />
        </ReactFlow>
      </div>
      {selectedTransition ? (
        <div className="fsm__inspector" data-testid="transition-inspector">
          <strong>transition</strong>
          <SelectionBadge confidence={highlights.confidence} />
          <span>
            {selectedTransition.from} →{' '}
            <select
              value={selectedTransition.to}
              onChange={(e) => updateEdge(selectedTransitionIndex, { to: e.target.value })}
            >
              {model.states.map((s) => (
                <option key={s} value={s}>{s}</option>
              ))}
            </select>
          </span>
          <span>
            when{' '}
            <input
              value={selectedTransition.when}
              onChange={(e) => updateEdge(selectedTransitionIndex, { when: e.target.value })}
              aria-label="transition guard"
            />
          </span>
          {highlights.nets.length || highlights.cells.length ? (
            <span className="link-list">
              nets {highlights.nets.join(', ') || '(none)'} · cells {highlights.cells.join(', ') || '(none)'}
            </span>
          ) : null}
        </div>
      ) : null}
      {selectedState ? (
        <div className="fsm__inspector" data-testid="state-inspector">
          <strong>state</strong>
          <SelectionBadge confidence={highlights.confidence} />
          <input
            defaultValue={selectedState}
            aria-label="state name"
            onBlur={(e) => {
              const newName = e.target.value.trim();
              if (newName && newName !== selectedState) {
                const { text } = renameState(specText, selectedState, newName);
                setSpecText(text);
              }
            }}
          />
        </div>
      ) : null}
    </div>
  );
}
