import { useRef, useState } from 'react';
import type { Resume } from '../../domain/types';

/** Bootstrap remains authoritative except while this editor has unsaved changes. */
export function useResumeDraft(server: Resume | undefined) {
  const [draft, setDraft] = useState<Resume>();
  const current = useRef<Resume>();
  const version = useRef(0);
  const id = useRef(server?.id);
  if (id.current !== server?.id) {
    id.current = server?.id;
    version.current += 1;
    current.current = undefined;
    if (draft) setDraft(undefined);
  }
  const resume = draft?.id === server?.id ? draft : server;
  current.current = resume;
  return {
    resume,
    edit(change: Partial<Resume>) {
      if (!current.current) return;
      version.current += 1;
      current.current = { ...current.current, ...change };
      setDraft(current.current);
    },
    saveVersion: () => version.current,
    finishSave(savedVersion: number) {
      // Typing during an in-flight save must remain dirty.
      if (savedVersion === version.current) setDraft(undefined);
    },
  };
}
