import { describe, expect, it, vi } from 'vitest';

import { exportTable, safeFileName, tableToPrintHtml, toCsv } from './tableExport';

const table = { title: '출결 신청', header: ['이름', '사유'], rows: [['홍길동', '버스, "고장"\n둘째 줄'], ['<b>x</b>', '']] };

function readBytes(blob: Blob): Promise<Uint8Array> {
  return new Promise((ok) => {
    const r = new FileReader();
    r.onload = () => ok(new Uint8Array(r.result as ArrayBuffer));
    r.readAsArrayBuffer(blob);
  });
}

describe('표 내려받기', () => {
  it('CSV 는 BOM 을 붙이고 쉼표 · 따옴표 · 줄바꿈 칸을 감싼다', () => {
    const csv = toCsv(table);
    expect(csv.startsWith('\uFEFF이름,사유\r\n')).toBe(true);
    expect(csv).toContain('"버스, ""고장""\n둘째 줄"');
  });

  it('PDF 용 인쇄 문서는 HTML 을 이스케이프한다', () => {
    expect(tableToPrintHtml(table, 't')).toContain('&lt;b&gt;x&lt;/b&gt;');
  });

  it('파일 이름에 못 쓰는 글자를 바꾼다', () => {
    expect(safeFileName('출결/신청:1')).toBe('출결_신청_1');
  });

  it('Excel · Word 는 zip(OOXML) 파일로 만든다', async () => {
    const blobs: Blob[] = [];
    URL.createObjectURL = vi.fn((b: Blob) => {
      blobs.push(b);
      return 'blob:x';
    }) as never;
    URL.revokeObjectURL = vi.fn();
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
    await exportTable(table, '출결 신청', 'xlsx');
    await exportTable(table, '출결 신청', 'docx');
    expect(blobs).toHaveLength(2);
    for (const b of blobs) {
      const head = (await readBytes(b)).slice(0, 2);
      expect(String.fromCharCode(...head)).toBe('PK');
    }
  }, 120_000);
});
