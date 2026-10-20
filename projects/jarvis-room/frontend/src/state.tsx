import { createContext, useContext, useEffect, useMemo, useState, useSyncExternalStore, type ReactNode } from 'react';
import { DemoSource, ReadOnlyEventSource } from './data/source';
import type { PresentationSource } from './contracts';

const Context = createContext<{ source: PresentationSource; mode: 'demo' | 'backend'; setMode: (mode: 'demo' | 'backend') => void } | null>(null);
export function PresentationProvider({ children }: { children: ReactNode }) {
  const [mode, setMode] = useState<'demo' | 'backend'>('demo');
  const source = useMemo(() => mode === 'demo' ? new DemoSource() : new ReadOnlyEventSource(), [mode]);
  useEffect(() => { source.activate(); return () => source.dispose(); }, [source]);
  return <Context.Provider value={{ source, mode, setMode }}>{children}</Context.Provider>;
}
export function usePresentation() {
  const context = useContext(Context);
  if (!context) throw new Error('presentation_provider_missing');
  const snapshot = useSyncExternalStore(context.source.subscribe, context.source.getSnapshot, context.source.getSnapshot);
  return { ...context, snapshot, demo: context.source instanceof DemoSource ? context.source : null };
}
export function useVisibility() {
  const [visible, setVisible] = useState(() => !document.hidden);
  useEffect(() => { const update = () => setVisible(!document.hidden); document.addEventListener('visibilitychange', update); return () => document.removeEventListener('visibilitychange', update); }, []);
  return visible;
}
export function useReducedMotion() {
  const [reduced, setReduced] = useState(() => matchMedia('(prefers-reduced-motion: reduce)').matches);
  useEffect(() => { const query = matchMedia('(prefers-reduced-motion: reduce)'); const update = () => setReduced(query.matches); query.addEventListener('change', update); return () => query.removeEventListener('change', update); }, []);
  return reduced;
}
