import { act } from 'react';
import { createRoot } from 'react-dom/client';
import { MemoryRouter } from 'react-router-dom';
import { expect, it, vi } from 'vitest';
import type { Resume } from '../../../domain/types';

const repo = vi.hoisted(() => ({
  useMyResumes: vi.fn(), deleteResume: vi.fn(), createResume: vi.fn(), setBaseResume: vi.fn(),
}));
vi.mock('../../../data/repository', () => repo);
vi.mock('../../auth/session', () => ({ useCurrentUser: () => ({ uid: 'test', displayName: 'Test' }) }));
const { ResumeScreen } = await import('../ResumeScreens');

it('opens the tailored deletion menu and confirmation without deleting', () => {
  repo.useMyResumes.mockReturnValue({ loading: false, error: null, data: [
    { id: 'base', title: 'Base', status: 'draft', isBaseResume: true, sections: {}, content: {}, feedbackCount: 0 },
    { id: 'base/tailored/copy', baseResumeId: 'base', title: 'Tailored', status: 'draft', isBaseResume: false, sections: {}, content: {}, feedbackCount: 0 },
  ] as Resume[] });
  const host = document.createElement('div');
  document.body.appendChild(host);
  const root = createRoot(host);
  try {
    act(() => root.render(<MemoryRouter><ResumeScreen /></MemoryRouter>));
    const trigger = host.querySelector('button[aria-label="Tailored 더보기"]') as HTMLButtonElement;
    expect(trigger).not.toBeNull();
    act(() => trigger.click());
    expect(trigger.getAttribute('aria-expanded')).toBe('true');
    const item = host.querySelector('[role="menuitem"]') as HTMLButtonElement;
    expect(item.textContent).toContain('삭제');
    act(() => item.click());
    expect(document.body.textContent).toContain('삭제할까요?');
    expect(repo.deleteResume).not.toHaveBeenCalled();
  } finally {
    act(() => root.unmount());
    host.remove();
    vi.clearAllMocks();
  }
});
