import { describe, expect, it } from 'vitest';

import { defaultQuestions, splitQuestions } from '../companyQuestions';

const ids = () => {
  let n = 0;
  return () => `q${++n}`;
};

const shape = (text: string) => splitQuestions(text, ids()).map(({ question, limit }) => ({ question, limit }));

describe('붙여 넣은 자소서 문항 나누기', () => {
  it('번호 문항과 괄호 속 글자 수를 나누고, 머리글은 버린다', () => {
    expect(
      shape(`[자기소개서]
1. 클라우드랩에 지원한 이유와 입사 후 포부를 기술하시오. (공백 포함 600자 이내)
2. 본인이 주도적으로 문제를 해결한 경험을 서술하시오. (공백 포함 1,000자 이내)`),
    ).toEqual([
      { question: '클라우드랩에 지원한 이유와 입사 후 포부를 기술하시오.', limit: 600 },
      { question: '본인이 주도적으로 문제를 해결한 경험을 서술하시오.', limit: 1000 },
    ]);
  });

  it('작성 안내 줄은 문항에 붙이지 않고, 다음 줄의 글자 수는 읽는다', () => {
    expect(
      shape(`① 자신을 소개하고, 지원한 직무를 선택한 이유를 작성해 주세요.
(* Guide : 본인의 가치관과 경험을 구체적으로 작성해 주세요.)
(500자 이내)
② 협업 경험을 작성해 주세요.`),
    ).toEqual([
      { question: '자신을 소개하고, 지원한 직무를 선택한 이유를 작성해 주세요.', limit: 500 },
      { question: '협업 경험을 작성해 주세요.', limit: null },
    ]);
  });

  it('두 줄로 접힌 번호 문항은 잇는다', () => {
    expect(shape('Q1. 팀 프로젝트에서 맡은 역할과\n기여를 작성하시오. 800자')).toEqual([
      { question: '팀 프로젝트에서 맡은 역할과 기여를 작성하시오.', limit: 800 },
    ]);
  });

  it('번호가 없으면 묻는 말로 끝나는 줄만 문항으로 본다', () => {
    expect(
      shape(`지원 양식 안내
우리 회사에 지원한 동기는 무엇인가요?
입사 후 이루고 싶은 목표를 작성해 주세요. (700자 내외)`),
    ).toEqual([
      { question: '우리 회사에 지원한 동기는 무엇인가요?', limit: null },
      { question: '입사 후 이루고 싶은 목표를 작성해 주세요.', limit: 700 },
    ]);
  });

  it('괄호 없이 끝에 붙은 글자 수도 문항 글에서 뗀다', () => {
    expect(shape('1. 지원 동기를 작성하시오 - 공백 포함 500자 이내')).toEqual([
      { question: '지원 동기를 작성하시오', limit: 500 },
    ]);
  });

  it('문항이 없는 글이면 빈 목록', () => {
    expect(shape('이력서 및 자기소개서 제출\n자유양식')).toEqual([]);
  });
});

describe('기본 6문항', () => {
  it('자기소개서 여섯 칸을 문항으로 옮기고, 써 둔 글을 답으로 둔다', () => {
    const qs = defaultQuestions({ motivation: { body: '데이터로 일하고 싶습니다.' } }, ids());
    expect(qs.map((q) => q.question)).toEqual([
      '자기소개', '지원동기', '어려움을 극복한 경험', '성장과정', '성격의 장단점', '입사 후 포부',
    ]);
    expect(qs[1]).toEqual({ id: 'q2', question: '지원동기', limit: null, answer: '데이터로 일하고 싶습니다.' });
    expect(qs[0].answer).toBe('');
  });
});
