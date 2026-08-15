import Editor from '@monaco-editor/react';

export interface MonacoEditorProps {
  value: string;
  onChange: (text: string) => void;
}

/**
 * The authoritative text editor. Text is the single source of truth for the
 * spec; every other view edits *through* it.
 */
export function MonacoEditor({ value, onChange }: MonacoEditorProps) {
  return (
    <Editor
      height="100%"
      language="yaml"
      value={value}
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
