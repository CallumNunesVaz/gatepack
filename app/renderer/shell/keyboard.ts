/**
 * The global shortcut handler, driven entirely by `keys/registry.ts`.
 *
 * It is one `keydown` listener on `window`, matching each event against
 * `COMMANDS` via `matchesChord`. Two rules that keep it from ruining the app:
 *
 *  1. It never fires while the user is typing — focus in an `<input>`,
 *     `<textarea>`, `<select>`, a `contentEditable`, or a Monaco editor
 *     (`.monaco-editor`) makes the handler a no-op for that event.
 *  2. It only intercepts chords that are actually in `COMMANDS`. Anything else
 *     (including Electron/browser-reserved chords like Mod+R, Mod+W, F5) is left
 *     to the host.
 */

import { useEffect } from 'react';
import { COMMANDS, matchesChord } from '../keys/registry';

export function isTypingTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  if (target.isContentEditable) return true;
  // jsdom does not implement `isContentEditable`, so read the attribute too.
  const contentEditable = target.getAttribute('contenteditable');
  if (contentEditable !== null && contentEditable !== 'false') return true;
  const tag = target.tagName;
  if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return true;
  // Monaco renders a `.monaco-editor` shell around its hidden textarea; match on
  // the container so a focus move within the editor can never leak a shortcut.
  if (target.closest('.monaco-editor')) return true;
  return false;
}

export function useGlobalShortcuts(dispatch: (id: string) => void): void {
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (isTypingTarget(e.target)) return;
      for (const command of COMMANDS) {
        if (command.keys && matchesChord(e, command.keys)) {
          e.preventDefault();
          dispatch(command.id);
          return;
        }
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [dispatch]);
}
