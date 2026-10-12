import { act } from 'react';
import { createRoot } from 'react-dom/client';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';

const { session, post } = vi.hoisted(() => ({
  session: { user: { uid: 'user-a', role: 'student', cohortId: 'cohort_34' } }, post: vi.fn(),
}));
vi.mock('../auth/session', () => ({ useSession: () => session }));
vi.mock('../../data/http', () => ({ API_BASE: '/api', http: { post } }));
vi.mock('../../data/sessionStore', () => ({ useSessionStore: { getState: () => ({ access: 'synthetic' }) } }));
const { ChatbotHost, OPEN_CHATBOT_EVENT } = await import('./ChatbotHost');
let root: ReturnType<typeof createRoot>;
let host: HTMLDivElement;
const originalScrollTo = Object.getOwnPropertyDescriptor(HTMLElement.prototype, 'scrollTo');

beforeEach(() => {
  Object.defineProperty(HTMLElement.prototype, 'scrollTo', { configurable: true, value: vi.fn() });
  vi.stubEnv('MODE', 'production');
  session.user = { uid: 'user-a', role: 'student', cohortId: 'cohort_34' };
  host = document.createElement('div'); document.body.appendChild(host);
  root = createRoot(host);
  act(() => root.render(<ChatbotHost />));
});
afterEach(() => {
  act(() => root.unmount()); host.remove();
  vi.unstubAllGlobals(); vi.unstubAllEnvs(); vi.clearAllMocks();
  if (originalScrollTo) Object.defineProperty(HTMLElement.prototype, 'scrollTo', originalScrollTo);
  else Reflect.deleteProperty(HTMLElement.prototype, 'scrollTo');
});

function reply(text: string) {
  return {
    ok: true, headers: { get: () => 'application/x-ndjson' },
    body: { getReader: () => ({ read: async () => ({ done: false, value: new TextEncoder().encode(
      JSON.stringify({ type: 'token', content: text }) + '\n' + JSON.stringify({ type: 'done' }) + '\n') }) }) },
  };
}
function send(text: string) {
  act(() => window.dispatchEvent(new Event(OPEN_CHATBOT_EVENT)));
  const input = host.querySelector('input')!;
  act(() => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(input, text);
    input.dispatchEvent(new Event('input', { bubbles: true }));
  });
  act(() => host.querySelector('form')!.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true })));
}

it('sends one conversation ID and retains it when the panel is closed and reopened', async () => {
  const fetch = vi.fn().mockResolvedValue(reply('합성 응답'));
  vi.stubGlobal('fetch', fetch);
  send('이번 단위기간 출석 어때?');
  await act(async () => {});
  const first = JSON.parse(fetch.mock.calls[0][1].body);
  expect(first.threadId).toMatch(/^[A-Za-z0-9._-]{1,80}$/);
  act(() => host.querySelector<HTMLButtonElement>('button[aria-label="챗봇 닫기"]')!.click());
  send('앞으로 며칠 더 출석해야 해?');
  await act(async () => {});
  expect(JSON.parse(fetch.mock.calls[1][1].body).threadId).toBe(first.threadId);
});

it('rotates identity, aborts old work, and never appends a late reply to another user', async () => {
  let resolve!: (value: ReturnType<typeof reply>) => void;
  const fetch = vi.fn().mockImplementationOnce(() => new Promise((done) => { resolve = done; }))
    .mockResolvedValue(reply('새 사용자 응답'));
  vi.stubGlobal('fetch', fetch);
  send('기존 사용자 질문');
  const old = JSON.parse(fetch.mock.calls[0][1].body).threadId;
  const signal = fetch.mock.calls[0][1].signal as AbortSignal;
  session.user = { uid: 'user-b', role: 'student', cohortId: 'cohort_40' };
  act(() => root.render(<ChatbotHost />));
  expect(signal.aborted).toBe(true);
  await act(async () => { resolve(reply('이전 사용자 늦은 응답')); });
  expect(host.textContent).not.toContain('이전 사용자 늦은 응답');
  expect(host.textContent).not.toContain('기존 사용자 질문');
  send('새 사용자 질문');
  await act(async () => {});
  expect(JSON.parse(fetch.mock.calls[1][1].body).threadId).not.toBe(old);
  expect(post).not.toHaveBeenCalled();
});
