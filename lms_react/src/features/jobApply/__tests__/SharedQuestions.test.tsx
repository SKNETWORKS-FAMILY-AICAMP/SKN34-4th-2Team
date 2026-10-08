import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { roleFromTitle, roleKey, similarRoles, type SharedQuestions as Shared } from '../sharedQuestionsApi';

const api = vi.hoisted(() => ({ list: vi.fn(), check: vi.fn(), save: vi.fn(), use: vi.fn(), report: vi.fn() }));

vi.mock('../sharedQuestionsApi', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../sharedQuestionsApi')>()),
  sharedQuestionsApi: api,
}));

const { QuestionsStep } = await import('../QuestionsStep');

const POSTING = { job_id: 'J1', company: '(주)현대모비스', title: '2026 하반기 SW 직군 신입사원 채용' };

const set = (id: string, questions: [string, number | null][], useCount = 0) => ({
  id,
  ids: [id],
  roleNames: ['SW 개발'],
  questions: questions.map(([question, limit]) => ({ question, limit })),
  useCount,
  updatedAt: '2026-10-07T09:00:00+09:00',
  mine: false,
  shared: true,
});

const SHARED: Shared = {
  company: '(주)현대모비스',
  season: '2026 하반기',
  canReport: false,
  roles: [
    {
      key: 'sw개발',
      name: 'SW 개발',
      names: ['SW 개발'],
      people: 2,
      useCount: 3,
      sets: [set('a', [['지원 동기를 쓰시오.', 700], ['협업 경험을 쓰시오.', 500]], 3), set('b', [['지원 동기를 쓰시오.', 800], ['입사 후 목표를 쓰시오.', 500]])],
    },
    { key: '생산기술', name: '생산기술', names: ['생산기술'], people: 1, useCount: 0, sets: [set('c', [['개선 경험을 쓰시오.', 700]])] },
  ],
  common: [],
};

describe('직무 이름 · 제목 짐작', () => {
  it('띄어쓰기 · 꼬리말 · 줄임말만 다르면 같은 직무', () => {
    expect(new Set(['SW 개발', 'SW개발 직무', '소프트웨어 개발', 'SW 개발자'].map(roleKey))).toEqual(new Set(['sw개발']));
    expect(similarRoles('소프트웨어 개발', SHARED.roles).map((r) => r.name)).toEqual(['SW 개발']);
    expect(similarRoles('마케팅', SHARED.roles)).toEqual([]);
  });

  it('공고 제목에서 시즌 · 신입 · 채용 같은 말을 뗀다', () => {
    expect(roleFromTitle('2026 하반기 SW 직군 신입사원 채용', '(주)현대모비스')).toBe('SW');
    expect(roleFromTitle('[현대모비스] 생산기술 신입 채용', '현대모비스')).toBe('생산기술');
  });
});

let host: HTMLDivElement;
let root: Root;

beforeEach(() => {
  host = document.createElement('div');
  document.body.appendChild(host);
  root = createRoot(host);
});

afterEach(() => {
  act(() => root.unmount());
  host.remove();
  vi.clearAllMocks();
});

const flush = () =>
  act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 0));
  });

const button = (text: string) => [...host.querySelectorAll('button')].find((b) => b.textContent?.includes(text)) as HTMLButtonElement;

describe('다른 수강생이 정리한 문항', () => {
  it('가장 많이 쓴 직무를 고르고, 그 직무의 정리를 가져와 쓴다', async () => {
    api.list.mockResolvedValue(SHARED);
    api.use.mockResolvedValue(undefined);
    const onChange = vi.fn();
    act(() => root.render(<QuestionsStep value={null} locked={false} onChange={onChange} posting={POSTING} />));
    await flush();
    expect(host.textContent).toContain('다른 수강생이 정리한 문항 · SW 개발');
    expect(host.textContent).toContain('3명 사용');
    // 다른 정리는 접어 두고, 펼치면 맨 위 정리에 없는 문항을 칠한다
    act(() => button('다른 정리 1개 보기').click());
    expect(host.querySelectorAll('.is-diff')).toHaveLength(1);
    act(() => button('이 문항으로 쓰기').click());
    expect(api.use).toHaveBeenCalledWith('a');
    expect(onChange.mock.calls[0][0].map((q: { question: string; limit: number | null }) => [q.question, q.limit])).toEqual([
      ['지원 동기를 쓰시오.', 700],
      ['협업 경험을 쓰시오.', 500],
    ]);
  });

  it('직접 입력하면 비슷한 기존 직무를 먼저 보여 준다', async () => {
    api.list.mockResolvedValue(SHARED);
    act(() => root.render(<QuestionsStep value={null} locked={false} onChange={vi.fn()} posting={POSTING} />));
    await flush();
    act(() => button('직접 입력').click());
    const input = host.querySelector('input[aria-label="지원 직무"]') as HTMLInputElement;
    act(() => {
      const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set;
      setter?.call(input, '소프트웨어 개발');
      input.dispatchEvent(new Event('input', { bubbles: true }));
    });
    expect(host.textContent).toContain('혹시 이 직무인가요?');
    act(() => button('2명 정리').click());
    expect(host.textContent).toContain('다른 수강생이 정리한 문항 · SW 개발');
  });

  it('아무도 정리하지 않았으면 제목에서 짐작한 직무로, 문항을 정하면 남긴다(같은 문항 직무가 있으면 묻는다)', async () => {
    api.list.mockResolvedValue({ ...SHARED, roles: [] });
    api.check.mockResolvedValue({ sameRole: { name: '백엔드', useCount: 2 } });
    api.save.mockResolvedValue({ id: 'n', created: true, roleName: '백엔드' });
    const onChange = vi.fn();
    act(() => root.render(<QuestionsStep value={null} locked={false} onChange={onChange} posting={POSTING} />));
    await flush();
    expect((host.querySelector('input[aria-label="지원 직무"]') as HTMLInputElement).value).toBe('SW');
    expect(host.textContent).toContain('아직 (주)현대모비스 2026 하반기 문항을 정리한 수강생이 없어요');
    const area = host.querySelector('textarea') as HTMLTextAreaElement;
    act(() => {
      const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value')?.set;
      setter?.call(area, '1. 지원 동기를 쓰시오. (700자)');
      area.dispatchEvent(new Event('input', { bubbles: true }));
    });
    act(() => button('문항 나누기').click());
    expect(host.textContent).toContain('다른 수강생에게도 보여주기');
    act(() => button('이 문항 1개로 정하기').click());
    await flush();
    expect(host.textContent).toContain('「백엔드」에 같은 문항이 이미 있어요');
    act(() => button('백엔드로 합치기').click());
    await flush();
    expect(api.save).toHaveBeenCalledWith('J1', '백엔드', expect.any(Array), true);
    expect(onChange).toHaveBeenCalledTimes(1);
  });

  it('공유 목록을 못 읽어도 직접 정하기는 그대로', async () => {
    api.list.mockRejectedValue(new Error('down'));
    act(() => root.render(<QuestionsStep value={null} locked={false} onChange={vi.fn()} posting={POSTING} />));
    await flush();
    expect(host.textContent).not.toContain('다른 수강생이 정리한 문항');
    expect(host.textContent).toContain('붙여넣기');
  });
});
