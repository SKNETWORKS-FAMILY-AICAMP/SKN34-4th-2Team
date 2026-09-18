import {isDeepStrictEqual} from "node:util";
import * as logger from "firebase-functions/logger";
import {defineSecret} from "firebase-functions/params";
import {onDocumentWritten} from "firebase-functions/v2/firestore";

import {db} from "./firebase";

const openaiApiKey = defineSecret("OPENAI_API_KEY");
const pineconeApiKey = defineSecret("PINECONE_API_KEY2");
const secrets = [openaiApiKey, pineconeApiKey];

const INDEX_NAME = "student";
const NAMESPACE = "notice";
const EMBEDDING_MODEL = "text-embedding-3-small";
const EMBEDDING_DIMENSION = 1536;
const PINECONE_API_VERSION = "2025-10";
const VECTOR_INDEX_FIELD = "_vectorIndex";
const VECTOR_INDEXES_FIELD = "_vectorIndexes";
const CHUNK_SIZE = 500;
const CHUNK_OVERLAP = 40;
const MEANINGFUL_SYMBOLS = new Set(["+", "=", "<", ">", "|", "₩", "$", "€", "¥"]);

type NoticeData = FirebaseFirestore.DocumentData & {
  title?: unknown;
  content?: unknown;
  authorId?: unknown;
  authorName?: unknown;
  isFavorite?: unknown;
  priority?: unknown;
  createdAt?: unknown;
  updatedAt?: unknown;
  _vectorIndex?: unknown;
  _vectorIndexes?: unknown;
};

type NoticeMetadata = Record<string, string | number | boolean>;

interface NoticeRecord {
  id: string;
  pageContent: string;
  metadata: NoticeMetadata;
}

let pineconeHostPromise: Promise<string> | undefined;

function timestampToIso(value: unknown): string {
  if (value instanceof Date) return value.toISOString();
  if (typeof value === "string") return value;
  if (value && typeof (value as {toDate?: unknown}).toDate === "function") {
    return (value as {toDate(): Date}).toDate().toISOString();
  }
  return "";
}

export function noticeDocId(cohort: string, index: number): string {
  return `${cohort}_${index}`;
}

/** policy_ingestion.py의 normalize_text와 같은 순서로 공지 원문을 정리합니다. */
export function normalizeText(text: string): string {
  text = text.normalize("NFKC").replace(/\r\n?/g, "\n");
  text = [...text].map((char) =>
    char === "\n" || MEANINGFUL_SYMBOLS.has(char) || !/[\p{C}\p{S}]/u.test(char) ?
      char : " ",
  ).join("");
  text = text.replace(/[^\S\n]+/g, " ");
  text = text.split("\n").map((line) => line.trim()).join("\n");
  return text.replace(/\n{3,}/g, "\n\n").trim();
}

/** 정책 적재기와 같은 기본값과 구분자 우선순위로 문맥 경계에서 나눕니다. */
// ponytail: LangChain 의존성 없이 경량 구현; 청크의 완전한 바이트 일치가 필요할 때만 패키지로 교체합니다.
export function chunkText(
  text: string,
  chunkSize = CHUNK_SIZE,
  chunkOverlap = CHUNK_OVERLAP,
): string[] {
  if (chunkSize <= 0 || chunkOverlap < 0 || chunkOverlap >= chunkSize) {
    throw new Error("chunkSize는 양수이고 chunkOverlap보다 커야 합니다.");
  }
  text = normalizeText(text);
  if (!text) return [];

  const chunks: string[] = [];
  let start = 0;
  while (start < text.length) {
    let end = Math.min(start + chunkSize, text.length);
    if (end < text.length) {
      const window = text.slice(start, end);
      const minimumBoundary = Math.floor(chunkSize / 2);
      for (const separator of ["\n\n", "\n", ". ", " "]) {
        const boundary = window.lastIndexOf(separator);
        if (boundary >= minimumBoundary) {
          end = start + boundary + (separator === ". " ? 1 : 0);
          break;
        }
      }
    }

    const chunk = text.slice(start, end).trim();
    if (chunk) chunks.push(chunk);
    if (end >= text.length) break;
    start = Math.max(start + 1, end - chunkOverlap);
  }
  return chunks;
}

export function buildNoticeRecords(
  cohort: string,
  indexes: number[],
  data: NoticeData,
): NoticeRecord[] {
  const chunks = chunkText(String(data.content ?? ""));
  if (indexes.length < chunks.length) throw new Error("공지 chunk용 vector index가 부족합니다.");

  return chunks.map((pageContent, chunkIndex) => {
    const id = noticeDocId(cohort, indexes[chunkIndex]);
    return {
      id,
      pageContent,
      metadata: {
        page_content: pageContent,
        doc_id: id,
        cohort,
        author_id: String(data.authorId ?? ""),
        author_name: String(data.authorName ?? ""),
        is_favorite: data.isFavorite === true,
        created_at: timestampToIso(data.createdAt),
        updated_at: timestampToIso(data.updatedAt),
        priority: typeof data.priority === "number" ? data.priority : 0,
        title: String(data.title ?? ""),
      },
    };
  });
}

function onlyVectorIndexChanged(before: NoticeData, after: NoticeData): boolean {
  const indexesChanged = !isDeepStrictEqual(
    [before[VECTOR_INDEX_FIELD], before[VECTOR_INDEXES_FIELD]],
    [after[VECTOR_INDEX_FIELD], after[VECTOR_INDEXES_FIELD]],
  );
  const beforeWithoutIndex = {...before};
  const afterWithoutIndex = {...after};
  delete beforeWithoutIndex[VECTOR_INDEX_FIELD];
  delete beforeWithoutIndex[VECTOR_INDEXES_FIELD];
  delete afterWithoutIndex[VECTOR_INDEX_FIELD];
  delete afterWithoutIndex[VECTOR_INDEXES_FIELD];
  return indexesChanged &&
    isDeepStrictEqual(beforeWithoutIndex, afterWithoutIndex);
}

function vectorIndexes(data: NoticeData): number[] {
  if (Array.isArray(data[VECTOR_INDEXES_FIELD])) {
    return [...new Set(data[VECTOR_INDEXES_FIELD]
      .filter((index): index is number => Number.isInteger(index) && index >= 0))];
  }
  const legacy = data[VECTOR_INDEX_FIELD];
  return Number.isInteger(legacy) && Number(legacy) >= 0 ? [Number(legacy)] : [];
}

async function prepareNotice(
  ref: FirebaseFirestore.DocumentReference,
): Promise<{data: NoticeData; indexes: number[]; staleIndexes: number[]} | null> {
  return db.runTransaction(async (transaction) => {
    const notice = await transaction.get(ref);
    if (!notice.exists) return null;

    const data = notice.data() as NoticeData;
    const chunkCount = chunkText(String(data.content ?? "")).length;
    const previousIndexes = vectorIndexes(data);
    const indexes = previousIndexes.slice(0, chunkCount);
    const staleIndexes = previousIndexes.slice(chunkCount);
    const missingCount = chunkCount - indexes.length;

    const cohortRef = ref.parent.parent;
    if (!cohortRef) throw new Error(`잘못된 공지 경로입니다: ${ref.path}`);
    if (missingCount > 0) {
      const counterRef = cohortRef.collection("vectorMetadata").doc("notices");
      const counter = await transaction.get(counterRef);
      const savedNextIndex = counter.data()?.nextIndex;
      let nextIndex = Number.isInteger(savedNextIndex) && savedNextIndex >= 0 ?
        savedNextIndex : 0;
      nextIndex = Math.max(nextIndex, ...previousIndexes.map((index) => index + 1));
      for (let i = 0; i < missingCount; i++) indexes.push(nextIndex++);
      transaction.set(counterRef, {nextIndex}, {merge: true});
    }

    if (!isDeepStrictEqual(data[VECTOR_INDEXES_FIELD], indexes)) {
      transaction.update(ref, {[VECTOR_INDEXES_FIELD]: indexes});
    }
    return {
      data: {...data, [VECTOR_INDEXES_FIELD]: indexes},
      indexes,
      staleIndexes,
    };
  });
}

async function requestJson<T>(url: string, init: RequestInit): Promise<T> {
  const response = await fetch(url, init);
  const text = await response.text();
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}: ${text}`);
  }
  return (text ? JSON.parse(text) : {}) as T;
}

async function pineconeHost(): Promise<string> {
  if (!pineconeHostPromise) {
    pineconeHostPromise = requestJson<{host?: string}>(
      `https://api.pinecone.io/indexes/${INDEX_NAME}`,
      {headers: {
        "Api-Key": pineconeApiKey.value(),
        "X-Pinecone-Api-Version": PINECONE_API_VERSION,
      }},
    ).then((index) => {
      if (!index.host) throw new Error(`Pinecone index '${INDEX_NAME}'의 host가 없습니다.`);
      return index.host;
    }).catch((error) => {
      pineconeHostPromise = undefined;
      throw error;
    });
  }
  return pineconeHostPromise;
}

async function embeddings(records: NoticeRecord[]): Promise<number[][]> {
  if (!records.length) return [];
  const result = await requestJson<{
    data?: Array<{index: number; embedding: number[]}>;
  }>("https://api.openai.com/v1/embeddings", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${openaiApiKey.value()}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      model: EMBEDDING_MODEL,
      dimensions: EMBEDDING_DIMENSION,
      input: records.map((record) => record.pageContent),
    }),
  });
  const vectors = [...(result.data ?? [])]
    .sort((a, b) => a.index - b.index)
    .map((item) => item.embedding);
  if (vectors.length !== records.length) {
    throw new Error("OpenAI embedding 응답 개수가 공지 개수와 다릅니다.");
  }
  return vectors;
}

async function upsertRecords(records: NoticeRecord[]): Promise<number> {
  let upserted = 0;
  for (let start = 0; start < records.length; start += 96) {
    const batch = records.slice(start, start + 96);
    const vectors = await embeddings(batch);
    const host = await pineconeHost();
    const result = await requestJson<{upsertedCount?: number}>(
      `https://${host}/vectors/upsert`,
      {
        method: "POST",
        headers: {
          "Api-Key": pineconeApiKey.value(),
          "Content-Type": "application/json",
          "X-Pinecone-Api-Version": PINECONE_API_VERSION,
        },
        body: JSON.stringify({
          namespace: NAMESPACE,
          vectors: batch.map((record, i) => ({
            id: record.id,
            values: vectors[i],
            metadata: record.metadata,
          })),
        }),
      },
    );
    upserted += result.upsertedCount ?? batch.length;
  }
  return upserted;
}

async function deleteRecords(ids: string[]): Promise<void> {
  if (!ids.length) return;
  const host = await pineconeHost();
  await requestJson(
    `https://${host}/vectors/delete`,
    {
      method: "POST",
      headers: {
        "Api-Key": pineconeApiKey.value(),
        "Content-Type": "application/json",
        "X-Pinecone-Api-Version": PINECONE_API_VERSION,
      },
      body: JSON.stringify({ids, namespace: NAMESPACE}),
    },
  );
}

const functionOptions = {
  region: "asia-northeast3" as const,
  secrets,
};

/** Firestore 공지 생성/수정/삭제를 Pinecone student/notice에 자동 반영합니다. */
export const syncNoticeVector = onDocumentWritten(
  {
    ...functionOptions,
    document: "cohorts/{cohort}/notices/{noticeId}",
    retry: true,
  },
  async (event) => {
    if (!event.data) return;
    const cohort = event.params.cohort;
    const before = event.data.before;
    const after = event.data.after;

    if (!after.exists) {
      const previous = before.data() as NoticeData | undefined;
      await deleteRecords(
        previous ? vectorIndexes(previous).map((index) => noticeDocId(cohort, index)) : [],
      );
      return;
    }

    const beforeData = before.exists ? before.data() as NoticeData : undefined;
    const afterData = after.data() as NoticeData;
    if (beforeData && onlyVectorIndexChanged(beforeData, afterData)) return;

    const prepared = await prepareNotice(after.ref);
    if (!prepared) return;
    if (!prepared.indexes.length) {
      await deleteRecords(
        prepared.staleIndexes.map((index) => noticeDocId(cohort, index)),
      );
      logger.warn("빈 공지 원문을 Pinecone에서 제외했습니다.", {cohort, noticeId: after.id});
      return;
    }

    const upserted = await upsertRecords(
      buildNoticeRecords(cohort, prepared.indexes, prepared.data),
    );
    await deleteRecords(
      prepared.staleIndexes.map((index) => noticeDocId(cohort, index)),
    );
    logger.info("Notice vector synced", {cohort, noticeId: after.id, upserted});
  },
);

/** 배포 전에 존재하던 모든 Firestore 공지를 한 번에 적재합니다. */
async function syncAllNoticeVectors(): Promise<Record<string, string | number>> {
  const snapshot = await db.collectionGroup("notices").get();
  const records: NoticeRecord[] = [];
  const staleIds: string[] = [];
  let skipped = 0;
  for (const notice of snapshot.docs) {
    const cohort = notice.ref.parent.parent?.id;
    if (!cohort) {
      skipped++;
      continue;
    }
    const prepared = await prepareNotice(notice.ref);
    if (!prepared) {
      skipped++;
      continue;
    }
    staleIds.push(...prepared.staleIndexes.map((index) => noticeDocId(cohort, index)));
    if (!prepared.indexes.length) {
      skipped++;
      continue;
    }
    records.push(...buildNoticeRecords(cohort, prepared.indexes, prepared.data));
  }

  const upserted = await upsertRecords(records);
  await deleteRecords(staleIds);
  return {found: snapshot.size, upserted, skipped, index: INDEX_NAME, namespace: NAMESPACE};
}

function selfCheck(): void {
  const normalized = normalizeText(
    "  공지①\t내용\r\n\r\n\r\n💡 가격 １０，０００₩  ",
  );
  if (normalized !== "공지1 내용\n\n가격 10,000₩") {
    throw new Error(`normalizeText self-check failed: ${JSON.stringify(normalized)}`);
  }

  const chunks = chunkText("가".repeat(620), 180, 40);
  if (chunks.length < 2 || chunks.some((chunk) => chunk.length > 180) ||
    chunks[0].slice(-40) !== chunks[1].slice(0, 40)) {
    throw new Error("chunkText self-check failed");
  }

  const records = buildNoticeRecords("SKN34", [0, 1], {
    title: "안내",
    content: "가".repeat(620),
    authorId: "admin-1",
    authorName: "관리자",
    isFavorite: true,
    priority: 2,
    createdAt: new Date("2026-09-04T00:00:00.000Z"),
    updatedAt: new Date("2026-09-04T01:00:00.000Z"),
  });
  if (records.length !== 2 || records[0].id !== "SKN34__0" ||
    records[1].id !== "SKN34__1" ||
    records[0].metadata.page_content !== records[0].pageContent) {
    throw new Error("notice vector record self-check failed");
  }
  console.log("notice normalize/chunk/metadata self-check passed");
}

if (require.main === module) {
  if (process.argv.includes("--sync")) {
    void syncAllNoticeVectors()
      .then((result) => console.log(JSON.stringify(result)))
      .catch((error) => {
        console.error(error);
        process.exitCode = 1;
      })
      .finally(() => db.terminate());
  } else {
    selfCheck();
  }
}
