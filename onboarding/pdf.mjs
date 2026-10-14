// capture.mjs가 찍은 화면으로 A4 사용자 안내서 PDF를 만든다.
// 구성: 표지 → 목차 → PART 1 시작하기 → 역할별(기능 챕터마다 단계별 캡처) → 자주 묻는 질문
// 결과: onboarding/output/PLAYDATA_LMS_사용자_가이드.pdf (중간 .html은 build/onboarding)
import fs from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
import { chromium } from 'playwright';
import { outRoot, deliverRoot, repoRoot } from './lib/app.mjs';
import { roles } from './scenes.mjs';

const shots = path.join(outRoot, 'shots');
const baseName = 'PLAYDATA_LMS_사용자_가이드';
const today = new Date();
const dateLabel = `${today.getFullYear()}.${String(today.getMonth() + 1).padStart(2, '0')}.${String(today.getDate()).padStart(2, '0')}`;

const esc = (s) =>
  String(s).replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;');

function img(rel) {
  const abs = path.join(shots, rel);
  if (!fs.existsSync(abs)) throw new Error(`캡처가 없습니다: ${abs} (node capture.mjs 먼저)`);
  return pathToFileURL(abs).href;
}

// 앱과 같은 글꼴(Paperlogy)을 쓴다.
const fontDir = path.join(repoRoot, 'assets', 'fonts', 'Paperlogy');
const fontFaces = [
  [400, '4Regular'],
  [500, '5Medium'],
  [600, '6SemiBold'],
  [700, '7Bold'],
  [800, '8ExtraBold'],
]
  .map(([w, f]) => `@font-face { font-family: 'Paperlogy'; font-weight: ${w}; src: url('${pathToFileURL(path.join(fontDir, `Paperlogy-${f}.ttf`)).href}'); }`)
  .join('\n');

// 앱 강조색(#0055FF)과 사이드바 네이비(#0B2A6F)를 기준으로 역할 색을 둔다.
const brand = '#0055FF';
const navy = '#0B2A6F';
const roleColor = { student: '#0055FF', instructor: '#0E9F7A', admin: '#6D4AFF' };

const partNo = (i) => i + 2;
const chapterNo = (ri, fi) => `${partNo(ri)}-${fi + 1}`;

function stepBlock(role, feature, step, si) {
  const points = step.points?.length
    ? `<ol class="points">${step.points.map((p, i) => `<li><span class="badge">${i + 1}</span><span>${esc(p)}</span></li>`).join('')}</ol>`
    : '';
  return `
  <section class="step">
    <div class="step-head">
      <span class="step-no" style="color:${roleColor[role]}">STEP ${si + 1}</span>
      <h3>${esc(step.title)}</h3>
    </div>
    <p class="step-desc">${esc(step.desc)}</p>
    <div class="step-body">
      <figure><img src="${img(`${role}/${feature.id}-${si + 1}.png`)}" alt="${esc(step.title)} 화면"></figure>
      ${points}
    </div>
  </section>`;
}

function featureChapter(r, ri, f, fi) {
  const color = roleColor[r.role];
  const tips = f.tips?.length
    ? `<aside class="tips"><strong>알아두세요</strong><ul>${f.tips.map((t) => `<li>${esc(t)}</li>`).join('')}</ul></aside>`
    : '';
  return `
  <article class="chapter" style="--accent:${color}">
    <div class="chapter-start">
    <header class="chapter-head">
      <p class="chapter-kicker"><span>${esc(r.label)}</span> ${chapterNo(ri, fi)}</p>
      <h2>${esc(f.title)}</h2>
      <p class="menu-path"><b>메뉴</b>${esc(f.menu)}</p>
      <p class="summary">${esc(f.summary)}</p>
      <div class="can">
        <strong>이 화면에서 할 수 있는 일</strong>
        <ul>${f.can.map((c) => `<li>${esc(c)}</li>`).join('')}</ul>
      </div>
    </header>
    ${stepBlock(r.role, f, f.steps[0], 0)}
    </div>
    ${f.steps.slice(1).map((s, si) => stepBlock(r.role, f, s, si + 1)).join('')}
    ${tips}
  </article>`;
}

const toc = roles
  .map(
    (r, ri) => `
    <li class="toc-part" style="--accent:${roleColor[r.role]}">
      <div class="toc-title"><span>PART ${partNo(ri)}</span><strong>${esc(r.label)}</strong></div>
      <ol class="toc-features">
        ${r.features.map((f, fi) => `<li><span>${chapterNo(ri, fi)}</span>${esc(f.title)}</li>`).join('')}
      </ol>
    </li>`,
  )
  .join('');

const roleSections = roles
  .map(
    (r, ri) => `
  <section class="divider" style="--accent:${roleColor[r.role]}">
    <p class="part">PART ${partNo(ri)}</p>
    <h2>${esc(r.label)} 화면 안내</h2>
    <p class="intro">${esc(r.intro)}</p>
    <div class="menu-grid">
      ${r.features.map((f, fi) => `<div><span>${chapterNo(ri, fi)}</span>${esc(f.title)}</div>`).join('')}
    </div>
  </section>
  ${r.features.map((f, fi) => featureChapter(r, ri, f, fi)).join('')}`,
  )
  .join('');

// capture.mjs가 테마별 대시보드를 찍었으면 PART 1 뒤에 비교 페이지를 넣는다.
const themes = [
  { id: 'light', label: '라이트', desc: '전체를 밝게' },
  { id: 'railDark', label: '사이드바 다크', desc: '본문은 밝게, 사이드바만 어둡게' },
  { id: 'dark', label: '전체 다크', desc: '전체를 어둡게' },
];
const hasThemeShots = themes.every((t) => fs.existsSync(path.join(shots, 'themes', `${t.id}.png`)));
const themeSection = hasThemeShots
  ? `
<section class="page">
  <h2>화면 테마 고르기</h2>
  <p class="lead">「설정 → 화면 테마」에서 세 가지 중 하나를 고릅니다. 고르는 즉시 전체 화면에 적용되고, 이 안내서의 나머지 화면은 기본값인 <b>라이트</b>로 찍었습니다.</p>
  <div class="themes">
    ${themes
      .map(
        (t) => `
    <figure>
      <img src="${img(`themes/${t.id}.png`)}" alt="${esc(t.label)} 테마">
      <figcaption><strong>${esc(t.label)}</strong> — ${esc(t.desc)}</figcaption>
    </figure>`,
      )
      .join('')}
  </div>
</section>`
  : '';

const html = `<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<title>PLAYDATA LMS 사용자 가이드</title>
<style>
  ${fontFaces}
  @page { size: A4; margin: 13mm 14mm 15mm 14mm; }
  * { box-sizing: border-box; }
  html { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
  body {
    margin: 0;
    font-family: 'Paperlogy', 'Malgun Gothic', sans-serif;
    color: #111827;
    font-size: 9.6pt;
    line-height: 1.62;
    word-break: keep-all;
  }
  h1, h2, h3, p { margin: 0; }
  h1, h2, h3 { line-height: 1.3; }
  b, strong { font-weight: 700; }

  /* 표지 */
  .cover {
    height: 266mm; padding: 18mm 16mm 12mm; border-radius: 4mm;
    display: flex; flex-direction: column; justify-content: space-between;
    page-break-after: always; color: #fff;
    background: radial-gradient(140mm 110mm at 90% 8%, rgba(0,85,255,.55), transparent 70%), linear-gradient(160deg, ${navy} 0%, #081a45 60%, #05102c 100%);
  }
  .brand { font-weight: 800; font-size: 14pt; letter-spacing: .08em; color: #9ec0ff; }
  .cover h1 { font-size: 34pt; font-weight: 800; letter-spacing: -.02em; margin-top: 30mm; }
  .cover .sub { font-size: 13pt; color: #c9d6f2; margin-top: 4mm; }
  .cover .roles { display: flex; gap: 3mm; margin-top: 9mm; }
  .cover .roles span { border-radius: 99px; padding: 1.4mm 5mm; font-weight: 700; font-size: 10pt; color: #fff; }
  .cover img { width: 100%; border-radius: 3mm; border: 1px solid rgba(255,255,255,.18); box-shadow: 0 4mm 12mm rgba(0,0,0,.35); }
  .cover .meta { color: #8fa3c8; font-size: 9pt; display: flex; justify-content: space-between; }

  /* 공통 페이지 */
  .page { page-break-after: always; }
  .page h2 { font-size: 20pt; font-weight: 800; margin-bottom: 5mm; }
  .lead { color: #374151; margin-bottom: 4mm; }

  /* 목차 */
  .toc { list-style: none; padding: 0; margin: 0 0 8mm; }
  .toc > li { padding: 3.2mm 0; border-bottom: 1px solid #e5e7eb; }
  .toc .toc-title { display: flex; align-items: baseline; gap: 4mm; }
  .toc .toc-title span { font-weight: 800; font-size: 8.5pt; letter-spacing: .06em; color: var(--accent, ${brand}); min-width: 16mm; }
  .toc .toc-title strong { font-size: 12pt; }
  .toc-plain { color: #4b5563; font-size: 9pt; margin: 1mm 0 0 20mm; }
  .toc-features { list-style: none; padding: 0; margin: 1.5mm 0 0 20mm; display: grid; grid-template-columns: repeat(3, 1fr); gap: .6mm 4mm; font-size: 9pt; color: #374151; }
  .toc-features span { display: inline-block; min-width: 9mm; color: var(--accent); font-weight: 700; }

  .steps { counter-reset: step; list-style: none; padding: 0; margin: 0; }
  .steps > li { counter-increment: step; position: relative; padding: 0 0 4.2mm 11mm; }
  .steps > li::before {
    content: counter(step); position: absolute; left: 0; top: .4mm;
    width: 7mm; height: 7mm; border-radius: 50%; background: ${brand}; color: #fff;
    font-weight: 700; font-size: 9pt; display: flex; align-items: center; justify-content: center;
  }
  .steps h4 { margin: 0 0 .6mm; font-size: 11pt; }
  .steps p { color: #374151; }

  .note { background: #eef4ff; border-left: 1.2mm solid ${brand}; border-radius: 1.5mm; padding: 3mm 4mm; margin: 4mm 0; color: #1f2937; }
  .two { display: grid; grid-template-columns: 1fr 1fr; gap: 5mm; margin-top: 2mm; }
  .two figure { margin: 0; }
  .two img { width: 100%; border: 1px solid #e5e7eb; border-radius: 2mm; }
  .two figcaption { font-size: 8.5pt; color: #6b7280; margin-top: 1mm; }

  .themes { display: flex; flex-direction: column; gap: 5mm; }
  .themes figure { margin: 0; break-inside: avoid; }
  .themes img { width: 112mm; display: block; border: 1px solid #e5e7eb; border-radius: 2mm; }
  .themes figcaption { font-size: 9pt; color: #4b5563; margin-top: 1mm; }

  /* 역할 구분 페이지 */
  .divider { page-break-before: always; page-break-after: always; padding-top: 50mm; }
  .divider .part { color: var(--accent); font-weight: 800; letter-spacing: .12em; }
  .divider h2 { font-size: 30pt; font-weight: 800; margin: 2mm 0 5mm; }
  .divider .intro { font-size: 12pt; color: #4b5563; max-width: 150mm; }
  .menu-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 2.5mm; margin-top: 14mm; }
  .menu-grid div { border: 1px solid #e5e7eb; border-left: 1mm solid var(--accent); border-radius: 2mm; padding: 2.5mm 3mm; font-weight: 600; }
  .menu-grid span { display: inline-block; min-width: 9mm; color: var(--accent); font-weight: 800; }

  /* 기능 챕터 */
  /* 챕터는 새 쪽을 강제하지 않고 이어 붙인다(쪽마다 아래가 비지 않게). 머리글은 첫 단계와 떨어지지 않게 한다. */
  .chapter + .chapter { margin-top: 9mm; padding-top: 7mm; border-top: 1.2mm solid var(--accent); }
  .chapter-start { break-inside: avoid; page-break-inside: avoid; }
  .chapter-head { border-bottom: 1px solid #e5e7eb; padding-bottom: 5mm; margin-bottom: 5mm; }
  .divider + .chapter { margin-top: 0; }
  .chapter-kicker { font-size: 9pt; font-weight: 800; letter-spacing: .06em; color: var(--accent); }
  .chapter-kicker span { background: var(--accent); color: #fff; border-radius: 99px; padding: .3mm 2.6mm; margin-right: 1.5mm; letter-spacing: 0; }
  .chapter-head h2 { font-size: 21pt; font-weight: 800; margin: 1.6mm 0 2mm; }
  .menu-path { font-size: 9pt; color: #374151; display: flex; gap: 2mm; align-items: baseline; }
  .menu-path b { font-size: 7.5pt; color: #fff; background: #4b5563; border-radius: 1mm; padding: 0 1.6mm; }
  .summary { margin-top: 2.5mm; font-size: 10.5pt; color: #1f2937; }
  .can { margin-top: 3.5mm; background: #f5f8ff; border: 1px solid #e0e9ff; border-radius: 2mm; padding: 3mm 4mm; }
  .can strong { font-size: 8.5pt; color: var(--accent); letter-spacing: .02em; }
  .can ul { list-style: none; padding: 0; margin: 1.2mm 0 0; display: grid; grid-template-columns: 1fr 1fr; gap: .6mm 5mm; }
  .can li { position: relative; padding-left: 4.5mm; }
  .can li::before { content: ''; position: absolute; left: .4mm; top: 1.9mm; width: 2.2mm; height: 1.2mm; border-left: .5mm solid var(--accent); border-bottom: .5mm solid var(--accent); transform: rotate(-45deg); }

  .step { break-inside: avoid; page-break-inside: avoid; margin-bottom: 6mm; }
  .step + .step, .chapter-start + .step { border-top: 1px dashed #e5e7eb; padding-top: 5mm; }
  .step-head { display: flex; align-items: baseline; gap: 3mm; }
  .step-no { font-size: 8.5pt; font-weight: 800; letter-spacing: .06em; }
  .step h3 { font-size: 13pt; font-weight: 700; }
  .step-desc { margin: 1mm 0 2mm; color: #374151; }
  .step figure { margin: 0; }
  /* 캡처(118mm, 높이 약 74mm)를 왼쪽에, 번호 설명을 오른쪽에 두어 한 쪽에 두세 단계가 들어가게 한다 */
  .step-body { display: grid; grid-template-columns: 118mm 1fr; gap: 5mm; align-items: start; }
  .step img { width: 118mm; display: block; border: 1px solid #e5e7eb; border-radius: 2mm; box-shadow: 0 1mm 3mm rgba(15,23,42,.08); }
  .points { list-style: none; padding: 0; margin: 0; display: grid; gap: 1.6mm; font-size: 9pt; line-height: 1.5; }
  .points li { display: grid; grid-template-columns: 6mm 1fr; align-items: start; }
  .badge { width: 4.6mm; height: 4.6mm; border-radius: 50%; background: #f97316; color: #fff; font-size: 7.5pt; font-weight: 800; display: flex; align-items: center; justify-content: center; margin-top: .5mm; }

  .tips { break-inside: avoid; background: #fff8eb; border: 1px solid #fde7bf; border-radius: 2mm; padding: 3mm 4mm; margin-top: 2mm; }
  .tips strong { color: #b45309; font-size: 9pt; }
  .tips ul { margin: 1mm 0 0; padding-left: 4.5mm; color: #374151; }

  dl.faq dt { font-weight: 700; margin-top: 4mm; }
  dl.faq dd { margin: 1mm 0 0; color: #374151; }
</style>
</head>
<body>

<section class="cover">
  <div class="brand">PLAYDATA</div>
  <div>
    <h1>LMS 사용자 가이드</h1>
    <p class="sub">처음 로그인부터 역할별 기능까지, 화면을 따라 하나씩</p>
    <div class="roles">
      ${roles.map((r) => `<span style="background:${roleColor[r.role]}">${esc(r.label)}</span>`).join('')}
    </div>
  </div>
  <img src="${img(hasThemeShots ? 'themes/light.png' : 'student/_tour.png')}" alt="학생 대시보드">
  <div class="meta"><span>SK네트웍스 Family AI 캠프</span><span>${dateLabel} 기준</span></div>
</section>

<section class="page">
  <h2>목차</h2>
  <ol class="toc">
    <li><div class="toc-title"><span>PART 1</span><strong>시작하기</strong></div><p class="toc-plain">로그인 · 비밀번호 변경 · 이용 안내 투어 · 화면 구성 · 화면 테마</p></li>
    ${toc}
    <li><div class="toc-title"><span>부록</span><strong>자주 묻는 질문</strong></div></li>
  </ol>
  <div class="note">
    <b>읽는 법</b> — 기능마다 메뉴 위치와 할 수 있는 일을 먼저 적고, 화면을 단계(STEP)별로 보여 줍니다.
    화면 위 <b style="color:#f97316">주황색 번호</b>는 아래 같은 번호의 설명과 짝입니다.
  </div>
  <div class="note">
    이 안내서의 화면은 <b>데모 계정</b>으로 찍었습니다. 이름·이메일·점수·공고는 예시이며 실제 정보가 아닙니다.
    기수 운영 상황에 따라 메뉴 이름이나 표시 내용이 조금 다를 수 있습니다.
  </div>
</section>

<section class="page">
  <h2>PART 1 · 시작하기</h2>
  <ol class="steps">
    <li>
      <h4>접속하기</h4>
      <p>매니저가 안내한 주소로 접속합니다. PC에서는 Chrome 브라우저를 권장합니다.</p>
    </li>
    <li>
      <h4>로그인</h4>
      <p>발급받은 이메일과 비밀번호를 입력하고 「로그인」을 누릅니다. 계정은 관리자가 발급·재설정하므로, 계정이 없거나 비밀번호를 잊었다면 매니저에게 요청하세요.</p>
    </li>
    <li>
      <h4>첫 로그인 시 비밀번호 변경</h4>
      <p>처음 로그인하면 「비밀번호 변경」 화면이 나옵니다. 새 비밀번호를 정해야 다음 화면으로 넘어갑니다.</p>
    </li>
    <li>
      <h4>이용 안내 투어</h4>
      <p>로그인 직후 메뉴를 하나씩 짚어 주는 안내 말풍선이 뜹니다. 「다음」으로 넘기고, 필요 없으면 「다시 보지 않기」를 누르세요. 마이페이지의 「이용 안내 다시보기」로 언제든 다시 볼 수 있습니다.</p>
    </li>
    <li>
      <h4>화면 구성</h4>
      <p>왼쪽 사이드바에서 메뉴를 고르고, 오른쪽 위에서 내 계정과 기수를 확인합니다. 로그인한 역할(학생·강사·관리자)에 따라 보이는 메뉴가 다릅니다.</p>
    </li>
    <li>
      <h4>화면 설정</h4>
      <p>사이드바 「설정」에서 화면 테마(라이트 · 사이드바 다크 · 전체 다크), 사이드바 색, 화면 밀도(자동 · 보통 · 좁게)를 고릅니다. 설정은 지금 쓰는 기기에만 저장됩니다.</p>
    </li>
  </ol>
  <div class="two">
    <figure><img src="${img('login.png')}" alt="로그인 화면"><figcaption>로그인 화면</figcaption></figure>
    <figure><img src="${img('student/_tour.png')}" alt="이용 안내 투어"><figcaption>로그인 직후 뜨는 이용 안내 투어</figcaption></figure>
  </div>
</section>
${themeSection}

${roleSections}

<section class="page" style="page-break-before: always">
  <h2>부록 · 자주 묻는 질문</h2>
  <dl class="faq">
    <dt>로그인이 안 됩니다.</dt>
    <dd>이메일 앞뒤 공백과 대소문자를 확인하세요. 계속 안 되면 계정 발급 여부와 비밀번호 재설정을 매니저에게 요청합니다.</dd>
    <dt>이용 안내 투어를 닫았는데 다시 보고 싶어요.</dt>
    <dd>마이페이지 → 「이용 안내 다시보기」를 누르면 처음부터 다시 볼 수 있습니다.</dd>
    <dt>출결 폼은 언제 내나요?</dt>
    <dd>지각·조퇴·외출·공가 같은 예외 출결이 있을 때 오른쪽 위 「출결 폼」으로 당일에 제출합니다.</dd>
    <dt>이력서 편집 화면에 AI 코치가 안 보여요.</dt>
    <dd>피드백을 요청한 이력서는 오른쪽에 피드백 창이 대신 보입니다. 기본 이력서(작성 중)를 열면 AI 코치가 나옵니다. 창이 좁으면 위쪽 로봇 아이콘으로 엽니다.</dd>
    <dt>기록실에 올린 기록은 언제 마일리지로 들어오나요?</dt>
    <dd>매니저가 승인하면 기수 규칙에 따라 자동으로 적립됩니다. 승인 상태는 기록실 목록에서 확인합니다.</dd>
    <dt>마일리지 상품을 구매 요청했는데 포인트가 그대로예요.</dt>
    <dd>구매 요청은 매니저가 승인할 때 차감됩니다. 반려되거나 취소하면 포인트는 변하지 않습니다.</dd>
    <dt>다크 모드로 바꿨는데 다른 PC에서는 밝게 나와요.</dt>
    <dd>화면 설정은 기기(브라우저)마다 따로 저장됩니다. 그 PC에서도 「설정 → 화면 테마」를 한 번 골라 주세요.</dd>
    <dt>글자와 여백이 너무 크거나 작아요.</dt>
    <dd>「설정 → 밀도」에서 「보통」(여유 있게) 또는 「좁게」(한 화면에 더 많이)를 고르세요. 「자동」은 창 크기에 맞춥니다.</dd>
    <dt>화면이 계속 로딩 중이에요.</dt>
    <dd>새로고침(F5)을 한 번 해 보세요. 그래도 같으면 로그아웃 후 다시 로그인하고, 해결되지 않으면 화면을 캡처해 매니저에게 알려 주세요.</dd>
  </dl>
</section>

</body>
</html>`;

fs.mkdirSync(outRoot, { recursive: true });
fs.mkdirSync(deliverRoot, { recursive: true });
const htmlPath = path.join(outRoot, `${baseName}.html`);
const pdfPath = path.join(deliverRoot, `${baseName}.pdf`);
fs.writeFileSync(htmlPath, html);

const browser = await chromium.launch({
  executablePath: process.platform === 'win32'
    ? 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe'
    : undefined,
});
try {
  const page = await browser.newPage();
  await page.goto(pathToFileURL(htmlPath).href, { waitUntil: 'networkidle' });
  await page.evaluate(() => document.fonts.ready);
  await page.pdf({
    path: pdfPath,
    format: 'A4',
    printBackground: true,
    preferCSSPageSize: true,
    displayHeaderFooter: true,
    headerTemplate: '<span></span>',
    footerTemplate:
      '<div style="width:100%;font-size:8px;color:#8a93a3;padding:0 14mm;display:flex;justify-content:space-between;font-family:sans-serif">' +
      '<span>PLAYDATA LMS 사용자 가이드</span><span><span class="pageNumber"></span> / <span class="totalPages"></span></span></div>',
  });
  console.log(pdfPath);
} finally {
  await browser.close();
}
