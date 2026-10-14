import { useRef, type DragEvent } from 'react';

import {
  canMoveGroup,
  canPlaceFixture,
  canPlaceSpan,
  cellsInGroup,
  groupFootprint,
  moveFixture,
  moveGroup,
  placeFixture,
  placeTable,
  removeGroup,
  sameGroup,
  type FixtureKind,
} from '../../domain/seatingLayout';
import type { SeatingCell, SeatingGrid } from '../../domain/types';
import { Icon } from '../../ui/Icon';
import { cellStyle } from './SeatingScreen';
import { useDragDrop } from './useDragDrop';

/**
 * 좌석 틀 편집 — widgets/layout_editor_grid.dart
 *
 * 위 팔레트에서 강사석·출입문·2인/3인 테이블을 끌어 격자에 놓는다. 놓인 테이블과
 * 비품은 다시 끌어 옮기고, 테이블은 휴지통에 놓으면 치워진다. 놓을 수 없는
 * 자리에서는 칸이 밝아지지 않는다.
 */

type PaletteItem = 'instructor' | 'door' | 'table2' | 'table3';

type LayoutPayload =
  | { kind: 'palette'; item: PaletteItem }
  /** 테이블 이동 — 잡은 칸이 테이블 왼쪽 위에서 얼마나 떨어졌는지 함께 싣는다. */
  | { kind: 'table'; groupId: string; dRow: number; dCol: number }
  | { kind: 'fixture'; fixture: FixtureKind; dCol: number };

const PALETTE: { item: PaletteItem; label: string; icon: string }[] = [
  { item: 'instructor', label: '강사석 (2칸)', icon: 'person' },
  { item: 'door', label: '출입문 (2칸)', icon: 'door_front' },
  { item: 'table2', label: '2인 테이블', icon: 'table_restaurant' },
  { item: 'table3', label: '3인 테이블', icon: 'table_bar' },
];

/** 끄는 그림을 겹쳐 둘 곳 — 화면 밖. 그림을 찍은 뒤 바로 지운다 */
function showGhost(e: DragEvent, ghost: HTMLElement, offsetX: number, offsetY: number) {
  // 끄는 그림을 바꿀 수 없는 환경(테스트의 가짜 이벤트 등)에서는 기본 그림 그대로
  if (typeof e.dataTransfer?.setDragImage !== 'function') return;
  Object.assign(ghost.style, { position: 'fixed', left: '-10000px', top: '0', pointerEvents: 'none' });
  document.body.appendChild(ghost);
  e.dataTransfer.setDragImage(ghost, offsetX, offsetY);
  window.setTimeout(() => ghost.remove(), 0);
}

/** 격자에 놓인 여러 칸(테이블 · 강사석 · 출입문)을 한 덩어리 그림으로 */
function groupGhost(e: DragEvent, cells: HTMLElement[]) {
  if (cells.length < 2) return;
  const rects = cells.map((el) => el.getBoundingClientRect());
  const left = Math.min(...rects.map((r) => r.left));
  const top = Math.min(...rects.map((r) => r.top));
  const ghost = document.createElement('div');
  ghost.className = 'seatmap lay-ghost';
  ghost.style.width = `${Math.max(...rects.map((r) => r.right)) - left}px`;
  ghost.style.height = `${Math.max(...rects.map((r) => r.bottom)) - top}px`;
  cells.forEach((el, i) => {
    const copy = el.cloneNode(true) as HTMLElement;
    const r = rects[i];
    Object.assign(copy.style, {
      position: 'absolute',
      left: `${r.left - left}px`,
      top: `${r.top - top}px`,
      width: `${r.width}px`,
      height: `${r.height}px`,
      margin: '0',
    });
    copy.classList.remove('lay-cell--lifted');
    ghost.appendChild(copy);
  });
  showGhost(e, ghost, e.clientX - left, e.clientY - top);
}

/** 팔레트의 새 테이블 — 빈 칸 크기로 n칸짜리 테이블 그림 */
function paletteGhost(e: DragEvent, map: HTMLElement | null, width: number) {
  const sample = map?.querySelector<HTMLElement>('.lay-empty, .lay-seat');
  if (!sample) return;
  const r = sample.getBoundingClientRect();
  const ghost = document.createElement('div');
  ghost.className = 'seatmap lay-ghost lay-ghost--new';
  ghost.style.width = `${r.width * width}px`;
  ghost.style.height = `${r.height}px`;
  for (let i = 0; i < width; i++) {
    const seat = document.createElement('div');
    seat.className = 'seat seat--empty lay-seat';
    Object.assign(seat.style, { position: 'absolute', left: `${r.width * i}px`, top: '0', width: `${r.width}px`, height: `${r.height}px`, margin: '0' });
    ghost.appendChild(seat);
  }
  showGhost(e, ghost, r.width / 2, r.height / 2);
}

export function LayoutEditor<G extends SeatingGrid>({
  grid,
  onChange,
  newGroupId,
}: {
  grid: G;
  onChange(next: G): void;
  newGroupId(): string;
}) {
  const dnd = useDragDrop<LayoutPayload>();
  const mapRef = useRef<HTMLDivElement>(null);

  /** 잡은 칸이 속한 묶음(같은 테이블 · 같은 비품)의 칸 요소들 */
  const groupCells = (p: LayoutPayload): HTMLElement[] => {
    const root = mapRef.current;
    if (!root) return [];
    if (p.kind === 'table') {
      // 선택자 문자열을 만들지 않고 속성 값으로 견준다 — 그룹 id 에 어떤 글자가 와도 안전하게
      return [...root.querySelectorAll<HTMLElement>('[data-group]')].filter((el) => el.dataset.group === p.groupId);
    }
    if (p.kind === 'fixture') return [...root.querySelectorAll<HTMLElement>(`[data-fixture="${p.fixture}"]`)];
    return [];
  };

  /** 놓는 칸(row, col)을 기준으로 실제로 차지할 칸들 */
  const footprint = (p: LayoutPayload, row: number, col: number): [number, number][] | null => {
    switch (p.kind) {
      case 'palette': {
        const width = p.item === 'table3' ? 3 : 2;
        return Array.from({ length: width }, (_, i) => [row, col + i]);
      }
      case 'table':
        return groupFootprint(grid, p.groupId, row - p.dRow, col - p.dCol);
      case 'fixture':
        return [
          [row, col - p.dCol],
          [row, col - p.dCol + 1],
        ];
    }
  };

  const canDrop = (p: LayoutPayload, row: number, col: number): boolean => {
    switch (p.kind) {
      case 'palette':
        if (p.item === 'instructor' || p.item === 'door') return canPlaceFixture(grid, p.item, row, col);
        return canPlaceSpan(grid, row, col, p.item === 'table3' ? 3 : 2);
      case 'table':
        return canMoveGroup(grid, p.groupId, row - p.dRow, col - p.dCol);
      case 'fixture':
        return canPlaceFixture(grid, p.fixture, row, col - p.dCol, true);
    }
  };

  const drop = (p: LayoutPayload, row: number, col: number) => {
    let next: G | null = null;
    switch (p.kind) {
      case 'palette':
        next =
          p.item === 'instructor' || p.item === 'door'
            ? placeFixture(grid, p.item, row, col)
            : placeTable(grid, row, col, p.item === 'table3' ? 3 : 2, newGroupId());
        break;
      case 'table':
        next = moveGroup(grid, p.groupId, row - p.dRow, col - p.dCol);
        break;
      case 'fixture':
        next = moveFixture(grid, p.fixture, row, col - p.dCol);
        break;
    }
    if (next !== null) onChange(next);
  };

  // 끌고 있는 것이 놓일 칸들을 미리 밝힌다.
  const preview = new Set<string>();
  if (dnd.dragging !== null && dnd.over !== null && dnd.over !== 'trash') {
    const [r, c] = dnd.over.split(',').map(Number);
    for (const [pr, pc] of footprint(dnd.dragging, r, c) ?? []) preview.add(`${pr},${pc}`);
  }

  const payloadOf = (cell: SeatingCell): LayoutPayload | null => {
    if (cell.type === 'seat' && cell.groupId !== undefined) {
      const group = cellsInGroup(grid, cell.groupId);
      const minR = Math.min(...group.map((c) => c.row));
      const minC = Math.min(...group.map((c) => c.col));
      return { kind: 'table', groupId: cell.groupId, dRow: cell.row - minR, dCol: cell.col - minC };
    }
    if (cell.type === 'instructor' || cell.type === 'door') {
      const leftIsSame = sameGroup(grid, cell, cell.row, cell.col - 1);
      return { kind: 'fixture', fixture: cell.type, dCol: leftIsSame ? 1 : 0 };
    }
    return null;
  };

  const draggingGroup =
    dnd.dragging?.kind === 'table'
      ? dnd.dragging.groupId
      : dnd.dragging?.kind === 'fixture'
        ? dnd.dragging.fixture
        : null;

  const trashHover = dnd.over === 'trash';

  return (
    <div className="lay-editor">
      <div className="lay-palette">
        <strong>끌어다 놓기:</strong>
        {PALETTE.map((p) => (
          <span
            key={p.item}
            className={`lay-chip${dnd.dragging?.kind === 'palette' && dnd.dragging.item === p.item ? ' lay-chip--dragging' : ''}`}
            {...dnd.source({ kind: 'palette', item: p.item }, (e) => {
              if (p.item === 'table2' || p.item === 'table3') paletteGhost(e, mapRef.current, p.item === 'table3' ? 3 : 2);
            })}
          >
            <Icon name={p.icon} size={18} />
            {p.label}
            <Icon name="drag_indicator" size={16} className="lay-chip__grip" />
          </span>
        ))}
      </div>

      <div
        className={`lay-trash${trashHover ? ' lay-trash--hover' : ''}`}
        {...dnd.target('trash', (p) => p.kind === 'table', (p) => {
          if (p.kind === 'table') onChange(removeGroup(grid, p.groupId));
        })}
      >
        <Icon name="delete" size={20} />
        {trashHover ? '놓아서 좌석 삭제' : '좌석을 이곳에 끌어 놓아 삭제'}
      </div>

      <div className="seatmap lay-map" ref={mapRef}>
        <p className="seatmap__hint">▲ 강사석 방향</p>
        <div
          className="seatmap__grid"
          style={{
            gridTemplateColumns: `repeat(${grid.cols}, var(--seat-track))`,
            gridTemplateRows: `repeat(${grid.rows}, var(--seat-h))`,
          }}
        >
          {grid.cells.map((cell) => {
            const key = `${cell.row},${cell.col}`;
            const target = dnd.target(
              key,
              (p) => canDrop(p, cell.row, cell.col),
              (p) => drop(p, cell.row, cell.col),
            );
            const hover = preview.has(key) ? ' lay-cell--hover' : '';

            if (cell.type === 'empty') {
              return (
                <div
                  key={key}
                  className={`lay-empty${hover}`}
                  style={{ gridRow: cell.row + 1, gridColumn: cell.col + 1 }}
                  {...target}
                />
              );
            }

            const payload = payloadOf(cell);
            const lifted =
              draggingGroup !== null &&
              (cell.groupId === draggingGroup ||
                (cell.type === draggingGroup && dnd.dragging?.kind === 'fixture'));
            const common = {
              style: cellStyle(grid, cell),
              ...target,
              ...(payload === null ? {} : dnd.source(payload, (e) => groupGhost(e, groupCells(payload)))),
            };

            if (cell.type === 'seat') {
              const grouped = cell.groupId !== undefined;
              const leader = grouped && cellsInGroup(grid, cell.groupId!)[0]?.seatId === cell.seatId;
              return (
                <div
                  key={key}
                  className={`seat seat--empty lay-seat${lifted ? ' lay-cell--lifted' : ''}${hover}`}
                  data-group={cell.groupId}
                  title="끌어서 옮기기"
                  {...common}
                >
                  <span className="seat__no">{cell.label}번</span>
                  {leader && <Icon name="drag_indicator" size={14} className="lay-seat__grip" />}
                </div>
              );
            }

            const leader = !sameGroup(grid, cell, cell.row, cell.col - 1);
            return (
              <div
                key={key}
                className={`seat-fixture seat-fixture--${cell.type} lay-fixture${lifted ? ' lay-cell--lifted' : ''}${hover}`}
                data-fixture={cell.type}
                title="끌어서 옮기기"
                {...common}
              >
                {leader && (
                  <span className="seat-fixture__mark">
                    <Icon name={cell.type === 'instructor' ? 'person' : 'door_front'} size={16} />
                    {cell.type === 'instructor' ? '강사석' : '출입문'}
                  </span>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
