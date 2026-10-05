/**
 * 관리자 화면의 표 내려받기 — CSV · Excel · Word · PDF
 *
 * 화면마다 표를 `ExportTable` 하나로 만들고, 형식은 여기서 고른다.
 * Excel · Word 라이브러리는 무거워서 고를 때 불러온다.
 */
export interface ExportTable {
  /** 문서 제목. 시트 이름 · Word/PDF 머리글에 쓴다. */
  title: string;
  header: string[];
  rows: string[][];
}

export type ExportFormat = 'csv' | 'xlsx' | 'docx' | 'pdf';

export const ExportFormatLabels: Record<ExportFormat, string> = {
  csv: 'CSV',
  xlsx: 'Excel (.xlsx)',
  docx: 'Word (.docx)',
  pdf: 'PDF',
};

function csvCell(value: string): string {
  return /[",\n\r]/.test(value) ? `"${value.replace(/"/g, '""')}"` : value;
}

/** 엑셀에서 바로 열리게 BOM 을 붙인다 */
export function toCsv(table: ExportTable): string {
  return `\uFEFF${[table.header, ...table.rows].map((r) => r.map(csvCell).join(',')).join('\r\n')}`;
}

/** 파일 이름에 못 쓰는 글자를 `_` 로 바꾼다 */
export function safeFileName(name: string): string {
  return name.replace(/[\\/:*?"<>|]/g, '_').trim() || '내보내기';
}

export function downloadBlob(filename: string, blob: Blob): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 0);
}

/** 한글처럼 넓은 글자는 두 칸으로 센다 */
function displayWidth(text: string): number {
  let w = 0;
  for (const ch of text) w += /[\u1100-\u11ff\u3000-\u9fff\uac00-\ud7af\uff00-\uffef]/.test(ch) ? 2 : 1;
  return w;
}

function columnWidths(table: ExportTable): number[] {
  return table.header.map((h, i) => {
    const longest = Math.max(
      displayWidth(h),
      ...table.rows.map((r) => Math.max(0, ...(r[i] ?? '').split('\n').map(displayWidth))),
    );
    return Math.min(60, Math.max(8, longest + 2));
  });
}

async function toXlsx(table: ExportTable): Promise<Blob> {
  const { default: ExcelJS } = await import('exceljs');
  const book = new ExcelJS.Workbook();
  // 시트 이름은 31자까지, 일부 기호는 못 쓴다
  const sheet = book.addWorksheet(table.title.replace(/[\\/?*[\]:]/g, ' ').slice(0, 31) || 'Sheet1', {
    views: [{ state: 'frozen', ySplit: 1 }],
  });
  sheet.addRow(table.header);
  table.rows.forEach((r) => sheet.addRow(r));
  columnWidths(table).forEach((w, i) => {
    sheet.getColumn(i + 1).width = w;
  });
  const head = sheet.getRow(1);
  head.font = { bold: true };
  head.alignment = { vertical: 'middle' };
  head.eachCell((cell) => {
    cell.fill = { type: 'pattern', pattern: 'solid', fgColor: { argb: 'FFEEF2F7' } };
  });
  sheet.eachRow((row, n) => {
    if (n > 1) row.alignment = { vertical: 'top', wrapText: true };
  });
  if (table.header.length > 0) {
    sheet.autoFilter = { from: { row: 1, column: 1 }, to: { row: 1, column: table.header.length } };
  }
  const buffer = await book.xlsx.writeBuffer();
  return new Blob([buffer], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' });
}

function today(): string {
  return new Date().toLocaleDateString('sv-SE', { timeZone: 'Asia/Seoul' });
}

/** 열이 많으면 가로로 둔다 */
function isWide(table: ExportTable): boolean {
  return table.header.length > 6;
}

async function toDocx(table: ExportTable): Promise<Blob> {
  const { AlignmentType, Document, Packer, PageOrientation, Paragraph, ShadingType, Table, TableCell, TableRow, TextRun, WidthType } =
    await import('docx');
  const cell = (text: string, head: boolean) =>
    new TableCell({
      shading: head ? { type: ShadingType.CLEAR, color: 'auto', fill: 'EEF2F7' } : undefined,
      margins: { top: 40, bottom: 40, left: 80, right: 80 },
      children: text.split('\n').map((line) => new Paragraph({ children: [new TextRun({ text: line, bold: head })] })),
    });
  const doc = new Document({
    creator: 'LMS',
    title: table.title,
    styles: { default: { document: { run: { font: '맑은 고딕', size: 18 } } } },
    sections: [
      {
        properties: {
          page: {
            size: { orientation: isWide(table) ? PageOrientation.LANDSCAPE : PageOrientation.PORTRAIT },
            margin: { top: 720, bottom: 720, left: 720, right: 720 },
          },
        },
        children: [
          new Paragraph({ children: [new TextRun({ text: table.title, bold: true, size: 28 })] }),
          new Paragraph({
            alignment: AlignmentType.RIGHT,
            spacing: { after: 160 },
            children: [new TextRun({ text: `${today()} · ${table.rows.length}건`, color: '666666' })],
          }),
          new Table({
            width: { size: 100, type: WidthType.PERCENTAGE },
            rows: [
              new TableRow({ tableHeader: true, children: table.header.map((h) => cell(h, true)) }),
              ...table.rows.map((r) => new TableRow({ children: table.header.map((_, i) => cell(r[i] ?? '', false)) })),
            ],
          }),
        ],
      },
    ],
  });
  return Packer.toBlob(doc);
}

function escapeHtml(text: string): string {
  return text.replace(/[&<>"']/g, (ch) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[ch] ?? ch);
}

export function tableToPrintHtml(table: ExportTable, docTitle: string): string {
  const row = (cells: string[], tag: 'th' | 'td') =>
    `<tr>${table.header.map((_, i) => `<${tag}>${escapeHtml(cells[i] ?? '')}</${tag}>`).join('')}</tr>`;
  return `<!doctype html><html lang="ko"><head><meta charset="utf-8"><title>${escapeHtml(docTitle)}</title><style>
@page { size: A4 ${isWide(table) ? 'landscape' : 'portrait'}; margin: 12mm; }
body { font-family: 'Malgun Gothic', 'Apple SD Gothic Neo', sans-serif; font-size: 9pt; color: #111; margin: 0; }
h1 { font-size: 14pt; margin: 0 0 2mm; }
.meta { color: #666; text-align: right; margin: 0 0 3mm; }
table { width: 100%; border-collapse: collapse; }
thead { display: table-header-group; }
tr { break-inside: avoid; }
th, td { border: 1px solid #bbb; padding: 1.2mm 1.6mm; text-align: left; vertical-align: top; white-space: pre-wrap; word-break: break-word; }
th { background: #eef2f7; -webkit-print-color-adjust: exact; print-color-adjust: exact; }
</style></head><body>
<h1>${escapeHtml(table.title)}</h1>
<p class="meta">${today()} · ${table.rows.length}건</p>
<table><thead>${row(table.header, 'th')}</thead><tbody>${table.rows.map((r) => row(r, 'td')).join('')}</tbody></table>
</body></html>`;
}

/**
 * 숨은 iframe 에 표만 그려 인쇄 창을 연다. 「PDF로 저장」을 고르면 PDF 가 된다.
 * 앱의 인쇄 CSS(이력서용)와 섞이지 않게 따로 띄운다.
 */
function printTable(table: ExportTable, docTitle: string): Promise<void> {
  return new Promise((resolve, reject) => {
    const frame = document.createElement('iframe');
    frame.setAttribute('aria-hidden', 'true');
    frame.style.cssText = 'position:fixed;right:0;bottom:0;width:0;height:0;border:0;visibility:hidden;';
    frame.onload = () => {
      const win = frame.contentWindow;
      if (!win) {
        frame.remove();
        reject(new Error('인쇄 창을 열지 못했습니다.'));
        return;
      }
      const cleanup = () => setTimeout(() => frame.remove(), 500);
      win.addEventListener('afterprint', cleanup, { once: true });
      win.focus();
      win.print();
      resolve();
    };
    frame.srcdoc = tableToPrintHtml(table, docTitle);
    document.body.appendChild(frame);
  });
}

/** `baseName` 은 확장자 없는 파일 이름 */
export async function exportTable(table: ExportTable, baseName: string, format: ExportFormat): Promise<void> {
  const name = safeFileName(baseName);
  switch (format) {
    case 'csv':
      downloadBlob(`${name}.csv`, new Blob([toCsv(table)], { type: 'text/csv;charset=utf-8' }));
      return;
    case 'xlsx':
      downloadBlob(`${name}.xlsx`, await toXlsx(table));
      return;
    case 'docx':
      downloadBlob(`${name}.docx`, await toDocx(table));
      return;
    case 'pdf':
      await printTable(table, name);
  }
}
