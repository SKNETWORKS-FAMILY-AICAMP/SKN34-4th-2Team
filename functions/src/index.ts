import {onCall, HttpsError} from "firebase-functions/v2/https";
import {onInit} from "firebase-functions/v2/core";
import {randomBytes} from "crypto";
import * as logger from "firebase-functions/logger";
import type {UserRecord} from "firebase-admin/auth";

import {auth, db, ensureInitialized, fieldValue} from "./firebase";

// Gen2: deploy discovery 때는 실행되지 않고, 런타임 요청 전에 Admin SDK 준비
onInit(() => {
  ensureInitialized();
});

export {
  syncDiscordNotices,
  syncDiscordNoticesNow,
} from "./discord";
export {googleFormWebhook} from "./googleForm";
export {
  createInstructorAccount,
  updateInstructorAccount,
  resetInstructorPassword,
  setInstructorActiveStatus,
} from "./instructors";
export {getQualExamSchedules} from "./qualExamSchd";
export {publishScheduledNotices, publishScheduledNoticesNow} from "./scheduledNotices";
export {syncNoticeVector} from "./noticeVectors";
export {
  submitPurchaseRequest,
  reviewPurchaseRequest,
  cancelPurchaseRequest,
  expireMileage,
  expireMileageNow,
} from "./mileage";
export {settleMissionsOnApproval} from "./missions";
export {
  getAssessmentForTake,
  submitAssessment,
  getAssessmentReview,
  adjustAssessmentScores,
  generateAssessmentQuestions,
  recordAiQuestionFeedback,
} from "./assessments";
export {recordAiGenerationLog, recordAiOutcomeFeedback} from "./aiOps";
export {getCurriculumYoutubeRecommendations} from "./youtubeRecommendations";
import {settleMissionsOnApproval} from "./missions";

const EMAIL_DOMAIN = "playdata.co.kr";

interface StudentIntakePayload {
  educationMajor?: string;
  currentStatus?: string;
  weeklyStudyHours?: string;
  programmingLevel?: string;
  collaborationTools?: string;
  aiLlmExperience?: string;
  motivation?: string;
  desiredRole?: string;
  postCompletionGoal?: string;
  awards?: string;
  projectLinks?: string;
  teamRole?: string;
  selfLearningStyle?: string;
  slumpOvercomeExperience?: string;
}

interface CreateStudentRequest {
  displayName: string;
  personalEmail: string;
  cohortId: string;
  cohortName: string;
  seatNumber?: number;
  intake?: StudentIntakePayload;
}

function normalizeEmail(email: string): string {
  return email.trim().toLowerCase();
}

function isValidEmail(email: string): boolean {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
}

async function assertPersonalEmailAvailable(personalEmail: string): Promise<void> {
  await assertPersonalEmailAvailableForUser(personalEmail, null);
}

async function assertPersonalEmailAvailableForUser(
  personalEmail: string,
  excludeUid: string | null,
): Promise<void> {
  const snap = await db
    .collection("users")
    .where("personalEmail", "==", personalEmail)
    .limit(2)
    .get();
  const taken = snap.docs.some((doc) => doc.id !== excludeUid);
  if (taken) {
    throw new HttpsError(
      "already-exists",
      "이미 다른 학생이 사용 중인 이메일입니다.",
    );
  }
}

function randomChars(length: number, charset: string): string {
  const bytes = randomBytes(length);
  let result = "";
  for (let i = 0; i < length; i++) {
    result += charset[bytes[i] % charset.length];
  }
  return result;
}

function generateRandomEmail(): string {
  const local = randomChars(12, "abcdefghijklmnopqrstuvwxyz0123456789");
  return `${local}@${EMAIL_DOMAIN}`;
}

function generateRandomPassword(): string {
  const length = 8 + Math.floor(Math.random() * 5);
  const charset =
    "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghjkmnpqrstuvwxyz23456789!@#$";
  return randomChars(length, charset);
}

async function assertAdmin(uid: string): Promise<void> {
  const callerDoc = await db.collection("users").doc(uid).get();
  if (!callerDoc.exists || callerDoc.data()?.role !== "admin") {
    throw new HttpsError(
      "permission-denied",
      "관리자만 이 작업을 수행할 수 있습니다.",
    );
  }
}

/**
 * 관리자 전용 — 상담 정보 기반 학생 계정 생성
 * 랜덤 이메일 + 랜덤 비밀번호 자동 생성
 */
export const createStudentAccount = onCall(
  {region: "asia-northeast3"},
  async (request) => {
    if (!request.auth) {
      throw new HttpsError("unauthenticated", "인증이 필요합니다.");
    }
    await assertAdmin(request.auth.uid);

    const data = request.data as CreateStudentRequest;
    const {displayName, cohortId, cohortName} = data;
    const intake = data.intake ?? {};
    const personalEmail = normalizeEmail(data.personalEmail ?? "");

    if (!displayName?.trim() || !cohortId || !cohortName) {
      throw new HttpsError(
        "invalid-argument",
        "displayName, cohortId, cohortName은 필수입니다.",
      );
    }

    if (!personalEmail || !isValidEmail(personalEmail)) {
      throw new HttpsError(
        "invalid-argument",
        "올바른 개인 이메일(personalEmail)을 입력해주세요.",
      );
    }

    await assertPersonalEmailAvailable(personalEmail);

    const cohortDoc = await db.collection("cohorts").doc(cohortId).get();
    if (!cohortDoc.exists) {
      throw new HttpsError("not-found", `기수 '${cohortId}'를 찾을 수 없습니다.`);
    }

    let email = "";
    let password = "";
    let userRecord: UserRecord | null = null;

    for (let attempt = 0; attempt < 8; attempt++) {
      email = generateRandomEmail();
      password = generateRandomPassword();
      try {
        userRecord = await auth.createUser({
          email,
          password,
          displayName: displayName.trim(),
          emailVerified: true,
        });
        break;
      } catch (error: unknown) {
        const err = error as {code?: string};
        if (err.code === "auth/email-already-exists") continue;
        throw error;
      }
    }

    if (!userRecord) {
      throw new HttpsError(
        "internal",
        "고유 이메일 생성에 실패했습니다. 다시 시도해주세요.",
      );
    }

    const uid = userRecord.uid;
    const batch = db.batch();

    const userRef = db.collection("users").doc(uid);
    batch.set(userRef, {
      email,
      personalEmail,
      displayName: displayName.trim(),
      role: "student",
      cohortId,
      cohortName,
      seatNumber: data.seatNumber ?? null,
      isActive: true,
      mustChangePassword: true,
      motto: null,
      skills: [],
      socialLinks: {},
      mileageBalance: 0,
      createdAt: fieldValue.serverTimestamp(),
      updatedAt: fieldValue.serverTimestamp(),
      createdBy: request.auth.uid,
    });

    const intakeRef = db.collection("studentIntakes").doc(uid);
    batch.set(intakeRef, {
      email,
      personalEmail,
      displayName: displayName.trim(),
      cohortId,
      cohortName,
      seatNumber: data.seatNumber ?? null,
      initialPassword: password,
      passwordChanged: false,
      isActive: true,
      intake: {
        educationMajor: intake.educationMajor ?? "",
        currentStatus: intake.currentStatus ?? "",
        weeklyStudyHours: intake.weeklyStudyHours ?? "",
        programmingLevel: intake.programmingLevel ?? "",
        collaborationTools: intake.collaborationTools ?? "",
        aiLlmExperience: intake.aiLlmExperience ?? "",
        motivation: intake.motivation ?? "",
        desiredRole: intake.desiredRole ?? "",
        postCompletionGoal: intake.postCompletionGoal ?? "",
        awards: intake.awards ?? "",
        projectLinks: intake.projectLinks ?? "",
        teamRole: intake.teamRole ?? "",
        selfLearningStyle: intake.selfLearningStyle ?? "",
        slumpOvercomeExperience: intake.slumpOvercomeExperience ?? "",
      },
      createdAt: fieldValue.serverTimestamp(),
      createdBy: request.auth.uid,
    });

    const cohortRef = db.collection("cohorts").doc(cohortId);
    batch.update(cohortRef, {
      studentCount: fieldValue.increment(1),
    });

    try {
      await batch.commit();
    } catch (error) {
      await auth.deleteUser(uid).catch(() => undefined);
      throw error;
    }

    return {
      uid,
      email,
      password,
      displayName: displayName.trim(),
      cohortId,
      cohortName,
      message: "학생 계정이 생성되었습니다.",
    };
  },
);

/**
 * 학생 본인 — 구글폼 매칭용 개인 이메일 등록/수정
 */
export const updatePersonalEmail = onCall(
  {region: "asia-northeast3"},
  async (request) => {
    if (!request.auth) {
      throw new HttpsError("unauthenticated", "인증이 필요합니다.");
    }

    const uid = request.auth.uid;
    const {personalEmail} = request.data as {personalEmail?: string};
    const normalized = normalizeEmail(personalEmail ?? "");

    if (!normalized || !isValidEmail(normalized)) {
      throw new HttpsError(
        "invalid-argument",
        "올바른 이메일 형식이 아닙니다.",
      );
    }

    const callerDoc = await db.collection("users").doc(uid).get();
    if (!callerDoc.exists || callerDoc.data()?.isActive !== true) {
      throw new HttpsError(
        "permission-denied",
        "활성 사용자만 수정할 수 있습니다.",
      );
    }

    await assertPersonalEmailAvailableForUser(normalized, uid);

    const batch = db.batch();
    batch.update(db.collection("users").doc(uid), {
      personalEmail: normalized,
      updatedAt: fieldValue.serverTimestamp(),
    });

    const intakeRef = db.collection("studentIntakes").doc(uid);
    const intakeDoc = await intakeRef.get();
    if (intakeDoc.exists) {
      batch.update(intakeRef, {personalEmail: normalized});
    }

    await batch.commit();

    return {
      message: "개인 이메일이 저장되었습니다.",
      personalEmail: normalized,
    };
  },
);

/**
 * 관리자 전용 — 학생 비밀번호 재발급
 */
export const resetStudentPassword = onCall(
  {region: "asia-northeast3"},
  async (request) => {
    if (!request.auth) {
      throw new HttpsError("unauthenticated", "인증이 필요합니다.");
    }
    await assertAdmin(request.auth.uid);

    const {uid} = request.data as {uid?: string};
    if (!uid) {
      throw new HttpsError("invalid-argument", "uid는 필수입니다.");
    }

    const intakeDoc = await db.collection("studentIntakes").doc(uid).get();
    if (!intakeDoc.exists) {
      throw new HttpsError("not-found", "학생 상담 정보를 찾을 수 없습니다.");
    }

    const password = generateRandomPassword();
    await auth.updateUser(uid, {password});

    await db.collection("users").doc(uid).update({
      mustChangePassword: true,
      updatedAt: fieldValue.serverTimestamp(),
    });

    await db.collection("studentIntakes").doc(uid).update({
      initialPassword: password,
      passwordChanged: false,
    });

    return {
      password,
      passwordChanged: false,
      message: "비밀번호가 재발급되었습니다.",
    };
  },
);

interface UpdateStudentRequest extends CreateStudentRequest {
  uid: string;
}

/**
 * 관리자 전용 — 학생 상담 정보 수정
 */
export const updateStudentAccount = onCall(
  {region: "asia-northeast3"},
  async (request) => {
    if (!request.auth) {
      throw new HttpsError("unauthenticated", "인증이 필요합니다.");
    }
    await assertAdmin(request.auth.uid);

    const data = request.data as UpdateStudentRequest;
    const {uid, displayName, cohortId, cohortName} = data;
    const intake = data.intake ?? {};
    const personalEmail = normalizeEmail(data.personalEmail ?? "");

    if (!uid || !displayName?.trim() || !cohortId || !cohortName) {
      throw new HttpsError(
        "invalid-argument",
        "uid, displayName, cohortId, cohortName은 필수입니다.",
      );
    }

    if (!personalEmail || !isValidEmail(personalEmail)) {
      throw new HttpsError(
        "invalid-argument",
        "올바른 개인 이메일(personalEmail)을 입력해주세요.",
      );
    }

    const userDoc = await db.collection("users").doc(uid).get();
    if (!userDoc.exists || userDoc.data()?.role !== "student") {
      throw new HttpsError("not-found", "학생을 찾을 수 없습니다.");
    }

    const intakeDoc = await db.collection("studentIntakes").doc(uid).get();
    if (!intakeDoc.exists) {
      throw new HttpsError("not-found", "학생 상담 정보를 찾을 수 없습니다.");
    }

    await assertPersonalEmailAvailableForUser(personalEmail, uid);

    await auth.updateUser(uid, {displayName: displayName.trim()});

    const batch = db.batch();
    const userRef = db.collection("users").doc(uid);
    batch.update(userRef, {
      displayName: displayName.trim(),
      personalEmail,
      seatNumber: data.seatNumber ?? null,
      updatedAt: fieldValue.serverTimestamp(),
    });

    const intakeRef = db.collection("studentIntakes").doc(uid);
    batch.update(intakeRef, {
      displayName: displayName.trim(),
      personalEmail,
      seatNumber: data.seatNumber ?? null,
      intake: {
        educationMajor: intake.educationMajor ?? "",
        currentStatus: intake.currentStatus ?? "",
        weeklyStudyHours: intake.weeklyStudyHours ?? "",
        programmingLevel: intake.programmingLevel ?? "",
        collaborationTools: intake.collaborationTools ?? "",
        aiLlmExperience: intake.aiLlmExperience ?? "",
        motivation: intake.motivation ?? "",
        desiredRole: intake.desiredRole ?? "",
        postCompletionGoal: intake.postCompletionGoal ?? "",
        awards: intake.awards ?? "",
        projectLinks: intake.projectLinks ?? "",
        teamRole: intake.teamRole ?? "",
        selfLearningStyle: intake.selfLearningStyle ?? "",
        slumpOvercomeExperience: intake.slumpOvercomeExperience ?? "",
      },
    });

    await batch.commit();

    return {
      uid,
      message: "학생 정보가 수정되었습니다.",
    };
  },
);

/**
 * 관리자 전용 — 학생 퇴소(비활성화) / 복학(재활성화)
 */
export const setStudentActiveStatus = onCall(
  {region: "asia-northeast3"},
  async (request) => {
    try {
      ensureInitialized();
      if (!request.auth) {
        throw new HttpsError("unauthenticated", "인증이 필요합니다.");
      }
      await assertAdmin(request.auth.uid);

      const {uid, active} = request.data as {uid?: string; active?: boolean};
      if (!uid || typeof active !== "boolean") {
        throw new HttpsError(
          "invalid-argument",
          "uid와 active(boolean)는 필수입니다.",
        );
      }

      const userDoc = await db.collection("users").doc(uid).get();
      if (!userDoc.exists || userDoc.data()?.role !== "student") {
        throw new HttpsError("not-found", "학생을 찾을 수 없습니다.");
      }

      const userData = userDoc.data()!;
      const currentlyActive = userData.isActive !== false;
      if (currentlyActive === active) {
        throw new HttpsError(
          "failed-precondition",
          active ? "이미 재원 중인 학생입니다." : "이미 퇴소 처리된 학생입니다.",
        );
      }

      const cohortId = userData.cohortId as string;
      if (!cohortId) {
        throw new HttpsError("failed-precondition", "학생의 기수 정보가 없습니다.");
      }

      const batch = db.batch();
      batch.update(db.collection("users").doc(uid), {
        isActive: active,
        updatedAt: fieldValue.serverTimestamp(),
      });

      const intakeRef = db.collection("studentIntakes").doc(uid);
      const intakeDoc = await intakeRef.get();
      if (intakeDoc.exists) {
        batch.update(intakeRef, {isActive: active});
      }

      batch.update(db.collection("cohorts").doc(cohortId), {
        studentCount: fieldValue.increment(active ? 1 : -1),
      });

      await batch.commit();

      return {
        uid,
        active,
        message: active ? "학생이 복학 처리되었습니다." : "학생이 퇴소 처리되었습니다.",
      };
    } catch (error) {
      if (error instanceof HttpsError) throw error;
      const msg = error instanceof Error ? error.message : String(error);
      logger.error("setStudentActiveStatus failed", error);
      throw new HttpsError("internal", msg);
    }
  },
);

/**
 * 관리자 전용 — 관리자 계정 생성 (최초 셋업용)
 */
export const createAdminAccount = onCall(
  {region: "asia-northeast3"},
  async (request) => {
    if (!request.auth) {
      throw new HttpsError("unauthenticated", "인증이 필요합니다.");
    }

    const data = request.data as CreateStudentRequest & {
      setupKey?: string;
      email?: string;
      password?: string;
    };

    const setupKey = process.env.ADMIN_SETUP_KEY ?? "playdata-setup-2026";
    if (data.setupKey !== setupKey) {
      throw new HttpsError("permission-denied", "셋업 키가 올바르지 않습니다.");
    }

    const {email, password, displayName, cohortId, cohortName} = data;
    if (!email || !password || !displayName || !cohortId || !cohortName) {
      throw new HttpsError("invalid-argument", "필수 항목이 누락되었습니다.");
    }

    const userRecord = await auth.createUser({
      email,
      password,
      displayName,
      emailVerified: true,
    });

    await db.collection("users").doc(userRecord.uid).set({
      email,
      displayName,
      role: "admin",
      cohortId,
      cohortName,
      isActive: true,
      mustChangePassword: false,
      skills: [],
      socialLinks: {},
      mileageBalance: 0,
      createdAt: fieldValue.serverTimestamp(),
      updatedAt: fieldValue.serverTimestamp(),
    });

    return {uid: userRecord.uid, message: "관리자 계정이 생성되었습니다."};
  },
);

/**
 * 관리자 전용 — 마일리지 지급/차감
 */
export const adjustMileage = onCall(
  {region: "asia-northeast3"},
  async (request) => {
    if (!request.auth) {
      throw new HttpsError("unauthenticated", "인증이 필요합니다.");
    }
    await assertAdmin(request.auth.uid);

    const {userId, amount, reason, cohortId} = request.data as {
      userId: string;
      amount: number;
      reason: string;
      cohortId: string;
    };

    if (!userId || !reason || !cohortId) {
      throw new HttpsError("invalid-argument", "필수 파라미터가 누락되었습니다.");
    }
    if (!Number.isFinite(amount) || amount === 0) {
      throw new HttpsError("invalid-argument", "amount는 0이 아닌 숫자여야 합니다.");
    }

    const userRef = db.collection("users").doc(userId);
    const txRef = db
      .collection("cohorts")
      .doc(cohortId)
      .collection("mileageTransactions")
      .doc();

    await db.runTransaction(async (transaction) => {
      const userDoc = await transaction.get(userRef);
      if (!userDoc.exists) {
        throw new HttpsError("not-found", "학생을 찾을 수 없습니다.");
      }

      const userData = userDoc.data()!;
      if (userData.cohortId && userData.cohortId !== cohortId) {
        throw new HttpsError(
          "failed-precondition",
          "선택한 기수와 학생 소속이 일치하지 않습니다.",
        );
      }

      const balance = Number(userData.mileageBalance ?? 0);
      if (amount < 0 && balance + amount < 0) {
        throw new HttpsError(
          "failed-precondition",
          `잔액이 부족합니다. (잔액: ${balance.toLocaleString()}M)`,
        );
      }

      transaction.update(userRef, {
        mileageBalance: fieldValue.increment(amount),
        updatedAt: fieldValue.serverTimestamp(),
      });

      transaction.set(txRef, {
        userId,
        userDisplayName: (userData.displayName as string | undefined) ?? "",
        amount,
        reason,
        type: "admin_adjust",
        adjustedBy: request.auth!.uid,
        createdAt: fieldValue.serverTimestamp(),
      });
    });

    return {
      message: `마일리지 ${amount > 0 ? "지급" : "차감"} 완료`,
      txId: txRef.id,
    };
  },
);

/**
 * 관리자 전용 — 제출물 승인/반려
 */
export const reviewSubmission = onCall(
  {region: "asia-northeast3"},
  async (request) => {
    if (!request.auth) {
      throw new HttpsError("unauthenticated", "인증이 필요합니다.");
    }
    await assertAdmin(request.auth.uid);

    const {cohortId, submissionId, status, comment} = request.data as {
      cohortId: string;
      submissionId: string;
      status: "approved" | "rejected";
      comment?: string;
    };

    if (!cohortId || !submissionId || !status) {
      throw new HttpsError("invalid-argument", "필수 파라미터가 누락되었습니다.");
    }

    const submissionRef = db
      .collection("cohorts")
      .doc(cohortId)
      .collection("submissions")
      .doc(submissionId);

    const submissionDoc = await submissionRef.get();
    if (!submissionDoc.exists) {
      throw new HttpsError("not-found", "제출물을 찾을 수 없습니다.");
    }

    const submissionData = submissionDoc.data()!;

    await submissionRef.update({
      status,
      reviewComment: comment ?? null,
      reviewedBy: request.auth.uid,
      reviewedAt: fieldValue.serverTimestamp(),
    });

    if (status === "approved" && !submissionData.mileageGranted) {
      const settled = await settleMissionsOnApproval({
        cohortId,
        submissionId,
        submission: submissionData,
        reviewedBy: request.auth.uid,
      });
      return {
        message: settled.grantedTotal > 0
          ? `승인되었습니다. 미션 마일리지 ${settled.grantedTotal.toLocaleString()}M이 적립되었습니다.`
          : "승인되었습니다.",
        grantedTotal: settled.grantedTotal,
      };
    }

    return {message: `제출물이 ${status === "approved" ? "승인" : "반려"}되었습니다.`};
  },
);
