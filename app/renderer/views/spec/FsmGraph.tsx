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
import '../views.css';

/**
 * FSM graph (React Flow): states are nodes, transitions are labelled edges. A
 * graph edit is a *document mutation* — it produces new YAML text, which is what
 * is saved. Node positions are cosmetic and live in the gitignored sidecar
 * store, never in the YAML.
 *
 * Selecting a node/edge emits a §15.2 selection; the same selection reflected
 * back from another view (a truth-table row, a schematic gate) highlights the
 * matching nodes/edges here. The direct selection and the cross-highlight are
 * both drawn with the selection tokens. A transition whose provenance has no
 * surviving link renders its "no exact link" state instead of silently
 * highlighting nothing.
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
    return <div className="gp-empty">The spec does not parse yet.</div>;
  }

  const selectedTransitionIndex =
    selection?.kind === 'transition'
      ? model.transitions.findIndex((t) => t.from === selection.from && t.to === selection.to)
      : -1;
  const selectedTransition = selectedTransitionIndex >= 0 ? model.transitions[selectedTransitionIndex] : null;
  const selectedState = selection?.kind === 'state' ? selection.id : null;

  const nodes: Node[] = model.states.map((state, i) => {
    const classes = [
      state === model.initial ? 'fsm-node--initial' : '',
      highlights.states.includes(state) ? 'fsm-node--highlight' : '',
      state === selectedState ? 'fsm-node--selected' : '',
    ].filter(Boolean).join(' ');
    return {
      id: state,
      position: positions[state] ?? { x: i * 180, y: 0 },
      data: { label: state },
      className: classes || undefined,
    };
  });

  const edges: Edge[] = model.transitions.map((t, i) => {
    const classes = [
      highlights.transitions.includes(i) ? 'fsm-edge--highlight' : '',
      selectedTransitionIndex === i ? 'fsm-edge--selected' : '',
    ].filter(Boolean).join(' ');
    return {
      id: `e${i}`,
      source: t.from,
      target: t.to,
      label: t.when,
      type: 'default',
      markerEnd: { type: MarkerType.ArrowClosed },
      className: classes || undefined,
    };
  });

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

  return (
    <div className="fsm" data-testid="fsm-graph">
      <div className="fsm__toolbar">
        <button type="button" className="view-btn" onClick={addState}>
          + state
        </button>
        <button type="button" className="view-btn" onClick={addTransition}>
          + transition
        </button>
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
