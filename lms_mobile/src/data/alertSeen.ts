import { useMemo } from 'react';
import type { AlertPopup } from '@web/domain/types';

import { useDb } from './query';

/**
 * 계정별로 확인한 알림 팝업 — 서버가 bootstrap 의 alertPopupReadIds 로 돌려준다(웹과 같은 기록).
 * 그래서 다른 기기 · 웹에서 확인한 알림도 읽음으로 보인다.
 */
export function useSeenAlerts(): Set<string> {
  const ids = useDb()?.alertReadIds;
  return useMemo(() => new Set(ids ?? []), [ids]);
}

/** 오늘 하루 보지 않기로 닫은 알림 — 계정별, 날짜별 */
export function useDismissedToday(uid: string, today: string): Set<string> {
  const map = useDb()?.alertDismissals?.[uid];
  return useMemo(() => new Set(Object.entries(map ?? {}).filter(([, day]) => day === today).map(([id]) => id)), [map, today]);
}

function hhmm(date: Date): string {
  return `${String(date.getHours()).padStart(2, '0')}:${String(date.getMinutes()).padStart(2, '0')}`;
}

function dayKey(date: Date): string {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
}

/** 지금 학생에게 보여야 하는 알림 — 켜져 있고, 끝난 날짜 · 노출 시간대 안 (웹 AlertPopupHost 와 같은 조건) */
export function visibleAlerts(alerts: AlertPopup[], now = new Date()): AlertPopup[] {
  const today = dayKey(now);
  const time = hhmm(now);
  return alerts.filter((popup) => {
    if (!popup.isActive) return false;
    if (popup.endDate && popup.endDate < today) return false;
    if (popup.startTime && time < popup.startTime) return false;
    if (popup.endTime && time > popup.endTime) return false;
    return true;
  });
}
