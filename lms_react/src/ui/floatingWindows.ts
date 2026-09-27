import { useEffect } from 'react';

/**
 * 화면 위에 뜨는 창들(이력서 첨삭 · 복습/연습장)이 서로 비켜 서게 한다.
 *
 * 둘 다 펼쳐지면 한 창이 다른 창을 덮고 뒤 배경이 두 번 어두워졌다. 그래서 한 창이 펼쳐지면
 * 나머지는 스스로 내려놓는다 — 늘 창 하나만 펼쳐 있고, 나머지는 아래 막대로 나란히 남는다.
 * 창끼리 서로를 모르게 브라우저 이벤트 하나로만 알린다.
 */

const EVENT = 'lms:floating-window-expanded';

/**
 * @param who      창 이름. 자기가 낸 알림에는 반응하지 않는다
 * @param expanded 지금 펼쳐져 있는가
 * @param minimize 다른 창이 펼쳐지면 부른다
 */
export function useYieldToOtherWindows(who: string, expanded: boolean, minimize: () => void): void {
  useEffect(() => {
    if (expanded) window.dispatchEvent(new CustomEvent(EVENT, { detail: who }));
  }, [who, expanded]);

  useEffect(() => {
    if (!expanded) return undefined;
    const onOther = (e: Event) => {
      if ((e as CustomEvent<string>).detail !== who) minimize();
    };
    window.addEventListener(EVENT, onOther);
    return () => window.removeEventListener(EVENT, onOther);
  }, [who, expanded, minimize]);
}
