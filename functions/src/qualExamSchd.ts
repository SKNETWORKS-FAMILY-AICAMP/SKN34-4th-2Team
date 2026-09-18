import {defineString} from "firebase-functions/params";
import {onCall, HttpsError} from "firebase-functions/v2/https";
import * as logger from "firebase-functions/logger";
import * as https from "https";
import {lookup} from "dns";
import {URL} from "url";

import {admin, db} from "./firebase";

export const dataGoKrServiceKey = defineString("DATA_GO_KR_SERVICE_KEY", {
  description: "공공데이터포털 일반 인증키 (국가자격 시험일정)",
  default: "",
});

const API_URL =
  "https://apis.data.go.kr/B490007/qualExamSchd/getQualExamSchdList";

const CACHE_COLLECTION = "systemCache";

export interface QualExamScheduleItem {
  implYy: string;
  implSeq: number;
  qualgbCd: string;
  qualgbNm: string;
  description: string;
  docRegStartDt: string | null;
  docRegEndDt: string | null;
  docExamStartDt: string | null;
  docExamEndDt: string | null;
  docPassDt: string | null;
  pracRegStartDt: string | null;
  pracRegEndDt: string | null;
  pracExamStartDt: string | null;
  pracExamEndDt: string | null;
  pracPassDt: string | null;
}

interface FetchParams {
  year: number;
  pageNo?: number;
  numOfRows?: number;
  qualgbCd?: string;
  keyword?: string;
}

function normalizeDate(value: unknown): string | null {
  if (value == null) return null;
  const s = String(value).trim();
  if (!s || s === "null") return null;
  return s.length >= 8 ? s.slice(0, 8) : s;
}

function parseItems(raw: unknown): Record<string, unknown>[] {
  if (!raw || typeof raw !== "object") return [];
  const body = raw as Record<string, unknown>;
  const response = (body.response ?? body) as Record<string, unknown>;
  const innerBody = (response.body ?? body.body ?? response) as Record<
    string,
    unknown
  >;
  const items = innerBody.items ?? innerBody.item;
  if (!items) return [];
  if (Array.isArray(items)) return items as Record<string, unknown>[];
  const item = (items as Record<string, unknown>).item;
  if (Array.isArray(item)) return item as Record<string, unknown>[];
  if (item && typeof item === "object") return [item as Record<string, unknown>];
  return [];
}

function parseTotalCount(raw: unknown): number {
  if (!raw || typeof raw !== "object") return 0;
  const body = raw as Record<string, unknown>;
  const response = (body.response ?? body) as Record<string, unknown>;
  const innerBody = (response.body ?? body.body ?? response) as Record<
    string,
    unknown
  >;
  const total = innerBody.totalCount ?? innerBody.totalcount;
  return total ? Number(total) : 0;
}

function mapItem(row: Record<string, unknown>): QualExamScheduleItem {
  return {
    implYy: String(row.implYy ?? ""),
    implSeq: Number(row.implSeq ?? 0),
    qualgbCd: String(row.qualgbCd ?? ""),
    qualgbNm: String(row.qualgbNm ?? ""),
    description: String(row.description ?? ""),
    docRegStartDt: normalizeDate(row.docRegStartDt),
    docRegEndDt: normalizeDate(row.docRegEndDt),
    docExamStartDt: normalizeDate(row.docExamStartDt),
    docExamEndDt: normalizeDate(row.docExamEndDt),
    docPassDt: normalizeDate(row.docPassDt),
    pracRegStartDt: normalizeDate(row.pracRegStartDt),
    pracRegEndDt: normalizeDate(row.pracRegEndDt),
    pracExamStartDt: normalizeDate(row.pracExamStartDt),
    pracExamEndDt: normalizeDate(row.pracExamEndDt),
    pracPassDt: normalizeDate(row.pracPassDt),
  };
}

function nextSortKey(item: QualExamScheduleItem): string {
  return (
    item.docExamStartDt ??
    item.docRegStartDt ??
    item.pracExamStartDt ??
    item.pracRegStartDt ??
    "99991231"
  );
}

function filterByKeyword(
  items: QualExamScheduleItem[],
  keyword?: string,
): QualExamScheduleItem[] {
  const q = keyword?.trim().toLowerCase();
  if (!q) return items;
  return items.filter((item) => item.description.toLowerCase().includes(q));
}

function buildApiUrl(params: FetchParams, key: string): string {
  const url = new URL(API_URL);
  url.searchParams.set("serviceKey", key);
  url.searchParams.set("numOfRows", String(params.numOfRows ?? 100));
  url.searchParams.set("pageNo", String(params.pageNo ?? 1));
  url.searchParams.set("dataFormat", "json");
  url.searchParams.set("implYy", String(params.year));
  if (params.qualgbCd) url.searchParams.set("qualgbCd", params.qualgbCd);
  return url.toString();
}

/** Cloud Run fetch 타임아웃 회피 — IPv4 + https 모듈 */
function fetchTextIpv4(url: string, timeoutMs = 30000): Promise<string> {
  return new Promise((resolve, reject) => {
    const req = https.get(
      url,
      {
        timeout: timeoutMs,
        lookup: (hostname, _options, callback) => {
          lookup(hostname, {family: 4}, callback);
        },
      },
      (res) => {
        const chunks: Buffer[] = [];
        res.on("data", (chunk: Buffer) => chunks.push(chunk));
        res.on("end", () => {
          const text = Buffer.concat(chunks).toString("utf8");
          if (res.statusCode && res.statusCode >= 400) {
            reject(new Error(`HTTP ${res.statusCode}: ${text.slice(0, 200)}`));
            return;
          }
          resolve(text);
        });
      },
    );
    req.on("error", reject);
    req.on("timeout", () => {
      req.destroy();
      reject(new Error(`Request timeout (${timeoutMs}ms)`));
    });
  });
}

async function fetchWithRetry(url: string, attempts = 3): Promise<string> {
  let lastError: unknown;
  for (let i = 0; i < attempts; i++) {
    try {
      return await fetchTextIpv4(url);
    } catch (error) {
      lastError = error;
      logger.warn(`Qual exam API attempt ${i + 1}/${attempts} failed`, error);
      if (i < attempts - 1) {
        await new Promise((r) => setTimeout(r, 1500 * (i + 1)));
      }
    }
  }
  throw lastError;
}

function parseApiResponse(text: string, keyword?: string): {
  items: QualExamScheduleItem[];
  totalCount: number;
} {
  let json: unknown;
  try {
    json = JSON.parse(text);
  } catch {
    logger.error("Qual exam API non-JSON", {text: text.slice(0, 500)});
    throw new HttpsError("internal", "시험일정 API 응답 파싱 실패");
  }

  const root = json as Record<string, unknown>;
  const serviceError = root.OpenAPI_ServiceResponse as
    | Record<string, unknown>
    | undefined;
  if (serviceError?.cmmMsgHeader) {
    const header = serviceError.cmmMsgHeader as Record<string, unknown>;
    throw new HttpsError(
      "failed-precondition",
      String(header.returnAuthMsg ?? header.errMsg ?? "API 키 오류"),
    );
  }

  const header = root.header as Record<string, unknown> | undefined;
  if (header?.resultCode && header.resultCode !== "00") {
    throw new HttpsError(
      "failed-precondition",
      String(header.resultMsg ?? "API 오류"),
    );
  }

  const items = parseItems(json).map(mapItem);
  const filtered = filterByKeyword(items, keyword);
  filtered.sort((a, b) => nextSortKey(a).localeCompare(nextSortKey(b)));

  return {
    items: filtered,
    totalCount: keyword ? filtered.length : parseTotalCount(json),
  };
}

async function readCache(year: number): Promise<{
  items: QualExamScheduleItem[];
  totalCount: number;
} | null> {
  const doc = await db
    .collection(CACHE_COLLECTION)
    .doc(`qualExamSchedules_${year}`)
    .get();
  if (!doc.exists) return null;
  const data = doc.data();
  if (!data?.items || !Array.isArray(data.items)) return null;
  return {
    items: data.items as QualExamScheduleItem[],
    totalCount: Number(data.totalCount ?? data.items.length),
  };
}

async function writeCache(
  year: number,
  items: QualExamScheduleItem[],
  totalCount: number,
): Promise<void> {
  await db.collection(CACHE_COLLECTION).doc(`qualExamSchedules_${year}`).set({
    year,
    items,
    totalCount,
    syncedAt: admin.firestore.FieldValue.serverTimestamp(),
  });
}

async function fetchFromApi(params: FetchParams): Promise<{
  items: QualExamScheduleItem[];
  totalCount: number;
}> {
  const key = dataGoKrServiceKey.value().trim();
  if (!key) {
    throw new HttpsError(
      "failed-precondition",
      "DATA_GO_KR_SERVICE_KEY가 설정되지 않았습니다.",
    );
  }

  const pageSize = Math.min(params.numOfRows ?? 50, 50);
  let pageNo = params.pageNo ?? 1;
  let allItems: QualExamScheduleItem[] = [];
  let totalCount = 0;

  while (true) {
    const url = buildApiUrl(
      {...params, numOfRows: pageSize, pageNo},
      key,
    );
    const text = await fetchWithRetry(url);
    const page = parseApiResponse(text, pageNo === 1 ? params.keyword : undefined);

    if (pageNo === 1) {
      totalCount = page.totalCount;
    }

    allItems = allItems.concat(page.items);

    if (allItems.length >= totalCount || page.items.length < pageSize) {
      break;
    }
    pageNo += 1;
  }

  const filtered = filterByKeyword(allItems, params.keyword);
  filtered.sort((a, b) => nextSortKey(a).localeCompare(nextSortKey(b)));

  return {
    items: filtered,
    totalCount: params.keyword ? filtered.length : totalCount,
  };
}

/** 국가자격 시험일정 조회 (공공데이터포털 프록시 + Firestore 캐시) */
export const getQualExamSchedules = onCall(
  {region: "asia-northeast3", timeoutSeconds: 60},
  async (request) => {
    const data = request.data as {
      year?: number;
      pageNo?: number;
      numOfRows?: number;
      qualgbCd?: string;
      keyword?: string;
    };

    const year = data.year ?? new Date().getFullYear();
    const pageNo = data.pageNo ?? 1;
    const numOfRows = Math.min(data.numOfRows ?? 50, 50);
    const qualgbCd = data.qualgbCd ?? "T";

    try {
      const result = await fetchFromApi({
        year,
        pageNo,
        numOfRows,
        qualgbCd,
        keyword: data.keyword,
      });

      writeCache(year, result.items, result.totalCount).catch((err) => {
        logger.warn("Qual exam cache write failed", err);
      });

      return {
        year,
        pageNo,
        numOfRows,
        totalCount: result.totalCount,
        items: result.items,
        fromCache: false,
      };
    } catch (error) {
      if (error instanceof HttpsError) {
        const cached = await readCache(year);
        if (cached && cached.items.length > 0) {
          const items = filterByKeyword(cached.items, data.keyword);
          return {
            year,
            pageNo,
            numOfRows,
            totalCount: cached.totalCount,
            items,
            fromCache: true,
          };
        }
        throw error;
      }

      logger.error("Qual exam fetch failed", error);
      const cached = await readCache(year);
      if (cached && cached.items.length > 0) {
        const items = filterByKeyword(cached.items, data.keyword);
        return {
          year,
          pageNo,
          numOfRows,
          totalCount: cached.totalCount,
          items,
          fromCache: true,
        };
      }

      throw new HttpsError(
        "unavailable",
        "공공 API 연결에 실패했습니다. 잠시 후 다시 시도해주세요.",
      );
    }
  },
);
