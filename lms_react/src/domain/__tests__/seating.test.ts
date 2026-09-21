import { describe, expect, it } from 'vitest';

import { assignTeamsToSeats, partitionMembers, teamSizes } from '../projectTeams';
import {
  cellAt,
  emptyGrid,
  moveFixture,
  moveGroup,
  placeFixture,
  placeTable,
  remapAssignments,
  removeGroup,
  seatCells,
} from '../seatingLayout';
import type { ProjectTeam, SeatingGrid } from '../types';

/** 늘 같은 수열 — 섞기 결과를 고정한다. */
function seeded(seed = 42): () => number {
  let s = seed;
  return () => {
    s = (s * 1103515245 + 12345) % 2 ** 31;
    return s / 2 ** 31;
  };
}

const labels = (grid: SeatingGrid) =>
  seatCells(grid)
    .sort((a, b) => a.row - b.row || a.col - b.col)
    .map((c) => `${c.row},${c.col}=${c.label}`);

describe('좌석 틀', () => {
  it('테이블을 놓으면 위→아래, 왼쪽→오른쪽으로 번호가 매겨진다', () => {
    let g = emptyGrid(3, 6);
    g = placeTable(g, 1, 3, 3, 'desk-1');
    g = placeTable(g, 0, 0, 2, 'desk-2');
    expect(labels(g)).toEqual(['0,0=1', '0,1=2', '1,3=3', '1,4=4', '1,5=5']);
  });

  it('겹치거나 격자를 벗어나는 자리에는 놓이지 않는다', () => {
    let g = placeTable(emptyGrid(2, 4), 0, 0, 3, 'desk-1');
    expect(placeTable(g, 0, 2, 2, 'desk-2')).toBe(g);
    expect(placeTable(g, 1, 2, 3, 'desk-2')).toBe(g);
    g = placeTable(g, 1, 1, 3, 'desk-2');
    expect(seatCells(g)).toHaveLength(6);
  });

  it('테이블을 옮기면 자기 칸과 겹쳐도 옮겨지고, 막히면 null이다', () => {
    let g = placeTable(emptyGrid(2, 6), 0, 0, 3, 'desk-1');
    g = moveGroup(g, 'desk-1', 0, 1)!;
    expect(cellAt(g, 0, 0)?.type).toBe('empty');
    expect(labels(g)).toEqual(['0,1=1', '0,2=2', '0,3=3']);

    g = placeTable(g, 1, 0, 2, 'desk-2');
    expect(moveGroup(g, 'desk-2', 0, 2)).toBeNull();
    expect(moveGroup(g, 'desk-2', 1, 5)).toBeNull();
  });

  it('강사석은 하나뿐이라 다시 놓으면 원래 자리가 비고, 옮길 수도 있다', () => {
    let g = placeFixture(emptyGrid(3, 6), 'instructor', 0, 0);
    g = placeFixture(g, 'instructor', 0, 3);
    expect(g.cells.filter((c) => c.type === 'instructor').map((c) => c.col)).toEqual([3, 4]);

    g = moveFixture(g, 'instructor', 0, 2)!;
    expect(g.cells.filter((c) => c.type === 'instructor').map((c) => c.col)).toEqual([2, 3]);
    expect(moveFixture(g, 'instructor', 0, 5)).toBeNull();
  });

  it('테이블을 치우면 남은 좌석 번호가 당겨진다', () => {
    let g = placeTable(emptyGrid(2, 4), 0, 0, 2, 'desk-1');
    g = placeTable(g, 1, 0, 2, 'desk-2');
    g = removeGroup(g, 'desk-1');
    expect(labels(g)).toEqual(['1,0=1', '1,1=2']);
  });

  it('틀을 고쳐 번호가 바뀌어도 학생은 앉던 자리를 따라간다', () => {
    let before = placeTable(emptyGrid(2, 4), 0, 0, 2, 'desk-1');
    before = placeTable(before, 1, 0, 2, 'desk-2');
    const after = removeGroup(before, 'desk-1');
    // 3번(1,0)에 앉던 학생은 이제 1번이다. 사라진 1·2번 학생은 빠진다.
    expect(remapAssignments(before, after, { '1': 'a', '3': 'b', '4': 'c' })).toEqual({ '1': 'b', '2': 'c' });
  });
});

describe('프로젝트 팀', () => {
  it('4~5명씩 나누고, 그렇게 안 되는 인원은 5명씩 채운 뒤 나머지를 둔다', () => {
    expect(teamSizes(0)).toEqual([]);
    expect(teamSizes(5)).toEqual([5]);
    expect(teamSizes(9)).toEqual([5, 4]);
    expect(teamSizes(13)).toEqual([5, 4, 4]);
    expect(teamSizes(30)).toEqual([5, 5, 5, 5, 5, 5]);
    expect(teamSizes(6)).toEqual([5, 1]);
    expect(teamSizes(11)).toEqual([5, 5, 1]);
  });

  it('랜덤 구성은 모든 학생을 한 번씩만 넣는다', () => {
    const ids = Array.from({ length: 17 }, (_, i) => `s${i}`);
    const parts = partitionMembers(ids, seeded());
    expect(parts.map((p) => p.length)).toEqual([5, 4, 4, 4]);
    expect(parts.flat().sort()).toEqual([...ids].sort());
  });

  it('팀끼리 앉히면 한 팀은 상하좌우로 이어진 자리에 앉는다', () => {
    // 3인 테이블 두 개가 위아래로 붙은 섬 두 개
    let g = emptyGrid(2, 8);
    g = placeTable(g, 0, 0, 3, 'd1');
    g = placeTable(g, 1, 0, 3, 'd2');
    g = placeTable(g, 0, 5, 3, 'd3');
    g = placeTable(g, 1, 5, 3, 'd4');
    const team = (id: string, n: number, colorIndex: number): ProjectTeam => ({
      id,
      cohortId: 'c',
      name: id,
      memberIds: Array.from({ length: n }, (_, i) => `${id}-${i}`),
      sortOrder: colorIndex,
      colorIndex,
    });

    const seats = assignTeamsToSeats(g, [team('A', 5, 0), team('B', 4, 1)], seeded(7));
    expect(Object.keys(seats)).toHaveLength(9);

    const byId = new Map(seatCells(g).map((c) => [c.seatId, c]));
    for (const prefix of ['A', 'B']) {
      const mine = Object.entries(seats)
        .filter(([, uid]) => uid.startsWith(prefix))
        .map(([seatId]) => byId.get(seatId)!);
      // 모두 한 섬 안에 있다.
      expect(new Set(mine.map((c) => (c.col < 4 ? 'left' : 'right'))).size).toBe(1);
    }
  });
});
