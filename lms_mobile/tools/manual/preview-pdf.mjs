// 앱이 만드는 설명서와 같은 HTML 로 PC 에서 PDF 미리보기를 만든다.
//   node tools/manual/preview-pdf.mjs <출력 폴더>
// 필요: npm i -D esbuild playwright-core (또는 전역 설치), 크롬 경로는 CHROME 환경 변수
import { build } from 'esbuild';
import { chromium } from 'playwright-core';
import { mkdirSync } from 'fs';
import { dirname, join, resolve } from 'path';
import { fileURLToPath } from 'url';

const here = dirname(fileURLToPath(import.meta.url));
const out = resolve(process.argv[2] ?? 'manual-preview');
mkdirSync(out, { recursive: true });
const bundle = join(out, 'manual-html.mjs');
await build({ entryPoints: [join(here, '../../src/manual/html.ts')], bundle: true, format: 'esm', platform: 'node', outfile: bundle, logLevel: 'error' });
const { manualHtml } = await import(bundle);

const browser = await chromium.launch(process.env.CHROME ? { executablePath: process.env.CHROME } : {});
const names = { student: '학생', instructor: '강사', admin: '관리자' };
for (const role of Object.keys(names)) {
  const page = await browser.newPage();
  await page.setContent(manualHtml(role), { waitUntil: 'load' });
  await page.pdf({ path: join(out, `PLAYDATA_모바일_매뉴얼_${names[role]}.pdf`), format: 'A4', printBackground: true, preferCSSPageSize: true });
  await page.close();
}
await browser.close();
console.log(`PDF → ${out}`);
