import { useQuery } from '@tanstack/react-query';

import { http } from './http';
import { useSessionStore } from './sessionStore';

/**
 * 그 해 공휴일 {"YYYY-MM-DD": 이름} — 출석 달력이 일요일처럼 칠한다.
 *
 * 서버(`/api/holidays`)가 공공데이터포털 특일 정보를 받아 둔 것을 읽는다. 원본은 앱 안에 표를
 * 박아 두었는데(`korean_holidays.dart`), 여기서는 임시공휴일이 생겨도 다시 배포하지 않게 서버에서 받는다.
 * 못 받으면 빈 표다 — 달력은 토 · 일만 칠한다.
 */
export function useHolidays(year: number): Record<string, string> {
  const access = useSessionStore((state) => state.access);
  const { data } = useQuery({
    queryKey: ['holidays', year],
    queryFn: async () => (await http.get<{ days: Record<string, string> }>('/holidays', { params: { year } })).data.days,
    enabled: import.meta.env.MODE !== 'test' && Boolean(access),
    // 한 해의 공휴일은 거의 바뀌지 않는다. 창을 다시 볼 때마다 묻지 않는다
    staleTime: 12 * 60 * 60 * 1000,
    refetchOnWindowFocus: false,
  });
  return data ?? {};
}
