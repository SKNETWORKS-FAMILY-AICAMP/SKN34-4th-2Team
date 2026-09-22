import { describe, expect, it } from 'vitest';

import type { PracticeSet } from '../../../domain/types';
import { newCell, type Cell } from '../notebookModel';
import { NotebookFileError, parseIpynb, parseNotebookFile, parsePy, toIpynb, toPy } from '../notebookFile';

const set: PracticeSet = {
  id: 'ps-x', cohortId: 'c', sourceTitle: 'repo', lessonDate: '2026-09-15', dayLabel: '15일차', title: 'BLIP', files: [], model: '',
  problems: [
    { kind: 'code_write', topic: '프레임', prompt: '`f(x)` 를 만드세요', sourceFiles: [], explanation: '', choices: [], answerIndex: 0,
      starterCode: 'def f(x):\n    pass', expectedStdout: '', blankAnswers: [], referenceSolution: 'SECRET_SOLUTION', hiddenTests: 'assert f(1) == 2  # SECRET_TEST', packages: [] },
  ],
};

function withOutput(c: Cell, patch: Partial<Cell>): Cell {
  return { ...c, ...patch };
}

describe('노트북 내보내기', () => {
  it('.ipynb — 코드·마크다운·출력, 문제 셀은 설명 + 내 코드로 풀고 숨긴 테스트는 뺀다', () => {
    const cells = [
      newCell('# 제목', 'markdown'),
      withOutput(newCell('print(1)\n2'), { count: 3, lines: [{ kind: 'out', text: '1' }, { kind: 'sys', text: '(무시)' }], value: '2' }),
      withOutput(newCell('plot()'), { images: ['data:image/png;base64,AAAA'] }),
      newCell('def f(x):\n    return x + 1', 'problem', 0),
    ];
    const text = toIpynb(cells, set);
    const nb = JSON.parse(text);
    expect(nb.nbformat).toBe(4);
    expect(nb.cells.map((c: { cell_type: string }) => c.cell_type)).toEqual(['markdown', 'code', 'code', 'markdown', 'code']);
    expect(nb.cells[1].source).toEqual(['print(1)\n', '2']);
    expect(nb.cells[1].execution_count).toBe(3);
    expect(nb.cells[1].outputs).toEqual([
      { output_type: 'stream', name: 'stdout', text: ['1\n'] },
      { output_type: 'execute_result', execution_count: 3, data: { 'text/plain': ['2'] }, metadata: {} },
    ]);
    expect(nb.cells[2].outputs[0].data['image/png']).toBe('AAAA');
    expect(nb.cells[3].source.join('')).toContain('문제 1 · 함수 작성 · 프레임');
    expect(nb.cells[4].source.join('')).toContain('return x + 1');
    expect(text).not.toContain('SECRET');
  });

  it('.py — # %% 로 셀을 가르고 마크다운은 주석으로', () => {
    const text = toPy([newCell('# 제목\n\n본문', 'markdown'), newCell('x = 1\n\n\n')], undefined);
    expect(text).toBe('# %% [markdown]\n# # 제목\n#\n# 본문\n\n# %%\nx = 1\n');
  });
});

describe('노트북 불러오기', () => {
  it('.ipynb — 줄 배열·문자열 source 모두, 매직은 주석으로, 출력은 버린다', () => {
    const nb = parseIpynb(
      JSON.stringify({
        nbformat: 4,
        cells: [
          { cell_type: 'markdown', source: ['# 수업\n', '설명'] },
          { cell_type: 'code', source: '!pip install torch\n%matplotlib inline\nimport numpy as np', outputs: [{ output_type: 'stream', text: 'x' }] },
          { cell_type: 'raw', source: 'raw' },
        ],
      }),
    );
    expect(nb.cells[0]).toEqual({ type: 'markdown', source: '# 수업\n설명' });
    expect(nb.cells[1].source).toBe('# (연습장에서는 못 씀) !pip install torch\n# (연습장에서는 못 씀) %matplotlib inline\nimport numpy as np');
    expect(nb.cells[2].type).toBe('markdown');
    expect(nb.notes.join(' ')).toContain('2개');
  });

  it('내보낸 걸 다시 불러오면 같은 셀이 된다', () => {
    const cells = [newCell('## 노트', 'markdown'), newCell('a = [1, 2]\nprint(a)')];
    const back = parseIpynb(toIpynb(cells, undefined)).cells;
    expect(back).toEqual([{ type: 'markdown', source: '## 노트' }, { type: 'code', source: 'a = [1, 2]\nprint(a)' }]);
    expect(parsePy(toPy(cells, undefined)).cells).toEqual(back);
  });

  it('.py — 표시가 없으면 통째로 한 셀, 첫 표시 앞 줄도 받는다', () => {
    expect(parsePy('import os\r\nprint(1)\r\n').cells).toEqual([{ type: 'code', source: 'import os\nprint(1)' }]);
    expect(parsePy('import os\n# %%\nx = 1\n# %% [markdown]\n# 글').cells).toEqual([
      { type: 'code', source: 'import os' },
      { type: 'code', source: 'x = 1' },
      { type: 'markdown', source: '글' },
    ]);
  });

  it('깨진 파일 · 옛 형식 · 다른 확장자는 알아듣게 막는다', () => {
    expect(() => parseIpynb('{nope')).toThrow(NotebookFileError);
    expect(() => parseIpynb(JSON.stringify({ nbformat: 3, worksheets: [] }))).toThrow(/nbformat 3/);
    expect(() => parseIpynb(JSON.stringify({ nbformat: 4, cells: [] }))).toThrow(/셀이 없/);
    expect(() => parseNotebookFile('a.txt', '')).toThrow(/\.ipynb/);
  });
});
