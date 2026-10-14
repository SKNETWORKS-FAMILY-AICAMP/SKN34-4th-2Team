// React 18의 act()가 테스트 환경임을 알아보게 한다.
(globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

// jsdom에는 matchMedia가 없다. 애니메이션 코드가 「움직임 줄이기」를 물어보므로
// 최소 구현을 둔다. 테스트는 「줄임」으로 답하게 해 둔다 — 로그인 퇴장 연출 같은
// 시간이 걸리는 장면을 기다리지 않고 결과만 본다.
if (typeof window !== 'undefined' && window.matchMedia === undefined) {
  window.matchMedia = ((query: string) => ({
    matches: query.includes('prefers-reduced-motion'),
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  })) as typeof window.matchMedia;
}
