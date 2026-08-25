/**
 * The sheet must hold still, and it must be draggable.
 *
 * Two defects, both reported by eye and both only pinnable by measurement:
 *
 *   jiggle   the value readout sits *above* the canvas in a flex column, so
 *            anything that changes its height moves the whole sheet. Hovering
 *            swapped a plain `<span>` for `<code>`/`<strong>`, which resolve to
 *            a different fallback family; `line-height: normal` is derived from
 *            the resolved font's metrics, so the line box went 12px -> 13px and
 *            the sheet stepped down 1px and back on every hover. Tracing a net
 *            across the gaps between its segments made it bob continuously.
 *
 *   panning   a sheet larger than the pane could only be moved by its
 *             scrollbars, because the wheel is already spoken for (it zooms,
 *             and claims the gesture).
 *
 * Both assertions are numeric on purpose. "The sheet did not move" is the whole
 * claim for the first, and a 1px regression is exactly the size of the original
 * bug — a boolean "is it still visible" would never have caught it.
 */

import { _electron, expect, test, type Page } from '@playwright/test';
import { execFileSync } from 'node:child_process';
import * as fs from 'node:fs';
import * as os from 'node:os';
import * as path from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const APP_DIR = path.resolve(HERE, '..', '..');
const REPO_ROOT = path.resolve(APP_DIR, '..');
const IMAGE = 'gatepack-toolchain:m6';

function toolchainAvailable(): boolean {
  try {
    execFileSync('docker', ['image', 'inspect', IMAGE], { stdio: 'ignore' });
    return true;
  } catch {
    return false;
  }
}

function makeCore(): string {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'gatepack-tccore-'));
  const p = path.join(dir, 'gatepack');
  fs.writeFileSync(
    p,
    [
      '#!/bin/sh',
      'exec docker run --rm \\',
      `  --user "${process.getuid!()}:${process.getgid!()}" \\`,
      '  -v /tmp:/tmp \\',
      `  -v "${REPO_ROOT}:${REPO_ROOT}" \\`,
      `  -e PYTHONPATH="${REPO_ROOT}" -e HOME=/tmp -w "$PWD" \\`,
      `  ${IMAGE} python3 -m gatepack.cli "$@"`,
      '',
    ].join('\n'),
  );
  fs.chmodSync(p, 0o755);
  return p;
}

/** Poll rather than `waitForFunction`: the app's CSP has no 'unsafe-eval'. */
async function waitForSheet(page: Page): Promise<number> {
  let geometry = 0;
  for (let i = 0; i < 120 && geometry <= 50; i++) {
    geometry = await page.evaluate(
      () =>
        document.querySelector('.schematic__zoom-host')?.querySelectorAll('path,line').length ?? 0,
    );
    if (geometry <= 50) await page.waitForTimeout(500);
  }
  return geometry;
}

/** Everything whose movement would read as the sheet jiggling. */
const layoutSnapshot = () => {
  const canvas = document.querySelector('[data-testid="schematic-svg"]') as HTMLElement;
  const readout = document.querySelector('[data-testid="schematic-readout"]') as HTMLElement | null;
  const svg = canvas.querySelector('svg') as SVGSVGElement;
  const cell = svg.querySelector('g[id^="cell_"]') as SVGGElement | null;
  const round = (n: number) => Math.round(n * 100) / 100;
  return {
    canvasTop: round(canvas.getBoundingClientRect().top),
    canvasHeight: round(canvas.getBoundingClientRect().height),
    readoutHeight: readout ? round(readout.getBoundingClientRect().height) : -1,
    svgTop: round(svg.getBoundingClientRect().top),
    svgLeft: round(svg.getBoundingClientRect().left),
    // A landmark *inside* the sheet: if the container held still but the
    // contents shifted, only this would show it.
    cellTop: cell ? round(cell.getBoundingClientRect().top) : -1,
    cellLeft: cell ? round(cell.getBoundingClientRect().left) : -1,
  };
};

test.describe('schematic stability and panning', () => {
  test.skip(!toolchainAvailable(), `toolchain image ${IMAGE} not available`);
  test.describe.configure({ timeout: 180_000 });

  let close: (() => Promise<void>) | null = null;
  test.afterEach(async () => {
    if (close) await close();
    close = null;
  });

  async function openBuiltSchematic(): Promise<Page> {
    const app = await _electron.launch({
      args: [APP_DIR],
      env: {
        ...process.env,
        GATEPACK_CORE: makeCore(),
        GATEPACK_SESSION_DIR: fs.mkdtempSync(path.join(os.tmpdir(), 'gatepack-session-')),
      },
    });
    close = () => app.close();
    const page = await app.firstWindow();
    await page.waitForFunction(() => typeof (window as any).gatepack !== 'undefined');
    const opened = await page.evaluate(() => (window as any).gatepack.openExample('seven_segment'));
    expect(opened.ok, 'openExample').toBe(true);
    const built = await page.evaluate(() => (window as any).gatepack.build());
    expect(built.ok, built.ok ? '' : built.error?.message).toBe(true);
    await page.getByTestId('nav-schematic').click();
    expect(await waitForSheet(page), 'schematic drew geometry').toBeGreaterThan(50);
    await page.waitForTimeout(600);
    return page;
  }

  /** Screen-space midpoints of a few wires, well inside the pane. */
  async function wirePoints(page: Page): Promise<Array<{ x: number; y: number; net: string }>> {
    return page.evaluate(() => {
      const canvas = document.querySelector('[data-testid="schematic-svg"]') as HTMLElement;
      const box = canvas.getBoundingClientRect();
      const svg = canvas.querySelector('svg') as SVGSVGElement;
      const netClassOf = (e: Element | null) =>
        (e?.getAttribute('class') ?? '').split(/\s+/).find((c) => c.startsWith('net_')) ?? null;
      const wires = (Array.from(svg.querySelectorAll('line,path')) as SVGGeometryElement[]).filter(
        (e) => netClassOf(e) !== null && !e.classList.contains('gp-hit'),
      );
      const out: Array<{ x: number; y: number; net: string }> = [];
      for (const el of wires) {
        if (out.length >= 6) break;
        const ctm = el.getScreenCTM();
        if (!ctm) continue;
        let p: DOMPoint;
        if (el.tagName === 'path') {
          const pe = el as SVGPathElement;
          p = pe.getPointAtLength(pe.getTotalLength() / 2);
        } else {
          const l = el as unknown as SVGLineElement;
          p = new DOMPoint(
            (l.x1.baseVal.value + l.x2.baseVal.value) / 2,
            (l.y1.baseVal.value + l.y2.baseVal.value) / 2,
          );
        }
        const c = p.matrixTransform(ctm);
        if (
          c.x < box.left + 24 || c.x > box.right - 24 ||
          c.y < box.top + 24 || c.y > box.bottom - 24
        ) continue;
        out.push({ x: c.x, y: c.y, net: netClassOf(el)! });
      }
      return out;
    });
  }

  test('hovering a net does not move the sheet by so much as a pixel', async () => {
    const page = await openBuiltSchematic();
    const points = await wirePoints(page);
    expect(points.length, 'wires sampled').toBeGreaterThan(2);

    await page.mouse.move(4, 4);
    await page.waitForTimeout(300);
    const idle = await page.evaluate(layoutSnapshot);

    for (const pt of points) {
      await page.mouse.move(pt.x, pt.y);
      await page.waitForTimeout(250);
      const lit = await page.evaluate(
        () => document.querySelectorAll('[data-gp-hover]').length,
      );
      // If nothing lit, the hover never happened and the comparison below would
      // pass for the wrong reason.
      if (lit === 0) continue;
      const hovered = await page.evaluate(layoutSnapshot);
      expect(hovered, `hovering ${pt.net} moved the sheet`).toEqual(idle);
    }

    await page.mouse.move(4, 4);
    await page.waitForTimeout(300);
    expect(await page.evaluate(layoutSnapshot), 'leaving the sheet moved it').toEqual(idle);
  });

  test('dragging the sheet pans it, by the distance dragged', async () => {
    const page = await openBuiltSchematic();
    const canvas = (await page.locator('[data-testid="schematic-svg"]').boundingBox())!;

    const scroll = () =>
      page.evaluate(() => {
        const el = document.querySelector('[data-testid="schematic-svg"]') as HTMLElement;
        return {
          left: el.scrollLeft,
          top: el.scrollTop,
          maxLeft: el.scrollWidth - el.clientWidth,
          maxTop: el.scrollHeight - el.clientHeight,
          pannable: el.getAttribute('data-pannable'),
        };
      });

    const before = await scroll();
    // The seven-segment sheet is far taller than the pane; if it were not,
    // there would be nothing to pan and the test would prove nothing.
    expect(before.maxTop, 'sheet overflows the pane vertically').toBeGreaterThan(200);
    expect(before.pannable, 'the grab cursor is offered').toBe('on');

    const startX = canvas.x + canvas.width / 2;
    const startY = canvas.y + canvas.height / 2;
    const dy = 150;
    await page.mouse.move(startX, startY);
    await page.mouse.down();
    // Stepped: one jump delivers a single mousemove, and the threshold that
    // separates a pan from a click needs real intermediate movement.
    await page.mouse.move(startX, startY - dy, { steps: 12 });
    await page.waitForTimeout(120);
    const during = await scroll();
    await page.mouse.up();

    // Dragging up moves the sheet up, so the scroll offset grows — by the drag
    // distance, less the threshold that had to be crossed first.
    expect(during.top - before.top, 'panned by roughly the drag distance').toBeGreaterThan(
      dy - 20,
    );
    expect(during.top - before.top).toBeLessThanOrEqual(dy);
  });

  test('a drag does not select what it passes over, but a click still does', async () => {
    const page = await openBuiltSchematic();
    const points = await wirePoints(page);
    expect(points.length, 'wires sampled').toBeGreaterThan(2);
    const selected = () =>
      page.evaluate(() => document.querySelectorAll('.gp-sel').length);

    expect(await selected(), 'nothing is selected to begin with').toBe(0);

    const scrollTop = () =>
      page.evaluate(
        () => (document.querySelector('[data-testid="schematic-svg"]') as HTMLElement).scrollTop,
      );

    // Drag starting on a wire: the press lands on it, the gesture is a pan.
    //
    // This is precisely the case the click suppression exists for. A pan drags
    // the sheet *with* the pointer, so the wire the press landed on is still
    // under the pointer at mouseup — mousedown and mouseup share a target, the
    // browser fires a `click` on the wire, and without the guard the drag also
    // changes the selection.
    const pt = points[0];
    const beforeTop = await scrollTop();
    await page.mouse.move(pt.x, pt.y);
    await page.mouse.down();
    await page.mouse.move(pt.x, pt.y - 120, { steps: 12 });
    await page.mouse.up();
    await page.waitForTimeout(300);
    // Assert the pan actually happened first: with no panning at all the
    // pointer simply travels to a different element, `click` resolves to their
    // common ancestor, and "nothing was selected" would hold for a reason that
    // has nothing to do with the guard under test.
    expect((await scrollTop()) - beforeTop, 'the drag panned the sheet').toBeGreaterThan(80);
    expect(await selected(), 'a pan selected the wire it started on').toBe(0);

    // A press that never crosses the threshold is still a click.
    const after = await wirePoints(page);
    expect(after.length, 'wires still reachable after the pan').toBeGreaterThan(0);
    await page.mouse.click(after[0].x, after[0].y);
    await page.waitForTimeout(400);
    expect(await selected(), 'a plain click no longer selects').toBeGreaterThan(0);
  });
});
