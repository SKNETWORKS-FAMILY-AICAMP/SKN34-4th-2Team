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
            {...dnd.source({ kind: 'palette', item: p.item })}
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

      <div className="seatmap lay-map">
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
              ...(payload === null ? {} : dnd.source(payload)),
            };

            if (cell.type === 'seat') {
              const grouped = cell.groupId !== undefined;
              const leader = grouped && cellsInGroup(grid, cell.groupId!)[0]?.seatId === cell.seatId;
              return (
                <div
                  key={key}
                  className={`seat seat--empty lay-seat${lifted ? ' lay-cell--lifted' : ''}${hover}`}
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
