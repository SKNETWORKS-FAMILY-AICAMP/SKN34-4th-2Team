/*
 * 파이썬 런타임 캐시 — 연습장의 Pyodide(런타임 · numpy · pandas · matplotlib 휠)를 Cache Storage 에 둔다.
 *
 * 브라우저 HTTP 캐시도 같은 일을 하지만 큰 파일(wasm 10MB 안팎)부터 밀려나고, 밀려나면 다시 CDN 에서 받는다.
 * 교실 와이파이에 수십 명이 한꺼번에 받으면 그게 느리다. Cache Storage 는 사용자가 지우기 전까지 남는다.
 * 앱 자체(로그인 · 데이터)가 서버를 쓰므로 오프라인 지원은 목표가 아니다.
 * 이 워커는 버전이 박힌 CDN 주소(…/pyodide/v<버전>/full/…)만 가로채서 캐시에서 먼저 준다.
 * 주소에 버전이 있어 내용이 바뀌지 않으니 다시 확인하지 않는다. 버전이 바뀌면 옛 캐시는 지운다.
 * 앱 파일·API 요청에는 손대지 않는다.
 *
 * 등록: src/features/practice/runtimeCache.ts — /pyodide-sw.js?v=<PYODIDE_VERSION>
 */
const VERSION = new URL(self.location.href).searchParams.get('v') || 'unknown';
const CACHE = `pyodide-${VERSION}`;
const PREFIX = `https://cdn.jsdelivr.net/pyodide/v${VERSION}/full/`;

self.addEventListener('install', () => self.skipWaiting());

self.addEventListener('activate', (event) => {
  event.waitUntil(
    (async () => {
      for (const name of await caches.keys()) {
        if (name.startsWith('pyodide-') && name !== CACHE) await caches.delete(name);
      }
      await self.clients.claim();
    })(),
  );
});

self.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.method !== 'GET' || !req.url.startsWith(PREFIX)) return;
  event.respondWith(
    (async () => {
      const cache = await caches.open(CACHE);
      const hit = await cache.match(req.url);
      if (hit) return hit;
      const res = await fetch(req);
      // CORS 로 받은 정상 응답만 둔다. opaque 응답은 크기를 알 수 없어 할당량을 크게 잡아먹는다.
      if (res.ok && res.type === 'cors') cache.put(req.url, res.clone()).catch(() => {});
      return res;
    })(),
  );
});
