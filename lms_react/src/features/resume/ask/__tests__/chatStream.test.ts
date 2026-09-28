import { describe, expect, it } from 'vitest';

import { parseEvents } from '../chatStream';

describe('스트림 줄 읽기', () => {
  it('빈 줄로 나뉜 블록을 이벤트로 읽고, 덜 온 블록은 남겨 둔다', () => {
    const { events, rest } = parseEvents(
      'data: {"event":"progress","label":"공고를 찾는 중…"}\n\ndata: {"event":"text","delta":"안녕"}\n\ndata: {"event":"do',
    );
    expect(events).toEqual([
      { event: 'progress', label: '공고를 찾는 중…' },
      { event: 'text', delta: '안녕' },
    ]);
    expect(rest).toBe('data: {"event":"do');
  });

  it('윈도 줄바꿈과 깨진 줄을 견딘다', () => {
    const { events } = parseEvents('data: {"event":"text","delta":"a"}\r\n\r\ndata: {깨짐}\n\ndata: {"event":"done","result":{}}\n\n');
    expect(events.map((e) => e.event)).toEqual(['text', 'done']);
  });
});
