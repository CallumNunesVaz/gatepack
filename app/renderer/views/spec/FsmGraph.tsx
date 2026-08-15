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

type Selection = { kind: 'node'; id: string } | { kind: 'edge'; index: number } | null;

/**
 * FSM graph (React Flow): states are nodes, transitions are labelled edges. A
 * graph edit is a *document mutation* — it produces new YAML text, which is what
 * is saved. Node positions are cosmetic and live in the gitignored sidecar
 * store, never in the YAML.
 */
export function FsmGraph() {
  const { specText, model, setSpecText, project } = useProject();
  const [selected, setSelected] = useState<Selection>(null);
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
    style: state === model.initial ? { border: '2px solid #4c9ffe' } : undefined,
  }));

  const edges: Edge[] = model.transitions.map((t, i) => ({
    id: `e${i}`,
    source: t.from,
    target: t.to,
    label: t.when,
    type: 'default',
    markerEnd: { type: MarkerType.ArrowClosed },
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

  const selectedTransition = selected?.kind === 'edge' ? model.transitions[selected.index] : null;
  const selectedState = selected?.kind === 'node' ? selected.id : null;

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
          onNodeClick={(_e, node) => setSelected({ kind: 'node', id: node.id })}
          onEdgeClick={(_e, edge) => setSelected({ kind: 'edge', index: Number(edge.id.slice(1)) })}
          onPaneClick={() => setSelected(null)}
          onNodeDragStop={onNodeDragStop}
          fitView
        >
          <Background />
          <Controls />
        </ReactFlow>
      </div>
      {selectedTransition ? (
        <div className="fsm__inspector">
          <strong>transition</strong>
          <span>
            {selectedTransition.from} →{' '}
            <select
              value={selectedTransition.to}
              onChange={(e) => updateEdge(selected!.kind === 'edge' ? selected!.index : 0, { to: e.target.value })}
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
              onChange={(e) =>
                updateEdge(selected!.kind === 'edge' ? selected!.index : 0, { when: e.target.value })
              }
              aria-label="transition guard"
            />
          </span>
        </div>
      ) : null}
      {selectedState ? (
        <div className="fsm__inspector">
          <strong>state</strong>
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
