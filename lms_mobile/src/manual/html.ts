import { MANUALS, SHOT_BY_BLOCK, type ManualBlock, type ManualRole } from './content';
import { SHOTS } from './shots';

/**
 * 사용 설명서 PDF 용 HTML — expo-print 가 이 HTML 을 A4 PDF 로 만든다.
 * 글꼴은 기기 기본 글꼴(iOS: Apple SD Gothic Neo, Android: Noto Sans CJK)을 쓴다.
 */
const esc = (text: string) =>
  text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');

/** 「」 로 감싼 화면 문구는 굵게 보여 준다 */
const rich = (text: string) => esc(text).replace(/「([^」]+)」/g, '<b class="ui">「$1」</b>');

const pad = (n: number) => String(n).padStart(2, '0');

function figure(key: string, wide: boolean): string {
  const src = SHOTS[key];
  return src ? `<img class="${wide ? 'shot-wide' : 'shot'}" src="${src}" alt="" />` : '';
}

function block(b: ManualBlock, chapter: number, index: number, role: ManualRole): string {
  const parts: string[] = [];
  parts.push(`<h3><span class="bn">${chapter}.${index}</span>${esc(b.title)}</h3>`);
  if (b.where) parts.push(`<p class="where"><span>여는 곳</span>${rich(b.where)}</p>`);
  if (b.body) parts.push(`<p>${rich(b.body)}</p>`);
  if (b.steps?.length) parts.push(`<ol class="steps">${b.steps.map((s) => `<li>${rich(s)}</li>`).join('')}</ol>`);
  if (b.bullets?.length) parts.push(`<ul>${b.bullets.map((s) => `<li>${rich(s)}</li>`).join('')}</ul>`);
  if (b.table?.length) {
    const [head, ...rows] = b.table;
    parts.push(
      `<table><thead><tr>${head.map((h) => `<th>${esc(h)}</th>`).join('')}</tr></thead><tbody>${rows
        .map((r) => `<tr>${r.map((c) => `<td>${rich(c)}</td>`).join('')}</tr>`)
        .join('')}</tbody></table>`,
    );
  }
  if (b.tip) parts.push(`<div class="note tip"><span>TIP</span><p>${rich(b.tip)}</p></div>`);
  if (b.pc) parts.push(`<div class="note pc"><span>PC 웹</span><p>${rich(b.pc)}</p></div>`);
  const shot = SHOT_BY_BLOCK[role][b.title];
  if (!shot) return `<section class="block">${parts.join('')}</section>`;
  const head = parts.shift() ?? '';
  const text = parts.join('');
  if (shot.wide) {
    return `<section class="block wide">${head}${text}<div class="fig-wide">${figure(shot.keys[0], true)}<p class="cap">태블릿 가로 화면</p></div></section>`;
  }
  if (shot.keys.length > 1) {
    return `<section class="block wide">${head}${text}<div class="fig-row">${shot.keys.map((k) => figure(k, false)).join('')}</div></section>`;
  }
  return `<section class="block">${head}<div class="with-shot"><div class="txt">${text}</div><div class="fig">${figure(shot.keys[0], false)}</div></div></section>`;
}

export function manualHtml(role: ManualRole, issued = new Date()): string {
  const m = MANUALS[role];
  const date = `${issued.getFullYear()}.${pad(issued.getMonth() + 1)}.${pad(issued.getDate())}`;
  const toc = m.chapters
    .map((c, i) => `<li><span class="tn">${pad(i + 1)}</span><span class="tt">${esc(c.title)}</span><span class="ts">${esc(c.summary)}</span></li>`)
    .join('');
  const chapters = m.chapters
    .map(
      (c, i) => `
      <article class="chapter">
        <div class="keep">
          <header class="ch-head">
            <div class="ch-num">${pad(i + 1)}</div>
            <div><h2>${esc(c.title)}</h2><p>${esc(c.summary)}</p></div>
          </header>
          ${c.blocks.length ? block(c.blocks[0], i + 1, 1, role) : ''}
        </div>
        ${c.blocks.slice(1).map((b, j) => block(b, i + 1, j + 2, role)).join('')}
      </article>`,
    )
    .join('');

  return `<!doctype html>
<html lang="ko"><head><meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>PLAYDATA LMS 모바일 앱 ${esc(m.roleLabel)} 사용 설명서</title>
<style>
  @page { size: A4; margin: 16mm 15mm 18mm; }
  * { box-sizing: border-box; }
  html { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
  body { margin: 0; font-family: -apple-system, 'Apple SD Gothic Neo', 'Noto Sans KR', 'Noto Sans CJK KR', 'Malgun Gothic', sans-serif;
         color: #111827; font-size: 10.5pt; line-height: 1.62; word-break: keep-all; }
  b.ui { font-weight: 700; color: #0f172a; }

  .cover { height: 255mm; display: flex; flex-direction: column; page-break-after: always; }
  .cover .band { background: linear-gradient(135deg, #0369a1 0%, #0f172a 62%); color: #fff; border-radius: 18px; padding: 34mm 14mm 16mm; position: relative; overflow: hidden; }
  .cover .band::after { content: 'PLAYDATA'; position: absolute; right: -6mm; bottom: -9mm; font-size: 66pt; font-weight: 800; color: rgba(255,255,255,0.06); transform: rotate(-10deg); }
  .cover .brand { font-size: 11pt; font-weight: 800; letter-spacing: 0.5px; }
  .cover .brand small { display: block; font-size: 8pt; font-weight: 500; letter-spacing: 3px; color: rgba(199,214,238,0.8); }
  .cover h1 { margin: 18mm 0 4mm; font-size: 30pt; line-height: 1.2; letter-spacing: -0.5px; }
  .cover .role { display: inline-block; margin-top: 2mm; padding: 2mm 5mm; border-radius: 999px; background: rgba(255,255,255,0.16); font-size: 12pt; font-weight: 700; }
  .cover .sub { margin-top: 5mm; color: rgba(226,232,240,0.9); font-size: 12pt; }
  .cover .meta { margin-top: auto; display: flex; justify-content: space-between; color: #6b7280; font-size: 9pt; padding: 0 2mm; }

  .toc { page-break-after: always; }
  .toc h2 { font-size: 18pt; margin: 0 0 6mm; }
  .toc ol { list-style: none; padding: 0; margin: 0; }
  .toc li { display: grid; grid-template-columns: 12mm 46mm 1fr; align-items: baseline; padding: 3.2mm 0; border-bottom: 1px solid #e5e7eb; }
  .toc .tn { color: #0284c7; font-weight: 800; }
  .toc .tt { font-weight: 700; }
  .toc .ts { color: #6b7280; font-size: 9.5pt; }
  .toc .guide { margin-top: 8mm; padding: 4mm 5mm; border-radius: 10px; background: #f1f5f9; color: #374151; font-size: 9.5pt; }

  .chapter { margin-top: 9mm; }
  .keep { page-break-inside: avoid; break-inside: avoid; }
  .chapter:first-of-type { margin-top: 0; }
  .ch-head { page-break-after: avoid; break-after: avoid; display: flex; gap: 5mm; align-items: center; padding-bottom: 4mm; margin-bottom: 5mm; border-bottom: 2px solid #0284c7; }
  .ch-num { width: 14mm; height: 14mm; border-radius: 10px; background: #0284c7; color: #fff; font-size: 15pt; font-weight: 800; display: flex; align-items: center; justify-content: center; flex: none; }
  .ch-head h2 { margin: 0; font-size: 17pt; letter-spacing: -0.3px; }
  .ch-head p { margin: 1mm 0 0; color: #6b7280; font-size: 10pt; }

  .block { margin: 0 0 6mm; page-break-inside: avoid; }
  .block h3 { page-break-after: avoid; break-after: avoid;
  }
  .block h3 { font-size: 12.5pt; margin: 0 0 2mm; display: flex; align-items: baseline; gap: 2.5mm; }
  .block h3 .bn { color: #0284c7; font-size: 10pt; font-weight: 800; }
  .block p { margin: 0 0 2mm; }
  .where { display: flex; gap: 2.5mm; align-items: baseline; color: #374151; font-size: 9.5pt; }
  .where span { flex: none; padding: 0.4mm 2.2mm; border-radius: 999px; background: #e0f2fe; color: #0369a1; font-weight: 700; font-size: 8.5pt; }
  ol.steps { list-style: none; counter-reset: s; padding: 0; margin: 1mm 0 2mm; }
  ol.steps li { counter-increment: s; position: relative; padding: 0.6mm 0 1.6mm 9mm; }
  ol.steps li::before { content: counter(s); position: absolute; left: 0; top: 0.9mm; width: 5.6mm; height: 5.6mm; border-radius: 50%; background: #0f172a; color: #fff; font-size: 8pt; font-weight: 700; display: flex; align-items: center; justify-content: center; }
  ul { margin: 1mm 0 2mm; padding-left: 5mm; }
  ul li { margin-bottom: 1.2mm; }
  ul li::marker { color: #0284c7; }
  table { width: 100%; border-collapse: collapse; margin: 2mm 0 3mm; font-size: 9.5pt; }
  th { background: #0f172a; color: #fff; text-align: left; padding: 2mm 3mm; font-weight: 700; }
  td { padding: 2mm 3mm; border-bottom: 1px solid #e5e7eb; vertical-align: top; }
  tr:nth-child(even) td { background: #f8fafc; }
  .note { display: flex; gap: 3mm; align-items: flex-start; border-radius: 8px; padding: 2.6mm 3.5mm; margin: 2mm 0; font-size: 9.5pt; }
  .note p { margin: 0; }
  .note span { flex: none; font-size: 7.5pt; font-weight: 800; letter-spacing: 0.5px; padding: 0.6mm 2mm; border-radius: 4px; margin-top: 0.5mm; }
  .with-shot { display: grid; grid-template-columns: 1fr 44mm; gap: 6mm; align-items: start; }
  .with-shot .txt { min-width: 0; }
  .shot { width: 100%; border-radius: 3.5mm; border: 1px solid #cbd5e1; box-shadow: 0 2mm 5mm rgba(15,23,42,0.12); display: block; }
  .fig-row { display: flex; gap: 6mm; justify-content: center; margin-top: 3mm; }
  .fig-row .shot { width: 44mm; }
  .block.wide { page-break-inside: auto; break-inside: auto; }
  .fig-wide, .fig-row { page-break-inside: avoid; break-inside: avoid; }
  .fig-wide { margin-top: 3mm; text-align: center; }
  .shot-wide { width: 150mm; max-width: 100%; border-radius: 3mm; border: 1px solid #cbd5e1; box-shadow: 0 2mm 5mm rgba(15,23,42,0.12); }
  .cap { margin: 1.5mm 0 0; color: #6b7280; font-size: 8.5pt; }
  .tip { background: #f0f9ff; border-left: 3px solid #0284c7; }
  .tip span { background: #0284c7; color: #fff; }
  .pc { background: #f8fafc; border-left: 3px solid #64748b; }
  .pc span { background: #64748b; color: #fff; }
</style></head>
<body>
  <section class="cover">
    <div class="band">
      <div class="brand">PLAYDATA<small>LMS MOBILE</small></div>
      <h1>모바일 앱<br/>사용 설명서</h1>
      <div class="role">${esc(m.roleLabel)}용</div>
      <div class="sub">${esc(m.subtitle)}</div>
    </div>
    <div class="meta"><span>PLAYDATA LMS · iPhone · iPad · Android</span><span>${date} 기준</span></div>
  </section>

  <section class="toc">
    <h2>차례</h2>
    <ol>${toc}</ol>
    <div class="guide"><b>읽는 법</b> — 「」 안의 글자는 앱 화면에 보이는 버튼 · 메뉴 이름 그대로입니다. <b>여는 곳</b>은 그 기능을 여는 위치, <b>TIP</b>은 알아 두면 좋은 점, <b>PC 웹</b>은 PC 웹에서 이어서 하는 일입니다. 화면 캡처는 가짜 데모 데이터로 찍어 실제 이름 · 숫자와 다릅니다.</div>
  </section>

  ${chapters}
</body></html>`;
}
