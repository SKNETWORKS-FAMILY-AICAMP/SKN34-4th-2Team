import { afterEach, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({ post: vi.fn() }));
vi.mock('axios', () => ({
  default: {
    create: () => ({
      post: mocks.post,
      interceptors: { request: { use: vi.fn() }, response: { use: vi.fn() } },
    }),
  },
}));

import { refreshAccess } from './http';
import { useSessionStore } from './sessionStore';

function deferred() {
  let resolve!: (value: { data: { access: string; refresh: string } }) => void;
  const promise = new Promise<{ data: { access: string; refresh: string } }>((done) => { resolve = done; });
  return { promise, resolve };
}

afterEach(() => {
  useSessionStore.getState().clear();
  mocks.post.mockReset();
});

it('does not resurrect tokens when logout occurs during refresh', async () => {
  const pending = deferred();
  mocks.post.mockReturnValue(pending.promise);
  useSessionStore.getState().setTokens('old-access', 'old-refresh');
  const flight = refreshAccess();
  useSessionStore.getState().clear();
  pending.resolve({ data: { access: 'late-access', refresh: 'late-refresh' } });
  await expect(flight).rejects.toThrow('stale refresh response');
  expect(useSessionStore.getState().refresh).toBeNull();
});

it('does not let an old refresh replace a newly logged-in session', async () => {
  const pending = deferred();
  mocks.post.mockReturnValue(pending.promise);
  useSessionStore.getState().setTokens('old-access', 'old-refresh');
  const flight = refreshAccess();
  useSessionStore.getState().setTokens('new-access', 'new-refresh');
  pending.resolve({ data: { access: 'late-access', refresh: 'late-refresh' } });
  await expect(flight).rejects.toThrow('stale refresh response');
  expect(useSessionStore.getState().refresh).toBe('new-refresh');
  expect(useSessionStore.getState().access).toBe('new-access');
});

it('coalesces simultaneous refresh requests in one session', async () => {
  const pending = deferred();
  mocks.post.mockReturnValue(pending.promise);
  useSessionStore.getState().setTokens('old-access', 'old-refresh');
  const first = refreshAccess();
  const second = refreshAccess();
  pending.resolve({ data: { access: 'rotated-access', refresh: 'rotated-refresh' } });
  expect(await first).toBe('rotated-access');
  expect(await second).toBe('rotated-access');
  expect(mocks.post).toHaveBeenCalledTimes(1);
  expect(useSessionStore.getState().refresh).toBe('rotated-refresh');
});
