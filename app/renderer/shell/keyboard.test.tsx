/**
 * The global shortcut handler's two hard guarantees:
 *
 *  1. It never fires while the user is typing — in an input, a textarea, a
 *     contentEditable, or a Monaco editor. This is the commonest way a shortcut
 *     handler ruins a text field, so it is tested directly against the real
 *     event path (the handler is on `window`, the event target is the field).
 *  2. It only intercepts chords that exist in `COMMANDS`; reserved/host chords
 *     pass through untouched.
 */

import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { isTypingTarget, useGlobalShortcuts } from './keyboard';

function Harness({ onDispatch }: { onDispatch: (id: string) => void }) {
  useGlobalShortcuts(onDispatch);
  return (
    <div>
      <input data-testid="input" />
      <textarea data-testid="textarea" />
      <select data-testid="select" />
      <div data-testid="editable" contentEditable suppressContentEditableWarning />
      <div className="monaco-editor">
        <div data-testid="monaco-inner">fake editor</div>
      </div>
      <div data-testid="plain" tabIndex={0}>
        plain
      </div>
    </div>
  );
}

function press(target: HTMLElement, key: string, init: Partial<KeyboardEventInit> = {}) {
  fireEvent.keyDown(target, { key, ...init });
}

describe('isTypingTarget', () => {
  it('recognises every typing surface, including a Monaco inner node', () => {
    const { container } = render(
      <div>
        <input data-testid="i" />
        <textarea data-testid="t" />
        <select data-testid="s" />
        <div data-testid="ce" contentEditable suppressContentEditableWarning />
        <div className="monaco-editor">
          <div data-testid="monaco">inside monaco</div>
        </div>
        <div data-testid="plain" />
      </div>,
    );
    const el = (id: string) => container.querySelector(`[data-testid="${id}"]`);
    expect(isTypingTarget(el('i'))).toBe(true);
    expect(isTypingTarget(el('t'))).toBe(true);
    expect(isTypingTarget(el('s'))).toBe(true);
    expect(isTypingTarget(el('ce'))).toBe(true);
    expect(isTypingTarget(el('monaco'))).toBe(true);
    expect(isTypingTarget(el('plain'))).toBe(false);
  });
});

describe('useGlobalShortcuts', () => {
  it('does not fire while typing in an input, textarea, select, contentEditable or Monaco', () => {
    const onDispatch = vi.fn();
    render(<Harness onDispatch={onDispatch} />);

    press(screen.getByTestId('input'), 'b', { ctrlKey: true });
    press(screen.getByTestId('textarea'), 'b', { ctrlKey: true });
    press(screen.getByTestId('select'), 'b', { ctrlKey: true });
    press(screen.getByTestId('editable'), 'b', { ctrlKey: true });
    press(screen.getByTestId('monaco-inner'), 'b', { ctrlKey: true });

    expect(onDispatch).not.toHaveBeenCalled();
  });

  it('dispatches a bound chord from a non-typing target', () => {
    const onDispatch = vi.fn();
    render(<Harness onDispatch={onDispatch} />);
    press(screen.getByTestId('plain'), 'b', { ctrlKey: true });
    expect(onDispatch).toHaveBeenCalledWith('run.build');
  });

  it('leaves a reserved chord (Mod+R) alone — no dispatch', () => {
    const onDispatch = vi.fn();
    render(<Harness onDispatch={onDispatch} />);
    press(screen.getByTestId('plain'), 'r', { ctrlKey: true });
    expect(onDispatch).not.toHaveBeenCalled();
  });

  it('ignores an unmodified letter (ordinary typing) even outside a field', () => {
    const onDispatch = vi.fn();
    render(<Harness onDispatch={onDispatch} />);
    press(screen.getByTestId('plain'), 'b');
    expect(onDispatch).not.toHaveBeenCalled();
  });
});
