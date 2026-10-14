import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { WritingStatus } from '../QuestionWorkflowAnswers';

// 문항 카드 대신 — 쓰는 중 · 다 씀을 테스트가 알린다. 내려둬도 창이 살아 있는지(마운트 횟수)를 센다
const fake = vi.hoisted(() => ({ report: null as null | ((s: WritingStatus) => void), mounts: 0 }));
vi.mock('../QuestionWorkflowAnswers', async () => {
  const { useEffect } = await import('react');
  return {
    QuestionWorkflowAnswers: ({ editId, onStatus }: { editId: string; onStatus?(s: WritingStatus): void }) => {
      useEffect(() => {
        fake.mounts += 1;
      }, []);
      fake.report = onStatus ?? null;
      return <p>문항 카드 {editId}</p>;
    },
  };
});

const api = vi.hoisted(() => ({ requirements: vi.fn() }));
vi.mock('../../resume/review/reviewApi', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../resume/review/reviewApi')>()),
  reviewApi: api,
}));

const { WriteDockHost, useWriteDock } = await import('../WriteDock');

// 1번 자소서는 2단계에서 불러온 요건을 넘기고, 2번은 창이 직접 읽는다
const GIVEN = [
  { id: 'R1', group: 'must', label: 'Python', postingQuote: 'Python 활용 능력' },
  { id: 'R2', group: 'preferred', label: 'AWS', postingQuote: 'AWS 경험자 우대' },
];

let host: HTMLDivElement;
let root: Root;

function Opener() {
  const { openWrite } = useWriteDock();
  const target = (id: string) => ({ resumeId: 'r1', tailoredId: id, editId: `r1/tailored/${id}`, title: `${id} 자소서`,
    job: '한국투자증권 디지털', jobId: 'SARAMIN-1', requirements: id !== 'apply_2' ? GIVEN : undefined,
    closed: id === 'apply_3' });
  return (
    <>
      <button type="button" onClick={() => openWrite(target('apply_1'))}>열기1</button>
      <button type="button" onClick={() => openWrite(target('apply_2'))}>열기2</button>
      <button type="button" onClick={() => openWrite(target('apply_3'))}>열기3</button>
    </>
  );
}

beforeEach(() => {
  fake.mounts = 0;
  api.requirements.mockResolvedValue({ requirements: [{ id: 'R9', group: 'task', label: '데이터 분석', posting_quote: '데이터 분석 업무' }] });
  host = document.createElement('div');
  document.body.appendChild(host);
  root = createRoot(host);
  act(() => root.render(<WriteDockHost><Opener /></WriteDockHost>));
});

afterEach(() => {
  act(() => root.unmount());
  host.remove();
  vi.clearAllMocks();
});

const button = (label: string) => [...document.querySelectorAll('button')].find((b) => b.textContent?.includes(label)) as HTMLButtonElement;
const layer = () => document.querySelector('.rv-layer') as HTMLElement | null;
const bar = () => document.querySelector('.aw-dockbar-wrap');
const report = (s: Partial<WritingStatus>) => act(() => fake.report?.({ busy: false, failed: false, label: '', ...s }));

describe('자소서 쓰기 창', () => {
  it('첨삭 창처럼 화면 위에 뜨고, 내려둬도 창을 치우지 않아 쓰는 중인 초안이 끝까지 돈다', () => {
    act(() => button('열기1').click());
    expect(document.querySelector('[role="dialog"]')?.textContent).toContain('apply_1 자소서');
    expect(document.querySelector('.rv-head__job')?.textContent).toBe('한국투자증권 디지털');
    report({ busy: true, label: '2번 문항 쓰는 중' });
    expect(button('').closest('header')).toBeDefined();
    expect((document.querySelector('[aria-label="닫기"]') as HTMLButtonElement).disabled).toBe(true);  // 쓰는 중엔 닫지 않는다

    act(() => button('내려두기').click());
    expect(layer()?.hidden).toBe(true);
    expect(fake.mounts).toBe(1);  // 다시 그리지 않았다 — 요청이 살아 있다
    expect(bar()?.textContent).toContain('자소서 초안 쓰는 중');
    expect(bar()?.textContent).toContain('2번 문항 쓰는 중');

    report({ busy: false });
    expect(bar()?.textContent).toContain('자소서 초안 완료');
    act(() => button('열기').click());
    expect(layer()?.hidden).toBe(false);
    expect(bar()).toBeNull();
  });

  it('실패하면 막대가 알리고, 쓰는 중에는 다른 자소서 창으로 바꾸지 않는다', () => {
    act(() => button('열기1').click());
    report({ busy: true, label: '1번 문항 쓰는 중' });
    act(() => button('열기2').click());
    expect(document.querySelector('[role="dialog"]')?.textContent).toContain('apply_1 자소서');
    expect(document.querySelector('.rv-notice')?.textContent).toContain('쓰는 중인 자소서 창이 있어요');

    act(() => button('내려두기').click());
    report({ busy: false, failed: true });
    expect(bar()?.textContent).toContain('자소서 초안을 쓰지 못했어요');
  });

  it('다 쓴 뒤에는 닫을 수 있고, 다른 자소서를 열면 그 자소서로 바뀐다', () => {
    act(() => button('열기1').click());
    act(() => button('열기2').click());
    expect(document.querySelector('[role="dialog"]')?.textContent).toContain('apply_2 자소서');
    act(() => (document.querySelector('[aria-label="닫기"]') as HTMLButtonElement).click());
    expect(document.querySelector('[role="dialog"]')).toBeNull();
  });
});

describe('쓰기 창의 공고 요건', () => {
  it('자소서를 반복 전환하고 상태를 갱신해도 요건과 문항 영역은 하나씩 유지한다', async () => {
    for (const id of ['열기1', '열기2', '열기1', '열기2', '열기1']) {
      await act(async () => button(id).click());
      expect(host.querySelectorAll('.aw-reqs__toggle')).toHaveLength(1);
      expect(host.querySelector('.aw-body')?.textContent?.match(/문항 카드/g)).toHaveLength(1);
      report({ busy: true, label: '문항 쓰는 중' });
      act(() => button('내려두기').click());
      report({ busy: false });
      act(() => (host.querySelector('.aw-dockbar-wrap') as HTMLElement).click());
      expect(host.querySelectorAll('.aw-reqs__toggle')).toHaveLength(1);
      act(() => button('공고 요건 보기').click());
      expect([...host.querySelectorAll('.aw-req')].map((chip) => chip.textContent))
        .toEqual(id === '열기1' ? ['Python', 'AWS'] : ['데이터 분석']);
    }
  });

  it('접어 두고 필수 · 우대 수를 보이다가, 펼치면 요건과 공고 원문을 보여 준다 — 2단계 요건을 그대로 쓴다', () => {
    act(() => button('열기1').click());
    const toggle = button('공고 요건 보기');
    expect(toggle.textContent).toContain('필수 1 · 우대 1');
    expect(document.querySelector('.aw-req')).toBeNull();
    act(() => toggle.click());
    const chips = [...document.querySelectorAll('.aw-req')];
    expect(chips.map((c) => c.textContent)).toEqual(['Python', 'AWS']);
    expect(chips[0].getAttribute('title')).toBe('공고 원문: Python 활용 능력');
    expect(api.requirements).not.toHaveBeenCalled();
  });

  it('「내 자소서」에서 바로 열어 요건이 아직 없으면 창이 직접 읽는다', async () => {
    act(() => button('열기2').click());
    await act(async () => { await Promise.resolve(); });
    expect(api.requirements).toHaveBeenCalledWith('SARAMIN-1', true); // 이미 만든 자소서 — 마감 공고 요건도 본다
    expect(button('공고 요건 보기').textContent).toContain('주요 업무 1');
    expect(document.querySelector('[role="note"]')).toBeNull(); // 열린 공고는 안내 없음
  });

  it('마감된 공고의 자소서는 창 맨 위에 「미리 사용해 보실 수 있어요」 안내를 띄운다', async () => {
    api.requirements.mockResolvedValueOnce({ job_closed: true, requirements: [{ id: 'R9', group: 'task', label: '데이터 분석', posting_quote: '데이터 분석 업무' }] });
    act(() => button('열기2').click());
    await act(async () => { await Promise.resolve(); });
    const note = document.querySelector('[role="note"]');
    expect(note?.textContent).toContain('마감된 공고입니다');
    expect(note?.textContent).toContain('미리 사용해 보실 수 있어요');
    expect(button('공고 요건 보기').textContent).toContain('주요 업무 1'); // 요건 목록도 함께
    expect(document.body.textContent).not.toContain('공고 요건을 불러오고 있어요');
  });

  it('바탕 이력서를 바꿔 요건을 넘겨받아 연 마감 공고 자소서도 안내를 띄운다', async () => {
    act(() => button('열기3').click());
    await act(async () => { await Promise.resolve(); });
    expect(api.requirements).not.toHaveBeenCalled(); // 요건은 넘겨받았다
    expect(document.querySelector('[role="note"]')?.textContent).toContain('마감된 공고입니다');
  });

  it('요건이 하나도 없는 공고는 칸을 없애지 않고 한 줄로 알린다', async () => {
    api.requirements.mockResolvedValueOnce({ requirements: [] });
    act(() => button('열기2').click());
    await act(async () => { await Promise.resolve(); });
    expect(document.body.textContent).toContain('이 공고는 요건을 글로 적지 않았어요');
  });
});
