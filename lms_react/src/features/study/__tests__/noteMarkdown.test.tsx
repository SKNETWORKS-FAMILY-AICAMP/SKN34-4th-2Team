import { act } from 'react';
import { createRoot } from 'react-dom/client';
import { describe, expect, it } from 'vitest';

import { boldLinesAsHeadings, Markdown } from '../StudyRoomScreen';

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

describe('노트 표시', () => {
  it('굵은 줄 하나짜리 소제목은 소제목으로, 문장 안의 굵게는 그대로', () => {
    expect(boldLinesAsHeadings('**오늘의 핵심 한 문장**\n본문\n\n**전체 수업 흐름**:\n문장 안의 **굵게**')).toBe(
      '## 오늘의 핵심 한 문장\n본문\n\n## 전체 수업 흐름\n문장 안의 **굵게**',
    );
  });

  it('굵게 · 인라인 코드 · 코드 블록이 기호째 보이지 않는다', () => {
    const host = document.createElement('div');
    const root = createRoot(host);
    act(() =>
      root.render(
        <Markdown text={'**파일별 학습 내용**\n- `02_video.ipynb` 에서 **프레임**을 뽑는다\n\n```python\nprint(1)\n```'} />,
      ),
    );
    expect(host.querySelector('h3')?.textContent).toBe('파일별 학습 내용');
    expect(host.querySelector('li code')?.textContent).toBe('02_video.ipynb');
    expect(host.querySelector('li strong')?.textContent).toBe('프레임');
    expect(host.querySelector('pre code')?.textContent).toBe('print(1)');
    expect(host.textContent).not.toContain('**');
    expect(host.textContent).not.toContain('`');
    act(() => root.unmount());
  });
});

describe('번호 목록 사이에 하위 목록이 끼면', () => {
  it('번호가 1로 되돌아가지 않고, 하위 목록은 들여 보인다', () => {
    const host = document.createElement('div');
    const root = createRoot(host);
    act(() => root.render(<Markdown text={'1. CNN 기본 원리\n   - 필터\n   - 풀링\n2. FashionMNIST\n   - 정규화'} />));
    const lists = host.querySelectorAll('ol');
    expect(lists[1].getAttribute('start')).toBe('2');
    expect(host.querySelector('ul')?.className).toBe('nb-md__nested');
    act(() => root.unmount());
  });
});
