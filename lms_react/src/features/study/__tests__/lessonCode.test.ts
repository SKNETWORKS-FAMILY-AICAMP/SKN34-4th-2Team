import { describe, expect, it } from 'vitest';

import { findCodeInFiles, isSqlBlock, lessonCells, lessonSlice, significantLines } from '../lessonCode';

const code = (source: string) => ({ type: 'code' as const, source });

describe('노트 코드가 어느 수업 파일 · 셀에서 왔나', () => {
  const lesson = [
    code('from transformers import BlipProcessor'),
    code("processor = BlipProcessor.from_pretrained('Salesforce/blip-image-captioning-base')"),
    code("print('done')"),
  ];

  it('줄을 나누거나 띄어쓰기를 바꿔도 같은 코드로 보고, 그 셀을 가리킨다', () => {
    const note = "processor = BlipProcessor.from_pretrained(\n    'Salesforce/blip-image-captioning-base'\n)";
    const match = findCodeInFiles(note, [{ path: 'b.py', cells: [code('x = 1')] }, { path: 'a.py', cells: lesson }]);
    expect(match).toMatchObject({ path: 'a.py', cellIndex: 1 });
  });

  it('노트가 새로 쓴 코드면 찾지 못한다', () => {
    expect(findCodeInFiles("model.fit(train, epochs=99)\nmodel.save('mine.h5')", [{ path: 'a.py', cells: lesson }])).toBeNull();
  });

  it('흐름도 · 주석 · 설명 글 · 짧은 줄은 견주지 않는다', () => {
    expect(significantLines('입력 이미지\n→ Convolution\n# 설명\nx = 1\nprint(processor)')).toEqual(['print(processor)']);
    // 구조도는 코드가 아니라 버튼도 달지 않는다
    expect(significantLines('입력: 1 × 28 × 28\n→ Conv1: 64 × 28 × 28\nLinear: 100')).toEqual([]);
  });

  it('노트북은 셀 글자로 견준다(JSON 따옴표에 막히지 않게)', () => {
    const ipynb = JSON.stringify({ cells: [{ cell_type: 'code', source: ['print("hello world")\n'] }], metadata: {}, nbformat: 4 });
    const cells = lessonCells('a.ipynb', ipynb);
    expect(findCodeInFiles('print("hello world")', [{ path: 'a.ipynb', cells }])?.cellIndex).toBe(0);
  });

  it('파일을 통째로 가져오지 않고 그 셀 앞 두 셀 · 뒤 한 셀만', () => {
    const many = Array.from({ length: 10 }, (_, i) => code(`x${i} = ${i}`));
    expect(lessonSlice(many, 5)).toMatchObject({ from: 4, to: 7 });
    expect(lessonSlice(many, 5).cells.map((c) => c.source)).toEqual(['x3 = 3', 'x4 = 4', 'x5 = 5', 'x6 = 6']);
    expect(lessonSlice(many, 0)).toMatchObject({ from: 1, to: 2 });
  });
});

describe('노트의 SQL 코드 블록', () => {
  it('```sql 이거나 언어 표시 없이 SQL 문장으로 시작하면 SQL', () => {
    expect(isSqlBlock('select 1', 'sql')).toBe(true);
    expect(isSqlBlock('-- 메뉴 조회\nSELECT menu_name FROM tbl_menu', '')).toBe(true);
    expect(isSqlBlock('SELECT = 1', 'python')).toBe(false);
    expect(isSqlBlock('print(1)', '')).toBe(false);
  });

  it('SQL 은 괄호 없는 줄도 견주고 대소문자를 가리지 않는다 · .sql 파일은 SQL 셀', () => {
    const cells = lessonCells('2일차/2_11 join.sql', 'select\n\ta.menu_name,\n\tb.category_name\nfrom\n\ttbl_menu a');
    expect(cells[0].type).toBe('sql');
    expect(findCodeInFiles('SELECT a.menu_name, b.category_name\nFROM tbl_menu a', [{ path: 'join.sql', cells }], true)?.path).toBe('join.sql');
  });
});
