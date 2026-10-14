import { describe, expect, it } from 'vitest';

import { mapBootstrap } from '../bootstrap';

describe('bootstrap 의 이력서 본문', () => {
  it('공고 맞춤 이력서의 회사 문항을 남긴다 — 빼면 편집기가 저장할 때 지워진다', () => {
    const companyQuestions = [{ id: 'cq1', question: '지원 동기를 작성하시오.', limit: 600, answer: '' }];
    const db = mapBootstrap({
      resumes: [{ id: 'r1/tailored/t1', pk: 2, title: '맞춤', status: 'writing', content: { companyQuestions } }],
    });
    expect(db.resumes[0].content.companyQuestions).toEqual(companyQuestions);
  });

  it('회사 문항이 없는 이력서에는 칸을 만들지 않는다', () => {
    const db = mapBootstrap({ resumes: [{ id: 'r1', pk: 1, title: '기본', status: 'writing', content: {} }] });
    expect('companyQuestions' in db.resumes[0].content).toBe(false);
  });
});
