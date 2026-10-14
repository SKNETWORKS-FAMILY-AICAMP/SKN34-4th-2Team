import { lazy, type ComponentType } from 'react';

/**
 * 이름 붙은 내보내기를 React.lazy 로 — 화면 파일들이 default 없이 여러 화면을 내보내서.
 * 같은 loader 를 쓰는 화면들은 한 청크를 같이 쓴다. props 타입은 원래 화면 것 그대로.
 *
 * 받는 중인 청크 수를 센다. 라우터는 화면 전환을 트랜지션으로 해서 받는 동안 옛 화면을 그대로
 * 보여 주므로(자리 표시가 안 뜬다), 이용 안내 투어는 이 수를 보고 타깃 찾기를 미룬다.
 */
let inFlight = 0;

/** 지금 받는 중인 화면 청크가 있는지 */
export function isScreenLoading(): boolean {
  return inFlight > 0;
}

export function tracked<M>(loader: () => Promise<M>): () => Promise<M> {
  return async () => {
    inFlight += 1;
    try {
      return await loader();
    } finally {
      inFlight -= 1;
    }
  };
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function lazyNamed<K extends string, M extends { [P in K]: ComponentType<any> }>(loader: () => Promise<M>, name: K) {
  return lazy(async () => ({ default: (await loader())[name] }));
}

/** 한가할 때 청크를 미리 받는다 — 메뉴를 눌렀을 때 기다리지 않게 */
export function prefetchWhenIdle(loaders: (() => Promise<unknown>)[]): () => void {
  const run = () => loaders.forEach((load) => void load().catch(() => {}));
  const w = window as Window & { requestIdleCallback?: (cb: () => void) => number; cancelIdleCallback?: (id: number) => void };
  if (w.requestIdleCallback) {
    const id = w.requestIdleCallback(run);
    return () => w.cancelIdleCallback?.(id);
  }
  const id = window.setTimeout(run, 1500);
  return () => window.clearTimeout(id);
}
