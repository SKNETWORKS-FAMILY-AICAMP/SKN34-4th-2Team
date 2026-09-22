import { describe, expect, it } from 'vitest';

import type { Resume } from '../../../domain/types';
import { groupResumes, resumeStatusFromServer, resumeStatusToServer } from '../resumeGroups';

const r = (id: string, extra: Partial<Resume> = {}): Resume => ({
  id, userId: 'u', title: id, status: 'draft', sections: {}, content: {} as Resume['content'], isBaseResume: false,
  feedbackCount: 0, lastSeenFeedbackCount: 0, readFeedbackIds: [], revisionCount: 0, ...extra,
});

describe('이력서 상태 — Flutter 값과 화면 값', () => {
  it('writing · ready 는 작성 중, submitted 는 피드백 요청, completed 는 승인', () => {
    expect(['writing', 'ready', 'draft', undefined].map(resumeStatusFromServer)).toEqual(['draft', 'draft', 'draft', 'draft']);
    expect(resumeStatusFromServer('submitted')).toBe('feedbackRequested');
    expect(resumeStatusFromServer('completed')).toBe('approved');
  });
  it('저장할 때는 DB 값으로 되돌린다', () => {
    expect(resumeStatusToServer('draft')).toBe('writing');
    expect(resumeStatusToServer('feedbackRequested')).toBe('submitted');
    expect(resumeStatusToServer('approved')).toBe('approved');
  });
});

describe('공고 맞춤 이력서 묶음', () => {
  const base = r('base', { isBaseResume: true });
  const list = [
    base,
    r('t1', { baseResumeId: 'base' }),
    r('other'),
    r('t2', { baseResumeId: 'other' }),
    r('lost', { baseResumeId: 'gone' }),
  ];

  it('기본 이력서 것은 카드 밑, 다른 이력서 것은 그 줄 밑, 원본이 없으면 따로 한 줄', () => {
    const g = groupResumes(list, base);
    expect(g.baseTailored.map((x) => x.id)).toEqual(['t1']);
    expect(g.rows.map((row) => [row.resume.id, row.children.map((c) => c.id)])).toEqual([
      ['other', ['t2']],
      ['lost', []],
    ]);
  });
});
