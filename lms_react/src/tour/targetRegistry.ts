/**
 * targetId → DOM 엘리먼트 레지스트리 (역할·화면 공통)
 *
 * Flutter의 GlobalKey 레지스트리를 옮긴 것. 화면 쪽은 `useTourTarget(id)`가
 * 돌려주는 ref만 붙이면 되고, 오버레이는 id로 사각형을 묻는다.
 */
const elements = new Map<string, HTMLElement>();

export interface TargetRect {
  left: number;
  top: number;
  width: number;
  height: number;
}

export function registerTarget(targetId: string, el: HTMLElement | null): void {
  if (el === null) {
    elements.delete(targetId);
    return;
  }
  elements.set(targetId, el);
}

export function elementOf(targetId: string): HTMLElement | undefined {
  return elements.get(targetId);
}

export function isMounted(targetId: string): boolean {
  const el = elements.get(targetId);
  return el !== undefined && el.isConnected;
}

/** 뷰포트 기준 사각형. 붙어 있지 않거나 크기가 0이면 null. */
export function rectOf(targetId: string): TargetRect | null {
  const el = elements.get(targetId);
  if (!el || !el.isConnected) return null;
  const r = el.getBoundingClientRect();
  if (r.width <= 0 || r.height <= 0) return null;
  return { left: r.left, top: r.top, width: r.width, height: r.height };
}

/** 테스트용 */
export function debugReset(): void {
  elements.clear();
}

export function sameRect(a: TargetRect | null, b: TargetRect | null): boolean {
  if (a === null || b === null) return a === b;
  return (
    Math.abs(a.left - b.left) < 0.5 &&
    Math.abs(a.top - b.top) < 0.5 &&
    Math.abs(a.width - b.width) < 0.5 &&
    Math.abs(a.height - b.height) < 0.5
  );
}
