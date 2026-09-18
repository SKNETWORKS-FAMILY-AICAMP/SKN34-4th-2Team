/**
 * cohort_34 학생 N명 일괄 생성 (랜덤 데이터)
 * 관리자 계정으로 createStudentAccount Cloud Function 호출
 *
 * 실행: node scripts/seed-students-bulk.mjs
 * 옵션: node scripts/seed-students-bulk.mjs --count=25
 */

import { writeFileSync } from "fs";
import { dirname, join } from "path";
import { fileURLToPath } from "url";
import { initializeApp } from "firebase/app";
import { getAuth, signInWithEmailAndPassword } from "firebase/auth";
import { getFunctions, httpsCallable } from "firebase/functions";

const __dirname = dirname(fileURLToPath(import.meta.url));

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
const ADMIN_EMAIL = "admin@playdata.co.kr";
const ADMIN_PASSWORD = "Playdata123!";

const countArg = process.argv.find((a) => a.startsWith("--count="));
const STUDENT_COUNT = countArg ? Number(countArg.split("=")[1]) : 25;

const SURNAMES = ["김", "이", "박", "최", "정", "강", "조", "윤", "장", "임"];
const GIVEN_NAMES = [
  "민준", "서연", "지호", "수아", "예준", "하은", "도윤", "지우",
  "시우", "서윤", "주원", "지민", "현우", "수빈", "건우", "유나",
  "우진", "채원", "민서", "준서", "소율", "태양", "은서", "승현", "다은",
];
const MAJORS = [
  "컴퓨터공학", "경영학", "전자공학", "디자인", "수학", "물리학",
  "화학", "기계공학", "심리학", "국어국문학", "영어영문학", "통계학",
];
const STATUSES = ["대학 졸업", "대학 재학", "휴학", "취업 준비", "직장인"];
const STUDY_HOURS = ["10시간 미만", "10~20시간", "20~30시간", "30시간 이상"];
const PROG_LEVELS = ["입문", "초급", "중급", "상급"];
const TOOLS = ["Notion", "Slack", "Jira", "Figma", "GitHub", "Discord"];
const AI_EXP = ["없음", "ChatGPT 사용 경험", "프롬프트 엔지니어링 경험", "API 연동 경험"];
const ROLES = ["백엔드 개발자", "프론트엔드 개발자", "데이터 분석가", "AI 엔지니어", "풀스택 개발자"];
const GOALS = ["스타트업 취업", "대기업 취업", "프리랜서", "창업", "대학원 진학"];
const TEAM_ROLES = ["리더형", "조율형", "실행형", "아이디어형", "분석형"];
const STYLES = ["강의 수강", "문서 학습", "프로젝트 중심", "멘토링 중심", "스터디 그룹"];

const app = initializeApp(firebaseConfig);
const auth = getAuth(app);
const functions = getFunctions(app, "asia-northeast3");

function pick(arr) {
  return arr[Math.floor(Math.random() * arr.length)];
}

function generateDisplayName(usedNames) {
  let name;
  do {
    name = pick(SURNAMES) + pick(GIVEN_NAMES);
  } while (usedNames.has(name));
  usedNames.add(name);
  return name;
}

function buildIntake() {
  return {
    educationMajor: pick(MAJORS),
    currentStatus: pick(STATUSES),
    weeklyStudyHours: pick(STUDY_HOURS),
    programmingLevel: pick(PROG_LEVELS),
    collaborationTools: pick(TOOLS),
    aiLlmExperience: pick(AI_EXP),
    motivation: "AI 분야로 커리어 전환을 희망합니다.",
    desiredRole: pick(ROLES),
    postCompletionGoal: pick(GOALS),
    awards: Math.random() > 0.7 ? "교내 해커톤 우수상" : "",
    projectLinks: Math.random() > 0.6 ? "https://github.com/example" : "",
    teamRole: pick(TEAM_ROLES),
    selfLearningStyle: pick(STYLES),
    slumpOvercomeExperience: "목표를 작게 나눠 꾸준히 달성했습니다.",
  };
}

async function seed() {
  console.log(`\n🚀 학생 ${STUDENT_COUNT}명 일괄 생성 시작\n`);

  console.log(`🔐 관리자 로그인: ${ADMIN_EMAIL}`);
  await signInWithEmailAndPassword(auth, ADMIN_EMAIL, ADMIN_PASSWORD);

  const createStudent = httpsCallable(functions, "createStudentAccount", {
    timeout: 60000,
  });

  const usedNames = new Set();
  const results = [];

  for (let i = 1; i <= STUDENT_COUNT; i++) {
    const displayName = generateDisplayName(usedNames);
    const personalEmail = `student${String(i).padStart(2, "0")}@example.com`;

    process.stdout.write(`  [${i}/${STUDENT_COUNT}] ${displayName} ... `);

    try {
      const response = await createStudent({
        displayName,
        cohortId: COHORT_ID,
        cohortName: COHORT_NAME,
        personalEmail,
        seatNumber: i,
        intake: buildIntake(),
      });

      const data = response.data;
      results.push({
        seatNumber: i,
        displayName: data.displayName,
        email: data.email,
        password: data.password,
        personalEmail,
        uid: data.uid,
      });
      console.log(`✓ ${data.email}`);
    } catch (error) {
      const msg = error.message ?? String(error);
      console.log(`✗ ${msg}`);
    }

    // API rate limit 방지
    await new Promise((r) => setTimeout(r, 300));
  }

  const csvPath = join(__dirname, `seed-students-${COHORT_ID}-${Date.now()}.csv`);
  const csvHeader = "seatNumber,displayName,email,password,personalEmail,uid\n";
  const csvBody = results
    .map(
      (s) =>
        `${s.seatNumber},${s.displayName},${s.email},${s.password},${s.personalEmail},${s.uid}`,
    )
    .join("\n");
  writeFileSync(csvPath, csvHeader + csvBody, "utf8");

  console.log(`\n✅ 완료: ${results.length}명 생성`);
  console.log(`📄 계정 목록: ${csvPath}\n`);
  console.log("── 생성된 계정 (이메일 / 비밀번호) ──");
  for (const s of results) {
    console.log(
      `  ${String(s.seatNumber).padStart(2, " ")}. ${s.displayName.padEnd(5)} ${s.email} / ${s.password}`,
    );
  }
  console.log("");
}

seed().catch((e) => {
  console.error("\n❌ 시드 실패:", e.message ?? e);
  if (e.code === "functions/not-found" || e.message?.includes("NOT_FOUND")) {
    console.error("→ createStudentAccount Function이 배포되지 않았습니다.");
    console.error("  firebase deploy --only functions:createStudentAccount");
  }
  if (e.code === "auth/user-not-found" || e.code === "auth/wrong-password") {
    console.error("→ 관리자 계정이 없습니다. 먼저 .\\scripts\\run-seed.ps1 실행");
  }
  process.exit(1);
});
