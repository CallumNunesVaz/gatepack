/**
 * Toast — the imperatively-triggered notification strip.
 *
 * Used by the shell for one thing today: reporting that a command id reached
 * the dispatcher but no panel has wired it yet ("not yet wired"). It is a
 * provider + hook so any component can push a message without threading a
 * callback prop through the tree.
 */

import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react';
import { Icon, type IconName } from './Icon';

export type ToastKind = 'info' | 'success' | 'error';

export interface ToastData {
  id: number;
  kind: ToastKind;
  message: ReactNode;
}

const AUTO_DISMISS_MS = 4200;
const MAX_VISIBLE = 4;

const ICONS: Record<ToastKind, IconName> = {
  info: 'info',
  success: 'check',
  error: 'error',
};

interface ToastContextValue {
  push: (message: ReactNode, kind?: ToastKind) => void;
}

const ToastContext = createContext<ToastContextValue | null>(null);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastData[]>([]);
  const nextId = useRef(0);
  const timers = useRef(new Map<number, ReturnType<typeof setTimeout>>());

  const dismiss = useCallback((id: number) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
    const timer = timers.current.get(id);
    if (timer) {
      clearTimeout(timer);
      timers.current.delete(id);
    }
  }, []);

  const push = useCallback(
    (message: ReactNode, kind: ToastKind = 'info') => {
      nextId.current += 1;
      const id = nextId.current;
      setToasts((prev) => [...prev.slice(-(MAX_VISIBLE - 1)), { id, kind, message }]);
      timers.current.set(id, setTimeout(() => dismiss(id), AUTO_DISMISS_MS));
    },
    [dismiss],
  );

  const value = useMemo(() => ({ push }), [push]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className="gp-toast-stack" role="region" aria-label="notifications">
        {toasts.map((t) => (
          <div
            key={t.id}
            className={`gp-toast gp-toast--${t.kind}`}
            data-kind={t.kind}
            role="status"
          >
            <Icon name={ICONS[t.kind]} size={16} decorative />
            <span className="gp-toast__msg">{t.message}</span>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast(): ToastContextValue {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error('useToast must be used inside <ToastProvider>');
  return ctx;
}
