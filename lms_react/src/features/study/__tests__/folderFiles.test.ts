import { describe, expect, it } from 'vitest';

import { blobId, isHiddenPath, isLessonFile, notebookCells, readPicked, uploadRow } from '../folderFiles';

const bytes = (...parts: (string | number[])[]) => {
  const chunks = parts.map((p) => (typeof p === 'string' ? new TextEncoder().encode(p) : new Uint8Array(p)));
  const all = new Uint8Array(chunks.reduce((n, c) => n + c.length, 0));
  let at = 0;
  for (const c of chunks) {
    all.set(c, at);
    at += c.length;
  }
  return all;
};

// 기댓값은 서버(study_notes/upload_plan.py 의 file_row)로 계산한 값 — 브라우저와 서버의 지문 · 글이 같아야 「같은 파일」을 가른다.
// 실제 34기 수업 파일 190개(python_basic · 34기_수업자료)도 서버와 하나도 다르지 않은 것을 확인했다(10/3).
describe('폴더 올리기 — 브라우저에서 읽은 목록이 서버 계산과 같다', () => {
  it('지문은 git blob id — CRLF 그대로, 한글은 UTF-8 바이트로', async () => {
    const row = await uploadRow('crlf.py', bytes("x = 1\r\nprint('한글')\r\n"), 0);
    expect(row.blob).toBe('f03f70bb2e70887514e4c6d164300ad8156ae138');
    expect(row.size).toBe(24);
    expect(row.head).toBe("x = 1\r\nprint('한글')\r\n");
  });

  it('빈 파일도 git 과 같은 지문', async () => {
    // git hash-object /dev/null
    expect(await blobId(new Uint8Array())).toBe('e69de29bb2d1d6434b8b29ae775ad8c2e48c5391');
  });

  it('앞부분은 8000 「글자」 — 이모지를 둘로 세지 않는다(파이썬과 같게)', async () => {
    const row = await uploadRow('emoji.md', bytes('😀'.repeat(8001)), 0);
    expect(row.blob).toBe('cb4129277dca27b1ff534403072c4d9f7e69a526');
    expect(row.size).toBe(32004);
    expect(Array.from(row.head ?? '')).toHaveLength(8000);
  });

  it('깨진 UTF-8 은 바꿈 글자로 — 지문은 원래 바이트로', async () => {
    const row = await uploadRow('broken.py', bytes('ok', [0xff, 0xfe], 'end'), 0);
    expect(row.blob).toBe('61c1c16bc34dd1ba7b05bbfd19e9fab1d2d38afb');
    expect(row.head).toBe('ok��end');
  });

  it('노트북은 셀만 — 실행 결과 · 셀이 아닌 것은 빼고, 셀 글은 2000 글자까지', () => {
    const cells = notebookCells(
      JSON.stringify({
        cells: [
          { cell_type: 'markdown', source: ['# 제목\n', '2026-09-23 수업'] },
          { cell_type: 'code', source: 'print(1)', outputs: [{ text: '1' }] },
          'not a cell',
          { source: null },
          { cell_type: 'code', source: ['😀'.repeat(2001)] },
        ],
      }),
    );
    expect(cells.map((c) => [c.type, Array.from(c.source).length])).toEqual([
      ['markdown', 18],
      ['code', 8],
      ['code', 0],
      ['code', 2000],
    ]);
    expect(cells[0].source).toBe('# 제목\n2026-09-23 수업');
  });

  it('읽을 수 없는 노트북은 셀 없음', async () => {
    const row = await uploadRow('bad.ipynb', bytes('{not json'), 0);
    expect(row.blob).toBe('74d7b706e672ee213cad5ba50840b65a7a488adb');
    expect(row.cells).toEqual([]);
    expect(row.head).toBeUndefined();
  });
});

describe('어떤 파일을 읽나', () => {
  it('수업 파일만, 숨김 폴더 · 체크포인트는 빼고', () => {
    expect(isLessonFile('01_variable/exercise.ipynb')).toBe(true);
    expect(isLessonFile('data/sample.csv')).toBe(false);
    expect(isHiddenPath('04_function/.ipynb_checkpoints/exercise-checkpoint.ipynb')).toBe(true);
    expect(isHiddenPath('app/__pycache__/views.py')).toBe(true);
    expect(isHiddenPath('01_variable/a.py')).toBe(false);
  });

  it('고른 폴더를 읽고 건너뛴 이유를 남긴다', async () => {
    const file = (path: string, body: string, size?: number) => {
      const f = new File([body], path.split('/').pop() ?? path, { lastModified: 1_750_000_000_000 });
      Object.defineProperty(f, 'webkitRelativePath', { value: path });
      if (size) Object.defineProperty(f, 'size', { value: size });
      return f;
    };
    const seen: number[] = [];
    const picked = await readPicked(
      [
        file('python_basic/01_variable/a.py', 'x = 1'),
        file('python_basic/data/sample.csv', 'a,b'),
        file('python_basic/.ipynb_checkpoints/a-checkpoint.ipynb', '{}'),
        file('python_basic/big.ipynb', '{}', 6 * 1024 * 1024),
      ],
      (done) => seen.push(done),
    );
    expect(picked.map((p) => [p.path, p.skipped ?? 'read'])).toEqual([
      ['python_basic/01_variable/a.py', 'read'],
      ['python_basic/data/sample.csv', 'not-lesson'],
      ['python_basic/.ipynb_checkpoints/a-checkpoint.ipynb', 'hidden'],
      ['python_basic/big.ipynb', 'too-big'],
    ]);
    expect(picked[0].row).toMatchObject({ path: 'python_basic/01_variable/a.py', size: 5, mtime: 1_750_000_000_000 });
    expect(seen).toEqual([1]);
  });
});
