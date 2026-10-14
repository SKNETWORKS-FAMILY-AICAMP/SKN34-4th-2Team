/** 날짜·숫자 표기 — Flutter `core/utils/date_utils.dart` */

const pad = (v: number) => String(v).padStart(2, '0');

/** API·캐시에서 Date 또는 ISO 문자열이 올 수 있을 때 안전하게 ms 로 바꾼다. */
export function toDate(value?: Date | string | null): Date {
  if (value instanceof Date && !Number.isNaN(value.getTime())) return value;
  if (value == null || value === '') return new Date(0);
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? new Date(0) : parsed;
}

export function toTime(value?: Date | string | null): number {
  return toDate(value).getTime();
}

export function formatDate(date?: Date | null): string {
  if (date === undefined || date === null) return '-';
  return `${date.getFullYear()}.${pad(date.getMonth() + 1)}.${pad(date.getDate())}`;
}

export function formatDateTime(date?: Date | null): string {
  if (date === undefined || date === null) return '-';
  return `${formatDate(date)} ${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

export function formatTime(date?: Date | null): string {
  if (date === undefined || date === null) return '-';
  return `${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

/** 목록에서 쓰는 상대 표기. 오늘은 시각, 어제는 「어제」, 그 전은 날짜. */
export function formatRelative(date?: Date | null): string {
  if (date === undefined || date === null) return '-';
  const now = new Date();
  const sameDay = date.toDateString() === now.toDateString();
  if (sameDay) return formatTime(date);
  const yesterday = new Date(now);
  yesterday.setDate(now.getDate() - 1);
  if (date.toDateString() === yesterday.toDateString()) return '어제';
  return formatDate(date);
}

/** 남은 기한. 지났으면 「마감」. */
export function formatDueIn(due: Date): string {
  const diff = due.getTime() - Date.now();
  if (diff <= 0) return '마감';
  const days = Math.floor(diff / 86400000);
  if (days >= 1) return `${days}일 남음`;
  const hours = Math.floor(diff / 3600000);
  if (hours >= 1) return `${hours}시간 남음`;
  return '오늘 마감';
}

export function formatMileage(amount: number): string {
  return `${amount.toLocaleString()} M`;
}

export function formatSigned(amount: number): string {
  return `${amount > 0 ? '+' : ''}${amount.toLocaleString()}`;
}

/** 'YYYYMMDD' → 'YYYY.MM.DD' (자격 시험 API 표기) */
export function formatYmd(raw?: string | null): string {
  if (raw === undefined || raw === null || raw.length !== 8) return '-';
  return `${raw.slice(0, 4)}.${raw.slice(4, 6)}.${raw.slice(6, 8)}`;
}

export function parseYmd(raw?: string | null): Date | null {
  if (raw === undefined || raw === null || raw.length !== 8) return null;
  return new Date(Number(raw.slice(0, 4)), Number(raw.slice(4, 6)) - 1, Number(raw.slice(6, 8)));
}
