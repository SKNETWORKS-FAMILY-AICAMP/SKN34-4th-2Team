/**
 * 표 데이터 모양과 CSV 변환 — 외부 라이브러리 · 브라우저 API 없이 쓴다.
 * 모바일(`@web/*`)에서도 가져오므로 무거운 의존성을 여기에 넣지 않는다.
 */
export interface ExportTable {
  /** 문서 제목. 시트 이름 · Word/PDF 머리글에 쓴다. */
  title: string;
  header: string[];
  rows: string[][];
}

function csvCell(value: string): string {
  return /[",\n\r]/.test(value) ? `"${value.replace(/"/g, '""')}"` : value;
}

/** 엑셀에서 바로 열리게 BOM 을 붙인다 */
export function toCsv(table: ExportTable): string {
  return `\uFEFF${[table.header, ...table.rows].map((r) => r.map(csvCell).join(',')).join('\r\n')}`;
}
