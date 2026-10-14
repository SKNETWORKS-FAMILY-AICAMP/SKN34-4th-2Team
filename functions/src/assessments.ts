import {onCall, HttpsError, type CallableRequest} from "firebase-functions/v2/https";
import {defineSecret} from "firebase-functions/params";
import * as logger from "firebase-functions/logger";

import {db, ensureInitialized, fieldValue} from "./firebase";
import {
  ASSESSMENT_MODEL,
  assessmentPromptVersion,
  ASSESSMENT_SYSTEM_PROMPT,
  buildAssessmentRegenPrompt,
  buildAssessmentUserPrompt,
  type ReplaceHint,
} from "./ai/assessmentPrompt";

const openaiApiKey = defineSecret("OPENAI_API_KEY");

const callOptions = {
  region: "asia-northeast3" as const,
  invoker: "public" as const,
};

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

function assertStaffOfCohort(caller: CallerUser, cohortId: string): void {
  if (caller.role === "admin") return;
  if (caller.role === "instructor" && caller.cohortId === cohortId) return;
  throw new HttpsError(
    "permission-denied",
    "강사 또는 관리자만 수행할 수 있습니다.",
  );
}

function assertCohortMember(caller: CallerUser, cohortId: string): void {
  if (caller.role === "admin") return;
  if (caller.cohortId === cohortId) return;
  throw new HttpsError("permission-denied", "해당 기수에 접근할 수 없습니다.");
}

function normalizeShortAnswer(value: unknown): string {
  return String(value ?? "")
    .trim()
    .toLowerCase()
    .replace(/\s+/g, " ");
}

function gradeAnswer(
  question: Record<string, unknown>,
  rawValue: unknown,
): {autoScore: number; finalScore: number; isCorrect: boolean; value: unknown} {
  const points = asFiniteNumber(question.points, 0);
  const type = String(question.type ?? "mc");

  if (type === "mc" || type === "multipleChoice") {
    let selected: number | null = null;
    if (typeof rawValue === "number" && Number.isFinite(rawValue)) {
      selected = rawValue;
    } else if (rawValue != null && String(rawValue).trim() !== "") {
      const parsed = Number.parseInt(String(rawValue), 10);
      selected = Number.isFinite(parsed) ? parsed : null;
    }
    const correct = asFiniteNumber(question.correctIndex, Number.NaN);
    const isCorrect =
      selected != null && Number.isFinite(correct) && selected === correct;
    const score = isCorrect ? points : 0;
    return {
      // Firestore는 undefined 거부 → 미응답은 null
      value: selected,
      autoScore: score,
      finalScore: score,
      isCorrect,
    };
  }

  // short answer
  const text = String(rawValue ?? "").trim();
  const normalized = normalizeShortAnswer(text);
  const accepted: string[] = Array.isArray(question.acceptedAnswers)
    ? question.acceptedAnswers.map(normalizeShortAnswer)
    : [];
  const isCorrect =
    normalized.length > 0 && accepted.includes(normalized);
  const score = isCorrect ? points : 0;
  return {
    value: text,
    autoScore: score,
    finalScore: score,
    isCorrect,
  };
}

function toMillis(v: unknown): number | null {
  if (v == null) return null;
  if (typeof v === "number" && Number.isFinite(v)) return v;
  if (typeof v === "string") {
    const parsed = Date.parse(v);
    return Number.isFinite(parsed) ? parsed : null;
  }
  if (typeof v === "object") {
    const anyV = v as {
      toDate?: () => Date;
      toMillis?: () => number;
      _seconds?: number;
      seconds?: number;
    };
    if (typeof anyV.toMillis === "function") {
      try {
        const ms = anyV.toMillis();
        return Number.isFinite(ms) ? ms : null;
      } catch {
        /* fall through */
      }
    }
    if (typeof anyV.toDate === "function") {
      try {
        return anyV.toDate().getTime();
      } catch {
        /* fall through */
      }
    }
    const seconds =
      typeof anyV._seconds === "number"
        ? anyV._seconds
        : typeof anyV.seconds === "number"
          ? anyV.seconds
          : null;
    if (seconds != null) return seconds * 1000;
  }
  return null;
}

function asFiniteNumber(v: unknown, fallback = 0): number {
  if (v == null || v === "") return fallback;
  const n = typeof v === "number" ? v : Number(v);
  return Number.isFinite(n) ? n : fallback;
}

/** Firestore/Callable JSON에 undefined가 섞이면 500이 난다 */
function stripUndefined<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

/**
 * 학생용 — 정답 없는 문항 페이로드
 */
export const getAssessmentForTake = onCall(callOptions, async (request) => {
  try {
    if (!request.auth) {
      throw new HttpsError("unauthenticated", "인증이 필요합니다.");
    }
    const caller = await getCaller(request.auth.uid);
    const {cohortId, assessmentId} = request.data as {
      cohortId?: string;
      assessmentId?: string;
    };
    if (!cohortId || !assessmentId) {
      throw new HttpsError(
        "invalid-argument",
        "cohortId, assessmentId가 필요합니다.",
      );
    }
    assertCohortMember(caller, cohortId);

    const assessmentRef = db
      .collection("cohorts")
      .doc(cohortId)
      .collection("assessments")
      .doc(assessmentId);
    const assessmentSnap = await assessmentRef.get();
    if (!assessmentSnap.exists) {
      throw new HttpsError("not-found", "평가를 찾을 수 없습니다.");
    }
    const assessment = assessmentSnap.data()!;
    if (!assessment.published && caller.role === "student") {
      throw new HttpsError(
        "failed-precondition",
        "아직 공개되지 않은 평가입니다.",
      );
    }

    const now = Date.now();
    const startAt = toMillis(assessment.startAt) ?? 0;
    const endAt = toMillis(assessment.endAt) ?? Number.MAX_SAFE_INTEGER;
    if (caller.role === "student") {
      if (now < startAt) {
        throw new HttpsError(
          "failed-precondition",
          "아직 응시 기간이 아닙니다.",
        );
      }
      if (now > endAt) {
        throw new HttpsError(
          "failed-precondition",
          "응시 기간이 종료되었습니다.",
        );
      }
    }

    const submissionId = `${assessmentId}_${caller.uid}`;
    const submissionSnap = await db
      .collection("cohorts")
      .doc(cohortId)
      .collection("assessmentSubmissions")
      .doc(submissionId)
      .get();
    if (submissionSnap.exists && caller.role === "student") {
      throw new HttpsError(
        "already-exists",
        "이미 응시한 평가입니다. 결과만 확인할 수 있습니다.",
      );
    }

    // orderBy는 인덱스/필드 이슈를 피하기 위해 클라이언트(함수)에서 정렬
    const questionsSnap = await assessmentRef.collection("questions").get();

    const questions = questionsSnap.docs
      .map((doc) => {
        const q = doc.data();
        const type = String(q.type ?? "mc");
        const isMc = type === "mc" || type === "multipleChoice";
        return {
          id: doc.id,
          order: asFiniteNumber(q.order, 0),
          type: isMc ? "mc" : "sa",
          prompt: String(q.prompt ?? ""),
          points: asFiniteNumber(q.points, 0),
          choices: isMc
            ? (Array.isArray(q.choices) ? q.choices.map((c) => String(c)) : [])
            : [],
        };
      })
      .sort((a, b) => a.order - b.order);

    return {
      assessment: {
        id: assessmentId,
        title: String(assessment.title ?? ""),
        tags: Array.isArray(assessment.tags)
          ? assessment.tags.map((t) => String(t))
          : [],
        questionCount: asFiniteNumber(
          assessment.questionCount,
          questions.length,
        ),
        maxScore: asFiniteNumber(assessment.maxScore, 0),
        startAtMs: toMillis(assessment.startAt),
        endAtMs: toMillis(assessment.endAt),
        thumbnailUrl:
          typeof assessment.thumbnailUrl === "string"
            ? assessment.thumbnailUrl
            : null,
      },
      questions,
    };
  } catch (err) {
    if (err instanceof HttpsError) throw err;
    logger.error("getAssessmentForTake failed", err);
    const message =
      err instanceof Error && err.message
        ? err.message
        : "평가를 불러오는 중 오류가 발생했습니다.";
    throw new HttpsError("internal", message);
  }
});

/**
 * 학생 제출 + 서버 자동채점 (1회)
 */
export const submitAssessment = onCall(callOptions, async (request) => {
  try {
    if (!request.auth) {
      throw new HttpsError("unauthenticated", "인증이 필요합니다.");
    }
    const caller = await getCaller(request.auth.uid);
    const {cohortId, assessmentId, answers} = request.data as {
      cohortId?: string;
      assessmentId?: string;
      answers?: Record<string, unknown>;
    };
    if (!cohortId || !assessmentId || !answers || typeof answers !== "object") {
      throw new HttpsError(
        "invalid-argument",
        "cohortId, assessmentId, answers가 필요합니다.",
      );
    }
    assertCohortMember(caller, cohortId);
    if (caller.role !== "student") {
      throw new HttpsError("permission-denied", "학생만 제출할 수 있습니다.");
    }

    const assessmentRef = db
      .collection("cohorts")
      .doc(cohortId)
      .collection("assessments")
      .doc(assessmentId);
    const submissionRef = db
      .collection("cohorts")
      .doc(cohortId)
      .collection("assessmentSubmissions")
      .doc(`${assessmentId}_${caller.uid}`);

    const assessmentSnap = await assessmentRef.get();
    if (!assessmentSnap.exists) {
      throw new HttpsError("not-found", "평가를 찾을 수 없습니다.");
    }
    const assessment = assessmentSnap.data()!;
    if (!assessment.published) {
      throw new HttpsError("failed-precondition", "공개되지 않은 평가입니다.");
    }
    const now = Date.now();
    const startAt = toMillis(assessment.startAt) ?? 0;
    const endAt = toMillis(assessment.endAt) ?? Number.MAX_SAFE_INTEGER;
    if (now < startAt || now > endAt) {
      throw new HttpsError("failed-precondition", "응시 가능 기간이 아닙니다.");
    }

    const existing = await submissionRef.get();
    if (existing.exists) {
      throw new HttpsError("already-exists", "이미 응시한 평가입니다.");
    }

    const questionsSnap = await assessmentRef.collection("questions").get();

    const graded: Record<
      string,
      {
        value: unknown;
        autoScore: number;
        finalScore: number;
        isCorrect: boolean;
      }
    > = {};
    let autoTotal = 0;
    for (const doc of questionsSnap.docs) {
      const q = doc.data() as Record<string, unknown>;
      const gradedOne = gradeAnswer(q, answers[doc.id]);
      graded[doc.id] = {
        value: gradedOne.value === undefined ? null : gradedOne.value,
        autoScore: asFiniteNumber(gradedOne.autoScore, 0),
        finalScore: asFiniteNumber(gradedOne.finalScore, 0),
        isCorrect: Boolean(gradedOne.isCorrect),
      };
      autoTotal += graded[doc.id].finalScore;
    }
    autoTotal = asFiniteNumber(autoTotal, 0);

    try {
      await submissionRef.create({
        assessmentId,
        userId: caller.uid,
        userDisplayName: caller.displayName ?? "",
        answers: stripUndefined(graded),
        autoTotalScore: autoTotal,
        totalScore: autoTotal,
        status: "submitted",
        submittedAt: fieldValue.serverTimestamp(),
        scoreAdjustments: [],
      });
    } catch (e: unknown) {
      const err = e as {code?: number | string};
      if (err.code === 6 || err.code === "already-exists") {
        throw new HttpsError("already-exists", "이미 응시한 평가입니다.");
      }
      throw e;
    }

    return {
      totalScore: autoTotal,
      autoTotalScore: autoTotal,
      submissionId: submissionRef.id,
    };
  } catch (err) {
    if (err instanceof HttpsError) throw err;
    logger.error("submitAssessment failed", err);
    const message =
      err instanceof Error && err.message
        ? err.message
        : "제출 처리 중 오류가 발생했습니다.";
    throw new HttpsError("internal", message);
  }
});

/**
 * 제출 후 리뷰 — 문항(정답 포함) + 내 제출 답안
 * 학생: 본인 제출이 있을 때만 / 스태프: submissionId로 조회 가능
 */
export const getAssessmentReview = onCall(callOptions, async (request) => {
  try {
    if (!request.auth) {
      throw new HttpsError("unauthenticated", "인증이 필요합니다.");
    }
    const caller = await getCaller(request.auth.uid);
    const {cohortId, assessmentId, submissionId} = request.data as {
      cohortId?: string;
      assessmentId?: string;
      submissionId?: string;
    };
    if (!cohortId || !assessmentId) {
      throw new HttpsError(
        "invalid-argument",
        "cohortId, assessmentId가 필요합니다.",
      );
    }
    assertCohortMember(caller, cohortId);

    const isStaff =
      caller.role === "admin" ||
      (caller.role === "instructor" && caller.cohortId === cohortId);

    const resolvedSubmissionId =
      submissionId ||
      (isStaff ? undefined : `${assessmentId}_${caller.uid}`);

    if (!resolvedSubmissionId) {
      throw new HttpsError(
        "invalid-argument",
        "스태프는 submissionId가 필요합니다.",
      );
    }

    const submissionRef = db
      .collection("cohorts")
      .doc(cohortId)
      .collection("assessmentSubmissions")
      .doc(resolvedSubmissionId);
    const submissionSnap = await submissionRef.get();
    if (!submissionSnap.exists) {
      throw new HttpsError("not-found", "제출 기록이 없습니다.");
    }
    const submission = submissionSnap.data()!;
    if (!isStaff && submission.userId !== caller.uid) {
      throw new HttpsError(
        "permission-denied",
        "본인 결과만 조회할 수 있습니다.",
      );
    }
    if (submission.assessmentId !== assessmentId) {
      throw new HttpsError("invalid-argument", "평가 ID가 일치하지 않습니다.");
    }

    const questionsSnap = await db
      .collection("cohorts")
      .doc(cohortId)
      .collection("assessments")
      .doc(assessmentId)
      .collection("questions")
      .get();

    const questions = questionsSnap.docs
      .map((doc) => {
        const q = doc.data();
        const type = String(q.type ?? "mc");
        const isMc = type === "mc" || type === "multipleChoice";
        return {
          id: doc.id,
          order: asFiniteNumber(q.order, 0),
          type: isMc ? "mc" : "sa",
          prompt: String(q.prompt ?? ""),
          points: asFiniteNumber(q.points, 0),
          choices: Array.isArray(q.choices)
            ? q.choices.map((c) => String(c))
            : [],
          correctIndex:
            q.correctIndex == null ? null : asFiniteNumber(q.correctIndex, 0),
          acceptedAnswers: Array.isArray(q.acceptedAnswers)
            ? q.acceptedAnswers.map((a) => String(a))
            : [],
          explanation:
            q.explanation == null ? null : String(q.explanation),
        };
      })
      .sort((a, b) => a.order - b.order);

    // answers 안의 undefined/Timestamp 등을 JSON-safe 하게
    const rawAnswers = submission.answers ?? {};
    const safeAnswers = stripUndefined(rawAnswers);

    return stripUndefined({
      questions,
      submission: {
        id: submissionSnap.id,
        totalScore: asFiniteNumber(submission.totalScore, 0),
        autoTotalScore: asFiniteNumber(submission.autoTotalScore, 0),
        answers: safeAnswers,
        userDisplayName: String(submission.userDisplayName ?? ""),
      },
    });
  } catch (err) {
    if (err instanceof HttpsError) throw err;
    logger.error("getAssessmentReview failed", err);
    const message =
      err instanceof Error && err.message
        ? err.message
        : "결과를 불러오는 중 오류가 발생했습니다.";
    throw new HttpsError("internal", message);
  }
});

/**
 * 강사 — 문항별 점수 수정 → 총점 재계산
 */
export const adjustAssessmentScores = onCall(callOptions, async (request) => {
  if (!request.auth) {
    throw new HttpsError("unauthenticated", "인증이 필요합니다.");
  }
  const caller = await getCaller(request.auth.uid);
  const {cohortId, submissionId, adjustments, note} = request.data as {
    cohortId?: string;
    submissionId?: string;
    adjustments?: Array<{questionId: string; finalScore: number}>;
    note?: string;
  };
  if (!cohortId || !submissionId || !Array.isArray(adjustments)) {
    throw new HttpsError(
      "invalid-argument",
      "cohortId, submissionId, adjustments가 필요합니다.",
    );
  }
  assertStaffOfCohort(caller, cohortId);

  const submissionRef = db
    .collection("cohorts")
    .doc(cohortId)
    .collection("assessmentSubmissions")
    .doc(submissionId);

  const submissionSnap = await submissionRef.get();
  if (!submissionSnap.exists) {
    throw new HttpsError("not-found", "제출을 찾을 수 없습니다.");
  }
  const submission = submissionSnap.data()!;
  const answers = {...(submission.answers ?? {})} as Record<
    string,
    {value: unknown; autoScore: number; finalScore: number; isCorrect: boolean}
  >;
  const history = [...(submission.scoreAdjustments ?? [])];

  for (const adj of adjustments) {
    const qid = adj.questionId;
    if (!qid || answers[qid] == null) continue;
    const previous = Number(answers[qid].finalScore ?? 0);
    const next = Math.max(0, Math.floor(Number(adj.finalScore)));
    if (previous === next) continue;
    answers[qid] = {
      ...answers[qid],
      finalScore: next,
      isCorrect: next > 0,
    };
    history.push({
      questionId: qid,
      previous,
      next,
      by: caller.uid,
      byName: caller.displayName ?? "",
      // Firestore: serverTimestamp()는 배열 요소 안에서 사용 불가
      at: new Date(),
      ...(note ? {note} : {}),
    });
  }

  const totalScore = Object.values(answers).reduce(
    (sum, a) => sum + Number(a.finalScore ?? 0),
    0,
  );

  await submissionRef.update({
    answers,
    totalScore,
    scoreAdjustments: history,
    updatedAt: fieldValue.serverTimestamp(),
  });

  return {totalScore, submissionId};
});

function resolveOpenaiApiKey(): string {
  const fromSecret = openaiApiKey.value().trim();
  if (fromSecret) return fromSecret;

  throw new HttpsError(
    "failed-precondition",
    "OPENAI_API_KEY Secret이 없습니다. firebase functions:secrets:set OPENAI_API_KEY 후 " +
      "firebase deploy --only functions:generateAssessmentQuestions 로 배포하세요.",
  );
}

async function writeAiGenerationLog(
  logRef: {set: (data: Record<string, unknown>) => Promise<unknown>},
  data: Record<string, unknown>,
): Promise<void> {
  try {
    await logRef.set({
      ...data,
      createdAt: fieldValue.serverTimestamp(),
    });
  } catch (e) {
    logger.error("aiGenerationLogs write failed", e);
  }
}

/**
 * 커리큘럼 CSV 시트 구간 → AI 문제 초안 생성
 * LLMOps: promptVersion + aiGenerationLogs (type=assessment_questions | assessment_questions_regen)
 * replaceOf가 있으면 선택 문항만 같은 단원 기준으로 재생성
 */
export const generateAssessmentQuestions = onCall(
  {
    ...callOptions,
    timeoutSeconds: 300,
    memory: "512MiB",
    cpu: 1,
    concurrency: 1,
    secrets: [openaiApiKey],
  },
  async (request) => {
    try {
      ensureInitialized();
      return await runGenerateAssessmentQuestions(request);
    } catch (e) {
      if (e instanceof HttpsError) throw e;
      const message = e instanceof Error ? e.message : String(e);
      logger.error("generateAssessmentQuestions unhandled", e);
      throw new HttpsError(
        "internal",
        `AI 문제 생성 실패: ${message.slice(0, 240)}`,
      );
    }
  },
);

async function runGenerateAssessmentQuestions(
  request: CallableRequest,
) {
    if (!request.auth) {
      throw new HttpsError("unauthenticated", "인증이 필요합니다.");
    }
    const caller = await getCaller(request.auth.uid);
    const {
      cohortId,
      sheetId,
      dayFrom,
      dayTo,
      mcCount = 40,
      saCount = 10,
      subjectFilter,
      replaceOf,
      parentLogId,
    } = request.data as {
      cohortId?: string;
      sheetId?: string;
      dayFrom?: number;
      dayTo?: number;
      mcCount?: number;
      saCount?: number;
      subjectFilter?: string;
      replaceOf?: ReplaceHint[];
      parentLogId?: string;
    };

    if (!cohortId || !sheetId) {
      throw new HttpsError("invalid-argument", "cohortId, sheetId가 필요합니다.");
    }
    assertStaffOfCohort(caller, cohortId);

    if (dayFrom == null || dayTo == null) {
      throw new HttpsError("invalid-argument", "dayFrom, dayTo가 필요합니다.");
    }

    const isRegen = Array.isArray(replaceOf) && replaceOf.length > 0;
    const regenHints = isRegen ? replaceOf!.slice(0, 20) : [];
    let resolvedMc = Math.max(0, Number(mcCount) || 0);
    let resolvedSa = Math.max(0, Number(saCount) || 0);
    if (isRegen) {
      resolvedMc = regenHints.filter((h) => h.type !== "sa").length;
      resolvedSa = regenHints.filter((h) => h.type === "sa").length;
    }

    const logRef = db.collection("aiGenerationLogs").doc();
    const logId = logRef.id;
    const startedAt = Date.now();

    const baseLog: Record<string, unknown> = {
      type: isRegen ? "assessment_questions_regen" : "assessment_questions",
      promptVersion: assessmentPromptVersion(),
      model: ASSESSMENT_MODEL,
      cohortId,
      sheetId,
      dayFrom,
      dayTo,
      mcCount: resolvedMc,
      saCount: resolvedSa,
      createdBy: caller.uid,
      createdByName: caller.displayName ?? "",
    };
    if (parentLogId) baseLog.parentLogId = parentLogId;
    if (isRegen) {
      baseLog.replaceDraftIds = regenHints
        .map((h) => h.draftId)
        .filter(Boolean);
    }

    try {
      const sheetSnap = await db
        .collection("cohorts")
        .doc(cohortId)
        .collection("curriculumSheets")
        .doc(sheetId)
        .get();
      if (!sheetSnap.exists) {
        await writeAiGenerationLog(logRef, {
          ...baseLog,
          generatedCount: 0,
          rowCount: 0,
          latencyMs: Date.now() - startedAt,
          status: "error",
          errorMessage: "curriculum sheet not found",
          drafts: [],
        });
        throw new HttpsError("not-found", "커리큘럼 시트를 찾을 수 없습니다.");
      }
      const sheet = sheetSnap.data()!;
      const rows = (Array.isArray(sheet.rows) ? sheet.rows : []) as Array<
        Record<string, unknown>
      >;
      const from = Math.min(dayFrom, dayTo);
      const to = Math.max(dayFrom, dayTo);
      const filtered = rows.filter((r) => {
        const day = Number(r.dayIndex ?? 0);
        if (day < from || day > to) return false;
        if (subjectFilter && String(r.subject ?? "") !== subjectFilter) {
          return false;
        }
        return true;
      });

      if (filtered.length === 0) {
        await writeAiGenerationLog(logRef, {
          ...baseLog,
          generatedCount: 0,
          rowCount: 0,
          latencyMs: Date.now() - startedAt,
          status: "error",
          errorMessage: "no curriculum rows in day range",
          drafts: [],
        });
        throw new HttpsError(
          "failed-precondition",
          "선택한 일수 구간에 커리큘럼 행이 없습니다.",
        );
      }

      const corpus = filtered
        .map((r) => {
          const day = r.dayIndex ?? "?";
          const date = r.dateLabel ? ` (${r.dateLabel})` : "";
          const subject = r.subject ?? "";
          const topic = r.topic ?? "";
          const detail = r.detail ?? "";
          const extra =
            detail && String(detail) !== String(topic) ?
              ` | 세부: ${detail}` :
              "";
          return `- 일수 ${day}${date} | 교과목: ${subject} | 내용: ${topic}${extra}`;
        })
        .join("\n")
        .slice(0, 24000);

      const topicList = [
        ...new Set(
          filtered
            .map((r) => String(r.topic ?? "").trim())
            .filter((t) => t.length > 0),
        ),
      ].join(", ");
      const subjectList = [
        ...new Set(
          filtered
            .map((r) => String(r.subject ?? "").trim())
            .filter((t) => t.length > 0),
        ),
      ].join(", ");

      const apiKey = resolveOpenaiApiKey();
      const openaiStarted = Date.now();

      const promptJobs: string[] = [];
      if (isRegen) {
        promptJobs.push(
          buildAssessmentRegenPrompt({
            sheetTitle: String(sheet.title ?? ""),
            sheetId,
            from,
            to,
            subjectList,
            topicList,
            corpus,
            replaceOf: regenHints,
          }),
        );
      } else {
        const batches: Array<{mcCount: number; saCount: number}> = [];
        const mcBatchSize = 20;
        let mcLeft = resolvedMc;
        while (mcLeft > 0) {
          const n = Math.min(mcBatchSize, mcLeft);
          batches.push({mcCount: n, saCount: 0});
          mcLeft -= n;
        }
        if (resolvedSa > 0) {
          batches.push({mcCount: 0, saCount: resolvedSa});
        }
        if (batches.length === 0) {
          throw new HttpsError(
            "invalid-argument",
            "객관식 또는 단답 문항 수를 1개 이상 지정하세요.",
          );
        }
        for (const batch of batches) {
          promptJobs.push(
            buildAssessmentUserPrompt({
              sheetTitle: String(sheet.title ?? ""),
              sheetId,
              from,
              to,
              subjectList,
              topicList,
              mcCount: batch.mcCount,
              saCount: batch.saCount,
              corpus,
            }),
          );
        }
      }

      const rawQuestions: unknown[] = [];
      for (const userPrompt of promptJobs) {
        const openaiRes = await fetch(
          "https://api.openai.com/v1/chat/completions",
          {
            method: "POST",
            headers: {
              Authorization: `Bearer ${apiKey}`,
              "Content-Type": "application/json",
            },
            body: JSON.stringify({
              model: ASSESSMENT_MODEL,
              temperature: isRegen ? 0.45 : 0.2,
              max_tokens: isRegen ? 8000 : 12000,
              response_format: {type: "json_object"},
              messages: [
                {role: "system", content: ASSESSMENT_SYSTEM_PROMPT},
                {role: "user", content: userPrompt},
              ],
            }),
          },
        );

        if (!openaiRes.ok) {
          const errText = await openaiRes.text();
          logger.error("OpenAI error", {
            status: openaiRes.status,
            errText: errText.slice(0, 500),
          });
          await writeAiGenerationLog(logRef, {
            ...baseLog,
            generatedCount: rawQuestions.length,
            rowCount: filtered.length,
            latencyMs: Date.now() - startedAt,
            status: "error",
            errorMessage: `OpenAI ${openaiRes.status}`,
            drafts: [],
          });
          throw new HttpsError(
            "internal",
            `AI 문제 생성 실패 (OpenAI ${openaiRes.status}). API 키·쿼터를 확인하세요.`,
          );
        }

        const openaiJson = (await openaiRes.json()) as {
          choices?: Array<{
            finish_reason?: string;
            message?: {content?: string};
          }>;
        };
        const choice = openaiJson.choices?.[0];
        const content = choice?.message?.content ?? "{}";
        if (choice?.finish_reason === "length") {
          logger.warn("OpenAI truncated", {contentLen: content.length});
        }
        let parsed: {questions?: unknown[]};
        try {
          parsed = JSON.parse(content);
        } catch {
          await writeAiGenerationLog(logRef, {
            ...baseLog,
            generatedCount: rawQuestions.length,
            rowCount: filtered.length,
            latencyMs: Date.now() - startedAt,
            status: "error",
            errorMessage: "JSON parse failed",
            drafts: [],
          });
          throw new HttpsError(
            "internal",
            "AI 응답을 파싱하지 못했습니다. 문항 수를 줄여 다시 시도해 주세요.",
          );
        }
        rawQuestions.push(...(parsed.questions ?? []));
      }

      const questions = rawQuestions.map((raw, index) => {
        const q = raw as Record<string, unknown>;
        const type = q.type === "sa" ? "sa" : "mc";
        const draftId = `draft_${index}`;
        const sourceDayRaw = q.sourceDay;
        const sourceDayNum =
          sourceDayRaw == null ? null : Number(sourceDayRaw);
        const sourceDay =
          sourceDayNum != null && Number.isFinite(sourceDayNum) ?
            sourceDayNum :
            undefined;
        const sourceTopic = q.sourceTopic ? String(q.sourceTopic) : undefined;
        const explanation = q.explanation ? String(q.explanation) : undefined;
        const item: Record<string, unknown> = {
          id: draftId,
          order: index,
          type,
          prompt: String(q.prompt ?? ""),
          points: Number(q.points ?? (type === "mc" ? 4 : 5)),
          choices: type === "mc" ?
            (Array.isArray(q.choices) ? q.choices.map(String) : []) :
            [],
          acceptedAnswers: type === "sa" ?
            (Array.isArray(q.acceptedAnswers) ?
              q.acceptedAnswers.map(String) :
              []) :
            [],
          origin: "ai",
          aiLogId: logId,
          promptVersion: assessmentPromptVersion(),
          aiDraftId: draftId,
        };
        if (type === "mc") {
          item.correctIndex = Number(q.correctIndex ?? 0);
        }
        if (explanation) item.explanation = explanation;
        if (sourceDay != null) item.sourceDay = sourceDay;
        if (sourceTopic) item.sourceTopic = sourceTopic;
        return item;
      });

      if (questions.length === 0) {
        await writeAiGenerationLog(logRef, {
          ...baseLog,
          generatedCount: 0,
          rowCount: filtered.length,
          latencyMs: Date.now() - openaiStarted,
          status: "error",
          errorMessage: "empty questions",
          drafts: [],
        });
        throw new HttpsError(
          "internal",
          "AI가 문항을 생성하지 못했습니다. 구간·문항 수를 조정해 다시 시도하세요.",
        );
      }

      const drafts = questions.map((q) => ({
        draftId: q.id,
        type: q.type,
        ...(q.sourceDay != null ? {sourceDay: q.sourceDay} : {}),
        ...(q.sourceTopic ? {sourceTopic: q.sourceTopic} : {}),
        promptPreview: String(q.prompt).slice(0, 120),
      }));

      await writeAiGenerationLog(logRef, {
        ...baseLog,
        generatedCount: questions.length,
        rowCount: filtered.length,
        latencyMs: Date.now() - openaiStarted,
        status: "success",
        drafts,
      });

      return {
        questions,
        rowCount: filtered.length,
        logId,
        promptVersion: assessmentPromptVersion(),
        model: ASSESSMENT_MODEL,
        ...(parentLogId ? {parentLogId} : {}),
        isRegen,
      };
    } catch (e) {
      if (e instanceof HttpsError) {
        throw e;
      }
      const message = e instanceof Error ? e.message : String(e);
      logger.error("generateAssessmentQuestions failed", e);
      await writeAiGenerationLog(logRef, {
        ...baseLog,
        generatedCount: 0,
        rowCount: 0,
        latencyMs: Date.now() - startedAt,
        status: "error",
        errorMessage: message.slice(0, 500),
        drafts: [],
      });
      throw new HttpsError(
        "internal",
        `AI 문제 생성 중 오류: ${message.slice(0, 200)}`,
      );
    }
}

/**
 * 강사 채택/폐기/수정 피드백 배치 기록
 * outcome 확장 예정: clicked | ignored (오답→추천)
 */
export const recordAiQuestionFeedback = onCall(
  callOptions,
  async (request) => {
    if (!request.auth) {
      throw new HttpsError("unauthenticated", "인증이 필요합니다.");
    }
    const caller = await getCaller(request.auth.uid);
    const {
      cohortId,
      logId,
      promptVersion,
      assessmentId,
      items,
    } = request.data as {
      cohortId?: string;
      logId?: string;
      promptVersion?: string;
      assessmentId?: string;
      items?: Array<{
        draftId: string;
        outcome: "adopted" | "edited" | "discarded";
        sourceDay?: number | string | null;
        sourceTopic?: string | null;
        questionId?: string;
      }>;
    };

    if (!cohortId || !logId || !Array.isArray(items) || items.length === 0) {
      throw new HttpsError(
        "invalid-argument",
        "cohortId, logId, items가 필요합니다.",
      );
    }
    assertStaffOfCohort(caller, cohortId);

    const batch = db.batch();
    for (const item of items) {
      if (!item?.draftId || !item?.outcome) continue;
      if (!["adopted", "edited", "discarded"].includes(item.outcome)) {
        continue;
      }
      const docId = `${logId}_${item.draftId}`;
      const ref = db.collection("aiQuestionFeedback").doc(docId);
      const existing = await ref.get();
      const payload: Record<string, unknown> = {
        logId,
        draftId: item.draftId,
        cohortId,
        outcome: item.outcome,
        promptVersion: promptVersion ?? assessmentPromptVersion(),
        actorUid: caller.uid,
        updatedAt: fieldValue.serverTimestamp(),
      };
      if (assessmentId) payload.assessmentId = assessmentId;
      if (item.questionId) payload.questionId = item.questionId;
      if (item.sourceDay != null) payload.sourceDay = item.sourceDay;
      if (item.sourceTopic != null) payload.sourceTopic = item.sourceTopic;
      if (!existing.exists) {
        payload.createdAt = fieldValue.serverTimestamp();
      }
      batch.set(ref, payload, {merge: true});
    }
    await batch.commit();
    return {ok: true, count: items.length};
  },
);
