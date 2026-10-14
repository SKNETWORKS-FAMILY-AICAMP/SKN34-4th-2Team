import type { ScheduleRepeatType } from '../domain/types';

/** Flutter computeNextPublishAt — 다음 게시 시각 (로컬). */
export function computeNextPublishAt(input: {
  repeatType: ScheduleRepeatType;
  publishTime: string;
  publishAt?: Date;
  weekday: number;
  from?: Date;
}): Date {
  const base = input.from ?? new Date();
  const [hourText, minuteText] = input.publishTime.split(':');
  const hour = Number(hourText) || 9;
  const minute = Number(minuteText) || 0;

  if (input.repeatType === 'once') {
    if (input.publishAt !== undefined) return input.publishAt;
    return new Date(base.getFullYear(), base.getMonth(), base.getDate(), hour, minute);
  }

  if (input.repeatType === 'daily') {
    const candidate = new Date(base.getFullYear(), base.getMonth(), base.getDate(), hour, minute);
    if (candidate.getTime() <= base.getTime()) candidate.setDate(candidate.getDate() + 1);
    return candidate;
  }

  const want = input.weekday >= 1 && input.weekday <= 7 ? input.weekday : 1;
  const candidate = new Date(base.getFullYear(), base.getMonth(), base.getDate(), hour, minute);
  const isoWeekday = (date: Date) => (date.getDay() === 0 ? 7 : date.getDay());
  while (isoWeekday(candidate) !== want || candidate.getTime() <= base.getTime()) {
    candidate.setDate(candidate.getDate() + 1);
  }
  return candidate;
}
