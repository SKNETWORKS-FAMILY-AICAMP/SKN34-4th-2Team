import { describe, expect, it } from 'vitest';

import { competencyCards } from '../ReviewWindow';
import { quotesOf } from '../reviewSession';

describe('핵심 역량 카드', () => {
  it('대시 없는 줄은 역량 이름, 대시 줄은 그 설명', () => {
    const body = [
      '복잡한 문제를 단계로 나누는 구조화 능력',
      '— 기능을 바로 구현하기보다 문제를 단계별로 나눠 설계합니다.',
      '기준선을 만들고 반복적으로 개선하는 개발 방식',
      ' — 먼저 비교 가능한 Baseline을 만든 뒤 확장합니다.',
      '— 두 번째 설명 줄',
    ].join('\n');
    expect(competencyCards(body)).toEqual([
      { title: '복잡한 문제를 단계로 나누는 구조화 능력', description: '기능을 바로 구현하기보다 문제를 단계별로 나눠 설계합니다.' },
      { title: '기준선을 만들고 반복적으로 개선하는 개발 방식', description: '먼저 비교 가능한 Baseline을 만든 뒤 확장합니다.\n두 번째 설명 줄' },
    ]);
  });

  it('대시 줄이 없는 글은 카드로 나누지 않는다(글 그대로)', () => {
    expect(competencyCards('데이터를 끝까지 따라가 봅니다.\n문제를 작게 나눕니다.')).toBeNull();
  });
});

describe('첨삭 중인 원문 문장', () => {
  it('수정안 · 질문 · 문장 다듬기 묶음에서 원문을 꺼낸다', () => {
    expect(quotesOf({ original_quote: '기능을 바로 구현하기보다', field_path: 'coreCompetencies.text' })).toEqual(['기능을 바로 구현하기보다']);
    expect(quotesOf({ context: { quote: '데이터 흐름 전체를 보는 시야' } })).toEqual(['데이터 흐름 전체를 보는 시야']);
    expect(
      quotesOf({ _kind: 'polish', items: [{ original_quote: '첫 번째 문장입니다' }, { original_quote: '두 번째 문장입니다' }] }),
    ).toEqual(['첫 번째 문장입니다', '두 번째 문장입니다']);
  });

  it('너무 짧은 조각 · 빈 값은 뺀다', () => {
    expect(quotesOf({ original_quote: '짧음', quote: '' })).toEqual([]);
    expect(quotesOf(null)).toEqual([]);
  });
});
