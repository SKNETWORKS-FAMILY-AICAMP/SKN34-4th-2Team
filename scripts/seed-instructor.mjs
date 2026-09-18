/**
 * 강사 테스트 계정 생성 — 관리자 로그인 후 Cloud Function 호출
 * 실행: node scripts/seed-instructor.mjs
 */

import { initializeApp } from "firebase/app";
import { getAuth, signInWithEmailAndPassword } from "firebase/auth";
import { getFunctions, httpsCallable } from "firebase/functions";

const firebaseConfig = {
  apiKey: "AIzaSyCd6amu1653Fc071OYeI_Fjfi6hMQvNih8",
  authDomain: "skn34-3rd-2team.firebaseapp.com",
  projectId: "skn34-3rd-2team",
  storageBucket: "skn34-3rd-2team.firebasestorage.app",
  messagingSenderId: "737679563447",
  appId: "1:737679563447:web:9c0a512bc37811f48bcb32",
};

const app = initializeApp(firebaseConfig);
const auth = getAuth(app);
const functions = getFunctions(app, "asia-northeast3");

async function seed() {
  const cred = await signInWithEmailAndPassword(
    auth,
    "admin@playdata.co.kr",
    "Playdata123!",
  );
  await cred.user.getIdToken(true);
  console.log("signed in:", cred.user.email, cred.user.uid);

  const createInstructor = httpsCallable(functions, "createInstructorAccount");
  try {
    const result = await createInstructor({
      displayName: "PLAYDATA 강사",
      email: "instructor@playdata.co.kr",
      password: "Playdata123!",
      cohortId: "cohort_34",
      cohortName: "SK네트웍스 Family AI 캠프 34기",
      mustChangePassword: false,
    });
    console.log("✅ 강사 계정:", result.data);
    console.log("로그인: instructor@playdata.co.kr / Playdata123!");
  } catch (e) {
    console.error("code:", e.code);
    console.error("message:", e.message);
    console.error("details:", e.details);
    console.error("customData:", e.customData);
    throw e;
  }
}

seed().catch((e) => {
  console.error("❌ 실패:", e.code ?? e.message, e.details ?? "");
  process.exit(1);
});
