import { useSeating } from '../../data/repository';
import type { Seat, SeatPresenceState, SeatingCell, SeatingLayout } from '../../domain/types';
import { Icon } from '../../ui/Icon';
import { useCurrentUser } from '../auth/session';

/**
 * 자리 배치 (학생) — features/seating/presentation/seating_screen.dart
 *
 * 강의실을 위에서 내려다본 그림이다. 제목 한 줄 아래로 「▲ 강사석 방향」,
 * 강사석, 책상들, 출입문이 제자리에 놓인다. 내 자리만 파랗게 칠하고
 * 「내 자리」라고 적는다.
 */
export function SeatingScreen() {
  const user = useCurrentUser();
  const seating = useSeating();

  const title = ['자리 배치', user.cohortName, seating.roomNumber]
    .filter((v): v is string => v !== undefined && v !== '')
    .join(' · ');

  return (
    <div className="seat-page">
      <header className="seat-page__bar">
        <h1>{title}</h1>
      </header>

      {!seating.published ? (
        <div className="seat-page__wait">
          <Icon name="event_seat" size={48} />
          <strong>좌석 배치 확정 대기 중</strong>
          <p>관리자가 배치를 확정하면 이곳에서 확인할 수 있습니다.</p>
        </div>
      ) : (
        <div className="seat-page__body">
          <SeatGrid layout={seating} highlightUserId={user.uid} />
        </div>
      )}
    </div>
  );
}

/**
 * widgets/seat_grid.dart
 *
 * 강사가 교실 뒤에서 보면 앞뒤가 뒤집힌다. `rotated`는 그 시선을 위한 것이고,
 * 칸을 옮기지 않고 행과 열만 거꾸로 읽는다.
 */
export function SeatGrid({
  layout,
  highlightUserId,
  highlightCaption = '내 자리',
  compact = false,
  rotated = false,
  presenceOf,
}: {
  layout: SeatingLayout;
  highlightUserId?: string;
  /** 표시된 자리 아래에 적을 말 */
  highlightCaption?: string;
  compact?: boolean;
  rotated?: boolean;
  /** 확인·보류 상태로 칸을 물들인다(자리 확인 화면). */
  presenceOf?(userId: string): SeatPresenceState;
}) {
  const seatOf = new Map<number, Seat>(layout.seats.map((s) => [s.seatNumber, s]));

  return (
    <div className={`seatmap${compact ? ' seatmap--compact' : ''}`}>
      <p className="seatmap__hint">{rotated ? '▼ 강사석 방향' : '▲ 강사석 방향'}</p>
      <div
        className="seatmap__grid"
        style={{ gridTemplateColumns: `repeat(${layout.cols}, var(--seat-w))` }}
      >
        {layout.cells.map((cell) => (
          <Cell
            key={`${cell.row}-${cell.col}`}
            cell={cell}
            layout={layout}
            rotated={rotated}
            seat={cell.type === 'seat' ? seatOf.get(Number(cell.label)) : undefined}
            highlightUserId={highlightUserId}
            highlightCaption={highlightCaption}
            presenceOf={presenceOf}
          />
        ))}
      </div>
    </div>
  );
}

/** 붙어 있는 같은 책상끼리는 사이 테두리를 지운다. */
function edgesOf(layout: SeatingLayout, cell: SeatingCell) {
  if (cell.groupId === undefined) return { left: true, right: true, top: true, bottom: true };
  const at = (row: number, col: number) =>
    layout.cells.some((c) => c.row === row && c.col === col && c.groupId === cell.groupId);
  return {
    left: !at(cell.row, cell.col - 1),
    right: !at(cell.row, cell.col + 1),
    top: !at(cell.row - 1, cell.col),
    bottom: !at(cell.row + 1, cell.col),
  };
}

function Cell({
  cell,
  layout,
  seat,
  rotated,
  highlightUserId,
  highlightCaption,
  presenceOf,
}: {
  cell: SeatingCell;
  layout: SeatingLayout;
  seat?: Seat;
  rotated: boolean;
  highlightUserId?: string;
  highlightCaption: string;
  presenceOf?(userId: string): SeatPresenceState;
}) {
  const raw = edgesOf(layout, cell);
  // 뒤집으면 위아래·좌우가 서로 바뀐다.
  const edges = rotated
    ? { left: raw.right, right: raw.left, top: raw.bottom, bottom: raw.top }
    : raw;
  const style = {
    gridRow: (rotated ? layout.rows - 1 - cell.row : cell.row) + 1,
    gridColumn: (rotated ? layout.cols - 1 - cell.col : cell.col) + 1,
    borderLeftWidth: edges.left ? undefined : 0,
    borderRightWidth: edges.right ? undefined : 0,
    borderTopWidth: edges.top ? undefined : 0,
    borderBottomWidth: edges.bottom ? undefined : 0,
    borderTopLeftRadius: edges.top && edges.left ? undefined : 0,
    borderTopRightRadius: edges.top && edges.right ? undefined : 0,
    borderBottomLeftRadius: edges.bottom && edges.left ? undefined : 0,
    borderBottomRightRadius: edges.bottom && edges.right ? undefined : 0,
  };

  if (cell.type === 'instructor' || cell.type === 'door') {
    // 두 칸짜리 비품은 왼쪽 칸에만 글씨를 적는다.
    return (
      <div className={`seat-fixture seat-fixture--${cell.type}`} style={style}>
        {edges.left && (
          <span className="seat-fixture__mark">
            <Icon name={cell.type === 'instructor' ? 'person' : 'door_front'} size={16} />
            {cell.label}
          </span>
        )}
      </div>
    );
  }

  const mine = seat?.userId !== undefined && seat.userId === highlightUserId;
  const taken = seat?.userDisplayName !== undefined;
  const presence = seat?.userId !== undefined ? presenceOf?.(seat.userId) : undefined;
  const tint =
    presence === 'confirmed' ? ' seat--confirmed' : presence === 'held' ? ' seat--held' : '';

  return (
    <div
      className={`seat${mine ? ' seat--mine' : ''}${taken ? '' : ' seat--empty'}${tint}`}
      style={style}
    >
      <span className="seat__no">{cell.label}번</span>
      <span className="seat__name">{seat?.userDisplayName ?? '—'}</span>
      {mine && <span className="seat__mark">{highlightCaption}</span>}
    </div>
  );
}
