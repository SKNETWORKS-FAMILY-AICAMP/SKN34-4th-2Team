import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

// 연습장 본체(파이썬 런타임)는 띄우지 않는다. 어느 세트로 열렸는지만 보인다
vi.mock('../PythonPlaygroundScreen', () => ({
  EmbeddedPlayground: ({ setId, active }: { setId: string | null; active: boolean }) => (
    <div data-testid="pane" data-set={setId ?? 'free'} data-active={String(active)} />
  ),
}));

const { PracticeDockHost, PracticeLink } = await import('../PracticeDock');

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

let root: Root;
let host: HTMLDivElement;

beforeEach(() => {
  host = document.createElement('div');
  document.body.append(host);
  root = createRoot(host);
});

afterEach(() => {
  act(() => root.unmount());
  host.remove();
});

async function render() {
  await act(async () => {
    root.render(
      <MemoryRouter>
        <PracticeDockHost>
          <PracticeLink setId="set-a">A 풀기</PracticeLink>
          <PracticeLink setId="set-b">B 풀기</PracticeLink>
          <PracticeLink setId={null}>연습장 열기</PracticeLink>
          {['c', 'd', 'e'].map((k) => (
            <PracticeLink key={k} setId={`set-${k}`}>
              {k.toUpperCase()} 풀기
            </PracticeLink>
          ))}
        </PracticeDockHost>
      </MemoryRouter>,
    );
  });
  // 창 안의 연습장은 늦게 불러온다(lazy)
  await act(async () => {
    await new Promise((r) => setTimeout(r, 0));
  });
}

const link = (text: string) => [...host.querySelectorAll('a')].find((a) => a.textContent === text)!;
const panes = () => [...host.querySelectorAll<HTMLElement>('[data-testid=pane]')];
const visiblePane = () => panes().find((p) => !p.closest('.pd-pane')!.hasAttribute('hidden'));

async function click(el: Element) {
  await act(async () => {
    el.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, button: 0 }));
    await new Promise((r) => setTimeout(r, 0));
  });
}

describe('복습 · 연습장 창', () => {
  it('링크는 주소를 가진 채로 창을 열고, 여러 개는 탭으로 쌓인다', async () => {
    await render();
    expect(link('A 풀기').getAttribute('href')).toBe('/study-room/playground?set=set-a');
    expect(host.querySelector('.pd-window')).toBeNull();

    await click(link('A 풀기'));
    await click(link('B 풀기'));
    expect(host.querySelectorAll('.pd-tab[role=tab]')).toHaveLength(2);
    expect(panes().map((p) => p.dataset.set)).toEqual(['set-a', 'set-b']);
    expect(visiblePane()?.dataset.set).toBe('set-b');

    // 같은 세트를 다시 누르면 새 탭이 아니라 그 탭으로 간다
    await click(link('A 풀기'));
    expect(host.querySelectorAll('.pd-tab[role=tab]')).toHaveLength(2);
    expect(visiblePane()?.dataset.set).toBe('set-a');
  });

  it('내려놓으면 창은 남아 있고 아래 막대에 몇 개가 열려 있는지 보인다', async () => {
    await render();
    await click(link('A 풀기'));
    await click(link('연습장 열기'));
    await click(host.querySelector('[aria-label=내려놓기]')!);

    expect(host.querySelector('.rv-layer')?.hasAttribute('hidden')).toBe(true);
    expect(panes()).toHaveLength(2); // 치우지 않는다 — 풀던 상태가 남는다
    expect(panes().every((p) => p.dataset.active === 'false')).toBe(true);
    const bar = host.querySelector('.pd-dockbar')!;
    expect(bar.textContent).toContain('복습 · 연습장 2개');
    expect(document.body.classList.contains('pd-docked')).toBe(true);

    await click(bar);
    expect(host.querySelector('.rv-layer')?.hasAttribute('hidden')).toBe(false);
    expect(host.querySelector('.pd-dockbar')).toBeNull();
  });

  it('탭을 닫으면 옆 탭으로, 다 닫으면 창이 사라진다', async () => {
    await render();
    await click(link('A 풀기'));
    await click(link('B 풀기'));
    await click(host.querySelectorAll('[aria-label="탭 닫기"]')[1]);
    expect(visiblePane()?.dataset.set).toBe('set-a');
    await click(host.querySelector('[aria-label="모두 닫기"]')!);
    expect(host.querySelector('.pd-window')).toBeNull();
  });

  it('탭은 4개까지 — 넘치면 가장 먼저 연 탭을 닫고 알린다', async () => {
    await render();
    for (const name of ['A 풀기', 'B 풀기', 'C 풀기', 'D 풀기', 'E 풀기']) await click(link(name));
    expect(panes().map((p) => p.dataset.set)).toEqual(['set-b', 'set-c', 'set-d', 'set-e']);
    expect(host.textContent).toContain('4개까지');
  });

  it('Ctrl · 가운데 버튼은 창을 열지 않고 브라우저에 맡긴다', async () => {
    await render();
    await act(async () => {
      link('A 풀기').dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, button: 0, ctrlKey: true }));
    });
    expect(host.querySelector('.pd-window')).toBeNull();
  });
});
