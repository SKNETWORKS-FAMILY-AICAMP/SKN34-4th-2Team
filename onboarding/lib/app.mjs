// 데모 모드 웹 빌드를 띄우고 Playwright로 조작하는 공통 도구.
// Flutter 웹은 캔버스에 그리므로, 접근성(semantics) 트리를 켜서 DOM으로 버튼·입력칸을 찾는다.
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
export const repoRoot = path.resolve(here, '../..');
export const webRoot = path.join(repoRoot, 'build', 'onboarding_web');
// 캡처 원본·녹화 원본 같은 중간 산출물 (git 제외)
export const outRoot = path.join(repoRoot, 'build', 'onboarding');
// 팀에 공유하는 결과물: PDF와 mp4 (git 포함)
export const deliverRoot = path.join(repoRoot, 'onboarding', 'output');

export const accounts = {
  student: { email: 'student@playdata.co.kr', password: 'Playdata123!' },
  instructor: { email: 'instructor@playdata.co.kr', password: 'Playdata123!' },
  admin: { email: 'admin@playdata.co.kr', password: 'Playdata123!' },
};

const mime = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript',
  '.mjs': 'text/javascript',
  '.json': 'application/json',
  '.wasm': 'application/wasm',
  '.css': 'text/css',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.svg': 'image/svg+xml',
  '.ttf': 'font/ttf',
  '.otf': 'font/otf',
  '.woff2': 'font/woff2',
  '.ico': 'image/x-icon',
};

/// 빌드 폴더를 정적으로 서빙한다. 반환값은 { url, close }.
export function serveBuild(port = 5178) {
  if (!fs.existsSync(path.join(webRoot, 'index.html'))) {
    throw new Error(
      `웹 빌드가 없습니다: ${webRoot}\n` +
        'flutter build web --dart-define=DEMO_MODE=true --output build/onboarding_web 를 먼저 실행하세요.',
    );
  }
  const server = http.createServer((req, res) => {
    const urlPath = decodeURIComponent(req.url.split('?')[0]);
    let file = path.join(webRoot, urlPath);
    if (!file.startsWith(webRoot)) {
      res.writeHead(403).end();
      return;
    }
    if (!fs.existsSync(file) || fs.statSync(file).isDirectory()) {
      file = path.join(webRoot, 'index.html');
    }
    res.writeHead(200, {
      'Content-Type': mime[path.extname(file)] ?? 'application/octet-stream',
    });
    fs.createReadStream(file).pipe(res);
  });
  return new Promise((resolve) => {
    server.listen(port, '127.0.0.1', () =>
      resolve({ url: `http://127.0.0.1:${port}`, close: () => server.close() }),
    );
  });
}

export const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

/// Flutter가 첫 프레임을 그리고 semantics 트리를 켤 때까지 기다린다.
export async function waitForApp(page) {
  await page.waitForSelector('flt-semantics-placeholder, flt-semantics-host', {
    state: 'attached',
    timeout: 60_000,
  });
  await page.evaluate(() => {
    const el = document.querySelector('flt-semantics-placeholder');
    if (el) el.click();
  });
  await page.waitForSelector('flt-semantics', { state: 'attached', timeout: 30_000 });
  await sleep(800);
}

/// hash 라우팅이라 location.hash만 바꾸면 새로고침 없이 이동한다(데모 세션 유지).
export async function go(page, route, settleMs = 1500) {
  await page.evaluate((r) => {
    window.location.hash = r;
  }, route);
  await sleep(settleMs);
}

export async function login(page, role) {
  const { email, password } = accounts[role];
  const email$ = page.getByRole('textbox').nth(0);
  const pass$ = page.getByRole('textbox').nth(1);
  await email$.click();
  await page.keyboard.type(email, { delay: 25 });
  await pass$.click();
  await page.keyboard.type(password, { delay: 25 });
  await page.getByRole('button', { name: '로그인', exact: true }).click();
  await sleep(3000);
}

/// 인앱 온보딩 투어가 떠 있으면 닫는다. PDF 캡처에는 투어 말풍선이 없어야 한다.
export async function dismissTour(page) {
  for (const name of ['건너뛰기', '닫기', '다시 보지 않기']) {
    const btn = page.getByRole('button', { name, exact: true });
    if (await btn.count()) {
      await btn.first().click().catch(() => {});
      await sleep(600);
      return true;
    }
  }
  return false;
}
