import { describe, expect, it } from 'vitest';

import type { ResumeContent } from '../../../../domain/types';
import {
  emptyScopeReason,
  nextSeenJobIds,
  nextShownJobIds,
  recommendSummary,
  sameChatConditions,
  shouldSendResume,
} from '../chatRefs';
import { parseChatText } from '../chatText';

const blank = { subtitle: '', body: '' };
const empty: ResumeContent = {
  basicInfo: { name: '', phone: '', email: '', birthDate: '', githubUrl: '', blogUrl: '' },
  coreCompetencies: { text: '' },
  experience: [],
  education: [],
  techStack: [],
  certifications: [],
  awards: [],
  trainingExperience: [],
  otherActivities: [],
  projects: [],
  selfIntroduction: {
    intro: blank,
    motivation: blank,
    challenge: blank,
    growth: blank,
    strengthsWeaknesses: blank,
    aspiration: blank,
  },
};

describe('번호가 가리킬 목록', () => {
  it('검색 답만 목록을 바꾼다. 비교 · 질문 답과 0건 검색은 앞 목록을 지킨다', () => {
    expect(nextShownJobIds('검색', ['a', 'b'], ['x'])).toEqual(['a', 'b']);
    expect(nextShownJobIds('비교', ['a', 'b'], ['x'])).toEqual(['x']);
    expect(nextShownJobIds('검색', [], ['x'])).toEqual(['x']);
  });
});

describe('이미 본 공고', () => {
  it('조건이 같으면 쌓고, 바뀌면 새로 센다', () => {
    expect(nextSeenJobIds('검색', ['b', 'c'], ['a', 'b'], true)).toEqual(['a', 'b', 'c']);
    expect(nextSeenJobIds('검색', ['c'], ['a', 'b'], false)).toEqual(['c']);
    expect(nextSeenJobIds('질문', ['c'], ['a'], true)).toEqual(['a']);
  });

  it('조건이 같은지는 서버가 돌려준 그대로 견준다', () => {
    expect(sameChatConditions({ regions: ['서울'] }, { regions: ['서울'] })).toBe(true);
    expect(sameChatConditions(null, { regions: [] })).toBe(false);
  });
});

describe('이력서를 함께 보낼지', () => {
  it('카드를 눌렀거나 직전에 목록을 보여 줬으면 보낸다', () => {
    expect(shouldSendResume(true, false)).toBe(true);
    expect(shouldSendResume(false, true)).toBe(true);
    expect(shouldSendResume(false, false)).toBe(false);
  });
});

describe('좁혀 추천', () => {
  it('좁힌 곳이 비어 있으면 먼저 알린다', () => {
    expect(emptyScopeReason('프로젝트', empty)).toContain('프로젝트가 아직 없어요');
    expect(emptyScopeReason('경력', empty)).toContain('경력이 아직 없어요');
    expect(emptyScopeReason('전체', empty)).toBeNull();
  });

  it('몇 건을 골랐는지 말한다', () => {
    expect(recommendSummary(3, '프로젝트')).toBe('프로젝트 경험을 읽고 3건을 골랐어요.');
    expect(recommendSummary(0, '전체')).toContain('찾지 못했어요');
  });
});

describe('답 서식', () => {
  it('굵게와 항목 줄만 읽고, 짝 없는 별표는 글자로 둔다', () => {
    const blocks = parseChatText('**서울** 공고예요\n\n- 첫째\n• 둘째 **굵게**\n별표 * 하나');
    expect(blocks).toEqual([
      { spans: [{ text: '서울', bold: true }, { text: ' 공고예요', bold: false }], bullet: false },
      { spans: [{ text: '첫째', bold: false }], bullet: true },
      { spans: [{ text: '둘째 ', bold: false }, { text: '굵게', bold: true }], bullet: true },
      { spans: [{ text: '별표 * 하나', bold: false }], bullet: false },
    ]);
  });
});
