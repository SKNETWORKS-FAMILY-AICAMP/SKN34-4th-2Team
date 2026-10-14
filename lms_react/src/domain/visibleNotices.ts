import type { Notice } from './types';

const ATTENDANCE_REMINDER_TITLE = '[출결] 오늘 예외 출결 제출';

/** 반복 발행된 출결 안내는 최신 한 건만 노출한다. 관리 이력은 원본에 남긴다. */
export function visibleNotices(notices: Notice[]): Notice[] {
  const reminders = notices.filter(isAttendanceReminder);
  const latest = reminders.reduce<Notice | undefined>((current, notice) =>
    current === undefined || timestamp(notice) > timestamp(current) ? notice : current, undefined);
  return notices.filter((notice) => !isAttendanceReminder(notice) || notice === latest);
}

function isAttendanceReminder(notice: Notice): boolean {
  return notice.source === 'scheduled' && notice.title.trim() === ATTENDANCE_REMINDER_TITLE;
}

function timestamp(notice: Notice): number {
  const value = notice.createdAt?.getTime() ?? 0;
  return Number.isFinite(value) ? value : 0;
}
