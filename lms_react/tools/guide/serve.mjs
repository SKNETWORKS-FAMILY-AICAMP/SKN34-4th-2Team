// 데모 모드 빌드(build/guide_web)를 정적으로 띄운다. BrowserRouter 라 없는 경로는 index.html 로 돌린다.
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
export const lmsRoot = path.resolve(here, '../..');
export const repoRoot = path.resolve(lmsRoot, '..');
export const webRoot = path.join(repoRoot, 'build', 'guide_web');
export const outRoot = path.join(repoRoot, 'build', 'guide');

const mime = {
  '.html': 'text/html; charset=utf-8', '.js': 'text/javascript', '.mjs': 'text/javascript', '.css': 'text/css',
  '.json': 'application/json', '.wasm': 'application/wasm', '.png': 'image/png', '.jpg': 'image/jpeg',
  '.svg': 'image/svg+xml', '.ttf': 'font/ttf', '.otf': 'font/otf', '.woff': 'font/woff', '.woff2': 'font/woff2',
  '.ico': 'image/x-icon', '.pdf': 'application/pdf',
};

export function serve(port = 0) {
  if (!fs.existsSync(path.join(webRoot, 'index.html'))) {
    throw new Error(`데모 빌드가 없습니다: ${webRoot}\nnpx vite build --mode test --outDir ../build/guide_web --emptyOutDir 를 먼저 실행하세요.`);
  }
  const server = http.createServer((req, res) => {
    const urlPath = decodeURIComponent(req.url.split('?')[0]);
    let file = path.join(webRoot, urlPath);
    if (!file.startsWith(webRoot)) return res.writeHead(403).end();
    if (!fs.existsSync(file) || fs.statSync(file).isDirectory()) file = path.join(webRoot, 'index.html');
    res.writeHead(200, {
      'Content-Type': mime[path.extname(file)] ?? 'application/octet-stream',
      'Cross-Origin-Opener-Policy': 'same-origin',
      'Cross-Origin-Embedder-Policy': 'require-corp',
    });
    fs.createReadStream(file).pipe(res);
  });
  return new Promise((resolve) => {
    server.listen(port, '127.0.0.1', () => resolve({ url: `http://127.0.0.1:${server.address().port}`, close: () => server.close() }));
  });
}
