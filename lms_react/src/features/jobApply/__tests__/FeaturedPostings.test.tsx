import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const http = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock('../../../data/http', () => ({ http }));

const { FeaturedPostings, ddayOf } = await import('../FeaturedPostings');

const card = (over: Record<string, unknown> = {}) => ({
  job_id: 'SARAMIN-1',
  company: 'CJ',
  title: '2026 CJ그룹 신입사원 모집',
  tier: '대기업',
  deadline: '2026-10-05',
  season: '2026 하반기',
  career_type: 'ENTRY',
  posting_count: 1,
  skills: ['Java'],
  open_hiring: true,
  homepage: true,
  logo_url: null,
  closed: false,
  ...over,
});

const page = (items: unknown[]) => ({ data: { items, total: items.length, counts: { '인기 기업': 0, 대기업: items.length, 외국계: 0 } } });

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

const flush = () => act(async () => {
  await new Promise((resolve) => setTimeout(resolve, 0));
});

describe('마감 표시', () => {
  const today = new Date(2026, 8, 30);

  it('오늘 · 이틀 안 · 그 뒤 · 상시 · 지난 공채', () => {
    expect(ddayOf('2026-09-30', today)).toEqual({ label: '오늘마감', tone: 'today' });
    expect(ddayOf('2026-10-02', today)).toEqual({ label: 'D-2', tone: 'soon' });
    expect(ddayOf('2026-10-11', today)).toEqual({ label: 'D-11', tone: 'later' });
    expect(ddayOf(null, today)).toEqual({ label: '상시', tone: 'rolling' });
    expect(ddayOf('2026-09-15', today, true)).toEqual({ label: '9/15 마감', tone: 'closed' });
  });
});

describe('주요 기업 카드', () => {
  it('카드를 누르면 그 공고로 연다 — 시즌 · 홈페이지 지원을 보여 준다', async () => {
    http.get.mockResolvedValue(page([card()]));
    const onPick = vi.fn();
    act(() => root.render(<FeaturedPostings onPick={onPick} />));
    await flush();

    expect(http.get).toHaveBeenCalledWith('/featured-postings', { params: { view: 'live', tier: '', offset: 0, limit: 12 } });
    expect(host.textContent).toContain('2026 하반기');
    expect(host.textContent).toContain('공채 · 홈페이지 지원');
    act(() => (host.querySelector('.featured-card') as HTMLButtonElement).click());
    expect(onPick).toHaveBeenCalledWith('SARAMIN-1');
  });

  it('홈페이지 지원 여부를 모르면 「공채」만 붙인다', async () => {
    http.get.mockResolvedValue(page([card({ homepage: null })]));
    act(() => root.render(<FeaturedPostings onPick={vi.fn()} />));
    await flush();
    expect(host.textContent).not.toContain('홈페이지 지원');
    expect(host.textContent).toContain('공채');
  });

  it('지난 공채 탭은 past 로 다시 부르고 마감일을 보여 준다', async () => {
    http.get.mockResolvedValue(page([card()]));
    act(() => root.render(<FeaturedPostings onPick={vi.fn()} />));
    await flush();

    http.get.mockResolvedValue(page([card({ closed: true, deadline: '2026-09-15', job_id: 'SARAMIN-2' })]));
    const past = [...host.querySelectorAll('[role="tab"]')].find((b) => b.textContent === '지난 공채') as HTMLButtonElement;
    act(() => past.click());
    await flush();

    expect(http.get).toHaveBeenLastCalledWith('/featured-postings', { params: { view: 'past', tier: '', offset: 0, limit: 12 } });
    expect(host.textContent).toContain('9/15 마감');
    expect(host.querySelector('.featured-card')?.classList.contains('is-closed')).toBe(true);
  });
});
