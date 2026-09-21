import type { ProjectTeam, SeatingCell, SeatingGrid } from './types';
import { seatCells } from './seatingLayout';

/**
 * 프로젝트 팀 — utils/project_team_randomizer.dart · utils/team_seating_assigner.dart
 *
 * `random`은 0 이상 1 미만을 내는 함수다. 시험에서는 고정된 수열을 넣는다.
 */

export const TEAM_MIN_MEMBERS = 4;
export const TEAM_MAX_MEMBERS = 5;

type Random = () => number;

export function shuffle<T>(items: readonly T[], random: Random = Math.random): T[] {
  const out = [...items];
  for (let i = out.length - 1; i > 0; i--) {
    const j = Math.floor(random() * (i + 1));
    [out[i], out[j]] = [out[j], out[i]];
  }
  return out;
}

export function teamSizeLabel(count: number): string {
  if (count === 0) return '비어 있음';
  if (count >= TEAM_MIN_MEMBERS) return `${count}명 · 구성 완료`;
  return `${count}명 · ${TEAM_MIN_MEMBERS}명 이상 권장`;
}

/**
 * 가능한 한 팀마다 4~5명이 되도록 나눈다. 4·5로만은 못 나누는 인원(6, 7, 11 …)은
 * 5명씩 채우고 나머지를 마지막 팀에 둔다.
 */
export function teamSizes(n: number): number[] {
  if (n <= 0) return [];
  if (n <= TEAM_MAX_MEMBERS) return [n];

  const minTeams = Math.ceil(n / TEAM_MAX_MEMBERS);
  const maxTeams = Math.floor(n / TEAM_MIN_MEMBERS);
  if (minTeams <= maxTeams) {
    const sizes = Array<number>(minTeams).fill(TEAM_MIN_MEMBERS);
    const leftover = n - TEAM_MIN_MEMBERS * minTeams;
    for (let i = 0; i < leftover; i++) sizes[i] += 1;
    return sizes;
  }

  const sizes: number[] = [];
  let remaining = n;
  while (remaining > 0) {
    const take = Math.min(remaining, TEAM_MAX_MEMBERS);
    sizes.push(take);
    remaining -= take;
  }
  return sizes;
}

/** 학생을 섞어 팀별 멤버 목록으로 자른다. */
export function partitionMembers(userIds: readonly string[], random: Random = Math.random): string[][] {
  const ids = shuffle(userIds, random);
  const result: string[][] = [];
  let offset = 0;
  for (const size of teamSizes(ids.length)) {
    result.push(ids.slice(offset, offset + size));
    offset += size;
  }
  return result;
}

// ── 팀끼리 앉히기 ──────────────────────────────────────

type Adjacency = Map<string, string[]>;

/** 상하좌우로 맞닿은 좌석만 이웃이다. */
function adjacency(grid: SeatingGrid): Adjacency {
  const byPos = new Map<string, SeatingCell>();
  for (const c of seatCells(grid)) byPos.set(`${c.row},${c.col}`, c);
  const adj: Adjacency = new Map();
  for (const c of seatCells(grid)) {
    const around = [
      [c.row - 1, c.col],
      [c.row + 1, c.col],
      [c.row, c.col - 1],
      [c.row, c.col + 1],
    ];
    adj.set(
      c.seatId,
      around.flatMap(([r, col]) => {
        const other = byPos.get(`${r},${col}`);
        return other === undefined ? [] : [other.seatId];
      }),
    );
  }
  return adj;
}

function bfsTake(start: string, allowed: Set<string>, adj: Adjacency, limit: number): string[] {
  if (!allowed.has(start) || limit <= 0) return [];
  const out: string[] = [];
  const seen = new Set([start]);
  const queue = [start];
  while (queue.length > 0 && out.length < limit) {
    const cur = queue.shift()!;
    out.push(cur);
    for (const n of adj.get(cur) ?? []) {
      if (!allowed.has(n) || seen.has(n)) continue;
      seen.add(n);
      queue.push(n);
    }
  }
  return out;
}

function connectedComponents(adj: Adjacency, nodes: Set<string>): string[][] {
  const seen = new Set<string>();
  const comps: string[][] = [];
  for (const start of nodes) {
    if (seen.has(start)) continue;
    seen.add(start);
    const comp: string[] = [];
    const queue = [start];
    while (queue.length > 0) {
      const cur = queue.shift()!;
      comp.push(cur);
      for (const n of adj.get(cur) ?? []) {
        if (!nodes.has(n) || seen.has(n)) continue;
        seen.add(n);
        queue.push(n);
      }
    }
    comps.push(comp);
  }
  return comps;
}

/** 덩어리가 차지하는 네모의 넓이 + 둘레 조금. 작을수록 옹기종기 모인 것이다. */
function bboxScore(seats: string[], byId: Map<string, SeatingCell>): number {
  const cells = seats.map((id) => byId.get(id)!);
  const h = Math.max(...cells.map((c) => c.row)) - Math.min(...cells.map((c) => c.row)) + 1;
  const w = Math.max(...cells.map((c) => c.col)) - Math.min(...cells.map((c) => c.col)) + 1;
  return h * w * 10 + (h + w);
}

/** candidates 안에서 이어져 있고 가장 옹기종기한 `need`석 */
function compactConnectedSubset(
  candidates: Set<string>,
  adj: Adjacency,
  byId: Map<string, SeatingCell>,
  need: number,
  random: Random,
): string[] | null {
  if (candidates.size < need) return null;
  let best: string[] | null = null;
  let bestScore = Infinity;
  for (const seed of shuffle([...candidates], random)) {
    const taken = bfsTake(seed, candidates, adj, need);
    if (taken.length < need) continue;
    const score = bboxScore(taken, byId);
    if (score < bestScore) {
      bestScore = score;
      best = taken;
      if (bestScore <= need) break;
    }
  }
  return best;
}

function centroid(seats: string[], byId: Map<string, SeatingCell>): [number, number] {
  let r = 0;
  let c = 0;
  for (const id of seats) {
    r += byId.get(id)!.row;
    c += byId.get(id)!.col;
  }
  return [r / seats.length, c / seats.length];
}

function distToSet(seats: string[], [cr, cc]: [number, number], byId: Map<string, SeatingCell>): number {
  return Math.min(...seats.map((id) => Math.abs(byId.get(id)!.row - cr) + Math.abs(byId.get(id)!.col - cc)));
}

function takeFrom(
  comp: string[],
  want: number,
  adj: Adjacency,
  byId: Map<string, SeatingCell>,
  random: Random,
): string[] {
  const n = Math.min(want, comp.length);
  return compactConnectedSubset(new Set(comp), adj, byId, n, random) ?? shuffle(comp, random).slice(0, n);
}

/** 한 덩어리로 모자라면 가장 큰 덩어리부터 채우고, 가까운 덩어리를 이어 붙인다. */
function fillAcrossComponents(
  components: string[][],
  adj: Adjacency,
  byId: Map<string, SeatingCell>,
  need: number,
  random: Random,
): string[] {
  if (components.length === 0) return [];
  const remaining = [...components].sort((a, b) => b.length - a.length);
  const picked = takeFrom(remaining.shift()!, need, adj, byId, random);
  while (picked.length < need && remaining.length > 0) {
    const center = centroid(picked, byId);
    remaining.sort((a, b) => distToSet(a, center, byId) - distToSet(b, center, byId));
    picked.push(...takeFrom(remaining.shift()!, need - picked.length, adj, byId, random));
  }
  return picked.slice(0, need);
}

function findNearbyCluster(
  byId: Map<string, SeatingCell>,
  adj: Adjacency,
  free: Set<string>,
  need: number,
  random: Random,
): string[] {
  // 1) 한 책상 안에서 먼저
  const byGroup = new Map<string, string[]>();
  for (const id of free) {
    const gid = byId.get(id)?.groupId;
    if (gid === undefined || gid === '') continue;
    byGroup.set(gid, [...(byGroup.get(gid) ?? []), id]);
  }
  for (const gid of shuffle([...byGroup.keys()], random)) {
    const pool = byGroup.get(gid)!;
    if (pool.length < need) continue;
    const cluster = compactConnectedSubset(new Set(pool), adj, byId, need, random);
    if (cluster !== null) return cluster;
  }

  // 2) 빈 좌석이 이어진 덩어리 안에서
  const components = connectedComponents(adj, free).sort((a, b) => b.length - a.length);
  for (const comp of components) {
    if (comp.length < need) continue;
    const cluster = compactConnectedSubset(new Set(comp), adj, byId, need, random);
    if (cluster !== null) return cluster;
  }

  // 3) 여러 덩어리에 걸쳐서
  return fillAcrossComponents(components, adj, byId, need, random);
}

/**
 * 팀마다 상하좌우로 붙은 좌석에 앉힌다. 반환: seatId → userId.
 * 좌석이 모자라면 늦게 뽑힌 팀의 남는 학생은 자리를 받지 못한다.
 */
export function assignTeamsToSeats(
  grid: SeatingGrid,
  teams: readonly ProjectTeam[],
  random: Random = Math.random,
): Record<string, string> {
  const active = shuffle(
    teams
      .filter((t) => t.memberIds.length > 0)
      .map((t) => ({ ...t, memberIds: shuffle(t.memberIds, random) })),
    random,
  );
  const byId = new Map(seatCells(grid).map((c) => [c.seatId, c]));
  const adj = adjacency(grid);
  const free = new Set(byId.keys());
  const result: Record<string, string> = {};

  for (const team of active) {
    if (free.size === 0) break;
    const seats = findNearbyCluster(byId, adj, free, team.memberIds.length, random);
    seats.forEach((seatId, i) => {
      if (i >= team.memberIds.length) return;
      result[seatId] = team.memberIds[i];
      free.delete(seatId);
    });
  }
  return result;
}

// ── 팀 색 ──────────────────────────────────────────────

/** 팀 카드 강조색 — ProjectTeamColors. 옅은 바탕은 CSS에서 이 색을 표면색에 섞어 만든다. */
const TEAM_ACCENTS = ['#0055ff', '#0d9488', '#7c3aed', '#db2777', '#ea580c', '#2563eb', '#059669', '#ca8a04'];

export function teamAccent(colorIndex: number): string {
  return TEAM_ACCENTS[Math.abs(colorIndex) % TEAM_ACCENTS.length];
}
