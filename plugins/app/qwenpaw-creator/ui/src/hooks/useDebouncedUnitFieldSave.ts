import { useEffect, useRef } from 'react';

/**
 * Preserve origin/main's edit-on-change semantics while the new client writes
 * one semantic SET_UNIT_TEXT command per field. Pending values are flushed on
 * unmount so route changes do not silently drop the last edit.
 */
export function useDebouncedUnitFieldSave<T>(
  save: (field: string, value: T) => Promise<unknown> | void,
  delay = 600,
) {
  const saveRef = useRef(save);
  const pendingRef = useRef(new Map<string, T>());
  const timersRef = useRef(new Map<string, ReturnType<typeof setTimeout>>());
  saveRef.current = save;

  const flush = (field: string) => {
    const timer = timersRef.current.get(field);
    if (timer) clearTimeout(timer);
    timersRef.current.delete(field);
    if (!pendingRef.current.has(field)) return;
    const value = pendingRef.current.get(field)!;
    pendingRef.current.delete(field);
    void saveRef.current(field, value);
  };

  const schedule = (field: string, value: T) => {
    pendingRef.current.set(field, value);
    const previous = timersRef.current.get(field);
    if (previous) clearTimeout(previous);
    timersRef.current.set(field, setTimeout(() => flush(field), delay));
  };

  useEffect(() => () => {
    for (const timer of timersRef.current.values()) clearTimeout(timer);
    timersRef.current.clear();
    for (const [field, value] of pendingRef.current) void saveRef.current(field, value);
    pendingRef.current.clear();
  }, []);

  return { schedule, flush };
}
