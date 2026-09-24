import { PYODIDE_VERSION } from './pythonProtocol';

/**
 * 파이썬 런타임 캐시 워커(public/pyodide-sw.js)를 등록한다. 배포 빌드에서만.
 * 개발 서버에서는 켜지 않는다 — 옛 캐시가 남아 헷갈리지 않게.
 * 실패해도 연습장은 그대로 CDN 에서 받는다.
 */
export function registerRuntimeCache(): void {
  if (!import.meta.env.PROD || typeof navigator === 'undefined' || !('serviceWorker' in navigator)) return;
  const register = () => {
    navigator.serviceWorker.register(`/pyodide-sw.js?v=${PYODIDE_VERSION}`, { scope: '/' }).catch(() => {});
  };
  if (document.readyState === 'complete') register();
  else window.addEventListener('load', register, { once: true });
}
