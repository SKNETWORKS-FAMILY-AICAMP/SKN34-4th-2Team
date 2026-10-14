/**
 * 폴더 올리기 — 고른 파일을 브라우저 안에서 읽어 「계획」에 보낼 목록을 만든다(내용은 아직 안 보낸다).
 *
 * 서버(study_notes/upload_plan.py 의 file_row · UpFile)와 똑같이 계산해야 한다.
 * - 내용 지문: git 의 blob id = sha1("blob <바이트 수>\0" + 내용). 지난번과 같은 파일을 올리기 전에 가른다.
 * - 노트북(.ipynb): 셀마다 {type, source} — 실행 결과는 빼고, 셀 글은 2000자 · 셀은 400개까지.
 * - 그 밖: 앞부분 8000자(날짜 · 키워드를 찾는 데만 쓴다).
 * 글자 수는 파이썬처럼 코드 포인트로 센다(JS 문자열 길이는 이모지를 둘로 센다).
 */

export const LESSON_SUFFIXES = ['.ipynb', '.py', '.md', '.sql', '.html', '.css', '.js'] as const;
export const MAX_FILE_BYTES = 5 * 1024 * 1024;
export const MAX_HEAD = 8_000;
export const MAX_CELLS = 400;
export const MAX_CELL_TEXT = 2_000;
const READ_AT_ONCE = 8;

export interface NotebookCell {
  type: string;
  source: string;
}

/** 계획 요청의 파일 한 줄 */
export interface UploadRow {
  path: string;
  blob: string;
  size: number;
  mtime: number;
  head?: string;
  cells?: NotebookCell[];
}

export type SkipReason = 'not-lesson' | 'too-big' | 'hidden';

/** 고른 파일 하나 — 올릴 때 다시 읽도록 File 을 들고 있는다 */
export interface PickedFile {
  path: string;
  file: File;
  row: UploadRow | null;
  skipped?: SkipReason;
}

export function isLessonFile(path: string): boolean {
  const lower = path.toLowerCase();
  return LESSON_SUFFIXES.some((s) => lower.endsWith(s));
}

/** .git · .DS_Store · __pycache__ · .ipynb_checkpoints 처럼 숨김 폴더 · 파일은 수업 자료가 아니다 */
export function isHiddenPath(path: string): boolean {
  // .github 은 수업 자료다 — 협업 수업(workflow)이 이슈 · PR 템플릿을 .github/ISSUE_TEMPLATE 에 둔다(서버 is_hidden 과 같다)
  return path.split('/').some((part) => (part.startsWith('.') && part !== '.github') || part === '__pycache__' || part === 'node_modules');
}

function firstChars(text: string, n: number): string {
  // 코드 포인트 기준 — 파이썬 text[:n] 과 같게
  let count = 0;
  let end = 0;
  for (const ch of text) {
    if (count === n) break;
    count += 1;
    end += ch.length;
  }
  return text.slice(0, end);
}

function hex(buffer: ArrayBuffer): string {
  return Array.from(new Uint8Array(buffer), (b) => b.toString(16).padStart(2, '0')).join('');
}

/** git 의 내용 지문(blob id) */
export async function blobId(bytes: Uint8Array): Promise<string> {
  const header = new TextEncoder().encode(`blob ${bytes.length}\0`);
  const all = new Uint8Array(header.length + bytes.length);
  all.set(header);
  all.set(bytes, header.length);
  return hex(await crypto.subtle.digest('SHA-1', all));
}

/** 노트북 → 셀(실행 결과 뺌). 읽을 수 없으면 빈 목록 */
export function notebookCells(text: string): NotebookCell[] {
  let data: unknown;
  try {
    data = JSON.parse(text);
  } catch {
    return [];
  }
  const cells = data && typeof data === 'object' ? (data as { cells?: unknown }).cells : null;
  if (!Array.isArray(cells)) return [];
  return cells
    .slice(0, MAX_CELLS)
    .filter((c): c is Record<string, unknown> => !!c && typeof c === 'object' && !Array.isArray(c))
    .map((c) => {
      const raw = c.source;
      const source = Array.isArray(raw) ? raw.map(String).join('') : raw == null ? '' : String(raw);
      return { type: typeof c.cell_type === 'string' && c.cell_type ? c.cell_type : 'code', source: firstChars(source, MAX_CELL_TEXT) };
    });
}

/** 파일 내용 → 계획 요청 한 줄(서버 file_row 와 같다) */
export async function uploadRow(path: string, bytes: Uint8Array, mtime: number): Promise<UploadRow> {
  const text = new TextDecoder('utf-8').decode(bytes);
  const row: UploadRow = { path, blob: await blobId(bytes), size: bytes.length, mtime };
  if (path.toLowerCase().endsWith('.ipynb')) row.cells = notebookCells(text);
  else row.head = firstChars(text, MAX_HEAD);
  return row;
}

/** 파일 내용 — 브라우저는 file.arrayBuffer(), 그게 없는 곳(시험의 jsdom)은 FileReader */
export async function readBytes(file: Blob): Promise<Uint8Array> {
  if (typeof file.arrayBuffer === 'function') return new Uint8Array(await file.arrayBuffer());
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(new Uint8Array(reader.result as ArrayBuffer));
    reader.onerror = () => reject(reader.error);
    reader.readAsArrayBuffer(file);
  });
}

/**
 * 노트북의 앞 셀 upto 개만 — 두 날에 나눌 때 앞 날짜 몫. 셀 번호는 notebookCells 와 같게 센다(셀이 아닌 항목은 빼고).
 * 뒤 날짜엔 원래 파일을 통째로 올리므로, 노트 · 출제는 그날 새로 생긴 셀만 그날 수업으로 본다.
 */
export function partialNotebook(text: string, upto: number): string {
  const data = JSON.parse(text) as { cells?: unknown };
  const cells = Array.isArray(data.cells) ? data.cells.filter((c) => !!c && typeof c === 'object' && !Array.isArray(c)) : [];
  return `${JSON.stringify({ ...data, cells: cells.slice(0, upto) }, null, 1)}\n`;
}

export async function partialNotebookFile(file: File, upto: number): Promise<File> {
  const text = new TextDecoder('utf-8').decode(await readBytes(file));
  return new File([partialNotebook(text, upto)], file.name, { type: 'application/x-ipynb+json', lastModified: file.lastModified });
}

/** 파일 고르기(폴더면 webkitRelativePath)의 경로 — 윈도 \ 를 / 로 */
export function pickedPath(file: File): string {
  const rel = (file as File & { webkitRelativePath?: string }).webkitRelativePath || file.name;
  return rel.replace(/\\/g, '/').replace(/^\/+/, '');
}

/**
 * 고른 파일을 읽는다. 수업 파일이 아니거나(데이터 · 그림 · 숨김) 5MB 를 넘으면 읽지 않고 이유만 남긴다.
 * 한꺼번에 읽으면 메모리가 튀어 READ_AT_ONCE 개씩 읽는다.
 */
export async function readPicked(files: File[], onProgress?: (done: number, total: number) => void): Promise<PickedFile[]> {
  const out: PickedFile[] = files.map((file) => {
    const path = pickedPath(file);
    if (isHiddenPath(path)) return { path, file, row: null, skipped: 'hidden' };
    if (!isLessonFile(path)) return { path, file, row: null, skipped: 'not-lesson' };
    if (file.size > MAX_FILE_BYTES) return { path, file, row: null, skipped: 'too-big' };
    return { path, file, row: null };
  });
  const todo = out.filter((p) => !p.skipped);
  let done = 0;
  for (let i = 0; i < todo.length; i += READ_AT_ONCE) {
    await Promise.all(
      todo.slice(i, i + READ_AT_ONCE).map(async (p) => {
        p.row = await uploadRow(p.path, await readBytes(p.file), p.file.lastModified);
        done += 1;
        onProgress?.(done, todo.length);
      }),
    );
  }
  return out;
}
