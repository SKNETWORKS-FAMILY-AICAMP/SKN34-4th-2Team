import { parseNotebookFile, type ImportedCell } from '../practice/notebookFile';

/**
 * 노트의 코드 블록이 어느 수업 파일 · 셀에서 왔는지 찾는다 — 「수업 파일에서 보기」.
 *
 * 노트는 수업 코드를 옮기면서 모양을 바꾼다. 한 줄 호출을 여러 줄로 나누고(`from_pretrained(` / `'...'`),
 * 공백을 고친다. 그래서 줄을 그대로 견주지 않고 **공백을 모두 뺀 글자**로 견준다. 설명용 흐름도
 * (`→ Convolution`)나 주석, 너무 짧은 줄은 세지 않는다.
 */

/** 공백을 모두 뺀 글자 — 줄바꿈 · 들여쓰기 · 띄어쓰기가 달라도 같은 코드로 본다 */
export function compact(text: string): string {
  return text.replace(/\s+/g, '');
}

/** 코드처럼 생긴 줄 — 대입 · 호출 · 괄호 · 파이썬 예약어. 「입력: 1 × 28 × 28」 같은 설명용 구조도는 아니다 */
const CODE_LIKE = /[=(){}[\]]|^(import|from|def|class|return|for|if|elif|else|while|with|try|except|print|lambda|yield|async|await)\b/;

/** 견줄 만한 줄 — 주석 · 흐름도 · 설명 글 · 너무 짧은 줄은 뺀다 */
export function significantLines(code: string): string[] {
  const lines = code.split('\n').map((line) => line.trim());
  return lines.filter(
    (line) => line !== '' && !line.startsWith('#') && !/^[→↓>\-*]/.test(line) && compact(line).length >= 6 && CODE_LIKE.test(line),
  );
}

/** 수업 파일을 셀로 — 노트북 · .py 는 셀마다, 그 밖(.md 등)은 글 셀 하나 */
export function lessonCells(path: string, raw: string): ImportedCell[] {
  if (!/\.(ipynb|py)$/i.test(path)) return [{ type: 'markdown', source: raw }];
  try {
    return parseNotebookFile(path, raw).cells;
  } catch {
    return [{ type: 'code', source: raw }];
  }
}

export interface LessonFile {
  path: string;
  cells: ImportedCell[];
}

export interface CodeMatch {
  path: string;
  /** 코드가 처음 나오는 셀 */
  cellIndex: number;
  /** 견줄 만한 줄 중 수업 파일에 있는 비율 */
  ratio: number;
}

/**
 * 코드 블록이 가장 많이 들어 있는 파일과 셀. 견줄 만한 줄의 절반 넘게 있어야 그 파일로 본다 —
 * 아니면 null(노트가 설명하려고 새로 쓴 코드).
 */
export function findCodeInFiles(code: string, files: LessonFile[]): CodeMatch | null {
  const lines = significantLines(code).map(compact);
  if (lines.length === 0) return null;
  let best: CodeMatch | null = null;
  for (const file of files) {
    const cells = file.cells.map((c) => compact(c.source));
    const haystack = cells.join('');
    const hits = lines.filter((line) => haystack.includes(line));
    const ratio = hits.length / lines.length;
    if (hits.length === 0 || (best !== null && ratio <= best.ratio)) continue;
    const cellIndex = cells.findIndex((c) => c.includes(hits[0]));
    best = { path: file.path, cellIndex: Math.max(0, cellIndex), ratio };
  }
  return best !== null && best.ratio >= 0.5 ? best : null;
}

/** 수업 파일에서 가져올 셀 — 그 셀과 앞 두 셀(변수 · import) · 뒤 한 셀. 파일을 통째로 열면 너무 길다 */
export function lessonSlice(cells: ImportedCell[], index: number): { cells: ImportedCell[]; from: number; to: number } {
  const from = Math.max(0, index - 2);
  const to = Math.min(cells.length - 1, index + 1);
  return { cells: cells.slice(from, to + 1), from: from + 1, to: to + 1 };
}
