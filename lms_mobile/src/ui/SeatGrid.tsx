import { MaterialIcons } from '@expo/vector-icons';
import { edgesOf, sameGroup } from '@web/domain/seatingLayout';
import type { SeatingCell, SeatingGrid } from '@web/domain/types';
import { ScrollView, Text, View, type ViewStyle } from 'react-native';

import { useTheme } from '../theme/Theme';

/** 웹 `.seatmap` 치수 — 폭이 모자라면 칸을 줄이고, 최소 폭보다 좁으면 가로로 민다 */
export type SeatMark = 'unknown' | 'confirmed' | 'held';

const SEAT_W = 76;
const SEAT_H = 68;
const MIN_SEAT_W = 44;
const PAD = 4;
const ROW_GAP = 8;
const BORDER = 1.5;

/**
 * 좌석 배치도 — 웹 `features/seating/SeatingScreen.tsx` 의 SeatGrid 와 같은 그림.
 * 같은 책상(groupId)과 맞닿은 변은 테두리 · 여백 · 모서리를 지워 한 덩어리로 잇는다.
 */
export function SeatGrid({
  grid,
  seatUserIds,
  seatNames,
  highlightUserId,
  highlightCaption = '내 자리',
  markOf,
  width,
}: {
  grid: SeatingGrid;
  seatUserIds: Record<string, string>;
  seatNames: Record<string, string>;
  highlightUserId?: string;
  highlightCaption?: string;
  /** 자리 확인 화면 — 학생별 확인 · 보류 표시 */
  markOf?: (userId: string) => SeatMark;
  /** 배치도가 쓸 수 있는 폭 */
  width: number;
}) {
  const { palette } = useTheme();
  const seatW = Math.max(MIN_SEAT_W, Math.min(SEAT_W, Math.floor(width / Math.max(1, grid.cols)) - PAD * 2));
  const seatH = Math.round(seatW * (SEAT_H / SEAT_W));
  const track = seatW + PAD * 2;
  const mapW = track * grid.cols;
  const mapH = grid.rows * seatH + Math.max(0, grid.rows - 1) * ROW_GAP;
  const small = seatW < 60;

  const body = (
    <View style={{ alignItems: 'center', gap: 12, minWidth: mapW }}>
      <Text style={{ fontSize: 12, fontWeight: '600', color: palette.textSecondary }}>▲ 강사석 방향</Text>
      <View style={{ width: mapW, height: mapH }}>
        {grid.cells
          .filter((cell) => cell.type !== 'empty')
          .map((cell) => {
            const userId = cell.type === 'seat' ? seatUserIds[cell.seatId] : undefined;
            return (
              <Cell
                key={`${cell.row}-${cell.col}`}
                grid={grid}
                cell={cell}
                frame={frameOf(grid, cell, track, seatW, seatH)}
                name={cell.type === 'seat' ? seatNames[cell.seatId] : undefined}
                occupied={userId !== undefined}
                mine={userId !== undefined && userId === highlightUserId}
                caption={highlightCaption}
                mark={userId !== undefined && markOf ? markOf(userId) : 'unknown'}
                small={small}
              />
            );
          })}
      </View>
    </View>
  );

  if (mapW <= width) return <View style={{ alignItems: 'center' }}>{body}</View>;
  return (
    <ScrollView horizontal showsHorizontalScrollIndicator contentContainerStyle={{ paddingBottom: 6 }}>
      {body}
    </ScrollView>
  );
}

function frameOf(grid: SeatingGrid, cell: SeatingCell, track: number, seatW: number, seatH: number): ViewStyle {
  const e = edgesOf(grid, cell);
  const joinLeft = sameGroup(grid, cell, cell.row, cell.col - 1);
  const joinRight = sameGroup(grid, cell, cell.row, cell.col + 1);
  const r = 10;
  return {
    position: 'absolute',
    top: cell.row * (seatH + ROW_GAP),
    left: cell.col * track + (joinLeft ? 0 : PAD),
    width: seatW + (joinLeft ? PAD : 0) + (joinRight ? PAD : 0),
    height: seatH,
    borderLeftWidth: e.left ? BORDER : 0,
    borderRightWidth: e.right ? BORDER : 0,
    borderTopWidth: e.top ? BORDER : 0,
    borderBottomWidth: e.bottom ? BORDER : 0,
    borderTopLeftRadius: e.top && e.left ? r : 0,
    borderTopRightRadius: e.top && e.right ? r : 0,
    borderBottomLeftRadius: e.bottom && e.left ? r : 0,
    borderBottomRightRadius: e.bottom && e.right ? r : 0,
  };
}

function Cell({
  grid,
  cell,
  frame,
  name,
  occupied,
  mine,
  caption,
  mark,
  small,
}: {
  grid: SeatingGrid;
  cell: SeatingCell;
  frame: ViewStyle;
  name?: string;
  occupied: boolean;
  mine: boolean;
  caption: string;
  mark: SeatMark;
  small: boolean;
}) {
  const { palette } = useTheme();

  if (cell.type === 'instructor' || cell.type === 'door') {
    const door = cell.type === 'door';
    // 두 칸짜리 비품은 왼쪽 칸에만 글씨를 적고, 두 칸 폭을 덮어 가운데에 세운다
    const leader = !sameGroup(grid, cell, cell.row, cell.col - 1);
    const fg = door ? '#b45309' : palette.textSecondary;
    return (
      <View
        style={[
          frame,
          {
            borderColor: door ? '#f59e0b' : palette.border,
            backgroundColor: door ? '#f59e0b26' : palette.surfaceVariant,
            zIndex: leader ? 1 : 0,
            overflow: 'visible',
          },
        ]}
      >
        {leader ? (
          <View style={{ position: 'absolute', top: 0, bottom: 0, left: 0, width: '200%', alignItems: 'center', justifyContent: 'center', gap: 2 }}>
            <MaterialIcons name={door ? 'door-front' : 'person'} size={16} color={fg} />
            <Text style={{ fontSize: 11, fontWeight: '700', color: fg }}>{door ? '출입문' : '강사'}</Text>
          </View>
        ) : null}
      </View>
    );
  }

  const filled = occupied && name !== undefined && name !== '';
  return (
    <View
      style={[
        frame,
        {
          alignItems: 'center',
          justifyContent: 'center',
          gap: 2,
          padding: 3,
          overflow: 'hidden',
          borderColor: mine ? palette.primaryDark : `${palette.primary}59`,
          backgroundColor: mine ? palette.primary : palette.primaryLight,
        },
        mine && {
          borderLeftWidth: frame.borderLeftWidth ? 2.5 : 0,
          borderRightWidth: frame.borderRightWidth ? 2.5 : 0,
          borderTopWidth: frame.borderTopWidth ? 2.5 : 0,
          borderBottomWidth: frame.borderBottomWidth ? 2.5 : 0,
          shadowColor: palette.primary,
          shadowOpacity: 0.45,
          shadowRadius: 8,
          shadowOffset: { width: 0, height: 0 },
          elevation: 4,
          zIndex: 2,
        },
      ]}
    >
      <Text style={{ fontSize: small ? 9 : 10, fontWeight: '600', color: mine ? '#fff' : palette.textSecondary }}>{cell.label}번</Text>
      <Text
        numberOfLines={1}
        style={{ fontSize: small ? 10 : 11, fontWeight: mine ? '800' : '500', color: mine ? '#fff' : filled ? palette.text : palette.textSecondary }}
      >
        {filled ? name : '—'}
      </Text>
      {mine ? <Text style={{ fontSize: small ? 9 : 10, fontWeight: '700', color: '#fff' }}>{caption}</Text> : null}
      {mark !== 'unknown' ? (
        <MaterialIcons
          name={mark === 'confirmed' ? 'check-circle' : 'pause-circle'}
          size={small ? 12 : 14}
          color={mark === 'confirmed' ? palette.success : palette.warning}
          style={{ position: 'absolute', top: 2, right: 2 }}
        />
      ) : null}
    </View>
  );
}
