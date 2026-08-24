/**
 * How close do you have to click?
 *
 * The schematic resolves a selection from `event.target` alone, so the
 * clickable area is exactly the geometry the browser painted — and netlistsvg
 * paints wires at `stroke-width: 1` and gate bodies with `fill: none`. Measured
 * against a real sheet before any change, that meant:
 *
 *   * a wire could only be hit within **0.5 px** of its centre line, roughly a
 *     quarter of the hand tremor of a mouse user at rest; and
 *   * clicking the middle of a 30x53 px gate symbol hit **nothing** — an
 *     unpainted fill is not hit-tested, so only the 1 px outline responded.
 *
 * These tests pin the fix by measuring the same way: step outward from the
 * geometry and ask what a click at that point would resolve to, using the same
 * `net_<bits>` class and `g[id^="cell_"]` lookups the handlers use.
 *
 * Numbers, not booleans: a regression here is likely to be a narrowing rather
 * than a disappearance (a stylesheet rule out-ranking the target width is
 * exactly how the first attempt failed), and only a measurement catches that.
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

/** The target half-width `schematicDecorate.ts` asks for; see HIT_HALF_WIDTH. */
const HIT_HALF_WIDTH = 5;

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

/** Wait for real geometry. Polled with evaluate(): the app's CSP has no
 *  'unsafe-eval', which is how Playwright's waitForFunction installs its
 *  predicate — so waitForFunction throws here rather than waiting. */
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

test.describe('schematic pointer targets', () => {
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
    await page.waitForTimeout(500);
    return page;
  }

  test('a wire can be hit without landing on the line itself', async () => {
    const page = await openBuiltSchematic();

    const measured = await page.evaluate(() => {
      const svg = document.querySelector('.schematic__zoom-host svg') as SVGSVGElement;
      const canvas = (
        document.querySelector('[data-testid="schematic-svg"]') as HTMLElement
      ).getBoundingClientRect();
      const netClassOf = (e: Element | null) =>
        (e?.getAttribute('class') ?? '').split(/\s+/).find((c) => c.startsWith('net_')) ?? null;

      // The drawn wires only; the click targets are invisible copies of them.
      const wires = (Array.from(svg.querySelectorAll('line,path')) as SVGGeometryElement[]).filter(
        (e) => netClassOf(e) !== null && !e.classList.contains('gp-hit'),
      );

      const results: Array<{ up: number; down: number; left: number; right: number }> = [];
      for (const el of wires) {
        if (results.length >= 8) break;
        const ctm = el.getScreenCTM();
        if (!ctm) continue;
        const mid =
          el.tagName === 'path'
            ? (el as SVGPathElement).getPointAtLength((el as SVGPathElement).getTotalLength() / 2)
            : new DOMPoint(
                ((el as unknown as SVGLineElement).x1.baseVal.value +
                  (el as unknown as SVGLineElement).x2.baseVal.value) / 2,
                ((el as unknown as SVGLineElement).y1.baseVal.value +
                  (el as unknown as SVGLineElement).y2.baseVal.value) / 2,
              );
        const c = mid.matrixTransform(ctm);
        // elementFromPoint outside the viewport reports the chrome, which would
        // read as "not clickable" for entirely the wrong reason.
        if (
          c.x < canvas.left + 16 || c.x > canvas.right - 16 ||
          c.y < canvas.top + 16 || c.y > canvas.bottom - 16
        ) continue;

        const want = netClassOf(el);
        const resolves = (dx: number, dy: number) =>
          netClassOf(document.elementFromPoint(c.x + dx, c.y + dy)) === want;
        if (!resolves(0, 0)) continue; // overdrawn by another element
        const reach = (ux: number, uy: number) => {
          let last = 0;
          for (let d = 0.25; d <= 16; d += 0.25) {
            if (!resolves(ux * d, uy * d)) break;
            last = d;
          }
          return last;
        };
        results.push({
          up: reach(0, -1), down: reach(0, 1),
          left: reach(-1, 0), right: reach(1, 0),
        });
      }
      return results;
    });

    expect(measured.length, 'wires sampled').toBeGreaterThan(3);
    for (const m of measured) {
      // Perpendicular is the narrow axis; along the wire the reach is the whole
      // segment. Whichever axis is the narrow one must still clear the target.
      const perpendicular = Math.min(Math.max(m.up, m.down), Math.max(m.left, m.right));
      expect(perpendicular, `perpendicular reach ${JSON.stringify(m)}`).toBeGreaterThanOrEqual(
        HIT_HALF_WIDTH - 1,
      );
    }
  });

  test('clicking the middle of a gate symbol selects that gate', async () => {
    const page = await openBuiltSchematic();

    const measured = await page.evaluate(() => {
      const svg = document.querySelector('.schematic__zoom-host svg') as SVGSVGElement;
      const canvas = (
        document.querySelector('[data-testid="schematic-svg"]') as HTMLElement
      ).getBoundingClientRect();
      const out: Array<{ id: string; w: number; h: number; hits: boolean }> = [];
      for (const g of Array.from(svg.querySelectorAll('g[id^="cell_"]')) as SVGGElement[]) {
        if (out.length >= 8) break;
        const box = (g as any).getBBox();
        const ctm = g.getScreenCTM();
        if (!ctm) continue;
        const centre = new DOMPoint(
          box.x + box.width / 2,
          box.y + box.height / 2,
        ).matrixTransform(ctm);
        if (
          centre.x < canvas.left + 16 || centre.x > canvas.right - 16 ||
          centre.y < canvas.top + 16 || centre.y > canvas.bottom - 16
        ) continue;
        const hit = document.elementFromPoint(centre.x, centre.y);
        // The same lookup the click handler performs.
        const resolved = hit?.closest?.('g[id^="cell_"]') ?? null;
        const far = new DOMPoint(box.x + box.width, box.y + box.height).matrixTransform(ctm);
        const near = new DOMPoint(box.x, box.y).matrixTransform(ctm);
        out.push({
          id: g.id,
          w: Math.round(far.x - near.x),
          h: Math.round(far.y - near.y),
          hits: resolved === g,
        });
      }
      return out;
    });

    expect(measured.length, 'cells sampled').toBeGreaterThan(3);
    for (const m of measured) {
      // The symbol is tens of pixels across and looks like one solid thing; a
      // click in the middle of it must not fall through to the sheet.
      expect(m.w * m.h, `${m.id} has area`).toBeGreaterThan(100);
      expect(m.hits, `centre of ${m.id} (${m.w}x${m.h}px) selects it`).toBe(true);
    }
  });

  test('the wheel zooms, anchored on the point under the pointer', async () => {
    const page = await openBuiltSchematic();

    const readZoom = () =>
      page.locator('[data-testid="schematic-zoom"]').innerText().then((t) => parseInt(t, 10));

    const before = await readZoom();
    expect(before).toBe(100);

    const canvas = await page.locator('[data-testid="schematic-svg"]').boundingBox();
    expect(canvas).not.toBeNull();
    // A point well inside the sheet, so there is something to stay anchored.
    const px = canvas!.x + canvas!.width * 0.5;
    const py = canvas!.y + canvas!.height * 0.5;

    // The anchoring invariant, read from scroll state rather than from an
    // element: with `transform-origin: top left`, the sheet coordinate under
    // the pointer is `(scroll + offset) / zoom`. If that coordinate is still
    // under the pointer after the zoom, the anchor held. Reading whatever
    // `elementFromPoint` returns instead compares two different elements — and
    // in a gap between wires it returns the whole `<svg>`, whose centre is far
    // off-screen, so the "drift" it reports is meaningless.
    const state = () =>
      page.evaluate(() => {
        const host = document.querySelector('[data-testid="schematic-svg"]') as HTMLElement;
        const readout = document.querySelector('[data-testid="schematic-zoom"]') as HTMLElement;
        const rect = host.getBoundingClientRect();
        return {
          scrollLeft: host.scrollLeft,
          scrollTop: host.scrollTop,
          left: rect.left,
          top: rect.top,
          zoom: parseInt(readout.innerText, 10) / 100,
          // Kept in the failure message: the first attempt at this anchored
          // correctly in Y and drifted 257 px in X, and only the scroll extents
          // showed why (the assignment was clamped to the old scroll area).
          scrollWidth: host.scrollWidth,
          clientWidth: host.clientWidth,
        };
      });

    const s0 = await state();
    const sheetX = (s0.scrollLeft + (px - s0.left)) / s0.zoom;
    const sheetY = (s0.scrollTop + (py - s0.top)) / s0.zoom;

    await page.mouse.move(px, py);
    await page.mouse.wheel(0, -240); // scroll up = zoom in
    await page.waitForTimeout(400);

    const after = await readZoom();
    expect(after, 'wheel up zoomed in').toBeGreaterThan(before);

    // Zooming about the scroll origin would fling whatever the user was looking
    // at off-screen on a large sheet, which is worse than no wheel zoom at all.
    const s1 = await state();
    const screenX = sheetX * s1.zoom - s1.scrollLeft + s1.left;
    const screenY = sheetY * s1.zoom - s1.scrollTop + s1.top;
    expect(
      Math.hypot(screenX - px, screenY - py),
      `anchor moved: pointer (${px}, ${py}) -> (${screenX}, ${screenY}); ` +
        `before=${JSON.stringify(s0)} after=${JSON.stringify(s1)}`,
    ).toBeLessThan(8);

    await page.mouse.wheel(0, 240);
    await page.waitForTimeout(400);
    expect(await readZoom(), 'wheel down zoomed back out').toBeLessThan(after);
  });
});
