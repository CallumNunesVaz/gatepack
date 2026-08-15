import { createContext, useContext, type ReactNode } from 'react';
import type { GatepackApi } from '../../shared/api';
import { getApi } from '../api';

const ApiContext = createContext<GatepackApi | null>(null);

export function ApiProvider({ children }: { children: ReactNode }) {
  const api = getApi();
  return <ApiContext.Provider value={api}>{children}</ApiContext.Provider>;
}

export function useApi(): GatepackApi {
  const api = useContext(ApiContext);
  if (!api) {
    throw new Error('useApi must be used inside <ApiProvider>');
  }
  return api;
}
