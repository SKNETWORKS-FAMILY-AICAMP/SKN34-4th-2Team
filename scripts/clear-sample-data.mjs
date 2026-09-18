/**
 * Firebase에 들어간 샘플 데이터 삭제 + 프로필 초기화
 * 실행: node scripts/clear-sample-data.mjs
 */

import { initializeApp } from "firebase/app";
import { getAuth, signInWithEmailAndPassword } from "firebase/auth";
import {
  getFirestore,
  doc,
  setDoc,
  collection,
  getDocs,
  deleteDoc,
  serverTimestamp,
} from "firebase/firestore";

const firebaseConfig = {
  apiKey: "AIzaSyCd6amu1653Fc071OYeI_Fjfi6hMQvNih8",
  authDomain: "skn34-3rd-2team.firebaseapp.com",
  projectId: "skn34-3rd-2team",
  storageBucket: "skn34-3rd-2team.firebasestorage.app",
  messagingSenderId: "737679563447",
  appId: "1:737679563447:web:9c0a512bc37811f48bcb32",
};

const COHORT_ID = "cohort_34";
const ADMIN_EMAIL = "admin@playdata.co.kr";
const ADMIN_PASSWORD = "Playdata123!";
const STUDENT_EMAIL = "student@playdata.co.kr";
const STUDENT_PASSWORD = "Playdata123!";

const SUBCOLLECTIONS = [
  "schedules",
  "notices",
  "posts",
  "weeklyTasks",
  "userProgress",
  "submissions",
  "mileageTransactions",
  "resumes",
  "assignments",
  "materials",
  "todos",
];

const app = initializeApp(firebaseConfig);
const auth = getAuth(app);
const db = getFirestore(app);

async function deleteCollection(path) {
  const snap = await getDocs(collection(db, path));
  if (snap.empty) return 0;
  await Promise.all(snap.docs.map((d) => deleteDoc(d.ref)));
  return snap.size;
}

async function clear() {
  console.log("\n🧹 샘플 데이터 삭제 시작\n");

  await signInWithEmailAndPassword(auth, ADMIN_EMAIL, ADMIN_PASSWORD);

  const cohortBase = `cohorts/${COHORT_ID}`;
  for (const sub of SUBCOLLECTIONS) {
    const count = await deleteCollection(`${cohortBase}/${sub}`);
    if (count > 0) console.log(`  ✓ ${sub}: ${count}건 삭제`);
  }

  // 학생 프로필 초기화
  await signInWithEmailAndPassword(auth, STUDENT_EMAIL, STUDENT_PASSWORD);
  const studentUid = auth.currentUser.uid;
  await setDoc(
    doc(db, "users", studentUid),
    {
      displayName: "학생",
      skills: [],
      socialLinks: {},
      mileageBalance: 0,
      motto: null,
      seatNumber: null,
      updatedAt: serverTimestamp(),
    },
    { merge: true },
  );
  console.log("  ✓ 학생 프로필 초기화");

  await signInWithEmailAndPassword(auth, ADMIN_EMAIL, ADMIN_PASSWORD);
  await setDoc(
    doc(db, "cohorts", COHORT_ID),
    { studentCount: 0 },
    { merge: true },
  );

  console.log("\n✅ 샘플 데이터 삭제 완료!\n");
}

clear().catch((e) => {
  console.error("❌ 실패:", e.code ?? e.message);
  process.exit(1);
});
