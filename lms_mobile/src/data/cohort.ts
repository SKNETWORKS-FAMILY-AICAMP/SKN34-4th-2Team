import AsyncStorage from '@react-native-async-storage/async-storage';
import { useEffect, useState } from 'react';

const KEY = 'lms.selectedCohort';

interface Selection {
  uid: string;
  cohortId: string;
}

let current: Selection | null = null;
const listeners = new Set<() => void>();

async function load(): Promise<void> {
  try {
    const raw = await AsyncStorage.getItem(KEY);
    const parsed = raw === null ? null : (JSON.parse(raw) as Partial<Selection>);
    current = parsed?.uid && parsed.cohortId ? { uid: parsed.uid, cohortId: parsed.cohortId } : null;
  } catch {
    current = null;
  }
  listeners.forEach((listener) => listener());
}

void load();

export function selectedCohortFor(uid: string | undefined): string | undefined {
  if (!uid || current?.uid !== uid) return undefined;
  return current.cohortId;
}

export async function selectCohort(uid: string, cohortId: string): Promise<void> {
  current = { uid, cohortId };
  await AsyncStorage.setItem(KEY, JSON.stringify(current));
  listeners.forEach((listener) => listener());
}

export function useSelectedCohort(uid: string | undefined): string | undefined {
  const [cohortId, setCohortId] = useState(() => selectedCohortFor(uid));
  useEffect(() => {
    const sync = () => setCohortId(selectedCohortFor(uid));
    listeners.add(sync);
    sync();
    return () => {
      listeners.delete(sync);
    };
  }, [uid]);
  return cohortId;
}
