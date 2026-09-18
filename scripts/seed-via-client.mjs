/**
 * Firebase Client SDK — 계정 + 기수만 생성 (샘플 데이터 없음)
 * 실행: node scripts/seed-via-client.mjs
 */

import { initializeApp } from "firebase/app";
import {
  getAuth,
  createUserWithEmailAndPassword,
  signInWithEmailAndPassword,
} from "firebase/auth";
import {
  getFirestore,
  doc,
  setDoc,
  serverTimestamp,
} from "firebase/firestore";
import { getFunctions, httpsCallable } from "firebase/functions";

const firebaseConfig = {
  apiKey: "AIzaSyCd6amu1653Fc071OYeI_Fjfi6hMQvNih8",
  authDomain: "skn34-3rd-2team.firebaseapp.com",
  projectId: "skn34-3rd-2team",
  storageBucket: "skn34-3rd-2team.firebasestorage.app",
  messagingSenderId: "737679563447",
  appId: "1:737679563447:web:9c0a512bc37811f48bcb32",
};

const COHORT_ID = "cohort_34";
const COHORT_NAME = "SK네트웍스 Family AI 캠프 34기";

const ACCOUNTS = [
  {
    email: "admin@playdata.co.kr",
    password: "Playdata123!",
    displayName: "PLAYDATA 관리자",
    role: "admin",
  },
  {
    email: "student@playdata.co.kr",
    password: "Playdata123!",
    displayName: "학생",
    role: "student",
  },
  {
    email: "instructor@playdata.co.kr",
    password: "Playdata123!",
    displayName: "PLAYDATA 강사",
    role: "instructor",
  },
];

const app = initializeApp(firebaseConfig);
const auth = getAuth(app);
const db = getFirestore(app);

async function ensureUser({ email, password, displayName, role }) {
  let uid;
  try {
    const cred = await createUserWithEmailAndPassword(auth, email, password);
    uid = cred.user.uid;
    console.log(`  ✓ Auth 생성: ${email}`);
  } catch (e) {
    if (e.code === "auth/email-already-in-use") {
      const cred = await signInWithEmailAndPassword(auth, email, password);
      uid = cred.user.uid;
      console.log(`  ↻ Auth 기존: ${email}`);
    } else {
      throw e;
    }
  }

  await setDoc(
    doc(db, "users", uid),
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
      updatedAt: serverTimestamp(),
      createdAt: serverTimestamp(),
    },
    { merge: true },
  );
  console.log(`  ✓ Firestore users/${uid}`);
  return uid;
}

async function seed() {
  console.log("\n🚀 계정 시드 시작 (샘플 데이터 없음)\n");

  for (const account of ACCOUNTS.filter((a) => a.role !== "instructor")) {
    console.log(`\n👤 ${account.role}:`);
    await ensureUser(account);
  }

  await signInWithEmailAndPassword(auth, ACCOUNTS[0].email, ACCOUNTS[0].password);

  await setDoc(doc(db, "cohorts", COHORT_ID), {
    cohortId: COHORT_ID,
    name: COHORT_NAME,
    isActive: true,
    studentCount: 1,
  });
  console.log("✓ cohorts/cohort_34");

  const COHORT_35_ID = "cohort_35";
  const COHORT_35_NAME = "SK네트웍스 Family AI 캠프 35기";
  await setDoc(doc(db, "cohorts", COHORT_35_ID), {
    cohortId: COHORT_35_ID,
    name: COHORT_35_NAME,
    isActive: true,
    studentCount: 0,
  });
  console.log("✓ cohorts/cohort_35");

  const instructor = ACCOUNTS.find((a) => a.role === "instructor");
  if (instructor) {
    try {
      const functions = getFunctions(app, "asia-northeast3");
      const createInstructor = httpsCallable(functions, "createInstructorAccount");
      await createInstructor({
        displayName: instructor.displayName,
        email: instructor.email,
        password: instructor.password,
        cohortId: COHORT_ID,
        cohortName: COHORT_NAME,
        mustChangePassword: false,
      });
      console.log("✓ instructor via Cloud Function");
    } catch (e) {
      console.log(
        "↻ instructor Cloud Function 호출 실패 — client write로 재시도:",
        e.code ?? e.message,
      );
      await ensureUser(instructor);
    }
  }

  console.log("\n✅ 시드 완료!");
  console.log("관리자: admin@playdata.co.kr / Playdata123!");
  console.log("강사:   instructor@playdata.co.kr / Playdata123!");
  console.log("학생:   student@playdata.co.kr / Playdata123!\n");
}

seed().catch((e) => {
  console.error("❌ 실패:", e.code ?? e.message);
  if (e.code === "auth/operation-not-allowed") {
    console.error("→ Firebase Console > Authentication > 이메일/비밀번호 활성화 필요");
  }
  if (e.code === "permission-denied") {
    console.error("→ bootstrap rules 배포 후 재시도: node scripts/toggle-bootstrap-rules.mjs");
  }
  process.exit(1);
});
