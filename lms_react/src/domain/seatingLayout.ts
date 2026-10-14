import type { SeatingCell, SeatingGrid } from './types';

/**
 * 좌석 틀 연산 — models/seating_layout_model.dart
 *
 * 모두 새 격자를 돌려주는 순수 함수다. 놓을 수 없는 자리면 받은 격자를 그대로
 * 돌려준다(이동은 `null`). 테이블을 놓거나 치우면 좌석 번호를 위→아래,
 * 왼쪽→오른쪽 차례로 다시 매긴다.
 */

export const MAX_COHORT_STUDENTS = 30;
export const DEFAULT_ROWS = 8;
export const DEFAULT_COLS = 10;
export const INSTRUCTOR_FIXTURE_ID = '__instructor__';
export const DOOR_FIXTURE_ID = '__door__';

export type FixtureKind = 'instructor' | 'door';

const fixtureIdOf = (kind: FixtureKind) =>
  kind === 'instructor' ? INSTRUCTOR_FIXTURE_ID : DOOR_FIXTURE_ID;

const blank = (cell: SeatingCell): SeatingCell => ({
  seatId: '',
  row: cell.row,
  col: cell.col,
  label: '',
  type: 'empty',
});

export function emptyGrid(rows = DEFAULT_ROWS, cols = DEFAULT_COLS): SeatingGrid {
  const cells: SeatingCell[] = [];
  for (let row = 0; row < rows; row++) {
    for (let col = 0; col < cols; col++) {
      cells.push({ seatId: '', row, col, label: '', type: 'empty' });
    }
  }
  return { rows, cols, cells };
}

export function cellAt(grid: SeatingGrid, row: number, col: number): SeatingCell | undefined {
  return grid.cells.find((c) => c.row === row && c.col === col);
}

export function seatCells(grid: SeatingGrid): SeatingCell[] {
  return grid.cells.filter((c) => c.type === 'seat');
}

export function seatCount(grid: SeatingGrid): number {
  return seatCells(grid).length;
}

export function cellsInGroup(grid: SeatingGrid, groupId: string): SeatingCell[] {
  return grid.cells
    .filter((c) => c.groupId === groupId)
    .sort((a, b) => a.row - b.row || a.col - b.col);
}

/** 좌석 번호를 위→아래, 왼쪽→오른쪽으로 1부터 다시 매긴다. */
export function relabeled<G extends SeatingGrid>(grid: G): G {
  const order = seatCells(grid).sort((a, b) => a.row - b.row || a.col - b.col);
  const idByPos = new Map(order.map((c, i) => [`${c.row},${c.col}`, String(i + 1)]));
  return {
    ...grid,
    cells: grid.cells.map((c) => {
      if (c.type !== 'seat') return c;
      const id = idByPos.get(`${c.row},${c.col}`) ?? '';
      return { ...c, seatId: id, label: id };
    }),
  };
}

function canOccupy(grid: SeatingGrid, row: number, col: number, ignoreGroupId?: string): boolean {
  const cell = cellAt(grid, row, col);
  if (cell === undefined) return false;
  if (cell.type === 'empty') return true;
  return ignoreGroupId !== undefined && cell.groupId === ignoreGroupId;
}

/** 가로로 `width`칸이 비었는가. `ignoreGroupId`의 칸은 빈 것으로 친다(자기 자리로 옮길 때). */
export function canPlaceSpan(
  grid: SeatingGrid,
  row: number,
  col: number,
  width: number,
  ignoreGroupId?: string,
): boolean {
  if (col < 0 || col + width > grid.cols) return false;
  for (let i = 0; i < width; i++) {
    if (!canOccupy(grid, row, col + i, ignoreGroupId)) return false;
  }
  return true;
}

export function canPlaceFixture(
  grid: SeatingGrid,
  kind: FixtureKind,
  row: number,
  col: number,
  moving = false,
): boolean {
  return canPlaceSpan(grid, row, col, 2, moving ? fixtureIdOf(kind) : undefined);
}

/** 강사석·출입문은 교실에 하나씩이다. 새로 놓으면 원래 것은 치워진다. */
export function placeFixture<G extends SeatingGrid>(
  grid: G,
  kind: FixtureKind,
  row: number,
  col: number,
): G {
  const id = fixtureIdOf(kind);
  if (!canPlaceSpan(grid, row, col, 2, id)) return grid;
  return {
    ...grid,
    cells: grid.cells.map((c) => {
      if (c.row === row && (c.col === col || c.col === col + 1)) {
        return { seatId: '', row: c.row, col: c.col, label: '', type: kind, groupId: id };
      }
      return c.groupId === id ? blank(c) : c;
    }),
  };
}

export function placeTable<G extends SeatingGrid>(
  grid: G,
  row: number,
  col: number,
  width: 2 | 3,
  groupId: string,
): G {
  if (!canPlaceSpan(grid, row, col, width)) return grid;
  return relabeled({
    ...grid,
    cells: grid.cells.map((c) =>
      c.row === row && c.col >= col && c.col < col + width
        ? { ...c, type: 'seat' as const, groupId }
        : c,
    ),
  });
}

/** 테이블 하나를 통째로 치우고 남은 좌석 번호를 다시 매긴다. */
export function removeGroup<G extends SeatingGrid>(grid: G, groupId: string): G {
  return relabeled({
    ...grid,
    cells: grid.cells.map((c) => (c.groupId === groupId ? blank(c) : c)),
  });
}

/** 테이블을 옮겼을 때 차지할 칸들. 격자를 벗어나면 `null`. */
export function groupFootprint(
  grid: SeatingGrid,
  groupId: string,
  toRow: number,
  toCol: number,
): [number, number][] | null {
  const group = cellsInGroup(grid, groupId);
  if (group.length === 0) return null;
  const minR = Math.min(...group.map((c) => c.row));
  const minC = Math.min(...group.map((c) => c.col));
  const out: [number, number][] = group.map((c) => [c.row - minR + toRow, c.col - minC + toCol]);
  return out.every(([r, c]) => r >= 0 && c >= 0 && r < grid.rows && c < grid.cols) ? out : null;
}

export function canMoveGroup(grid: SeatingGrid, groupId: string, toRow: number, toCol: number): boolean {
  const spots = groupFootprint(grid, groupId, toRow, toCol);
  return spots !== null && spots.every(([r, c]) => canOccupy(grid, r, c, groupId));
}

/** 테이블의 왼쪽 위 칸을 (toRow, toCol)로 옮긴다. 막히면 `null`. */
export function moveGroup<G extends SeatingGrid>(
  grid: G,
  groupId: string,
  toRow: number,
  toCol: number,
): G | null {
  if (!canMoveGroup(grid, groupId, toRow, toCol)) return null;
  const spots = new Set(groupFootprint(grid, groupId, toRow, toCol)!.map(([r, c]) => `${r},${c}`));
  return relabeled({
    ...grid,
    cells: grid.cells.map((c) => {
      if (spots.has(`${c.row},${c.col}`)) return { ...c, type: 'seat' as const, groupId };
      return c.groupId === groupId ? blank(c) : c;
    }),
  });
}

export function moveFixture<G extends SeatingGrid>(
  grid: G,
  kind: FixtureKind,
  toRow: number,
  toCol: number,
): G | null {
  if (!canPlaceFixture(grid, kind, toRow, toCol, true)) return null;
  return placeFixture(grid, kind, toRow, toCol);
}

/**
 * 틀을 고친 뒤 기존 배치를 자리(행·열) 기준으로 옮겨 싣는다.
 * 번호가 바뀌어도 그 자리에 앉아 있던 학생은 그대로 남고, 사라진 좌석의 학생은 빠진다.
 */
export function remapAssignments(
  oldGrid: SeatingGrid,
  newGrid: SeatingGrid,
  assignments: Record<string, string>,
): Record<string, string> {
  const byPos = new Map<string, string>();
  for (const c of seatCells(oldGrid)) {
    const uid = assignments[c.seatId];
    if (uid !== undefined) byPos.set(`${c.row},${c.col}`, uid);
  }
  const next: Record<string, string> = {};
  for (const c of seatCells(newGrid)) {
    const uid = byPos.get(`${c.row},${c.col}`);
    if (uid !== undefined) next[c.seatId] = uid;
  }
  return next;
}

/** 같은 책상(같은 groupId·같은 종류)으로 붙어 있는가 — seat_group_helper.dart */
export function sameGroup(grid: SeatingGrid, cell: SeatingCell, row: number, col: number): boolean {
  if (cell.groupId === undefined || cell.groupId === '') return false;
  const other = cellAt(grid, row, col);
  return other !== undefined && other.groupId === cell.groupId && other.type === cell.type;
}

export interface GroupEdges {
  top: boolean;
  bottom: boolean;
  left: boolean;
  right: boolean;
  grouped: boolean;
}

/** 테두리를 그을 변. 같은 책상과 맞닿은 변은 지운다. */
export function edgesOf(grid: SeatingGrid, cell: SeatingCell): GroupEdges {
  if (cell.groupId === undefined || cell.groupId === '') {
    return { top: true, bottom: true, left: true, right: true, grouped: false };
  }
  return {
    top: !sameGroup(grid, cell, cell.row - 1, cell.col),
    bottom: !sameGroup(grid, cell, cell.row + 1, cell.col),
    left: !sameGroup(grid, cell, cell.row, cell.col - 1),
    right: !sameGroup(grid, cell, cell.row, cell.col + 1),
    grouped: true,
  };
}
