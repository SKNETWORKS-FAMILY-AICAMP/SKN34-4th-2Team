import type { PracticeSet } from '../../domain/types';
import type { TableData } from './pythonProtocol';
import { FIRST_CELLS } from './notebookExamples';
import { RETRY_SET_ID } from './review';

/**
 * 연습장 노트북의 셀 — 모양, 새 셀, 세트로 채우기, 저장·불러오기.
 * 화면과 실행기에는 기대지 않는다.
 */

/**
 * 셀 내용만 이 브라우저에 임시로 둔다(학생 계정과 무관). 서버 저장은 DB를 붙일 때 이 자리를 바꾼다.
 * v1 은 코드 문자열 배열이었다.
 */
const STORE_KEY = 'lxp.pythonNotebook.v2';
const OLD_STORE_KEY = 'lxp.pythonNotebook.v1';
/** problem — 복습 세트의 문제 셀. 학생이 새로 만들 수는 없고 세트를 열면 채워진다 */
export type CellType = 'code' | 'markdown' | 'problem';

export type LineKind = 'out' | 'sys' | 'err';
export interface Line {
  kind: LineKind;
  text: string;
}
export type CellState = 'idle' | 'queued' | 'running' | 'ok' | 'error';
export interface Cell {
  id: string;
  type: CellType;
  code: string;
  /** 마크다운 셀이 편집 중인지 */
  editing: boolean;
  lines: Line[];
  value: string | null;
  table: TableData | null;
  images: string[];
  count: number | null;
  state: CellState;
  ms: number | null;
  /** 문제 셀이면 세트 안 몇 번째 문제인지 */
  problemIndex: number | null;
}

let cellSeq = 0;
export function newCell(code = '', type: CellType = 'code', problemIndex: number | null = null): Cell {
  cellSeq += 1;
  return {
    id: `c${Date.now().toString(36)}${cellSeq}`,
    type,
    code,
    problemIndex,
    editing: type === 'markdown' && code.trim() === '',
    lines: [],
    value: null,
    table: null,
    images: [],
    count: null,
    state: 'idle',
    ms: null,
  };
}

export const CLEAR_OUTPUT = { lines: [], value: null, table: null, images: [], count: null, state: 'idle' as CellState, ms: null };

/** 세트를 처음 열 때의 셀 — 안내 · 문제 셀들 · 자유 셀 */
export function cellsForSet(set: PracticeSet): Cell[] {
  if (set.id === RETRY_SET_ID) {
    return [
      newCell(
        '지난 복습에서 틀렸던 문제를 모았습니다. 문제 머리에 원래 수업 날짜가 적혀 있어요. ' +
          '막히면 그날 공부방 노트를 다시 보고 오세요.',
        'markdown',
      ),
      ...set.problems.map((p, i) => newCell(p.starterCode, 'problem', i)),
      newCell('# 자유롭게 시험해 보는 칸\n'),
    ];
  }
  return [
    newCell(
      `${set.lessonDate} 수업 저장소(\`${set.sourceTitle}\`)의 파일 ${set.files.length}개로 만든 문제입니다. ` +
        '문제 셀에서 **실행**하면 그 코드가 이 노트북에 남아 아래 셀에서 불러 쓸 수 있고, ' +
        '**채점**은 숨긴 테스트와 함께 새 공간에서 따로 돌립니다.',
      'markdown',
    ),
    ...set.problems.map((p, i) => newCell(p.starterCode, 'problem', i)),
    newCell('# 자유롭게 시험해 보는 칸 — 위 문제 셀에서 실행한 함수를 불러 써 보세요\n'),
  ];
}

export function storeKey(set: PracticeSet | undefined): string {
  return set ? `${STORE_KEY}:${set.id}` : STORE_KEY;
}

export function loadNotebook(set: PracticeSet | undefined): { cells: Cell[]; stdin: string } {
  try {
    // 다시 풀 문제는 열 때마다 목록이 달라서 저장본을 쓰지 않는다
    if (set?.id === RETRY_SET_ID) return { cells: cellsForSet(set), stdin: '' };
    const raw = window.localStorage.getItem(storeKey(set));
    if (raw) {
      const saved = JSON.parse(raw) as {
        cells?: { type?: CellType; source?: string; problemIndex?: number | null }[];
        stdin?: string;
      };
      if (Array.isArray(saved.cells) && saved.cells.length) {
        return {
          cells: saved.cells
            .filter((c) => c.type !== 'problem' || (set && c.problemIndex != null && set.problems[c.problemIndex]))
            .map((c) =>
              c.type === 'problem'
                ? newCell(String(c.source ?? ''), 'problem', c.problemIndex ?? 0)
                : newCell(String(c.source ?? ''), c.type === 'markdown' ? 'markdown' : 'code'),
            ),
          stdin: saved.stdin ?? '',
        };
      }
    }
    if (set) return { cells: cellsForSet(set), stdin: '' };
    const old = window.localStorage.getItem(OLD_STORE_KEY);
    if (old) {
      const saved = JSON.parse(old) as { cells?: string[]; stdin?: string };
      if (Array.isArray(saved.cells) && saved.cells.length) {
        return { cells: saved.cells.map((code) => newCell(String(code))), stdin: saved.stdin ?? '' };
      }
    }
  } catch {
    // 저장본이 깨졌거나 저장소가 막혀 있으면 처음 셀로 연다.
  }
  return { cells: FIRST_CELLS.map((c) => newCell(c.source, c.type)), stdin: '민지\n3' };
}

export function saveNotebook(key: string, cells: Cell[], stdin: string) {
  try {
    window.localStorage.setItem(
      key,
      JSON.stringify({ cells: cells.map((c) => ({ type: c.type, source: c.code, problemIndex: c.problemIndex })), stdin }),
    );
  } catch {
    // 저장이 막혀 있어도 연습장은 돈다.
  }
}
