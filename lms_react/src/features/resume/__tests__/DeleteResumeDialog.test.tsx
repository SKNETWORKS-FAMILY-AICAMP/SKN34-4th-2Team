import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { Resume } from '../../../domain/types';

const repo = vi.hoisted(() => ({ deleteResume: vi.fn() }));
vi.mock('../../../data/repository', () => repo);

const { DeleteResumeDialog } = await import('../DeleteResumeDialog');

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

const copy = { id: 'r1/tailored/apply_1', title: '(주)넥스트그라운드 맞춤 이력서' } as Resume;
const button = (label: string) =>
  [...document.querySelectorAll('button')].find((b) => b.textContent?.trim() === label) as HTMLButtonElement;

describe('공고용 사본 삭제 확인', () => {
  it('취소하면 지우지 않고, 삭제를 눌러야 지운다', () => {
    const onClose = vi.fn();
    const onDeleted = vi.fn();
    act(() => root.render(<DeleteResumeDialog resume={copy} title="(주)넥스트그라운드 자소서" onClose={onClose} onDeleted={onDeleted} />));
    expect(document.body.textContent).toContain('「(주)넥스트그라운드 자소서」을 삭제할까요?');

    act(() => button('취소').click());
    expect(repo.deleteResume).not.toHaveBeenCalled();
    expect(onClose).toHaveBeenCalledTimes(1);

    act(() => button('삭제').click());
    expect(repo.deleteResume).toHaveBeenCalledWith('r1/tailored/apply_1');
    expect(onDeleted).toHaveBeenCalledTimes(1);
  });
});
