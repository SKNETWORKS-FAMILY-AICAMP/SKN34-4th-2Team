/**
 * 불시 점검 화면 말 — 웹 `SpotCheck.tsx` 와 모바일(`@web/*`)이 같이 쓴다.
 * 모바일에서도 가져오므로 브라우저 API · 무거운 의존성을 넣지 않는다.
 */
export const ABSENT_REASONS = ['외출', '조퇴', '병원', '화장실 · 휴식', '상담 · 면담', '결석'] as const;

export const SpotCheckPeriodLabels = { am: '오전', pm: '오후' } as const;
