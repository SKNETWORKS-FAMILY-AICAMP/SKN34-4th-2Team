/**
 * 가상 이력서를 특정 계정 아래에 넣는다 (Firebase Client SDK).
 *
 * 이력서 문서는 firestore.rules 에서 `userId == request.auth.uid` 여야 만들 수
 * 있다. 관리자도 다른 사람 이력서를 새로 만들 수는 없다. 그래서 이 스크립트는
 * **넣고 싶은 계정으로 직접 로그인**해서 쓴다. 비밀번호는 인자로 받지 않고
 * 환경변수로만 받는다(셸 히스토리에 남기지 않기 위해서).
 *
 * 데이터는 resume_mocks.json 이고, 키는 job_matching_bot/schemas/resume.py 의
 * mock_resumes() 와 1:1이다. 문서 ID는 `mock-<키>`로 고정해서 여러 번 실행해도
 * 같은 문서를 덮어쓴다(중복 생성 없음).
 *
 * 실행 (PowerShell):
 *   $env:SEED_EMAIL="<로그인 이메일>"; $env:SEED_PASSWORD="<비밀번호>"
 *   node scripts/seed-resume-mocks.mjs            # 5건 생성/갱신
 *   node scripts/seed-resume-mocks.mjs --clear    # mock-* 문서만 삭제
 *   node scripts/seed-resume-mocks.mjs --only backend_entry,frontend_entry
 *   node scripts/seed-resume-mocks.mjs --data demo_review_resume.json   # 첨삭 시연용 이력서
 */

import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { initializeApp } from "firebase/app";
import { getAuth, signInWithEmailAndPassword } from "firebase/auth";
import {
  collection,
  deleteDoc,
  doc,
  getDoc,
  getDocs,
  getFirestore,
  serverTimestamp,
  setDoc,
} from "firebase/firestore";

const firebaseConfig = {
  apiKey: "AIzaSyCd6amu1653Fc071OYeI_Fjfi6hMQvNih8",
  authDomain: "skn34-3rd-2team.firebaseapp.com",
  projectId: "skn34-3rd-2team",
  storageBucket: "skn34-3rd-2team.firebasestorage.app",
  messagingSenderId: "737679563447",
  appId: "1:737679563447:web:9c0a512bc37811f48bcb32",
};

const MOCK_ID_PREFIX = "mock-";
const here = dirname(fileURLToPath(import.meta.url));

function parseArgs(argv) {
  const args = { clear: false, only: null, data: "resume_mocks.json" };
  for (let i = 0; i < argv.length; i += 1) {
    if (argv[i] === "--clear") args.clear = true;
    else if (argv[i] === "--only") args.only = (argv[i + 1] ?? "").split(",").filter(Boolean);
    else if (argv[i] === "--data") args.data = argv[i + 1] ?? args.data;
  }
  return args;
}

function loadPersonas(only, data) {
  const raw = JSON.parse(readFileSync(join(here, data), "utf-8"));
  const entries = Object.entries(raw.personas);
  if (!only) return entries;
  const unknown = only.filter((key) => !raw.personas[key]);
  if (unknown.length > 0) {
    throw new Error(`${data} 에 없는 키: ${unknown.join(", ")}`);
  }
  return entries.filter(([key]) => only.includes(key));
}

/** ResumeContent.computeSections() 와 같은 규칙. 이력서 목록의 진행률이 이 값을 본다. */
function computeSections(content) {
  const anyFilled = (items, field) => (items ?? []).some((item) => (item[field] ?? "").trim() !== "");
  const intro = content.selfIntroduction ?? {};
  return {
    basicInfo: (content.basicInfo?.name ?? "").trim() !== "" && (content.basicInfo?.email ?? "").trim() !== "",
    coreCompetencies: (content.coreCompetencies?.text ?? "").trim() !== "",
    experience: anyFilled(content.experience, "company"),
    education: anyFilled(content.education, "school"),
    techStack: anyFilled(content.techStack, "name"),
    certifications: anyFilled(content.certifications, "name"),
    awards: anyFilled(content.awards, "name"),
    trainingExperience: anyFilled(content.trainingExperience, "course"),
    otherActivities: anyFilled(content.otherActivities, "name"),
    projects: anyFilled(content.projects, "name"),
    selfIntroduction: Object.values(intro).some((section) => (section?.body ?? "").trim() !== ""),
  };
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const email = process.env.SEED_EMAIL;
  const password = process.env.SEED_PASSWORD;
  if (!email || !password) {
    console.error("SEED_EMAIL / SEED_PASSWORD 환경변수가 필요합니다. (이력서를 넣을 계정)");
    process.exit(2);
  }

  const app = initializeApp(firebaseConfig);
  const auth = getAuth(app);
  const db = getFirestore(app);

  const cred = await signInWithEmailAndPassword(auth, email, password);
  const uid = cred.user.uid;
  const userSnap = await getDoc(doc(db, "users", uid));
  if (!userSnap.exists()) {
    throw new Error(`users/${uid} 문서가 없습니다. 앱에 한 번 로그인해 프로필을 만든 뒤 다시 실행하세요.`);
  }
  const user = userSnap.data();
  const cohortId = user.cohortId;
  if (!cohortId) throw new Error(`users/${uid} 에 cohortId 가 없습니다.`);
  console.log(`로그인: ${user.displayName ?? "(이름 없음)"} <${email}> / 기수 ${cohortId}`);

  const resumesRef = collection(db, "cohorts", cohortId, "resumes");

  if (args.clear) {
    const snap = await getDocs(resumesRef);
    let removed = 0;
    for (const item of snap.docs) {
      if (item.id.startsWith(MOCK_ID_PREFIX) && item.data().userId === uid) {
        await deleteDoc(item.ref);
        removed += 1;
        console.log(`  삭제 ${item.id}`);
      }
    }
    console.log(`목업 이력서 ${removed}건 삭제`);
    return;
  }

  const personas = loadPersonas(args.only, args.data);
  for (const [key, persona] of personas) {
    const content = structuredClone(persona.content);
    // 이력서 이름·이메일은 계정 것으로. 가상 인물 데이터가 남의 이름으로 남지 않게 한다.
    content.basicInfo.name = user.displayName ?? "";
    content.basicInfo.email = email;

    const id = `${MOCK_ID_PREFIX}${key}`;
    const ref = doc(resumesRef, id);
    // 읽기 규칙이 resource.data.userId를 보므로 아직 없는 문서를 읽으면 permission-denied가 난다.
    // 그때는 새 문서로 보고 만든다(만들기 규칙은 request.resource의 userId만 본다).
    const existing = await getDoc(ref).catch((e) => {
      if (e.code === "permission-denied") return { exists: () => false };
      throw e;
    });
    await setDoc(ref, {
      userId: uid,
      title: persona.title,
      status: "writing",
      sections: computeSections(content),
      content,
      feedbackCount: existing.exists() ? existing.data().feedbackCount ?? 0 : 0,
      lastSeenFeedbackCount: existing.exists() ? existing.data().lastSeenFeedbackCount ?? 0 : 0,
      revisionCount: existing.exists() ? (existing.data().revisionCount ?? 0) + 1 : 0,
      updatedAt: serverTimestamp(),
      ...(existing.exists() ? {} : { createdAt: serverTimestamp() }),
    });
    console.log(`  ${existing.exists() ? "갱신" : "생성"} ${id} — ${persona.title}`);
  }
  console.log(`\n완료: ${personas.length}건 → cohorts/${cohortId}/resumes/${MOCK_ID_PREFIX}*`);
  console.log("앱에서 이력서 목록을 열면 '[목업]' 제목으로 보입니다.");
}

main()
  .then(() => process.exit(0))
  .catch((e) => {
    console.error("실패:", e.code ?? e.message);
    if (e.code === "auth/invalid-credential" || e.code === "auth/wrong-password") {
      console.error("→ SEED_EMAIL / SEED_PASSWORD 를 확인하세요.");
    }
    if (e.code === "permission-denied") {
      console.error("→ 로그인 계정의 cohortId 와 이력서 기수가 같아야 하고, userId 는 본인 uid 여야 합니다.");
    }
    process.exit(1);
  });
