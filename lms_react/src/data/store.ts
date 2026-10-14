import {
  DemoConfig,
  dateKeyOf,
  seedAiEvals,
  seedAiLogs,
  seedAlertPopups,
  seedAssessmentQuestions,
  seedAssessmentSubmissions,
  seedAssessments,
  seedAttendances,
  seedCohorts,
  seedCurriculumSheets,
  seedFormResponses,
  seedFormTasks,
  seedInflearnPackages,
  seedMileageProducts,
  seedMileageSettings,
  seedMileageTransactions,
  seedNotices,
  seedPosts,
  seedPostComments,
  seedPracticeAttempts,
  seedPracticeReports,
  seedPurchaseRequests,
  seedQualExams,
  seedResumeFeedbacks,
  seedResumes,
  seedScheduledNotices,
  seedProjectTeams,
  seedSeatingAssignments,
  seedSeatingMeta,
  seedSeatingRooms,
  seedStudyNotes,
  seedStudySources,
  seedSubmissions,
  seedTodos,
  seedUsers,
  seedYoutubeRecommendations,
} from './seed';
import { seedPracticeSets } from './practiceSeed';
import type { Database } from './database';

export type { Database };
export { emptyDb } from './database';

/**
 * 메모리 저장소 — Flutter의 `DemoLmsRepository` 자리.
 *
 * Dart 쪽은 StreamController로 화면에 값을 흘려보냈다. 여기서는 스냅샷 하나와
 * 구독자 목록을 두고, 쓰기가 끝날 때마다 새 스냅샷을 만들어 알린다. React는
 * `useSyncExternalStore`로 그 스냅샷을 읽는다 — 불변 객체라 참조 비교가 통한다.
 */

function initial(): Database {
  return {
    users: seedUsers,
    cohorts: seedCohorts,
    notices: seedNotices,
    scheduledNotices: seedScheduledNotices,
    alertPopups: seedAlertPopups,
    posts: seedPosts,
    postComments: seedPostComments,
    todos: seedTodos,
    submissions: seedSubmissions,
    attendances: seedAttendances,
    resumes: seedResumes,
    resumeFeedbacks: seedResumeFeedbacks,
    assessments: seedAssessments,
    assessmentQuestions: seedAssessmentQuestions,
    assessmentSubmissions: seedAssessmentSubmissions,
    inflearnPackages: seedInflearnPackages,
    youtubeRecommendations: seedYoutubeRecommendations,
    studySources: seedStudySources,
    studyNotes: seedStudyNotes,
    curriculumSheets: seedCurriculumSheets,
    curriculumPdfs: [],
    formTasks: seedFormTasks,
    formResponses: seedFormResponses,
    mileageProducts: seedMileageProducts,
    mileageTransactions: seedMileageTransactions,
    purchaseRequests: seedPurchaseRequests,
    mileageSettings: seedMileageSettings,
    seatingRooms: seedSeatingRooms,
    seatingAssignments: seedSeatingAssignments,
    seatingMeta: seedSeatingMeta,
    projectTeams: seedProjectTeams,
    seatPresence: [],
    spotChecks: [],
    attendanceIssues: [],
    qualExams: seedQualExams,
    practiceSets: seedPracticeSets,
    practiceAttempts: seedPracticeAttempts,
    practiceReports: seedPracticeReports,
    practiceReviews: [],
    aiLogs: seedAiLogs,
    aiEvals: seedAiEvals,
    alertDismissals: {},
    alertReadIds: [],
  };
}

let db: Database = initial();
const listeners = new Set<() => void>();

export function getDb(): Database {
  return db;
}

export function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/** 쓰기는 모두 여기를 지난다. 스냅샷을 새로 만들고 구독자에게 알린다. */
export function mutate(change: (current: Database) => Partial<Database>): void {
  db = { ...db, ...change(db) };
  listeners.forEach((l) => l());
}

export function resetDb(): void {
  db = initial();
  listeners.forEach((l) => l());
}

export function nextId(prefix: string): string {
  return `${prefix}-${Math.random().toString(36).slice(2, 9)}`;
}

export const todayKey = (): string => dateKeyOf(new Date());

export { DemoConfig };
