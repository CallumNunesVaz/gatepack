/**
 * Pure helpers for the C12 schematic overlay layers (packed + test-point/
 * unobservable). netlistsvg lays the cells out once; these layers are drawn
 * *over* that layout and never re-run it, so they are keyed by the same
 * instance names the rendered SVG uses (`id="cell_<instance>"`).
 *
 * Everything here is DOM-read-only and unit-testable without a browser: cell
 * positions come from the `transform` attributes netlistsvg emits, and the net
 * wire positions come from the `net_<bits>` classes it emits. jsdom cannot do
 * `getBBox`, so this module never calls it.
 */

import type { AnalysisSummary, PackedView } from '../../shared/api';

/**
 * The §13.1 wire sentinel for "infinite" (unobservable), mirrored from
 * `gatepack/analysis/scoap.py`. JSON has no infinity, so a large finite value
 * stands in; any `observability >= UNOBSERVABLE` is an unobservable net.
 */
export const UNOBSERVABLE = 1 << 30;

export interface Point {
  x: number;
  y: number;
}

export interface PackageLayout {
  refdes: string;
  partNumber: string;
  capacity: number;
  spare: number;
  instanceCells: string[];
  x: number;
  y: number;
  width: number;
  height: number;
}

/** Nominal per-cell footprint for the container bbox (netlistsvg gates are
 * ~20-40 units; the container is only a visual boundary, so an approximation
 * is honest and stable). */
const CELL_WIDTH = 40;
const CELL_HEIGHT = 24;
const PADDING = 14;
const STACK_STEP = CELL_HEIGHT + 2 * PADDING + 20;

const TRANSLATE_RE = /translate\(\s*(-?[\d.]+)\s*[, ]\s*(-?[\d.]+)\s*\)/;

/**
 * Instance name -> top-left position, read from netlistsvg's per-cell groups
 * (`<g id="cell_<instance>" transform="translate(x,y)">`).
 */
export function readCellPositions(svg: SVGSVGElement): Map<string, Point> {
  const out = new Map<string, Point>();
  const groups = svg.querySelectorAll('g[id^="cell_"]');
  for (const g of Array.from(groups)) {
    const id = g.getAttribute('id');
    if (id === null || !id.startsWith('cell_')) continue;
    const instance = id.slice('cell_'.length);
    const transform = g.getAttribute('transform') ?? '';
    const m = TRANSLATE_RE.exec(transform);
    if (m === null) continue;
    out.set(instance, { x: Number(m[1]), y: Number(m[2]) });
  }
  return out;
}

/**
 * One bounding container per package. Packages whose cells are not present in
 * the layout (e.g. a cell dropped from the netlist) stack at the top-left
 * instead of being dropped silently — a package boundary the renderer cannot
 * place is still reported, never fabricated into the wrong place.
 */
export function computePackageLayouts(
  packages: PackedView['packages'],
  positions: Map<string, Point>,
): PackageLayout[] {
  return packages.map((pkg, index) => {
    const points = pkg.instanceCells
      .map((name) => positions.get(name))
      .filter((p): p is Point => p !== undefined);

    if (points.length === 0) {
      return {
        refdes: pkg.refdes,
        partNumber: pkg.partNumber,
        capacity: pkg.capacity,
        spare: pkg.spare,
        instanceCells: pkg.instanceCells,
        x: 0,
        y: index * STACK_STEP,
        width: CELL_WIDTH + 2 * PADDING,
        height: CELL_HEIGHT + 2 * PADDING,
      };
    }

    const minX = Math.min(...points.map((p) => p.x));
    const minY = Math.min(...points.map((p) => p.y));
    const maxX = Math.max(...points.map((p) => p.x));
    const maxY = Math.max(...points.map((p) => p.y));
    return {
      refdes: pkg.refdes,
      partNumber: pkg.partNumber,
      capacity: pkg.capacity,
      spare: pkg.spare,
      instanceCells: pkg.instanceCells,
      x: minX - PADDING,
      y: minY - PADDING,
      width: maxX - minX + CELL_WIDTH + 2 * PADDING,
      height: maxY - minY + CELL_HEIGHT + 2 * PADDING,
    };
  });
}

/** Unobservable net names in a SCOAP table, by the sentinel only. */
export function unobservableNets(analysis: AnalysisSummary): string[] {
  return analysis.scoap
    .filter((s) => s.observability >= UNOBSERVABLE)
    .map((s) => s.net);
}

function asRecord(v: unknown): Record<string, unknown> | null {
  return typeof v === 'object' && v !== null && !Array.isArray(v)
    ? (v as Record<string, unknown>)
    : null;
}

/**
 * Net name -> bit indices, from a Yosys `write_json` document. Port names win
 * over `_int` aliases (the same rule `gatepack/netlist.py` applies), so a SCOAP
 * net name like `y` resolves to the same bit as `y_int`.
 */
export function netBitIndices(netlist: unknown): Map<string, number[]> {
  const out = new Map<string, number[]>();
  const root = asRecord(netlist);
  const modules = root ? asRecord(root['modules']) : null;
  if (modules === null) return out;
  const top = modules[Object.keys(modules)[0]];
  const mod = asRecord(top);
  if (mod === null) return out;

  const add = (name: unknown, bits: unknown) => {
    if (typeof name !== 'string') return;
    const arr = Array.isArray(bits)
      ? bits.filter((b): b is number => typeof b === 'number')
      : [];
    if (arr.length > 0) out.set(name, arr);
  };

  const netnames = asRecord(mod['netnames']) ?? {};
  for (const [name, infoRaw] of Object.entries(netnames)) {
    const info = asRecord(infoRaw);
    if (info) add(name, info['bits']);
  }
  const ports = asRecord(mod['ports']) ?? {};
  for (const [name, infoRaw] of Object.entries(ports)) {
    const info = asRecord(infoRaw);
    if (info) add(name, info['bits']);
  }
  return out;
}

/**
 * Net name -> a representative point on its wires, read from the rendered SVG's
 * `net_<bits>` line classes. Used to place the unobservable/test-point markers
 * next to the net they flag rather than in a disconnected legend.
 */
export function readNetMarkerPoints(
  svg: SVGSVGElement,
  netlist: unknown,
): Map<string, Point> {
  const bitsByName = netBitIndices(netlist);
  const out = new Map<string, Point>();
  for (const [name, bits] of bitsByName) {
    if (bits.length === 0) continue;
    const cls = `net_${bits.join(',')}`;
    const els = Array.from(svg.querySelectorAll(`[class~="${cls}"]`));
    const points = els
      .map((el): Point | null => {
        const cx = el.getAttribute('cx');
        if (cx !== null) {
          return { x: Number(cx), y: Number(el.getAttribute('cy') ?? 0) };
        }
        const x1 = el.getAttribute('x1');
        if (x1 === null) return null;
        const x2 = el.getAttribute('x2') ?? x1;
        const y1 = el.getAttribute('y1') ?? '0';
        const y2 = el.getAttribute('y2') ?? y1;
        return {
          x: (Number(x1) + Number(x2)) / 2,
          y: (Number(y1) + Number(y2)) / 2,
        };
      })
      .filter((p): p is Point => p !== null);
    if (points.length === 0) continue;
    out.set(
      name,
      {
        x: points.reduce((s, p) => s + p.x, 0) / points.length,
        y: points.reduce((s, p) => s + p.y, 0) / points.length,
      },
    );
  }
  return out;
}
