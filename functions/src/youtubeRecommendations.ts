import {onCall, HttpsError} from "firebase-functions/v2/https";
import * as logger from "firebase-functions/logger";
import * as https from "https";

import {db, fieldValue} from "./firebase";

const REGION = "asia-northeast3";
const CACHE_TTL_MS = 12 * 60 * 60 * 1000; // 12h
const CACHE_VERSION = "v2";
const MAX_QUERIES = 5;
const RESULTS_PER_QUERY = 6;
const MAX_VIDEOS = 12;

interface CurriculumRow {
  dayIndex?: number;
  dateLabel?: string;
  subject?: string;
  topic?: string;
  detail?: string;
  order?: number;
}

export interface YoutubeVideoItem {
  videoId: string;
  title: string;
  channelTitle: string;
  thumbnailUrl: string;
  publishedAt: string | null;
  query: string;
  topicLabel: string;
}

function parseKoreanDateLabel(label: string): Date | null {
  const m = label.match(/(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일/);
  if (!m) return null;
  return new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
}

function startOfWeekMonday(d: Date): Date {
  const copy = new Date(d.getFullYear(), d.getMonth(), d.getDate());
  const day = copy.getDay(); // 0=Sun
  const diff = day === 0 ? -6 : 1 - day;
  copy.setDate(copy.getDate() + diff);
  copy.setHours(0, 0, 0, 0);
  return copy;
}

function endOfWeekSunday(monday: Date): Date {
  const end = new Date(monday);
  end.setDate(monday.getDate() + 6);
  end.setHours(23, 59, 59, 999);
  return end;
}

function weekKeyFromMonday(monday: Date): string {
  const y = monday.getFullYear();
  const m = String(monday.getMonth() + 1).padStart(2, "0");
  const d = String(monday.getDate()).padStart(2, "0");
  return `${y}${m}${d}`;
}

function uniqueParts(...values: string[]): string[] {
  const unique: string[] = [];
  for (const raw of values) {
    const p = raw.trim();
    if (!p) continue;
    if (unique.some((u) => u.toLowerCase() === p.toLowerCase())) continue;
    unique.push(p);
  }
  return unique;
}

function joinQuery(...values: string[]): string {
  return uniqueParts(...values).join(" ").replace(/\s+/g, " ").trim();
}

/** 같은 주제에 서로 다른 검색어를 만들어 YouTube 결과 겹침을 줄인다. */
function buildQueryVariants(row: CurriculumRow): string[] {
  const subject = (row.subject ?? "").trim();
  const topic = (row.topic ?? "").trim();
  const detail = (row.detail ?? "").trim();
  const specific = joinQuery(subject, topic, detail);
  const mid = joinQuery(subject, topic);
  const focus =
    detail && detail.toLowerCase() !== topic.toLowerCase()
      ? joinQuery(subject, detail)
      : mid;

  const variants = [
    `${specific} 강의`,
    `${mid} 튜토리얼`,
    `${focus} 개념 정리`,
  ]
    .map((q) => q.replace(/\s+/g, " ").trim())
    .filter((q) => q.length > 4);

  const seen = new Set<string>();
  const unique: string[] = [];
  for (const q of variants) {
    const key = q.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    unique.push(q);
  }
  return unique;
}

function topicLabel(row: CurriculumRow): string {
  const topic = (row.topic ?? "").trim();
  const subject = (row.subject ?? "").trim();
  if (topic && subject && topic !== subject) return `${subject} · ${topic}`;
  return topic || subject || "커리큘럼";
}

function rowKey(row: CurriculumRow): string {
  return `${(row.subject ?? "").trim()}|${(row.topic ?? "").trim()}|${(row.detail ?? "").trim()}`;
}

function uniquifyRows(rows: CurriculumRow[]): CurriculumRow[] {
  const seen = new Set<string>();
  const unique: CurriculumRow[] = [];
  for (const r of rows) {
    const key = rowKey(r);
    if (!key.replace(/\|/g, "").trim() || seen.has(key)) continue;
    seen.add(key);
    unique.push(r);
  }
  return unique;
}

function pickCurrentRows(rows: CurriculumRow[], now = new Date()): {
  weekStart: Date;
  weekEnd: Date;
  weekKey: string;
  rows: CurriculumRow[];
} {
  const weekStart = startOfWeekMonday(now);
  const weekEnd = endOfWeekSunday(weekStart);
  const weekKey = weekKeyFromMonday(weekStart);

  const dated = rows
    .map((r) => ({row: r, date: parseKoreanDateLabel(r.dateLabel ?? "")}))
    .filter((x): x is {row: CurriculumRow; date: Date} => x.date != null);

  let inWeek = dated
    .filter((x) => x.date >= weekStart && x.date <= weekEnd)
    .sort((a, b) => a.date.getTime() - b.date.getTime())
    .map((x) => x.row);

  if (inWeek.length === 0 && dated.length > 0) {
    // 폴백: 오늘과 가장 가까운 날짜의 행들
    dated.sort(
      (a, b) =>
        Math.abs(a.date.getTime() - now.getTime()) -
        Math.abs(b.date.getTime() - now.getTime()),
    );
    const nearest = dated[0].date;
    const windowStart = new Date(nearest);
    windowStart.setDate(nearest.getDate() - 2);
    windowStart.setHours(0, 0, 0, 0);
    const windowEnd = new Date(nearest);
    windowEnd.setDate(nearest.getDate() + 3);
    windowEnd.setHours(23, 59, 59, 999);
    inWeek = dated
      .filter((x) => x.date >= windowStart && x.date <= windowEnd)
      .map((x) => x.row);
    if (inWeek.length === 0) {
      inWeek = dated.slice(0, MAX_QUERIES).map((x) => x.row);
    }
  }

  let uniqueRows = uniquifyRows(inWeek);

  // 이번 주 주제가 적으면 가까운 날짜의 다른 주제로 채움
  if (uniqueRows.length < MAX_QUERIES && dated.length > 0) {
    const byDistance = [...dated].sort(
      (a, b) =>
        Math.abs(a.date.getTime() - now.getTime()) -
        Math.abs(b.date.getTime() - now.getTime()),
    );
    const seen = new Set(uniqueRows.map(rowKey));
    for (const x of byDistance) {
      if (uniqueRows.length >= MAX_QUERIES) break;
      const key = rowKey(x.row);
      if (!key.replace(/\|/g, "").trim() || seen.has(key)) continue;
      seen.add(key);
      uniqueRows.push(x.row);
    }
  }

  return {
    weekStart,
    weekEnd,
    weekKey,
    rows: uniqueRows.slice(0, MAX_QUERIES),
  };
}

interface SearchQuery {
  query: string;
  label: string;
  duration: "medium" | "long";
}

/** 1차: 주제별 대표 검색 → 2차: 같은 주제의 다른 검색어로 슬롯을 채움 */
function buildSearchQueries(rows: CurriculumRow[]): SearchQuery[] {
  const perRow = rows.map((r) => ({
    label: topicLabel(r),
    variants: buildQueryVariants(r),
  }));
  const queries: SearchQuery[] = [];
  const seen = new Set<string>();

  const push = (query: string, label: string, duration: "medium" | "long") => {
    const key = query.toLowerCase();
    if (query.length <= 2 || seen.has(key) || queries.length >= MAX_QUERIES) {
      return;
    }
    seen.add(key);
    queries.push({query, label, duration});
  };

  for (const item of perRow) {
    if (item.variants[0]) push(item.variants[0], item.label, "medium");
  }
  for (const item of perRow) {
    if (item.variants[1]) push(item.variants[1], item.label, "long");
  }
  for (const item of perRow) {
    for (const variant of item.variants.slice(2)) {
      push(variant, item.label, "medium");
    }
  }
  return queries;
}

function interleaveByTopic(
  videos: YoutubeVideoItem[],
  limit: number,
): YoutubeVideoItem[] {
  const groups = new Map<string, YoutubeVideoItem[]>();
  const order: string[] = [];
  for (const v of videos) {
    const key = v.topicLabel || "_";
    if (!groups.has(key)) {
      groups.set(key, []);
      order.push(key);
    }
    groups.get(key)!.push(v);
  }

  const result: YoutubeVideoItem[] = [];
  let i = 0;
  while (result.length < limit) {
    let added = false;
    for (const key of order) {
      const group = groups.get(key) ?? [];
      if (i < group.length) {
        result.push(group[i]);
        added = true;
        if (result.length >= limit) break;
      }
    }
    if (!added) break;
    i += 1;
  }
  return result;
}

function httpsGetJson(url: string): Promise<unknown> {
  return new Promise((resolve, reject) => {
    https
      .get(url, (res) => {
        let body = "";
        res.on("data", (chunk) => {
          body += chunk;
        });
        res.on("end", () => {
          try {
            resolve(JSON.parse(body));
          } catch (e) {
            reject(e);
          }
        });
      })
      .on("error", reject);
  });
}

async function searchYoutube(
  apiKey: string,
  query: string,
  duration?: "medium" | "long",
): Promise<YoutubeVideoItem[]> {
  const params = new URLSearchParams({
    part: "snippet",
    type: "video",
    maxResults: String(RESULTS_PER_QUERY),
    q: query,
    key: apiKey,
    relevanceLanguage: "ko",
    regionCode: "KR",
    safeSearch: "moderate",
  });
  if (duration) {
    params.set("videoDuration", duration);
  }
  const url = `https://www.googleapis.com/youtube/v3/search?${params}`;
  const raw = (await httpsGetJson(url)) as {
    error?: {message?: string};
    items?: Array<{
      id?: {videoId?: string};
      snippet?: {
        title?: string;
        channelTitle?: string;
        publishedAt?: string;
        thumbnails?: {
          medium?: {url?: string};
          high?: {url?: string};
          default?: {url?: string};
        };
      };
    }>;
  };

  if (raw.error?.message) {
    throw new Error(raw.error.message);
  }

  const items: YoutubeVideoItem[] = [];
  for (const item of raw.items ?? []) {
    const videoId = item.id?.videoId;
    if (!videoId) continue;
    const sn = item.snippet ?? {};
    const thumb =
      sn.thumbnails?.medium?.url ??
      sn.thumbnails?.high?.url ??
      sn.thumbnails?.default?.url ??
      `https://img.youtube.com/vi/${videoId}/hqdefault.jpg`;
    items.push({
      videoId,
      title: sn.title ?? "",
      channelTitle: sn.channelTitle ?? "",
      thumbnailUrl: thumb,
      publishedAt: sn.publishedAt ?? null,
      query,
      topicLabel: "",
    });
  }
  return items;
}

/**
 * 학생/관리자 — 현재 커리큘럼 주차 기반 YouTube 추천
 */
export const getCurriculumYoutubeRecommendations = onCall(
  {region: REGION, timeoutSeconds: 60},
  async (request) => {
    if (!request.auth) {
      throw new HttpsError("unauthenticated", "인증이 필요합니다.");
    }

    const {cohortId} = request.data as {cohortId?: string};
    if (!cohortId?.trim()) {
      throw new HttpsError("invalid-argument", "cohortId는 필수입니다.");
    }

    const uid = request.auth.uid;
    const userDoc = await db.collection("users").doc(uid).get();
    if (!userDoc.exists || userDoc.data()?.isActive !== true) {
      throw new HttpsError("permission-denied", "활성 사용자만 이용할 수 있습니다.");
    }
    const userData = userDoc.data()!;
    const role = userData.role as string;
    const userCohort = userData.cohortId as string | undefined;
    if (role !== "admin" && userCohort !== cohortId) {
      throw new HttpsError("permission-denied", "해당 기수 추천에 접근할 수 없습니다.");
    }

    const sheetsSnap = await db
      .collection("cohorts")
      .doc(cohortId)
      .collection("curriculumSheets")
      .orderBy("uploadedAt", "desc")
      .limit(1)
      .get();

    if (sheetsSnap.empty) {
      return {
        weekKey: null,
        weekLabel: null,
        topics: [] as string[],
        videos: [] as YoutubeVideoItem[],
        cached: false,
        message: "업로드된 커리큘럼이 없습니다.",
      };
    }

    const sheet = sheetsSnap.docs[0].data();
    const rows = (sheet.rows ?? []) as CurriculumRow[];
    if (!rows.length) {
      return {
        weekKey: null,
        weekLabel: null,
        topics: [] as string[],
        videos: [] as YoutubeVideoItem[],
        cached: false,
        message: "커리큘럼 행이 비어 있습니다.",
      };
    }

    const picked = pickCurrentRows(rows);
    const topics = picked.rows.map(topicLabel);
    const queries = buildSearchQueries(picked.rows);

    const weekLabel = `${picked.weekStart.getMonth() + 1}/${picked.weekStart.getDate()} ~ ${picked.weekEnd.getMonth() + 1}/${picked.weekEnd.getDate()}`;
    const cacheRef = db
      .collection("cohorts")
      .doc(cohortId)
      .collection("youtubeCurriculumCache")
      .doc(`${picked.weekKey}_${CACHE_VERSION}`);

    const cacheDoc = await cacheRef.get();
    if (cacheDoc.exists) {
      const cached = cacheDoc.data()!;
      const fetchedAt = cached.fetchedAt?.toDate?.() as Date | undefined;
      if (
        fetchedAt &&
        Date.now() - fetchedAt.getTime() < CACHE_TTL_MS &&
        Array.isArray(cached.videos)
      ) {
        return {
          weekKey: picked.weekKey,
          weekLabel,
          topics: cached.topics ?? topics,
          videos: cached.videos as YoutubeVideoItem[],
          cached: true,
          message: null,
        };
      }
    }

    const apiKey = (process.env.YOUTUBE_API_KEY ?? "").trim();
    if (!apiKey) {
      throw new HttpsError(
        "failed-precondition",
        "YOUTUBE_API_KEY가 설정되지 않았습니다. Cloud Functions 환경에 API 키를 등록하세요.",
      );
    }

    const collected: YoutubeVideoItem[] = [];
    const seenIds = new Set<string>();
    const seenChannels = new Set<string>();

    for (const q of queries) {
      try {
        let found = await searchYoutube(apiKey, q.query, q.duration);
        if (found.length < 2) {
          const extra = await searchYoutube(apiKey, q.query);
          const extraIds = new Set(found.map((v) => v.videoId));
          found = [...found, ...extra.filter((v) => !extraIds.has(v.videoId))];
        }
        const uniqueChannel: YoutubeVideoItem[] = [];
        const rest: YoutubeVideoItem[] = [];
        for (const v of found) {
          if (seenIds.has(v.videoId)) continue;
          seenIds.add(v.videoId);
          const item = {...v, topicLabel: q.label, query: q.query};
          const channelKey = v.channelTitle.trim().toLowerCase();
          if (channelKey && seenChannels.has(channelKey)) {
            rest.push(item);
          } else {
            if (channelKey) seenChannels.add(channelKey);
            uniqueChannel.push(item);
          }
        }
        collected.push(...uniqueChannel, ...rest);
      } catch (e) {
        logger.error("YouTube search failed", {query: q.query, error: e});
      }
    }

    const videos = interleaveByTopic(collected, MAX_VIDEOS);

    if (videos.length === 0) {
      throw new HttpsError(
        "unavailable",
        "YouTube 추천을 가져오지 못했습니다. API 키·쿼터를 확인하세요.",
      );
    }

    await cacheRef.set({
      weekKey: picked.weekKey,
      weekLabel,
      cacheVersion: CACHE_VERSION,
      topics,
      queries: queries.map((q) => q.query),
      videos,
      fetchedAt: fieldValue.serverTimestamp(),
      updatedAt: fieldValue.serverTimestamp(),
    });

    return {
      weekKey: picked.weekKey,
      weekLabel,
      topics,
      videos,
      cached: false,
      message: null,
    };
  },
);
