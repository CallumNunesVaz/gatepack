/**
 * Locating the bundled examples and parsing `gatepack examples list` output for
 * the application menu (§18.1).
 *
 * Discovery, ordering and summarisation belong to the core
 * (`gatepack examples list`); the main process only locates the examples
 * directory on disk (for the showcase on first launch, which must not depend on
 * the core) and parses the list command's output (for the Examples menu).
 */

import * as fs from 'node:fs';
import * as path from 'node:path';

export interface ExampleEntry {
  name: string;
  isShowcase: boolean;
}

const SHOWCASE_SUFFIX = ' (showcase)';

/** Locate the bundled examples directory, or null when it is not shipped. */
export function findExamplesRoot(appRoot: string, projectRoot: string): string | null {
  const candidates = [
    path.join(projectRoot, 'examples'),
    path.join(appRoot, 'examples'),
    path.join(appRoot, 'resources', 'examples'),
  ];
  for (const dir of candidates) {
    if (isExamplesRoot(dir)) return dir;
  }
  return null;
}

function isExamplesRoot(dir: string): boolean {
  try {
    if (!fs.statSync(dir).isDirectory()) return false;
    for (const entry of fs.readdirSync(dir)) {
      if (fs.existsSync(path.join(dir, entry, 'design.yaml'))) return true;
    }
  } catch {
    // Not readable -> not an examples root.
  }
  return false;
}

/** Parse `gatepack examples list` stdout into name/showcase entries. */
export function parseExamplesList(output: string): ExampleEntry[] {
  const entries: ExampleEntry[] = [];
  for (const line of output.split('\n')) {
    if (line.trim() === '') continue;
    if (line.startsWith(' ') || line.startsWith('\t')) continue; // summary line
    const name = line.trim();
    const isShowcase = name.endsWith(SHOWCASE_SUFFIX);
    entries.push({
      name: isShowcase ? name.slice(0, -SHOWCASE_SUFFIX.length) : name,
      isShowcase,
    });
  }
  return entries;
}
