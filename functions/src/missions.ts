import {Timestamp} from "firebase-admin/firestore";
import * as logger from "firebase-functions/logger";

import {db, fieldValue} from "./firebase";

/** 예수학제(학습인증) 티어: 횟수 → 목표 적립액 */
export const STUDY_CERT_TIERS: Array<{count: number; amount: number}> = [
  {count: 3, amount: 10000},
  {count: 5, amount: 30000},
  {count: 10, amount: 50000},
];

/** 프리코스 퀴즈 티어 (60점 이상 횟수) */
export const QUIZ_TIERS: Array<{count: number; amount: number}> = [
  {count: 1, amount: 10000},
  {count: 3, amount: 30000},
  {count: 5, amount: 50000},
];

export const BLOG_UNIT_REWARD = 20000;
export const BLOG_MAX_UNITS = 5;
export const STUDY_TEAM_REWARD = 50000;
export const CODING_PCCE = 25000;
export const CODING_ADVANCED = 50000;
export const QUIZ_PASS_SCORE = 60;

export type MissionProgress = {
  studyCertCount: number;
  studyCertGranted: number;
  quizPassCount: number;
  quizGranted: number;
  codingPcce: boolean;
  codingPccp: boolean;
  codingPcsql: boolean;
  codingGranted: number;
  blogWeeks: number[];
  blogUnitsGranted: number[];
  studyWeekKeys: string[];
  studyGranted: boolean;
};

export function emptyProgress(): MissionProgress {
  return {
    studyCertCount: 0,
    studyCertGranted: 0,
    quizPassCount: 0,
    quizGranted: 0,
    codingPcce: false,
    codingPccp: false,
    codingPcsql: false,
    codingGranted: 0,
    blogWeeks: [],
    blogUnitsGranted: [],
    studyWeekKeys: [],
    studyGranted: false,
  };
}

export function progressFromData(data: FirebaseFirestore.DocumentData | undefined): MissionProgress {
  const p = emptyProgress();
  if (!data) return p;
  return {
    studyCertCount: (data.studyCertCount as number) ?? 0,
    studyCertGranted: (data.studyCertGranted as number) ?? 0,
    quizPassCount: (data.quizPassCount as number) ?? 0,
    quizGranted: (data.quizGranted as number) ?? 0,
    codingPcce: data.codingPcce === true,
    codingPccp: data.codingPccp === true,
    codingPcsql: data.codingPcsql === true,
    codingGranted: (data.codingGranted as number) ?? 0,
    blogWeeks: Array.isArray(data.blogWeeks) ?
      (data.blogWeeks as number[]) :
      [],
    blogUnitsGranted: Array.isArray(data.blogUnitsGranted) ?
      (data.blogUnitsGranted as number[]) :
      [],
    studyWeekKeys: Array.isArray(data.studyWeekKeys) ?
      (data.studyWeekKeys as string[]) :
      [],
    studyGranted: data.studyGranted === true,
  };
}

function tierTarget(
  count: number,
  tiers: Array<{count: number; amount: number}>,
): number {
  let target = 0;
  for (const t of tiers) {
    if (count >= t.count) target = t.amount;
  }
  return target;
}

function addMonths(date: Date, months: number): Date {
  const d = new Date(date.getTime());
  d.setMonth(d.getMonth() + months);
  return d;
}

function startOfDay(d: Date): Date {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate());
}

function toDate(raw: unknown): Date | null {
  if (!raw) return null;
  if (raw instanceof Timestamp) return raw.toDate();
  if (raw instanceof Date) return raw;
  if (typeof raw === "string") {
    const d = new Date(raw);
    return Number.isNaN(d.getTime()) ? null : d;
  }
  return null;
}

/** 단위기간 1~6 (개강일 기준 한 달 롤링) */
export function unitPeriods(
  cohortStart: Date,
  cohortEnd?: Date | null,
): Array<{index: number; start: Date; end: Date}> {
  const start = startOfDay(cohortStart);
  const periods: Array<{index: number; start: Date; end: Date}> = [];
  for (let i = 1; i <= 6; i++) {
    const uStart = addMonths(start, i - 1);
    let uEnd = new Date(addMonths(start, i).getTime() - 24 * 60 * 60 * 1000);
    if (i === 6 && cohortEnd) {
      uEnd = startOfDay(cohortEnd);
    }
    periods.push({index: i, start: uStart, end: uEnd});
  }
  return periods;
}

function weekStartsInRange(rangeStart: Date, rangeEnd: Date, cohortStart: Date): Date[] {
  const weeks: Date[] = [];
  let cursor = startOfDay(cohortStart);
  // advance to first week start that is >= rangeStart (or still overlapping)
  while (cursor.getTime() + 6 * 24 * 60 * 60 * 1000 < rangeStart.getTime()) {
    cursor = new Date(cursor.getTime() + 7 * 24 * 60 * 60 * 1000);
    if (cursor > rangeEnd) return weeks;
  }
  while (cursor <= rangeEnd) {
    weeks.push(cursor);
    cursor = new Date(cursor.getTime() + 7 * 24 * 60 * 60 * 1000);
  }
  return weeks;
}

/** 블로그 weekNumber → 주차 시작일 (기수 시작 기준) */
export function blogWeekStart(cohortStart: Date, weekNumber: number): Date {
  const start = startOfDay(cohortStart);
  return new Date(start.getTime() + (weekNumber - 1) * 7 * 24 * 60 * 60 * 1000);
}

function weekNumbersForUnit(
  unit: {start: Date; end: Date},
  cohortStart: Date,
): number[] {
  const nums: number[] = [];
  for (let n = 1; n <= 30; n++) {
    const ws = blogWeekStart(cohortStart, n);
    if (ws > unit.end) break;
    if (ws >= unit.start && ws <= unit.end) {
      nums.push(n);
    }
  }
  return nums;
}

function isoWeekKey(d: Date): string {
  const date = startOfDay(d);
  // ISO week: Thursday-based year
  const tmp = new Date(date.getTime());
  tmp.setDate(tmp.getDate() + 3 - ((tmp.getDay() + 6) % 7));
  const week1 = new Date(tmp.getFullYear(), 0, 4);
  const week =
    1 +
    Math.round(
      ((tmp.getTime() - week1.getTime()) / 86400000 -
        3 +
        ((week1.getDay() + 6) % 7)) /
        7,
    );
  return `${tmp.getFullYear()}-W${String(week).padStart(2, "0")}`;
}

function requiredStudyWeekKeys(
  cohortStart: Date,
  cohortEnd: Date | null | undefined,
): string[] {
  const periods = unitPeriods(cohortStart, cohortEnd);
  const u1 = periods[0];
  const u2 = periods[1];
  const rangeStart = u1.start;
  const rangeEnd = u2.end;
  const weeks = weekStartsInRange(rangeStart, rangeEnd, cohortStart);
  return weeks.map((w) => isoWeekKey(w));
}

function codingTarget(p: MissionProgress): number {
  if (p.codingPccp || p.codingPcsql) return CODING_ADVANCED;
  if (p.codingPcce) return CODING_PCCE;
  return 0;
}

type GrantItem = {amount: number; reason: string; missionKey: string};

function pushDiff(
  grants: GrantItem[],
  already: number,
  target: number,
  reason: string,
  missionKey: string,
): number {
  const diff = target - already;
  if (diff > 0) {
    grants.push({amount: diff, reason, missionKey});
    return target;
  }
  return already;
}

export type SettleResult = {
  grantedTotal: number;
  grants: GrantItem[];
  progress: MissionProgress;
};

/**
 * 승인된 제출 1건을 반영해 미션 진행도를 갱신하고, 지급할 차액을 계산한다.
 * (트랜잭션 밖에서 순수 계산 — 호출측에서 progress/잔액 반영)
 */
export function computeMissionSettlement(params: {
  progress: MissionProgress;
  submission: FirebaseFirestore.DocumentData;
  cohortStart: Date | null;
  cohortEnd: Date | null;
}): SettleResult {
  const progress = {...params.progress, blogWeeks: [...params.progress.blogWeeks],
    blogUnitsGranted: [...params.progress.blogUnitsGranted],
    studyWeekKeys: [...params.progress.studyWeekKeys]};
  const grants: GrantItem[] = [];
  const type = params.submission.type as string;
  const title = (params.submission.title as string) ?? type;

  if (type === "studyCert") {
    progress.studyCertCount += 1;
    const target = tierTarget(progress.studyCertCount, STUDY_CERT_TIERS);
    progress.studyCertGranted = pushDiff(
      grants,
      progress.studyCertGranted,
      target,
      `학습인증 ${progress.studyCertCount}회 달성 적립`,
      "studyCert",
    );
  } else if (type === "precourseQuiz") {
    const score = (params.submission.quizScore as number) ?? 0;
    if (score >= QUIZ_PASS_SCORE) {
      progress.quizPassCount += 1;
      const target = tierTarget(progress.quizPassCount, QUIZ_TIERS);
      progress.quizGranted = pushDiff(
        grants,
        progress.quizGranted,
        target,
        `프리코스 퀴즈 60점↑ ${progress.quizPassCount}회 달성 적립`,
        "precourseQuiz",
      );
    }
  } else if (type === "certification") {
    const cert = ((params.submission.certType as string) ?? "").toUpperCase();
    if (cert === "PCCE") progress.codingPcce = true;
    if (cert === "PCCP") progress.codingPccp = true;
    if (cert === "PCSQL") progress.codingPcsql = true;
    const target = codingTarget(progress);
    progress.codingGranted = pushDiff(
      grants,
      progress.codingGranted,
      target,
      `코딩테스트(${cert || title}) 적립`,
      "coding",
    );
  } else if (type === "blog") {
    const weekNumber = params.submission.weekNumber as number | undefined;
    if (weekNumber != null && !progress.blogWeeks.includes(weekNumber)) {
      progress.blogWeeks.push(weekNumber);
      progress.blogWeeks.sort((a, b) => a - b);
    }
    if (params.cohortStart) {
      const periods = unitPeriods(params.cohortStart, params.cohortEnd)
        .filter((u) => u.index >= 1 && u.index <= BLOG_MAX_UNITS);
      for (const unit of periods) {
        if (progress.blogUnitsGranted.includes(unit.index)) continue;
        const needed = weekNumbersForUnit(unit, params.cohortStart);
        if (needed.length === 0) continue;
        const done = needed.every((n) => progress.blogWeeks.includes(n));
        if (done) {
          progress.blogUnitsGranted.push(unit.index);
          grants.push({
            amount: BLOG_UNIT_REWARD,
            reason: `블로그 ${unit.index}단위기간 전 주차 작성 적립`,
            missionKey: `blog:unit${unit.index}`,
          });
        }
      }
    }
  } else if (type === "study") {
    const isTeam = params.submission.isTeamStudy !== false;
    // 명시적으로 false면 미션 미반영 (개인 스터디)
    if (params.submission.isTeamStudy === false) {
      // no-op for mission
    } else if (isTeam && params.cohortStart) {
      const studyDate =
        toDate(params.submission.startAt) ?? toDate(params.submission.submittedAt);
      if (studyDate) {
        const key = isoWeekKey(studyDate);
        if (!progress.studyWeekKeys.includes(key)) {
          progress.studyWeekKeys.push(key);
        }
      }
      if (!progress.studyGranted) {
        const required = requiredStudyWeekKeys(
          params.cohortStart,
          params.cohortEnd,
        );
        const ok =
          required.length > 0 &&
          required.every((k) => progress.studyWeekKeys.includes(k));
        if (ok) {
          progress.studyGranted = true;
          grants.push({
            amount: STUDY_TEAM_REWARD,
            reason: "팀 스터디 1~2단위기간 주 1회 이상 인증 적립",
            missionKey: "studyTeam",
          });
        }
      }
    }
  }

  const grantedTotal = grants.reduce((s, g) => s + g.amount, 0);
  return {grantedTotal, grants, progress};
}

/**
 * 기록실 승인 시 미션 정산 + 마일리지 적립
 */
export async function settleMissionsOnApproval(params: {
  cohortId: string;
  submissionId: string;
  submission: FirebaseFirestore.DocumentData;
  reviewedBy: string;
}): Promise<SettleResult> {
  const {cohortId, submissionId, submission, reviewedBy} = params;
  const userId = submission.userId as string;

  const cohortDoc = await db.collection("cohorts").doc(cohortId).get();
  const cohortStart = toDate(cohortDoc.data()?.startDate);
  const cohortEnd = toDate(cohortDoc.data()?.endDate);

  const progressRef = db
    .collection("cohorts")
    .doc(cohortId)
    .collection("missionProgress")
    .doc(userId);
  const subRef = db
    .collection("cohorts")
    .doc(cohortId)
    .collection("submissions")
    .doc(submissionId);
  const userRef = db.collection("users").doc(userId);

  return db.runTransaction(async (tx) => {
    const subSnap = await tx.get(subRef);
    if (!subSnap.exists) {
      return {grantedTotal: 0, grants: [], progress: emptyProgress()};
    }
    if (subSnap.data()?.mileageGranted === true) {
      return {
        grantedTotal: 0,
        grants: [],
        progress: progressFromData((await tx.get(progressRef)).data()),
      };
    }

    const progressSnap = await tx.get(progressRef);
    const userSnap = await tx.get(userRef);
    const userDisplayName =
      (userSnap.data()?.displayName as string | undefined) ??
      (submission.userDisplayName as string | undefined) ??
      "";
    const before = progressFromData(progressSnap.data());
    const settled = computeMissionSettlement({
      progress: before,
      submission,
      cohortStart,
      cohortEnd,
    });

    tx.set(
      progressRef,
      {
        ...settled.progress,
        updatedAt: fieldValue.serverTimestamp(),
      },
      {merge: true},
    );

    tx.update(subRef, {
      mileageGranted: true,
      mileageAmount: settled.grantedTotal,
    });

    if (settled.grantedTotal > 0) {
      tx.update(userRef, {
        mileageBalance: fieldValue.increment(settled.grantedTotal),
        updatedAt: fieldValue.serverTimestamp(),
      });

      for (const g of settled.grants) {
        const txRef = db
          .collection("cohorts")
          .doc(cohortId)
          .collection("mileageTransactions")
          .doc();
        tx.set(txRef, {
          userId,
          userDisplayName,
          amount: g.amount,
          reason: g.reason,
          type: "accrual",
          relatedId: submissionId,
          missionKey: g.missionKey,
          adjustedBy: reviewedBy,
          createdAt: fieldValue.serverTimestamp(),
        });
      }
    }

    logger.info("mission settle", {
      cohortId,
      submissionId,
      userId,
      type: submission.type,
      grantedTotal: settled.grantedTotal,
    });

    return settled;
  });
}
