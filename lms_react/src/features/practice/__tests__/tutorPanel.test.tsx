import { act } from 'react';
import { createRoot } from 'react-dom/client';
import { describe, expect, it } from 'vitest';

import { TutorProvider, useTutor, useTutorMarks, type TutorTarget } from '../TutorContext';
import { TutorPanel } from '../TutorPanel';

const PROBLEM: TutorTarget = {
  cellId: 'p1',
  mode: 'problem',
  setId: 'ps-1',
  index: 0,
  label: '문제 1 · 맥스 풀링',
  read: () => ({ code: 'def f(w):\n    return min(w)', run: '', grade: '실패 · 테스트 1번이 맞지 않아요' }),
};

/** 문제 셀 자리 — 튜터를 열고, 튜터가 가리킨 줄을 보여 준다 */
function Opener({ target }: { target: TutorTarget }) {
  const tutor = useTutor();
  const marks = useTutorMarks(target.cellId);
  return (
    <>
      <button type="button" data-testid="open" onClick={() => tutor?.open(target)} />
      <output data-testid="marks">{(marks ?? []).join(',')}</output>
    </>
  );
}

function mount(target: TutorTarget) {
  const host = document.createElement('div');
  document.body.appendChild(host);
  act(() =>
    createRoot(host).render(
      <TutorProvider>
        <Opener target={target} />
        <TutorPanel />
      </TutorProvider>,
    ),
  );
  return host;
}

async function click(el: Element | null | undefined) {
  await act(async () => {
    (el as HTMLElement).click();
    await new Promise((r) => setTimeout(r, 600)); // 데모 답은 0.5초 뒤에 온다
  });
}

const byText = (host: HTMLElement, text: string) => [...host.querySelectorAll('button')].find((b) => b.textContent?.includes(text));

describe('연습장 튜터', () => {
  it('누르기 전엔 없고, 문제 셀에서 열면 힌트 단계가 「힌트 더」로만 오른다', async () => {
    const host = mount(PROBLEM);
    expect(host.querySelector('.tutor')).toBeNull();

    await click(host.querySelector('[data-testid="open"]'));
    expect(host.querySelector('.tutor__target')?.textContent).toContain('문제 1 · 맥스 풀링');
    expect(host.querySelectorAll('.tutor__ladder .on')).toHaveLength(0);

    await click(byText(host, '힌트 더 (1/3)'));
    await click(byText(host, '힌트 더 (2/3)'));
    expect(host.querySelectorAll('.tutor__ladder .on')).toHaveLength(2);
    expect(host.querySelector('.tutor__msg--bot:last-child')?.textContent).toContain('힌트 2단계');
    // 2단계 힌트는 줄을 가리킨다 — 그 셀 편집기에 칠한다
    expect(host.querySelector('[data-testid="marks"]')?.textContent).toBe('2');

    await click(byText(host, '정답 알려 줘'));
    expect(host.querySelector('.tutor__msg--muted')?.textContent).toContain('모범답안 보기');
    expect(host.querySelectorAll('.tutor__ladder .on')).toHaveLength(2);
  });

  it('일반 셀은 힌트 단계 없이 오류 설명 칩을 보인다', async () => {
    const host = mount({ cellId: 'c1', mode: 'cell', label: '셀 2', read: () => ({ code: 'print(x)', run: "NameError: name 'x' is not defined", grade: '' }) });
    await click(host.querySelector('[data-testid="open"]'));
    expect(host.querySelector('.tutor__ladder')).toBeNull();
    await click(byText(host, '이 오류 설명'));
    expect(host.querySelector('.tutor__msg--bot')?.textContent).toContain('NameError');
  });
});
