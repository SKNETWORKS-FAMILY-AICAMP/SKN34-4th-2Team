import {onCall, HttpsError} from "firebase-functions/v2/https";
import {randomBytes} from "crypto";
import * as logger from "firebase-functions/logger";

import {auth, db, fieldValue} from "./firebase";

const EMAIL_DOMAIN = "playdata.co.kr";

const callOptions = {
  region: "asia-northeast3" as const,
  invoker: "public" as const,
};

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

function normalizeEmail(email: string): string {
  return email.trim().toLowerCase();
}

function isValidEmail(email: string): boolean {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
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

async function assertInstructorDoc(uid: string) {
  const userDoc = await db.collection("users").doc(uid).get();
  if (!userDoc.exists || userDoc.data()?.role !== "instructor") {
    throw new HttpsError("not-found", "강사를 찾을 수 없습니다.");
  }
  return userDoc;
}

/**
 * 관리자 전용 — 강사 계정 생성 + 담당 기수 배정
 */
export const createInstructorAccount = onCall(
  callOptions,
  async (request) => {
    if (!request.auth) {
      throw new HttpsError("unauthenticated", "인증이 필요합니다.");
    }
    await assertAdmin(request.auth.uid);

    const data = request.data as {
      displayName?: string;
      cohortId?: string;
      cohortName?: string;
      email?: string;
      password?: string;
      mustChangePassword?: boolean;
    };

    const displayName = data.displayName?.trim() ?? "";
    const {cohortId, cohortName} = data;
    if (!displayName || !cohortId || !cohortName) {
      throw new HttpsError(
        "invalid-argument",
        "displayName, cohortId, cohortName은 필수입니다.",
      );
    }

    const cohortDoc = await db.collection("cohorts").doc(cohortId).get();
    if (!cohortDoc.exists) {
      throw new HttpsError("not-found", `기수 '${cohortId}'를 찾을 수 없습니다.`);
    }

    const requestedEmail = data.email ? normalizeEmail(data.email) : "";
    if (requestedEmail && !isValidEmail(requestedEmail)) {
      throw new HttpsError("invalid-argument", "올바른 이메일을 입력해주세요.");
    }

    let email = requestedEmail;
    let password = data.password?.trim() || generateRandomPassword();
    let userRecord: Awaited<ReturnType<typeof auth.createUser>> | null = null;

    if (requestedEmail) {
      try {
        userRecord = await auth.createUser({
          email: requestedEmail,
          password,
          displayName,
          emailVerified: true,
        });
      } catch (error: unknown) {
        const err = error as {code?: string};
        if (err.code === "auth/email-already-exists") {
          const existing = await auth.getUserByEmail(requestedEmail);
          const existingDoc = await db.collection("users").doc(existing.uid).get();
          const existingRole = existingDoc.data()?.role;
          if (existingDoc.exists && existingRole && existingRole !== "instructor") {
            throw new HttpsError(
              "already-exists",
              "이미 다른 역할로 사용 중인 이메일입니다.",
            );
          }
          await auth.updateUser(existing.uid, {
            password,
            displayName,
            disabled: false,
          });
          await db.collection("users").doc(existing.uid).set(
            {
              email: requestedEmail,
              displayName,
              role: "instructor",
              cohortId,
              cohortName,
              isActive: true,
              mustChangePassword: data.mustChangePassword === true,
              motto: existingDoc.data()?.motto ?? null,
              skills: existingDoc.data()?.skills ?? [],
              socialLinks: existingDoc.data()?.socialLinks ?? {},
              mileageBalance: existingDoc.data()?.mileageBalance ?? 0,
              updatedAt: fieldValue.serverTimestamp(),
              createdAt:
                existingDoc.data()?.createdAt ?? fieldValue.serverTimestamp(),
            },
            {merge: true},
          );
          return {
            uid: existing.uid,
            email: requestedEmail,
            password,
            displayName,
            cohortId,
            cohortName,
            message: "기존 강사 계정을 갱신했습니다.",
          };
        }
        throw error;
      }
    } else {
      for (let attempt = 0; attempt < 8; attempt++) {
        email = generateRandomEmail();
        password = data.password?.trim() || generateRandomPassword();
        try {
          userRecord = await auth.createUser({
            email,
            password,
            displayName,
            emailVerified: true,
          });
          break;
        } catch (error: unknown) {
          const err = error as {code?: string};
          if (err.code === "auth/email-already-exists") continue;
          throw error;
        }
      }
    }

    if (!userRecord) {
      throw new HttpsError(
        "internal",
        "고유 이메일 생성에 실패했습니다. 다시 시도해주세요.",
      );
    }

    const uid = userRecord.uid;
    const mustChangePassword = data.mustChangePassword !== false;

    try {
      await db.collection("users").doc(uid).set({
        email,
        displayName,
        role: "instructor",
        cohortId,
        cohortName,
        isActive: true,
        mustChangePassword,
        motto: null,
        skills: [],
        socialLinks: {},
        mileageBalance: 0,
        createdAt: fieldValue.serverTimestamp(),
        updatedAt: fieldValue.serverTimestamp(),
        createdBy: request.auth.uid,
      });
    } catch (error) {
      await auth.deleteUser(uid).catch(() => undefined);
      throw error;
    }

    return {
      uid,
      email,
      password,
      displayName,
      cohortId,
      cohortName,
      message: "강사 계정이 생성되었습니다.",
    };
  },
);

/**
 * 관리자 전용 — 강사 이름/담당 기수 수정
 */
export const updateInstructorAccount = onCall(
  callOptions,
  async (request) => {
    if (!request.auth) {
      throw new HttpsError("unauthenticated", "인증이 필요합니다.");
    }
    await assertAdmin(request.auth.uid);

    const data = request.data as {
      uid?: string;
      displayName?: string;
      cohortId?: string;
      cohortName?: string;
    };

    const uid = data.uid?.trim() ?? "";
    const displayName = data.displayName?.trim() ?? "";
    const {cohortId, cohortName} = data;
    if (!uid || !displayName || !cohortId || !cohortName) {
      throw new HttpsError("invalid-argument", "필수 항목이 누락되었습니다.");
    }

    await assertInstructorDoc(uid);

    const cohortDoc = await db.collection("cohorts").doc(cohortId).get();
    if (!cohortDoc.exists) {
      throw new HttpsError("not-found", `기수 '${cohortId}'를 찾을 수 없습니다.`);
    }

    await auth.updateUser(uid, {displayName});
    await db.collection("users").doc(uid).update({
      displayName,
      cohortId,
      cohortName,
      updatedAt: fieldValue.serverTimestamp(),
    });

    return {uid, message: "강사 정보가 수정되었습니다."};
  },
);

/**
 * 관리자 전용 — 강사 비밀번호 재발급
 */
export const resetInstructorPassword = onCall(
  callOptions,
  async (request) => {
    if (!request.auth) {
      throw new HttpsError("unauthenticated", "인증이 필요합니다.");
    }
    await assertAdmin(request.auth.uid);

    const {uid} = request.data as {uid?: string};
    if (!uid) {
      throw new HttpsError("invalid-argument", "uid는 필수입니다.");
    }

    const userDoc = await assertInstructorDoc(uid);
    const password = generateRandomPassword();
    await auth.updateUser(uid, {password});
    await db.collection("users").doc(uid).update({
      mustChangePassword: true,
      updatedAt: fieldValue.serverTimestamp(),
    });

    const data = userDoc.data()!;
    return {
      uid,
      email: data.email as string,
      password,
      displayName: data.displayName as string,
      message: "비밀번호가 재발급되었습니다.",
    };
  },
);

/**
 * 관리자 전용 — 강사 활성/비활성
 */
export const setInstructorActiveStatus = onCall(
  callOptions,
  async (request) => {
    try {
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

      const userDoc = await assertInstructorDoc(uid);
      const currentlyActive = userDoc.data()?.isActive !== false;
      if (currentlyActive === active) {
        throw new HttpsError(
          "failed-precondition",
          active ? "이미 활성 상태인 강사입니다." : "이미 비활성 상태인 강사입니다.",
        );
      }

      await db.collection("users").doc(uid).update({
        isActive: active,
        updatedAt: fieldValue.serverTimestamp(),
      });
      await auth.updateUser(uid, {disabled: !active});

      return {
        uid,
        active,
        message: active ? "강사를 활성화했습니다." : "강사를 비활성화했습니다.",
      };
    } catch (error) {
      if (error instanceof HttpsError) throw error;
      const msg = error instanceof Error ? error.message : String(error);
      logger.error("setInstructorActiveStatus failed", error);
      throw new HttpsError("internal", msg);
    }
  },
);
