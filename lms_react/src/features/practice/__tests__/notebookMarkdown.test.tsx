import { act } from 'react';
import { createRoot } from 'react-dom/client';
import { describe, expect, it } from 'vitest';

import { NotebookMarkdown, parseBlocks } from '../NotebookMarkdown';

function render(source: string): HTMLDivElement {
  const host = document.createElement('div');
  act(() => createRoot(host).render(<NotebookMarkdown source={source} />));
  return host;
}

describe('노트북 마크다운', () => {
  it('제목·목록·인용·코드 블록을 나눈다', () => {
    const blocks = parseBlocks(
      ['## 오늘 정리', '- 첫째', '- 둘째', '', '> 메모', '```python', 'x = 1', '```', '1. 하나', '2. 둘'].join('\n'),
    );
    expect(blocks.map((b) => b.kind)).toEqual(['heading', 'list', 'quote', 'code', 'list']);
    expect(blocks[3]).toEqual({ kind: 'code', lang: 'python', text: 'x = 1' });
    expect(blocks[4]).toMatchObject({ ordered: true, items: ['하나', '둘'] });
  });

  it('이어진 줄은 한 문단으로 붙인다', () => {
    expect(parseBlocks('첫 줄\n둘째 줄\n\n새 문단')).toEqual([
      { kind: 'para', lines: ['첫 줄', '둘째 줄'] },
      { kind: 'para', lines: ['새 문단'] },
    ]);
  });

  it('인라인 코드·굵게·링크를 그린다', () => {
    const host = render('`re.search`는 **처음 하나**만 찾는다. [문서](https://docs.python.org)');
    expect(host.querySelector('code')?.textContent).toBe('re.search');
    expect(host.querySelector('strong')?.textContent).toBe('처음 하나');
    expect(host.querySelector('a')?.getAttribute('href')).toBe('https://docs.python.org');
  });

  it('태그는 글자로 두고, http 가 아닌 링크는 걸지 않는다', () => {
    const host = render('<img src=x onerror=alert(1)> [눌러](javascript:alert(1))');
    expect(host.querySelector('img')).toBeNull();
    expect(host.querySelector('a')).toBeNull();
    expect(host.textContent).toContain('<img src=x onerror=alert(1)>');
  });
});
