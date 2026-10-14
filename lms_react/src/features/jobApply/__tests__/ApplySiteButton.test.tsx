import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const http = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock('../../../data/http', () => ({ http }));

const { ApplySiteButton } = await import('../ApplySiteButton');

let host: HTMLDivElement;
let root: Root;
let tab: { opener: unknown; location: { href: string } };

beforeEach(() => {
  host = document.createElement('div');
  document.body.appendChild(host);
  root = createRoot(host);
  tab = { opener: window, location: { href: '' } };
  vi.spyOn(window, 'open').mockReturnValue(tab as unknown as Window);
});

afterEach(() => {
  act(() => root.unmount());
  host.remove();
  vi.restoreAllMocks();
  vi.clearAllMocks();
});

const flush = () => act(async () => {
  await new Promise((resolve) => setTimeout(resolve, 0));
});

const click = () => act(() => (host.querySelector('button') as HTMLButtonElement).click());

describe('회사 채용 사이트 열기', () => {
  it('누르자마자 빈 탭을 열고, 찾은 회사 주소로 옮긴다', async () => {
    http.get.mockResolvedValue({ data: { url: 'https://job.shinsegae.com/rcrut/detail/5365', precise: true } });
    act(() => root.render(<ApplySiteButton jobId="SARAMIN-1" fallbackUrl="https://www.saramin.co.kr/x" />));
    click();

    expect(window.open).toHaveBeenCalledWith('', '_blank');
    await flush();
    expect(http.get).toHaveBeenCalledWith('/postings/SARAMIN-1/apply-link');
    expect(tab.location.href).toBe('https://job.shinsegae.com/rcrut/detail/5365');
    expect(tab.opener).toBeNull();
    expect(host.textContent).not.toContain('첫 화면');
  });

  it('사람인 주소면 채용 사이트 첫 화면일 수 있다고 알린다', async () => {
    http.get.mockResolvedValue({ data: { url: 'https://recruit.cj.net/', precise: false } });
    act(() => root.render(<ApplySiteButton jobId="SARAMIN-1" fallbackUrl="https://www.saramin.co.kr/x" />));
    click();
    await flush();
    expect(tab.location.href).toBe('https://recruit.cj.net/');
    expect(host.textContent).toContain('첫 화면');
  });

  it('onNote 를 주면 안내를 버튼 밑에 두지 않고 부모에게 넘긴다', async () => {
    http.get.mockResolvedValue({ data: { url: 'https://recruit.cj.net/', precise: false } });
    const onNote = vi.fn();
    act(() => root.render(<ApplySiteButton jobId="SARAMIN-1" fallbackUrl="https://www.saramin.co.kr/x" onNote={onNote} />));
    click();
    await flush();
    expect(onNote).toHaveBeenLastCalledWith(expect.stringContaining('첫 화면'));
    expect(host.textContent).not.toContain('첫 화면');
  });

  it('못 찾거나 실패하면 공고 원문을 연다', async () => {
    http.get.mockResolvedValue({ data: { url: null, precise: false } });
    act(() => root.render(<ApplySiteButton jobId="SARAMIN-1" fallbackUrl="https://www.saramin.co.kr/x" />));
    click();
    await flush();
    expect(tab.location.href).toBe('https://www.saramin.co.kr/x');
    expect(host.textContent).toContain('홈페이지 지원');

    http.get.mockRejectedValue(new Error('down'));
    tab.location.href = '';
    click();
    await flush();
    expect(tab.location.href).toBe('https://www.saramin.co.kr/x');
  });
});
