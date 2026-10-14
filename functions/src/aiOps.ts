/**
 * LLMOps: 생성 로그 / outcome 피드백.
 * 클라이언트가 메타만 넘기고 Admin SDK가 Firestore에 쓴다 (rules: client write 금지).
 * 이력서·채팅·공고·질문 원문은 받지 않는다.
 */
import {onCall, HttpsError} from "firebase-functions/v2/https";

import {db, ensureInitialized, fieldValue} from "./firebase";

const callOptions = {
  region: "asia-northeast3" as const,
  invoker: "public" as const,
};

export const JOB_CHAT_PROMPT_VERSION = "job_chat_v1";
export const JOB_RECOMMEND_PROMPT_VERSION = "job_recommend_v1";
export const RESUME_REVIEW_PROMPT_VERSION = "resume_review_v1";
export const STUDENT_CHATBOT_PROMPT_VERSION = "student_chatbot_v2";

const CLIENT_LOG_TYPES = new Set([
  "job_chat",
  "job_recommend",
  "resume_review",
  "student_chatbot",
]);

const OUTCOMES = new Set([
  // assessment
  "adopted",
  "edited",
  "discarded",
  // job_chat
  "clicked_job",
  "followed_up",
  "ignored",
  // job_recommend
  "opened",
  "selected_for_review",
  "dismissed",
  // resume_review
  "applied",
  "partial_apply",
  "undone",
  "abandoned",
  // student_chatbot
  "helpful",
  "not_helpful",
]);

const META_KEYS = new Set([
  "mode",
  "intent",
  "topK",
  "jobCount",
  "appliedCount",
  "requestIdHash",
  "messageLength",
  "resumeLength",
  "reranked",
  "reviewMode",
  "selectedCount",
  "route",
  "namespaces",
  "studentScopes",
  "blocked",
  "retrievalMs",
  "llmMs",
  "evalRunId",
]);

type UserRole = "admin" | "instructor" | "student";

interface CallerUser {
  uid: string;
  role: UserRole;
  cohortId?: string;
  displayName?: string;
}

async function getCaller(uid: string): Promise<CallerUser> {
  ensureInitialized();
  const snap = await db.collection("users").doc(uid).get();
  if (!snap.exists) {
    throw new HttpsError("permission-denied", "사용자 정보를 찾을 수 없습니다.");
  }
  const data = snap.data()!;
  if (data.isActive === false) {
    throw new HttpsError("permission-denied", "비활성 계정입니다.");
  }
  return {
    uid,
    role: data.role as UserRole,
    cohortId: data.cohortId as string | undefined,
    displayName: data.displayName as string | undefined,
  };
}

function assertCohortMember(caller: CallerUser, cohortId: string): void {
  if (caller.role === "admin") return;
  if (caller.cohortId === cohortId) return;
  throw new HttpsError("permission-denied", "해당 기수에 접근할 수 없습니다.");
}

function asInt(value: unknown, fallback = 0): number {
  if (typeof value === "number" && Number.isFinite(value)) {
    return Math.max(0, Math.floor(value));
  }
  if (typeof value === "string" && value.trim() !== "") {
    const n = Number.parseInt(value, 10);
    if (Number.isFinite(n)) return Math.max(0, n);
  }
  return fallback;
}

function sanitizeMeta(raw: unknown): Record<string, string | number | boolean> {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return {};
  const out: Record<string, string | number | boolean> = {};
  for (const [key, value] of Object.entries(raw as Record<string, unknown>)) {
    if (!META_KEYS.has(key)) continue;
    if (typeof value === "boolean" || typeof value === "number") {
      if (typeof value === "number" && !Number.isFinite(value)) continue;
      out[key] = value;
      continue;
    }
    if (typeof value === "string") {
      out[key] = value.slice(0, 200);
    }
  }
  return out;
}

/**
 * 취업 코치 LLM 호출 1회분 관측 로그.
 * type: job_chat | job_recommend | resume_review | student_chatbot
 */
export const recordAiGenerationLog = onCall(callOptions, async (request) => {
  if (!request.auth) {
    throw new HttpsError("unauthenticated", "인증이 필요합니다.");
  }
  const caller = await getCaller(request.auth.uid);
  const data = request.data as {
    type?: string;
    cohortId?: string;
    promptVersion?: string;
    model?: string;
    latencyMs?: number;
    status?: string;
    errorMessage?: string;
    reasoningEffort?: string;
    tokenIn?: number;
    tokenOut?: number;
    generatedCount?: number;
    meta?: Record<string, unknown>;
  };

  const type = (data.type ?? "").trim();
  const cohortId = (data.cohortId ?? "").trim();
  if (!CLIENT_LOG_TYPES.has(type) || !cohortId) {
    throw new HttpsError(
      "invalid-argument",
      "type(job_chat|job_recommend|resume_review|student_chatbot)과 cohortId가 필요합니다.",
    );
  }
  assertCohortMember(caller, cohortId);

  const status = data.status === "error" ? "error" : "success";
  const promptVersion = (data.promptVersion ?? "").trim().slice(0, 80);
  const model = (data.model ?? "").trim().slice(0, 80);
  const meta = sanitizeMeta(data.meta);
  const logRef = db.collection("aiGenerationLogs").doc();

  const payload: Record<string, unknown> = {
    type,
    promptVersion:
      promptVersion ||
      (type === "job_chat"
        ? JOB_CHAT_PROMPT_VERSION
        : type === "job_recommend"
          ? JOB_RECOMMEND_PROMPT_VERSION
          : type === "student_chatbot"
            ? STUDENT_CHATBOT_PROMPT_VERSION
            : RESUME_REVIEW_PROMPT_VERSION),
    model: model || "unknown",
    cohortId,
    latencyMs: asInt(data.latencyMs),
    status,
    generatedCount: asInt(data.generatedCount, status === "success" ? 1 : 0),
    createdBy: caller.uid,
    createdByName: caller.displayName ?? "",
    createdAt: fieldValue.serverTimestamp(),
    ...meta,
  };
  if (data.reasoningEffort) {
    payload.reasoningEffort = String(data.reasoningEffort).slice(0, 40);
  }
  if (data.tokenIn != null) payload.tokenIn = asInt(data.tokenIn);
  if (data.tokenOut != null) payload.tokenOut = asInt(data.tokenOut);
  if (status === "error" && data.errorMessage) {
    payload.errorMessage = String(data.errorMessage).slice(0, 500);
  }

  await logRef.set(payload);
  return {logId: logRef.id, promptVersion: payload.promptVersion};
});

/**
 * 취업 코치 outcome 피드백 (클릭·적용 등).
 * 문서 id: `${logId}_${draftId}` — 같은 행동 재기록 시 갱신.
 */
export const recordAiOutcomeFeedback = onCall(callOptions, async (request) => {
  if (!request.auth) {
    throw new HttpsError("unauthenticated", "인증이 필요합니다.");
  }
  const caller = await getCaller(request.auth.uid);
  const data = request.data as {
    cohortId?: string;
    logId?: string;
    draftId?: string;
    outcome?: string;
    promptVersion?: string;
    type?: string;
  };

  const cohortId = (data.cohortId ?? "").trim();
  const logId = (data.logId ?? "").trim();
  const draftId = (data.draftId ?? "session").trim().slice(0, 120);
  const outcome = (data.outcome ?? "").trim();
  if (!cohortId || !logId || !OUTCOMES.has(outcome)) {
    throw new HttpsError(
      "invalid-argument",
      "cohortId, logId, 허용된 outcome이 필요합니다.",
    );
  }
  assertCohortMember(caller, cohortId);

  const docId = `${logId}_${draftId}`.slice(0, 700);
  const ref = db.collection("aiQuestionFeedback").doc(docId);
  const existing = await ref.get();
  const payload: Record<string, unknown> = {
    logId,
    draftId,
    cohortId,
    outcome,
    promptVersion: (data.promptVersion ?? "").trim().slice(0, 80),
    actorUid: caller.uid,
    updatedAt: fieldValue.serverTimestamp(),
  };
  if (data.type) payload.type = String(data.type).slice(0, 40);
  if (!existing.exists) {
    payload.createdAt = fieldValue.serverTimestamp();
    await ref.set(payload);
  } else {
    await ref.update(payload);
  }
  return {ok: true, id: docId};
});
