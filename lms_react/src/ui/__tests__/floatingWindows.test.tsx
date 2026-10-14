import { act, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { describe, expect, it } from 'vitest';

import { useYieldToOtherWindows } from '../floatingWindows';

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

let expand: Record<string, () => void> = {};

function FakeWindow({ who }: { who: string }) {
  const [expanded, setExpanded] = useState(false);
  expand[who] = () => setExpanded(true);
  useYieldToOtherWindows(who, expanded, () => setExpanded(false));
  return <span data-who={who}>{expanded ? '펼침' : '내림'}</span>;
}

describe('화면 위 창끼리 비켜 서기', () => {
  it('한 창이 펼쳐지면 펼쳐져 있던 다른 창은 내려간다', () => {
    expand = {};
    const host = document.createElement('div');
    const root = createRoot(host);
    act(() =>
      root.render(
        <>
          <FakeWindow who="review" />
          <FakeWindow who="practice" />
        </>,
      ),
    );
    const state = (who: string) => host.querySelector(`[data-who=${who}]`)!.textContent;

    act(() => expand.review());
    expect(state('review')).toBe('펼침');

    act(() => expand.practice());
    expect(state('practice')).toBe('펼침');
    expect(state('review')).toBe('내림');

    act(() => expand.review());
    expect(state('review')).toBe('펼침');
    expect(state('practice')).toBe('내림');
    act(() => root.unmount());
  });
});
