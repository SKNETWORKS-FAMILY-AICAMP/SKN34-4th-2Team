import {onCall, HttpsError} from "firebase-functions/v2/https";
import {onSchedule} from "firebase-functions/v2/scheduler";
import * as logger from "firebase-functions/logger";
import {Timestamp} from "firebase-admin/firestore";

import {admin, db, fieldValue} from "./firebase";

type RepeatType = "once" | "daily" | "weekly";

interface ScheduledNoticeData {
  title: string;
  content: string;
  authorId: string;
  authorName: string;
  isFavorite: boolean;
  repeatType: RepeatType;
  publishTime: string;
  publishAt?: FirebaseFirestore.Timestamp;
  weekday?: number;
  isActive: boolean;
  nextPublishAt: FirebaseFirestore.Timestamp;
}

const KST = "Asia/Seoul";

function parsePublishTime(publishTime: string): {hour: number; minute: number} {
  const [h, m] = publishTime.split(":");
  return {
    hour: Number.parseInt(h ?? "9", 10) || 9,
    minute: Number.parseInt(m ?? "0", 10) || 0,
  };
}

function dartWeekdayToJs(dartWeekday: number): number {
  return dartWeekday === 7 ? 0 : dartWeekday;
}

/** KST 기준 날짜·시각 파트 */
function getKstParts(date: Date): {
  year: number;
  month: number;
  day: number;
  hour: number;
  minute: number;
  jsWeekday: number;
} {
  const formatter = new Intl.DateTimeFormat("en-US", {
    timeZone: KST,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    weekday: "short",
    hour12: false,
  });
  const parts = formatter.formatToParts(date);
  const get = (type: Intl.DateTimeFormatPartTypes) =>
    Number.parseInt(parts.find((p) => p.type === type)?.value ?? "0", 10);

  const weekdayShort = parts.find((p) => p.type === "weekday")?.value ?? "Mon";
  const weekdayMap: Record<string, number> = {
    Sun: 0, Mon: 1, Tue: 2, Wed: 3, Thu: 4, Fri: 5, Sat: 6,
  };

  return {
    year: get("year"),
    month: get("month"),
    day: get("day"),
    hour: get("hour"),
    minute: get("minute"),
    jsWeekday: weekdayMap[weekdayShort] ?? 1,
  };
}

/** KST 시각을 UTC Date로 변환 (한국은 DST 없음) */
function kstToUtcDate(
  year: number,
  month: number,
  day: number,
  hour: number,
  minute: number,
): Date {
  return new Date(Date.UTC(year, month - 1, day, hour - 9, minute, 0, 0));
}

function computeNextPublishAt(
  data: ScheduledNoticeData,
  from: Date = new Date(),
): Date | null {
  const {hour, minute} = parsePublishTime(data.publishTime ?? "09:00");

  if (data.repeatType === "once") {
    return null;
  }

  const kst = getKstParts(from);

  if (data.repeatType === "daily") {
    let candidate = kstToUtcDate(kst.year, kst.month, kst.day, hour, minute);
    if (candidate <= from) {
      const nextDay = new Date(
        Date.UTC(kst.year, kst.month - 1, kst.day + 1, hour - 9, minute, 0, 0),
      );
      candidate = nextDay;
    }
    return candidate;
  }

  const targetWeekday = dartWeekdayToJs(data.weekday ?? 1);
  let y = kst.year;
  let m = kst.month;
  let d = kst.day;

  for (let i = 0; i < 8; i++) {
    const candidate = kstToUtcDate(y, m, d, hour, minute);
    const parts = getKstParts(candidate);
    if (parts.jsWeekday === targetWeekday && candidate > from) {
      return candidate;
    }
    d += 1;
    const rollover = new Date(Date.UTC(y, m - 1, d));
    y = rollover.getUTCFullYear();
    m = rollover.getUTCMonth() + 1;
    d = rollover.getUTCDate();
  }

  return kstToUtcDate(kst.year, kst.month, kst.day + 7, hour, minute);
}

async function publishSingleScheduledNotice(
  cohortRef: FirebaseFirestore.DocumentReference,
  scheduledDoc: FirebaseFirestore.DocumentSnapshot,
  now: Date,
): Promise<void> {
  const data = scheduledDoc.data() as ScheduledNoticeData;

  const noticesRef = cohortRef.collection("notices");
  const publishedNoticeRef = noticesRef.doc(`scheduled_${scheduledDoc.id}`);
  const previousNotices = await noticesRef
    .where("scheduledNoticeId", "==", scheduledDoc.id)
    .get();
  const publishBatch = db.batch();

  // 반복 예약 공지는 최신 게시물 하나만 남긴다. 기존 add() 방식으로
  // 생성된 문서도 같은 scheduledNoticeId를 기준으로 함께 정리한다.
  for (const previous of previousNotices.docs) {
    if (previous.ref.path !== publishedNoticeRef.path) {
      publishBatch.delete(previous.ref);
    }
  }

  publishBatch.set(publishedNoticeRef, {
    title: data.title,
    content: data.content,
    authorId: data.authorId,
    authorName: data.authorName,
    isFavorite: data.isFavorite ?? false,
    priority: 0,
    source: "scheduled",
    scheduledNoticeId: scheduledDoc.id,
    createdAt: fieldValue.serverTimestamp(),
    updatedAt: fieldValue.serverTimestamp(),
  });
  await publishBatch.commit();

  if (data.repeatType === "once") {
    await scheduledDoc.ref.update({
      isActive: false,
      lastPublishedAt: fieldValue.serverTimestamp(),
      updatedAt: fieldValue.serverTimestamp(),
    });
  } else {
    const next = computeNextPublishAt(data, now);
    await scheduledDoc.ref.update({
      lastPublishedAt: fieldValue.serverTimestamp(),
      nextPublishAt: next ?
        admin.firestore.Timestamp.fromDate(next) :
        fieldValue.serverTimestamp(),
      updatedAt: fieldValue.serverTimestamp(),
    });
  }

  logger.info("Scheduled notice published", {
    cohortId: cohortRef.id,
    scheduledId: scheduledDoc.id,
    title: data.title,
  });
}

export async function publishSelectedScheduledNotices(
  cohortId: string,
  scheduledIds: string[],
): Promise<{published: number; skipped: number}> {
  const now = new Date();
  let published = 0;
  let skipped = 0;

  const cohortRef = db.collection("cohorts").doc(cohortId);
  const cohortDoc = await cohortRef.get();
  if (!cohortDoc.exists) {
    throw new Error(`Cohort '${cohortId}' not found`);
  }

  const uniqueIds = [...new Set(scheduledIds.filter((id) => id.trim()))];
  for (const id of uniqueIds) {
    const scheduledDoc = await cohortRef.collection("scheduledNotices").doc(id).get();
    if (!scheduledDoc.exists) {
      skipped++;
      continue;
    }

    const data = scheduledDoc.data() as ScheduledNoticeData;
    if (data.isActive !== true) {
      skipped++;
      continue;
    }

    await publishSingleScheduledNotice(cohortRef, scheduledDoc, now);
    published++;
  }

  return {published, skipped};
}

export async function publishDueScheduledNotices(): Promise<{
  published: number;
  cohorts: number;
}> {
  const now = new Date();
  let published = 0;
  const cohortsSnap = await db.collection("cohorts").get();

  for (const cohortDoc of cohortsSnap.docs) {
    const scheduledSnap = await cohortDoc.ref
      .collection("scheduledNotices")
      .where("isActive", "==", true)
      .where("nextPublishAt", "<=", Timestamp.fromDate(now))
      .get();

    for (const scheduledDoc of scheduledSnap.docs) {
      await publishSingleScheduledNotice(cohortDoc.ref, scheduledDoc, now);
      published++;
    }
  }

  return {published, cohorts: cohortsSnap.size};
}

const scheduleOptions = {
  region: "asia-northeast3" as const,
};

/**
 * 1분마다 예약 공지를 실제 notices로 게시
 */
export const publishScheduledNotices = onSchedule(
  {
    ...scheduleOptions,
    schedule: "every 1 minutes",
    timeZone: KST,
  },
  async () => {
    try {
      const result = await publishDueScheduledNotices();
      if (result.published > 0) {
        logger.info("Scheduled notices batch complete", result);
      }
    } catch (error) {
      logger.error("Scheduled notice publish failed", error);
      throw error;
    }
  },
);

/**
 * 관리자 수동 즉시 실행 — 선택한 활성 예약만 게시
 */
export const publishScheduledNoticesNow = onCall(scheduleOptions, async (request) => {
  if (!request.auth) {
    throw new HttpsError("unauthenticated", "인증이 필요합니다.");
  }

  const caller = await db.collection("users").doc(request.auth.uid).get();
  if (!caller.exists || caller.data()?.role !== "admin") {
    throw new HttpsError("permission-denied", "관리자만 실행할 수 있습니다.");
  }

  const {cohortId, scheduledIds} = request.data as {
    cohortId?: string;
    scheduledIds?: string[];
  };

  if (!cohortId || typeof cohortId !== "string") {
    throw new HttpsError("invalid-argument", "cohortId가 필요합니다.");
  }
  if (!Array.isArray(scheduledIds) || scheduledIds.length === 0) {
    throw new HttpsError("invalid-argument", "게시할 예약 공지를 선택해 주세요.");
  }

  try {
    const result = await publishSelectedScheduledNotices(cohortId, scheduledIds);
    return {
      message: "선택한 예약 공지 게시가 완료되었습니다.",
      ...result,
    };
  } catch (error) {
    const msg = error instanceof Error ? error.message : String(error);
    if (msg.includes("not found")) {
      throw new HttpsError("not-found", "기수를 찾을 수 없습니다.");
    }
    throw error;
  }
});
