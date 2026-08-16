import { useMemo } from 'react';

/**
 * A pretty-printed, monospace JSON dump with the current search query
 * highlighted. Used by the mapped/packed netlist inspectors for their raw
 * views; it renders the data as-is and never interprets it.
 */
export function RawJson({ data, query }: { data: unknown; query: string }) {
  const text = useMemo(() => JSON.stringify(data, null, 2), [data]);

  const parts = useMemo(() => {
    const q = query.trim();
    if (!q) return [text];
    const lower = text.toLowerCase();
    const needle = q.toLowerCase();
    const out: string[] = [];
    let at = 0;
    for (;;) {
      const idx = lower.indexOf(needle, at);
      if (idx === -1) {
        out.push(text.slice(at));
        break;
      }
      out.push(text.slice(at, idx), text.slice(idx, idx + q.length));
      at = idx + q.length;
    }
    return out;
  }, [text, query]);

  return (
    <pre className="gp-raw" data-testid="raw-json">
      {parts.map((part, i) =>
        i % 2 === 1 ? <mark key={i}>{part}</mark> : <span key={i}>{part}</span>,
      )}
    </pre>
  );
}
