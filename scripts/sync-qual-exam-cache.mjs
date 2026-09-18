/**
 * 로컬 PC에서 공공 API → Firestore 캐시 동기화
 * Cloud Functions(asia-northeast3)에서 apis.data.go.kr 연결 타임아웃 시 캐시 fallback용
 *
 * 사용법 (프로젝트 루트):
 *   cd functions && npm install && node ../scripts/sync-qual-exam-cache.mjs
 *
 * 환경변수 (선택):
 *   ADMIN_EMAIL, ADMIN_PASSWORD — 기본값: admin@playdata.co.kr / Playdata123!
 */
import { readFileSync } from "fs";
import { resolve, dirname } from "path";
import { fileURLToPath } from "url";
import { initializeApp } from "firebase/app";
import { getAuth, signInWithEmailAndPassword } from "firebase/auth";
import { getFirestore, doc, setDoc, serverTimestamp } from "firebase/firestore";

const __dirname = dirname(fileURLToPath(import.meta.url));
const year = new Date().getFullYear();

const firebaseConfig = {
  apiKey: "AIzaSyCd6amu1653Fc071OYeI_Fjfi6hMQvNih8",
  authDomain: "skn34-3rd-2team.firebaseapp.com",
  projectId: "skn34-3rd-2team",
  storageBucket: "skn34-3rd-2team.firebasestorage.app",
  messagingSenderId: "737679563447",
  appId: "1:737679563447:web:9c0a512bc37811f48bcb32",
};

function loadEnvKey() {
  const envPath = resolve(__dirname, "../.env");
  const text = readFileSync(envPath, "utf8");
  for (const line of text.split("\n")) {
    const trimmed = line.trim();
    if (trimmed.startsWith("DATA_GO_KR_SERVICE_KEY=")) {
      return trimmed.slice("DATA_GO_KR_SERVICE_KEY=".length).trim();
    }
  }
  throw new Error("DATA_GO_KR_SERVICE_KEY not found in root .env");
}

function parseItems(json) {
  const body = json.body ?? json.response?.body;
  const items = body?.items ?? body?.item;
  if (!items) return [];
  if (Array.isArray(items)) return items;
  if (Array.isArray(items.item)) return items.item;
  if (items.item) return [items.item];
  return [];
}

async function fetchAllPages(year, key) {
  const pageSize = 50;
  let pageNo = 1;
  let allItems = [];
  let totalCount = 0;

  while (true) {
    const url =
      `https://apis.data.go.kr/B490007/qualExamSchd/getQualExamSchdList` +
      `?serviceKey=${encodeURIComponent(key)}` +
      `&numOfRows=${pageSize}&pageNo=${pageNo}&dataFormat=json&implYy=${year}&qualgbCd=T`;

    const res = await fetch(url);
    const json = await res.json();

    if (json.header?.resultCode !== "00") {
      throw new Error(`API error: ${json.header?.resultMsg}`);
    }

    const items = parseItems(json);
    totalCount = json.body?.totalCount ?? items.length;
    allItems = allItems.concat(items);

    if (allItems.length >= totalCount || items.length < pageSize) break;
    pageNo += 1;
  }

  return { items: allItems, totalCount };
}

async function main() {
  const key = loadEnvKey();
  const adminEmail = process.env.ADMIN_EMAIL ?? "admin@playdata.co.kr";
  const adminPassword = process.env.ADMIN_PASSWORD ?? "Playdata123!";

  console.log(`Fetching ${year} schedules from public API...`);
  const { items, totalCount } = await fetchAllPages(year, key);
  console.log(`Fetched ${items.length} items (totalCount=${totalCount})`);

  const app = initializeApp(firebaseConfig);
  const auth = getAuth(app);
  console.log(`Signing in as ${adminEmail}...`);
  await signInWithEmailAndPassword(auth, adminEmail, adminPassword);

  const db = getFirestore(app);
  await setDoc(doc(db, "systemCache", `qualExamSchedules_${year}`), {
    year,
    items,
    totalCount,
    syncedAt: serverTimestamp(),
  });

  console.log(`Cached to systemCache/qualExamSchedules_${year}`);
  process.exit(0);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
