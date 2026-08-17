import { Fragment, useCallback, useMemo, useState } from 'react';
import ReactFlow, {
  Background,
  BaseEdge,
  Controls,
  EdgeLabelRenderer,
  Handle,
  MarkerType,
  Position,
  type Edge,
  type EdgeProps,
  type Node,
  type NodeChange,
  type NodeProps,
} from 'reactflow';
import { useProject } from '../../state/project';
import { createLocalStorageLayoutStore, type LayoutMap } from '../../design/layout';
import { applyTopLevelEdit, renameState, type Transition } from '../../design/model';
import { useHighlights, useSelection } from '../../selection/bus';
import { useLinkContext } from '../../selection/useLinkContext';
import { SelectionBadge } from '../../selection/SelectionBadge';
import '../views.css';

/** The four sides a state exposes, each carrying both a source and a target
 * port so an edge can leave (and arrive) on whichever face is nearest. */
const SIDES = [
  ['t', Position.Top],
  ['r', Position.Right],
  ['b', Position.Bottom],
  ['l', Position.Left],
] as const;

type SideId = (typeof SIDES)[number][0];

/** Nominal node box, used only to reason about *centres* when picking sides.
 * React Flow measures the real element for routing; this just has to be close
 * enough that the dominant axis between two states comes out right. */
const NODE_W = 112;
const NODE_H = 40;

/**
 * A state node with visible, addressable interfaces on all four faces.
 *
 * The default React Flow node exposes exactly one target (top) and one source
 * (bottom), so every transition left the bottom of one state and entered the
 * top of another regardless of where the two sat — a state to the *left* got an
 * edge that dived below the source, ran sideways and climbed back up. With a
 * port on each face the edge can take the short way round.
 */
function StateNode({ data }: NodeProps<{ label: string }>) {
  return (
    <>
      {SIDES.map(([id, position]) => (
        <Fragment key={id}>
          <Handle
            type="target"
            id={`${id}-t`}
            position={position}
            className="fsm-handle fsm-handle--target"
            isConnectable={false}
          />
          <Handle
            type="source"
            id={`${id}-s`}
            position={position}
            className="fsm-handle fsm-handle--source"
            isConnectable={false}
          />
        </Fragment>
      ))}
      <span className="fsm-node__label">{data.label}</span>
    </>
  );
}

// Must be module-level and stable: a fresh object each render makes React Flow
// remount every node.
const nodeTypes = { fsmState: StateNode };

/**
 * A self-transition, drawn as a loop standing above its own state.
 *
 * The default edge cannot draw one: both endpoints are the same node, so it
 * produced a ~10px hook tucked against the node's corner with the guard label
 * floating beside it, apparently unattached to anything. A state that holds
 * while its guard is true is a real and common thing for an FSM to do — it
 * deserves to be as legible as any other transition.
 */
function SelfLoopEdge({ id, sourceX, sourceY, markerEnd, label }: EdgeProps) {
  const spread = 55;
  const height = 84;
  const path =
    `M ${sourceX},${sourceY} ` +
    `C ${sourceX - spread},${sourceY - height} ` +
    `${sourceX + spread},${sourceY - height} ` +
    `${sourceX},${sourceY}`;
  // The apex of a symmetric cubic sits at 3/4 of the control height.
  const labelY = sourceY - height * 0.75;
  return (
    <>
      <BaseEdge id={id} path={path} markerEnd={markerEnd} />
      {label ? (
        <EdgeLabelRenderer>
          <div
            className="fsm-edge__loop-label nodrag nopan"
            style={{ transform: `translate(-50%, -50%) translate(${sourceX}px, ${labelY}px)` }}
          >
            {label}
          </div>
        </EdgeLabelRenderer>
      ) : null}
    </>
  );
}

const edgeTypes = { fsmSelfLoop: SelfLoopEdge };

const OPPOSITE: Record<SideId, SideId> = { t: 'b', b: 't', l: 'r', r: 'l' };

/** Pick the faces that give the shortest run between two state boxes. */
export function nearestSides(
  from: { x: number; y: number },
  to: { x: number; y: number },
): { source: SideId; target: SideId } {
  const dx = to.x - from.x;
  const dy = to.y - from.y;
  // Compare in units of the box's own half-extent, so a wide-but-short node
  // does not get an edge off its long face just because dx happens to be
  // numerically larger.
  const source: SideId =
    Math.abs(dx) / (NODE_W / 2) > Math.abs(dy) / (NODE_H / 2)
      ? dx > 0
        ? 'r'
        : 'l'
      : dy > 0
        ? 'b'
        : 't';
  return { source, target: OPPOSITE[source] };
}

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

  // Default layout: a circle, not a row.
  //
  // The previous default was `{ x: i * 180, y: 0 }` — every state on one line,
  // so a five-state machine rendered as a 900px-wide strip with every edge
  // looping over the top of it and the guard labels colliding. An FSM is a
  // cycle far more often than it is a pipeline (the showcase crossing is
  // literally GO -> WARN -> STOP -> CROSS -> CLEAR -> GO), and on a circle
  // every transition gets its own chord and the back edges are visible as
  // themselves.
  //
  // Saved positions still win: this is only what an unpositioned state gets,
  // and dragging one persists to the sidecar as before.
  const ringRadius = Math.max(180, 62 * model.states.length);
  const circleLayout = (i: number): { x: number; y: number } => {
    // Start at the top and go clockwise, so the initial state — which sorts
    // first in a well-written spec — lands where the eye starts.
    const angle = (2 * Math.PI * i) / Math.max(1, model.states.length) - Math.PI / 2;
    return {
      x: Math.round(ringRadius * (1 + Math.cos(angle))),
      y: Math.round(ringRadius * (1 + Math.sin(angle))),
    };
  };

  // Where each state actually sits this render — saved position if it has one,
  // otherwise its slot on the ring. Edge routing needs the same numbers the
  // nodes are drawn at, so both read from here.
  const placed: Record<string, { x: number; y: number }> = {};
  model.states.forEach((state, i) => {
    placed[state] = positions[state] ?? circleLayout(i);
  });
  const centreOf = (state: string) => {
    const p = placed[state] ?? { x: 0, y: 0 };
    return { x: p.x + NODE_W / 2, y: p.y + NODE_H / 2 };
  };

  const nodes: Node[] = model.states.map((state) => {
    const classes = [
      state === model.initial ? 'fsm-node--initial' : '',
      highlights.states.includes(state) ? 'fsm-node--highlight' : '',
      state === selectedState ? 'fsm-node--selected' : '',
    ].filter(Boolean).join(' ');
    return {
      id: state,
      type: 'fsmState',
      position: placed[state],
      data: { label: state },
      className: classes || undefined,
    };
  });

  const edges: Edge[] = model.transitions.map((t, i) => {
    const highlighted = highlights.transitions.includes(i);
    const selected = selectedTransitionIndex === i;
    const classes = [
      highlighted ? 'fsm-edge--highlight' : '',
      selected ? 'fsm-edge--selected' : '',
    ].filter(Boolean).join(' ');
    // A self-transition has no direction to derive: leave and re-enter the top
    // face and let the loop edge draw the arc above the state.
    const selfLoop = t.from === t.to;
    const sides = selfLoop
      ? { source: 't' as SideId, target: 't' as SideId }
      : nearestSides(centreOf(t.from), centreOf(t.to));
    return {
      id: `e${i}`,
      source: t.from,
      target: t.to,
      sourceHandle: `${sides.source}-s`,
      targetHandle: `${sides.target}-t`,
      label: t.when,
      type: selfLoop ? 'fsmSelfLoop' : 'default',
      // The marching-ants dash carries the direction of travel along the whole
      // edge, which a static arrowhead only states once at the far end — on a
      // ring layout, where two states are joined in both directions, that is
      // the difference between a readable machine and a tangle. Honours
      // `prefers-reduced-motion` (see views.css).
      animated: true,
      markerEnd: { type: MarkerType.ArrowClosed },
      className: classes || undefined,
    };
  });

  // Drag must move the node under the cursor, not on release.
  //
  // `nodes` is recomputed from `positions` every render, so with no
  // `onNodesChange` React Flow's own in-flight drag position was overwritten by
  // the stale one on the very next render: the node stayed put until
  // `onNodeDragStop` finally wrote the new coordinates. Feeding position
  // changes straight back into `positions` makes the drag live — and, because
  // edges route off the same map, the transitions follow the node as it moves.
  // Only drag stop persists, so a drag in progress never hits the sidecar.
  const onNodesChange = useCallback((changes: NodeChange[]) => {
    const moves = changes.filter(
      (c): c is NodeChange & { type: 'position'; id: string; position: { x: number; y: number } } =>
        c.type === 'position' && c.position !== undefined,
    );
    if (moves.length === 0) return;
    setPositions((prev) => {
      const next = { ...prev };
      for (const move of moves) next[move.id] = { x: move.position.x, y: move.position.y };
      return next;
    });
  }, []);

  const onNodeDragStop = (_event: unknown, node: Node) => {
    // `positions` is already current here — the live drag wrote every
    // intermediate frame into it — so this is the final frame plus the save.
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
          nodeTypes={nodeTypes}
          edgeTypes={edgeTypes}
          onNodesChange={onNodesChange}
          onNodeClick={(_e, node) => setSelection({ kind: 'state', id: node.id })}
          onEdgeClick={(_e, edge) => {
            const index = Number(edge.id.slice(1));
            const t = model.transitions[index];
            if (t) setSelection({ kind: 'transition', from: t.from, to: t.to });
          }}
          onPaneClick={() => setSelection(null)}
          onNodeDragStop={onNodeDragStop}
          fitView
          // A self-loop stands ~84px above its own node and `fitView` fits the
          // node boxes only, so the default padding clipped the topmost loop
          // against the canvas edge.
          fitViewOptions={{ padding: 0.34 }}
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
