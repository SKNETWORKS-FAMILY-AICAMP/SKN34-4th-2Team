/**
 * 온보딩 「다시 보지 않기」 — 영구 dismiss (버전별로 재노출 가능)
 *
 * 키: `onboarding_{tourId}_v{version}_{uid}`
 * 메모리 캐시가 소스 오브 트루스다. Flutter의 SharedPreferences 자리에
 * localStorage가 들어왔을 뿐, 키와 동작은 그대로다.
 */
const cache = new Map<string, boolean>();

export interface DismissKey {
  tourId: string;
  version: number;
  uid: string;
}

export function storageKey({ tourId, version, uid }: DismissKey): string {
  return `onboarding_${tourId}_v${version}_${uid}`;
}

function readStorage(key: string): boolean | null {
  try {
    const raw = window.localStorage.getItem(key);
    if (raw === null) return null;
    return raw === 'true';
  } catch {
    return null;
  }
}

export function isDismissed(target: DismissKey): boolean {
  const key = storageKey(target);
  const cached = cache.get(key);
  if (cached !== undefined) return cached;
  const saved = readStorage(key) ?? false;
  cache.set(key, saved);
  return saved;
}

export function dismiss(target: DismissKey): void {
  const key = storageKey(target);
  cache.set(key, true);
  try {
    window.localStorage.setItem(key, 'true');
  } catch {
    /* 저장에 실패해도 이번 세션 동안은 캐시가 막아 준다 */
  }
}

/** 마이페이지 「이용 안내 다시 보기」용 */
export function clearDismiss(target: DismissKey): void {
  const key = storageKey(target);
  cache.set(key, false);
  try {
    window.localStorage.removeItem(key);
  } catch {
    /* 무시 */
  }
}

/** 테스트용 */
export function debugReset(): void {
  cache.clear();
}
