/**
 * Firebase Emulator 테스트 계정 시드 (샘플 데이터 없음)
 * 실행: node scripts/seed-test-users.mjs
 */

import admin from "firebase-admin";

process.env.FIREBASE_AUTH_EMULATOR_HOST = "127.0.0.1:9099";
process.env.FIRESTORE_EMULATOR_HOST = "127.0.0.1:8080";
process.env.GCLOUD_PROJECT = "demo-playdata-lms";

admin.initializeApp({ projectId: "demo-playdata-lms" });

const auth = admin.auth();
const db = admin.firestore();

const COHORT_ID = "cohort_34";
const COHORT_NAME = "SK네트웍스 Family AI 캠프 34기";

const ACCOUNTS = {
  admin: {
    email: "admin@playdata.co.kr",
    password: "Playdata123!",
    displayName: "PLAYDATA 관리자",
    role: "admin",
  },
  student: {
    email: "student@playdata.co.kr",
    password: "Playdata123!",
    displayName: "학생",
    role: "student",
  },
  instructor: {
    email: "instructor@playdata.co.kr",
    password: "Playdata123!",
    displayName: "PLAYDATA 강사",
    role: "instructor",
  },
};

async function createAuthUser({ email, password, displayName }) {
  try {
    return await auth.createUser({ email, password, displayName, emailVerified: true });
  } catch (e) {
    if (e.code === "auth/email-already-exists") {
      const existing = await auth.getUserByEmail(email);
      await auth.updateUser(existing.uid, { password, displayName });
      return existing;
    }
    throw e;
  }
}

async function seed() {
  console.log("🌱 시드 시작...\n");

  await db.collection("cohorts").doc(COHORT_ID).set({
    cohortId: COHORT_ID,
    name: COHORT_NAME,
    isActive: true,
    studentCount: 0,
    createdAt: admin.firestore.FieldValue.serverTimestamp(),
  });

  const adminUser = await createAuthUser(ACCOUNTS.admin);
  await db.collection("users").doc(adminUser.uid).set({
    email: ACCOUNTS.admin.email,
    displayName: ACCOUNTS.admin.displayName,
    role: "admin",
    cohortId: COHORT_ID,
    cohortName: COHORT_NAME,
    isActive: true,
    mustChangePassword: false,
    skills: [],
    socialLinks: {},
    mileageBalance: 0,
    createdAt: admin.firestore.FieldValue.serverTimestamp(),
    updatedAt: admin.firestore.FieldValue.serverTimestamp(),
  });
  console.log("✅ 관리자:", ACCOUNTS.admin.email, "/", ACCOUNTS.admin.password);

  const studentUser = await createAuthUser(ACCOUNTS.student);
  await db.collection("users").doc(studentUser.uid).set({
    email: ACCOUNTS.student.email,
    displayName: ACCOUNTS.student.displayName,
    role: "student",
    cohortId: COHORT_ID,
    cohortName: COHORT_NAME,
    isActive: true,
    mustChangePassword: false,
    skills: [],
    socialLinks: {},
    mileageBalance: 0,
    createdAt: admin.firestore.FieldValue.serverTimestamp(),
    updatedAt: admin.firestore.FieldValue.serverTimestamp(),
  });
  console.log("✅ 학생:", ACCOUNTS.student.email, "/", ACCOUNTS.student.password);

  const instructorUser = await createAuthUser(ACCOUNTS.instructor);
  await db.collection("users").doc(instructorUser.uid).set({
    email: ACCOUNTS.instructor.email,
    displayName: ACCOUNTS.instructor.displayName,
    role: "instructor",
    cohortId: COHORT_ID,
    cohortName: COHORT_NAME,
    isActive: true,
    mustChangePassword: false,
    skills: [],
    socialLinks: {},
    mileageBalance: 0,
    createdAt: admin.firestore.FieldValue.serverTimestamp(),
    updatedAt: admin.firestore.FieldValue.serverTimestamp(),
  });
  console.log("✅ 강사:", ACCOUNTS.instructor.email, "/", ACCOUNTS.instructor.password);

  console.log("\n🎉 시드 완료! Emulator UI: http://127.0.0.1:4000");
}

seed().catch((e) => {
  console.error("❌ 시드 실패:", e.message);
  process.exit(1);
});
