import { describe, expect, it } from 'vitest';
import type { Notice } from './types';
import { visibleNotices } from './visibleNotices';

const reminder = (id: string, day: number, extra: Partial<Notice> = {}): Notice => ({
  id, title: '[출결] 오늘 예외 출결 제출', content: '출결 신청 안내', authorName: '관리자',
  isFavorite: true, priority: 0, source: 'scheduled', createdAt: new Date(2026, 9, day), ...extra,
});

describe('visibleNotices', () => {
  it('keeps the newest attendance reminder regardless of input order without changing history', () => {
    const rows = [reminder('old', 10), reminder('latest', 13), reminder('middle', 12)];
    expect(visibleNotices(rows).map(n => n.id)).toEqual(['latest']);
    expect(rows).toHaveLength(3);
  });

  it('preserves manually written notices and other scheduled announcements', () => {
    const rows = [reminder('latest', 13), reminder('manual', 12, { source: undefined }),
      reminder('old', 11), reminder('event', 10, { title: '프로젝트 발표 안내' })];
    expect(visibleNotices(rows).map(n => n.id)).toEqual(['latest', 'manual', 'event']);
  });
});
