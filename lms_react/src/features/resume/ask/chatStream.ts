import { API_BASE } from '../../../data/http';
import { useSessionStore } from '../../../data/sessionStore';

/**
 * 코치에게 묻기 — 답을 만드는 동안 흘려받는다(`/api/jobs/chat/stream`).
 *
 * 서버가 보내는 줄은 넷이다(job_matching_bot `chat_stream`).
 *   progress — 지금 하는 일("조건에 맞는 공고를 찾는 중…")
 *   text     — 답 글 조각. 질문 · 공고 · 비교 답만 온다. 공고 검색 답은 정해진 틀이라 없다
 *   done     — `/jobs/chat` 응답 그대로
 *   error    — 실패
 *
 * 스트림을 열지 못하면(로그인 만료 · 옛 서버 · 프록시) `StreamUnavailable`을 던진다.
 * 부르는 쪽은 그때 `/jobs/chat`으로 물러난다 — 그쪽은 토큰 갱신까지 axios 가 해 준다.
 */

export class StreamUnavailable extends Error {}

/** 스트림 도중 서버가 알린 실패. 물러나지 않고 그 말을 보여 준다 */
export class StreamFailed extends Error {}

export interface StreamHandlers {
  onProgress(label: string): void;
  onText(delta: string): void;
}

interface StreamEvent {
  event?: string;
  label?: string;
  delta?: string;
  detail?: string;
  result?: unknown;
}

/** `data: {...}` 블록을 이벤트로. 블록 사이는 빈 줄 하나다 */
export function parseEvents(buffer: string): { events: StreamEvent[]; rest: string } {
  const blocks = buffer.split(/\r?\n\r?\n/);
  const rest = blocks.pop() ?? '';
  const events: StreamEvent[] = [];
  for (const block of blocks) {
    const data = block
      .split(/\r?\n/)
      .filter((line) => line.startsWith('data:'))
      .map((line) => line.slice(5).trimStart())
      .join('\n');
    if (data === '') continue;
    try {
      events.push(JSON.parse(data) as StreamEvent);
    } catch {
      // 깨진 줄 하나 때문에 답 전체를 버리지 않는다
    }
  }
  return { events, rest };
}

export async function streamChat<T>(body: unknown, handlers: StreamHandlers): Promise<T> {
  const access = useSessionStore.getState().access;
  let response: Response;
  try {
    response = await fetch(`${API_BASE}/jobs/chat/stream`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'text/event-stream',
        ...(access ? { Authorization: `Bearer ${access}` } : {}),
      },
      body: JSON.stringify(body),
    });
  } catch {
    throw new StreamUnavailable('stream fetch failed');
  }
  const type = response.headers.get('content-type') ?? '';
  if (!response.ok || !type.includes('text/event-stream') || response.body === null) {
    throw new StreamUnavailable(`stream not available: ${response.status}`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  for (;;) {
    const { value, done } = await reader.read();
    buffer += decoder.decode(value, { stream: !done });
    const { events, rest } = parseEvents(done ? `${buffer}\n\n` : buffer);
    buffer = rest;
    for (const e of events) {
      if (e.event === 'progress' && e.label) handlers.onProgress(e.label);
      else if (e.event === 'text' && e.delta) handlers.onText(e.delta);
      else if (e.event === 'done') return e.result as T;
      else if (e.event === 'error') throw new StreamFailed(e.detail ?? '답을 찾지 못했습니다. 잠시 후 다시 물어봐 주세요.');
    }
    if (done) break;
  }
  // 결과 없이 끊겼다. 답을 모르므로 물러나 다시 묻는다
  throw new StreamUnavailable('stream ended without a result');
}
