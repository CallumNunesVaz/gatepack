import { useCallback, useEffect, useRef, useState } from 'react';
import Editor, { useMonaco, type Monaco, type OnMount } from '@monaco-editor/react';

export interface MonacoEditorProps {
  value: string;
  onChange: (text: string) => void;
  /**
   * When set, reveal (scroll to + highlight) this 1-based line, without moving
   * the cursor or stealing keyboard focus. `token` disambiguates two reveals of
   * the same line (e.g. after an edit leaves the anchor on the same line).
   */
  reveal?: { line: number; token: number } | null;
}

type StandaloneEditor = Parameters<OnMount>[0];
type MonacoApi = Parameters<OnMount>[1];

const THEME_NAME = 'gatepack';

/** Read a design token off `<html>`, but only if it really is a plain hex.
 *
 * Monaco accepts `#rrggbb`/`#rrggbbaa` and nothing else — an `rgba()` token
 * (the selection colours are `rgba`) makes `defineTheme` throw and the editor
 * falls back to its default white. So a token that is not hex is *declined*
 * here and the caller's fallback applies, rather than being reformatted into
 * something that might not be the colour anyone chose.
 */
function hexToken(name: string, fallback: string): string {
  if (typeof window === 'undefined') return fallback;
  const raw = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return /^#(?:[0-9a-f]{6}|[0-9a-f]{8})$/i.test(raw) ? raw : fallback;
}

function isDark(): boolean {
  const explicit = document.documentElement.getAttribute('data-theme');
  if (explicit === 'dark') return true;
  if (explicit === 'light') return false;
  return typeof window.matchMedia === 'function'
    ? window.matchMedia('(prefers-color-scheme: dark)').matches
    : false;
}

/**
 * Define the editor theme from the app's own tokens.
 *
 * Monaco ships its own light theme and does not know about `tokens.css`, so
 * the editor sat as a white rectangle inside a dark application. It cannot read
 * CSS custom properties itself — a Monaco theme is literal hex — so the tokens
 * are resolved off `<html>` at call time and handed over. That keeps
 * `tokens.css` the single source of truth: change a token there and the editor
 * follows, including when the user toggles the theme mid-session.
 */
function defineTheme(monaco: Monaco): void {
  const dark = isDark();
  const surface = hexToken('--gp-surface', dark ? '#12201b' : '#ffffff');
  const surface2 = hexToken('--gp-surface-2', dark ? '#17291f' : '#f4f6f4');
  const surface3 = hexToken('--gp-surface-3', dark ? '#1e3428' : '#e8ece9');
  const border = hexToken('--gp-border', dark ? '#27402f' : '#d9e0da');
  const borderStrong = hexToken('--gp-border-strong', dark ? '#3a5a45' : '#b6c3ba');
  const text = hexToken('--gp-text', dark ? '#e8efe9' : '#12201b');
  const muted = hexToken('--gp-text-muted', dark ? '#a3b8ab' : '#5c6b64');
  const faint = hexToken('--gp-text-faint', dark ? '#7a8e85' : '#7a8e85');
  const accent = hexToken('--gp-accent', dark ? '#f2c75c' : '#c9962a');
  const ok = hexToken('--gp-ok', dark ? '#5fd08e' : '#1e7a4a');
  const info = hexToken('--gp-info', dark ? '#7fb8e8' : '#1d5b8f');

  const bare = (hex: string) => hex.replace('#', '').slice(0, 6);

  monaco.editor.defineTheme(THEME_NAME, {
    base: dark ? 'vs-dark' : 'vs',
    inherit: true,
    rules: [
      { token: '', foreground: bare(text), background: bare(surface) },
      { token: 'comment', foreground: bare(faint), fontStyle: 'italic' },
      { token: 'string', foreground: bare(ok) },
      { token: 'number', foreground: bare(info) },
      { token: 'keyword', foreground: bare(accent) },
      { token: 'type', foreground: bare(accent) },
      { token: 'tag', foreground: bare(accent) },
    ],
    colors: {
      'editor.background': surface,
      'editor.foreground': text,
      'editorGutter.background': surface,
      'editorLineNumber.foreground': faint,
      'editorLineNumber.activeForeground': muted,
      'editor.lineHighlightBackground': surface2,
      'editor.lineHighlightBorder': surface2,
      'editorCursor.foreground': accent,
      'editor.selectionBackground': surface3,
      'editor.inactiveSelectionBackground': surface2,
      'editorWhitespace.foreground': border,
      'editorIndentGuide.background': border,
      'editorIndentGuide.activeBackground': borderStrong,
      'editorWidget.background': surface2,
      'editorWidget.border': border,
      'editorSuggestWidget.background': surface2,
      'editorSuggestWidget.border': border,
      'editorSuggestWidget.selectedBackground': surface3,
      'input.background': surface2,
      'input.border': border,
      'dropdown.background': surface2,
      // The editor's own scrollbars: the same treatment as every other
      // scrollbar in the app (see styles.css), expressed in Monaco's vocabulary.
      'scrollbar.shadow': surface,
      'scrollbarSlider.background': border,
      'scrollbarSlider.hoverBackground': borderStrong,
      'scrollbarSlider.activeBackground': borderStrong,
      'minimap.background': surface,
    },
  });
}

/**
 * The authoritative text editor. Text is the single source of truth for the
 * spec; every other view edits *through* it.
 */
export function MonacoEditor({ value, onChange, reveal }: MonacoEditorProps) {
  const monaco = useMonaco();
  // Bumped whenever the effective theme changes, to re-resolve the tokens.
  const [themeTick, setThemeTick] = useState(0);
  const editorRef = useRef<StandaloneEditor | null>(null);
  const monacoRef = useRef<MonacoApi | null>(null);
  const revealDecorations = useRef<ReturnType<StandaloneEditor['createDecorationsCollection']> | null>(null);
  const [editorReady, setEditorReady] = useState(false);

  const beforeMount = useCallback((instance: Monaco) => defineTheme(instance), []);

  const onMount = useCallback<OnMount>((editor, instance) => {
    editorRef.current = editor;
    monacoRef.current = instance;
    setEditorReady(true);
  }, []);

  // Reveal a line without stealing focus: `revealLineInCenter` scrolls and a
  // whole-line decoration highlights, neither of which touches the cursor or
  // the keyboard focus. `editorReady` is in the deps because `onMount` fires
  // after the first render — a reveal requested on mount must apply once the
  // editor actually exists.
  useEffect(() => {
    if (!editorReady || !editorRef.current || !monacoRef.current) return;
    const editor = editorRef.current;
    const instance = monacoRef.current;
    if (!reveal) {
      revealDecorations.current?.clear();
      return;
    }
    const model = editor.getModel();
    const maxLine = model ? model.getLineCount() : 1;
    const line = Math.min(Math.max(1, reveal.line), maxLine);
    editor.revealLineInCenter(line);
    const decoration = {
      range: new instance.Range(line, 1, line, 1),
      options: { isWholeLine: true, className: 'spec-editor__reveal-line' },
    };
    if (!revealDecorations.current) {
      revealDecorations.current = editor.createDecorationsCollection([decoration]);
    } else {
      revealDecorations.current.set([decoration]);
    }
  }, [editorReady, reveal?.line, reveal?.token]);

  // Follow both ways the theme can change: an explicit toggle (which sets
  // `data-theme` on <html>) and, when the user has made no explicit choice, the
  // OS preference flipping under a live session.
  useEffect(() => {
    const bump = () => setThemeTick((t) => t + 1);
    const observer = new MutationObserver(bump);
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
    const mq =
      typeof window.matchMedia === 'function'
        ? window.matchMedia('(prefers-color-scheme: dark)')
        : null;
    mq?.addEventListener('change', bump);
    return () => {
      observer.disconnect();
      mq?.removeEventListener('change', bump);
    };
  }, []);

  useEffect(() => {
    if (!monaco) return;
    defineTheme(monaco);
    monaco.editor.setTheme(THEME_NAME);
  }, [monaco, themeTick]);

  return (
    <Editor
      height="100%"
      language="yaml"
      value={value}
      theme={THEME_NAME}
      beforeMount={beforeMount}
      onMount={onMount}
      onChange={(next) => onChange(next ?? '')}
      options={{
        minimap: { enabled: false },
        fontSize: 13,
        wordWrap: 'on',
        scrollBeyondLastLine: false,
      }}
    />
  );
}
