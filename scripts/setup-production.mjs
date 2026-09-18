/**
 * 프로덕션 Firebase 초기 데이터 시드 (계정 + 기수만)
 * 실행: node scripts/setup-production.mjs
 */

import admin from "firebase-admin";

const PROJECT_ID = "skn34-3rd-2team";
const COHORT_ID = "cohort_34";
const COHORT_NAME = "SK네트웍스 Family AI 캠프 34기";

const ACCOUNTS = {
  admin: {
    email: "admin@playdata.co.kr",
    password: "Playdata123!",
    displayName: "PLAYDATA 관리자",
  },
  student: {
    email: "student@playdata.co.kr",
    password: "Playdata123!",
    displayName: "학생",
  },
};

admin.initializeApp({ projectId: PROJECT_ID });
const auth = admin.auth();
const db = admin.firestore();

async function upsertUser({ email, password, displayName, role }) {
  let userRecord;
  try {
    userRecord = await auth.getUserByEmail(email);
    await auth.updateUser(userRecord.uid, { password, displayName });
    console.log(`  ↻ 기존 Auth 유저 업데이트: ${email}`);
  } catch (e) {
    if (e.code === "auth/user-not-found") {
      userRecord = await auth.createUser({
        email,
        password,
        displayName,
        emailVerified: true,
      });
      console.log(`  ✓ Auth 유저 생성: ${email}`);
    } else {
      throw e;
    }
  }

  await db.collection("users").doc(userRecord.uid).set(
    {
      email,
      displayName,
      role,
      cohortId: COHORT_ID,
      cohortName: COHORT_NAME,
      isActive: true,
      mustChangePassword: false,
      skills: [],
      socialLinks: {},
      mileageBalance: 0,
      motto: null,
      seatNumber: null,
      updatedAt: admin.firestore.FieldValue.serverTimestamp(),
      createdAt: admin.firestore.FieldValue.serverTimestamp(),
    },
    { merge: true },
  );

  return userRecord;
}

async function seed() {
  console.log(`\n🚀 Firebase 프로덕션 시드 시작 (${PROJECT_ID})\n`);

  await db.collection("cohorts").doc(COHORT_ID).set(
    {
      cohortId: COHORT_ID,
      name: COHORT_NAME,
      isActive: true,
      studentCount: 0,
      createdAt: admin.firestore.FieldValue.serverTimestamp(),
    },
    { merge: true },
  );
  console.log("✓ cohorts/cohort_34");

  console.log("\n👤 관리자 계정:");
  await upsertUser({ ...ACCOUNTS.admin, role: "admin" });

  console.log("\n👤 학생 계정:");
  await upsertUser({ ...ACCOUNTS.student, role: "student" });

  console.log("\n✅ 시드 완료!\n");
  console.log("── 로그인 계정 ──");
  console.log(`관리자: ${ACCOUNTS.admin.email} / ${ACCOUNTS.admin.password}`);
  console.log(`학생:   ${ACCOUNTS.student.email} / ${ACCOUNTS.student.password}`);
  console.log("");
}

seed().catch((e) => {
  console.error("\n❌ 시드 실패:", e.message);
  process.exit(1);
});
