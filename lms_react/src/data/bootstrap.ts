import { http } from './http';
import { queryClient, queryKeys } from './queryClient';
import { mapBootstrap } from './bootstrapMap';
import type { Database } from './database';

export {
  mapAlert,
  mapAttendanceIssue,
  mapBootstrap,
  mapCohort,
  mapNotice,
  mapQualExams,
  mapScheduled,
  mapSpotCheck,
  mapStudyNote,
  mapUser,
  parseJsonb,
} from './bootstrapMap';

let lastSessionUid = '';
let lastSessionCohortId = '';

export function lastBootstrapSession(): { uid: string; cohortId: string } {
  return { uid: lastSessionUid, cohortId: lastSessionCohortId };
}

/** bootstrap 은 문제 본문을 뺀 세트를 보낸다. 이미 받아 둔 본문은 다시 받을 때 덮지 않는다(열린 연습장이 깨지지 않게) */
function keepFullSets(db: Database): Database {
  const prev = queryClient.getQueryData<Database>(queryKeys.bootstrap);
  const full = new Map((prev?.practiceSets ?? []).filter((s) => !s.partial).map((s) => [s.id, s]));
  if (full.size === 0) return db;
  return { ...db, practiceSets: db.practiceSets.map((s) => (s.partial ? full.get(s.id) ?? s : s)) };
}

export async function fetchBootstrap(): Promise<Database> {
  const { data } = await http.get<Record<string, unknown>>('/bootstrap');
  const db = keepFullSets(mapBootstrap(data));
  const me = (data.me ?? {}) as Record<string, unknown>;
  lastSessionUid = String(me.uid ?? me.firebase_uid ?? '');
  lastSessionCohortId = String(me.cohortId ?? db.cohorts[0]?.cohortId ?? '');
  return db;
}
