import { useLayoutEffect, useRef, useState, type CSSProperties, type HTMLAttributes, type ReactNode } from 'react';
import { useNavigate } from 'react-router-dom';

import { RoutePaths } from '../../app/routePaths';
import { usePublishedSeating } from '../../data/repository';
import { edgesOf, sameGroup } from '../../domain/seatingLayout';
import type { SeatPresenceState, SeatingCell, SeatingGrid } from '../../domain/types';
import { Icon } from '../../ui/Icon';
import { PageHeader } from '../../ui/components';
import { useCurrentUser } from '../auth/session';

/**
 * 자리 배치 (학생) — features/seating/presentation/seating_screen.dart
 *
 * 관리자가 확정한 강의실 하나를 위에서 내려다본 그림으로 보여 준다. 내 자리만
 * 파랗게 칠하고 「내 자리」라고 적는다. 확정 전이면 기다리라는 안내만 선다.
 */
export function SeatingScreen() {
  const user = useCurrentUser();
  const { room, assignment, published } = usePublishedSeating(user.cohortId);

  const where = [user.cohortName, room?.roomNumber?.trim()]
    .filter((v): v is string => v !== undefined && v !== '')
    .join(' · ');

  return (
    <div className="seat-page">
      <PageHeader title="자리 배치" description={where === '' ? '확정된 강의실 자리를 확인하세요.' : `${where} · 내 자리는 파랗게 표시됩니다.`} />

      {room === undefined ? (
        <div className="seat-page__wait">
          <p>좌석 배치가 아직 준비되지 않았습니다.</p>
        </div>
      ) : !published || assignment === undefined ? (
        <div className="seat-page__wait">
          <Icon name="event_seat" size={48} />
          <strong>좌석 배치 확정 대기 중</strong>
          <p>관리자가 배치를 확정하면 이곳에서 확인할 수 있습니다.</p>
        </div>
      ) : (
        <div className="seat-page__body">
          <SeatGrid
            grid={room}
            seatUserIds={assignment.assignments}
            seatNames={assignment.seatNames}
            highlightUserId={user.uid}
          />
        </div>
      )}
    </div>
  );
}

/** 대시보드 미니 배치표는 확정 뒤 사흘 동안만 뜬다. */
const DASHBOARD_PREVIEW_MS = 3 * 24 * 60 * 60 * 1000;

/**
 * 대시보드 — 내 자리 배치 (widgets/my_seating_dashboard_card.dart)
 *
 * 새로 확정된 배치를 놓치지 않게, 확정 후 3일간만 작은 배치표를 띄운다.
 * 누르면 자리 배치 화면으로 간다.
 */
export function MySeatingDashboardSection() {
  const user = useCurrentUser();
  const navigate = useNavigate();
  const { room, assignment, published } = usePublishedSeating(user.cohortId);

  const publishedAt = assignment?.publishedAt?.getTime();
  const fresh = publishedAt !== undefined && Date.now() - publishedAt <= DASHBOARD_PREVIEW_MS;
  if (!published || room === undefined || assignment === undefined || !fresh) return null;

  return (
    <div className="panel side-card">
      <header className="side-card__head">
        <h2 className="card__title">내 자리 배치</h2>
      </header>
      <button type="button" className="seat-mini" onClick={() => navigate(RoutePaths.seating)}>
        <FitWidth>
          <SeatGrid
            grid={room}
            seatUserIds={assignment.assignments}
            seatNames={assignment.seatNames}
            highlightUserId={user.uid}
            compact
          />
        </FitWidth>
        <span className="seat-mini__hint">탭하여 크게 보기</span>
      </button>
    </div>
  );
}

/**
 * 폭이 모자라면 통째로 줄인다 — Flutter의 `FittedBox(fit: BoxFit.scaleDown)`.
 * 늘리지는 않는다. 줄인 만큼 높이도 줄여 아래가 붕 뜨지 않게 한다.
 */
export function FitWidth({ children }: { children: ReactNode }) {
  const outer = useRef<HTMLDivElement>(null);
  const inner = useRef<HTMLDivElement>(null);
  const [fit, setFit] = useState({ scale: 1, height: 0 });

  useLayoutEffect(() => {
    const o = outer.current;
    const i = inner.current;
    if (o === null || i === null) return;
    const measure = () => {
      const scale = Math.min(1, o.clientWidth / Math.max(1, i.scrollWidth));
      setFit({ scale, height: i.scrollHeight * scale });
    };
    measure();
    if (typeof ResizeObserver === 'undefined') return;
    const ro = new ResizeObserver(measure);
    ro.observe(o);
    return () => ro.disconnect();
  }, []);

  return (
    <div ref={outer} className="fit-width" style={{ height: fit.height || undefined }}>
      {/* 줄일 때는 왼쪽 위를 축으로 줄여야 폭에 꼭 맞는다. 안 줄일 때만 가운데에 둔다. */}
      <div
        ref={inner}
        className="fit-width__inner"
        style={fit.scale < 1 ? { transform: `scale(${fit.scale})`, marginLeft: 0 } : undefined}
      >
        {children}
      </div>
    </div>
  );
}

export interface SeatGridProps {
  grid: SeatingGrid;
  /** seatId → userId */
  seatUserIds: Record<string, string>;
  /** seatId → 표시 이름 */
  seatNames: Record<string, string>;
  highlightUserId?: string;
  /** 표시된 자리 아래에 적을 말 */
  highlightCaption?: string;
  compact?: boolean;
  /** 강사가 교실 뒤에서 볼 때 — 칸을 옮기지 않고 행과 열만 거꾸로 읽는다. */
  rotated?: boolean;
  /** 확인·보류 상태로 칸을 물들인다(자리 확인 화면). */
  presenceOf?(userId: string): SeatPresenceState;
  /** 퇴소한 학생이 앉아 있는 좌석 — 붉게 칠한다. */
  inactiveSeatIds?: ReadonlySet<string>;
  /** seatId → 팀 강조색. 팀끼리 뭉쳐 앉았는지 한눈에 본다. */
  seatTints?: Readonly<Record<string, string>>;
  /** 배치 편집 — 좌석마다 끌기·놓기 속성을 붙인다. */
  seatAttrs?(seatId: string, occupied: boolean): HTMLAttributes<HTMLDivElement>;
}

/**
 * 좌석 배치도 — widgets/seat_grid.dart
 *
 * 학생 조회, 대시보드 미니 배치표, 자리 확인, 관리자 배치 편집이 모두 이것을 쓴다.
 */
export function SeatGrid({
  grid,
  seatUserIds,
  seatNames,
  highlightUserId,
  highlightCaption = '내 자리',
  compact = false,
  rotated = false,
  presenceOf,
  inactiveSeatIds,
  seatTints,
  seatAttrs,
}: SeatGridProps) {
  return (
    <div className={`seatmap${compact ? ' seatmap--compact' : ''}`} style={{ '--cols': grid.cols } as CSSProperties}>
      <p className="seatmap__hint">{rotated ? '▼ 강사석 방향' : '▲ 강사석 방향'}</p>
      <div
        className="seatmap__grid"
        style={{
          gridTemplateColumns: `repeat(${grid.cols}, var(--seat-track))`,
          gridTemplateRows: `repeat(${grid.rows}, var(--seat-h))`,
        }}
      >
        {grid.cells
          .filter((cell) => cell.type !== 'empty')
          .map((cell) => {
            const userId = cell.type === 'seat' ? seatUserIds[cell.seatId] : undefined;
            return (
              <Cell
                key={`${cell.row}-${cell.col}`}
                cell={cell}
                grid={grid}
                rotated={rotated}
                userId={userId}
                name={cell.type === 'seat' ? seatNames[cell.seatId] : undefined}
                highlighted={userId !== undefined && userId === highlightUserId}
                highlightCaption={highlightCaption}
                presence={userId !== undefined ? presenceOf?.(userId) : undefined}
                inactive={inactiveSeatIds?.has(cell.seatId) ?? false}
                tint={seatTints?.[cell.seatId]}
                attrs={seatAttrs}
              />
            );
          })}
      </div>
    </div>
  );
}

/** 칸 자리와 테두리. 같은 책상과 맞닿은 쪽은 여백·테두리·모서리를 지워 한 덩어리로 잇는다. */
export function cellStyle(grid: SeatingGrid, cell: SeatingCell, rotated = false): CSSProperties {
  const raw = edgesOf(grid, cell);
  // 뒤집으면 위아래·좌우가 서로 바뀐다.
  const e = rotated ? { left: raw.right, right: raw.left, top: raw.bottom, bottom: raw.top } : raw;
  const joinLeft = sameGroup(grid, cell, cell.row, cell.col + (rotated ? 1 : -1));
  const joinRight = sameGroup(grid, cell, cell.row, cell.col + (rotated ? -1 : 1));
  return {
    gridRow: (rotated ? grid.rows - 1 - cell.row : cell.row) + 1,
    gridColumn: (rotated ? grid.cols - 1 - cell.col : cell.col) + 1,
    marginLeft: joinLeft ? 0 : undefined,
    marginRight: joinRight ? 0 : undefined,
    borderLeftWidth: e.left ? undefined : 0,
    borderRightWidth: e.right ? undefined : 0,
    borderTopWidth: e.top ? undefined : 0,
    borderBottomWidth: e.bottom ? undefined : 0,
    borderTopLeftRadius: e.top && e.left ? undefined : 0,
    borderTopRightRadius: e.top && e.right ? undefined : 0,
    borderBottomLeftRadius: e.bottom && e.left ? undefined : 0,
    borderBottomRightRadius: e.bottom && e.right ? undefined : 0,
  };
}

function Cell({
  cell,
  grid,
  rotated,
  userId,
  name,
  highlighted,
  highlightCaption,
  presence,
  inactive,
  tint,
  attrs,
}: {
  cell: SeatingCell;
  grid: SeatingGrid;
  rotated: boolean;
  userId?: string;
  name?: string;
  highlighted: boolean;
  highlightCaption: string;
  presence?: SeatPresenceState;
  inactive: boolean;
  tint?: string;
  attrs?: SeatGridProps['seatAttrs'];
}) {
  const style = cellStyle(grid, cell, rotated);

  if (cell.type === 'instructor' || cell.type === 'door') {
    // 두 칸짜리 비품은 눈에 보이는 왼쪽 칸에만 글씨를 적는다.
    const leader = !sameGroup(grid, cell, cell.row, cell.col + (rotated ? 1 : -1));
    return (
      <div className={`seat-fixture seat-fixture--${cell.type}`} style={style}>
        {leader && (
          <span className="seat-fixture__mark">
            <Icon name={cell.type === 'instructor' ? 'person' : 'door_front'} size={16} />
            {cell.type === 'instructor' ? '강사' : '출입문'}
          </span>
        )}
      </div>
    );
  }

  const occupied = userId !== undefined && name !== undefined && name !== '';
  // 한 칸에 한 가지 색만 — 내 자리 > 확인 > 보류 > 퇴소 > 팀 순으로 앞선 것이 이긴다.
  const state = highlighted
    ? ' seat--mine'
    : presence === 'confirmed'
      ? ' seat--confirmed'
      : presence === 'held'
        ? ' seat--held'
        : inactive
          ? ' seat--inactive'
          : tint !== undefined
            ? ' seat--tinted'
            : '';
  const extra = attrs?.(cell.seatId, occupied) ?? {};
  const tintStyle = state === ' seat--tinted' ? ({ '--seat-tint': tint } as CSSProperties) : undefined;

  return (
    <div
      {...extra}
      className={`seat${occupied ? '' : ' seat--empty'}${state} ${extra.className ?? ''}`.trim()}
      style={{ ...style, ...tintStyle }}
    >
      <span className="seat__no">{cell.label}번</span>
      <span className="seat__name" title={occupied ? name : undefined}>
        {occupied ? name : '—'}
      </span>
      {highlighted && <span className="seat__mark">{highlightCaption}</span>}
      {!highlighted && presence === 'confirmed' && <span className="seat__mark seat__mark--ok">확인</span>}
      {!highlighted && presence === 'held' && <span className="seat__mark seat__mark--hold">보류</span>}
      {highlighted && <span className="seat__me">나</span>}
    </div>
  );
}
