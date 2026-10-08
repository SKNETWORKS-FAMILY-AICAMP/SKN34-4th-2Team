import { MaterialIcons } from '@expo/vector-icons';
import { edgesOf, sameGroup } from '@web/domain/seatingLayout';
import type { SeatingCell, SeatingGrid } from '@web/domain/types';
import { useMemo, useState } from 'react';
import { Pressable, Text, View, type ViewStyle } from 'react-native';

import { useTheme } from '../theme/Theme';

export type SeatMark = 'unknown' | 'confirmed' | 'held';

/** 웹 `.seatmap` 치수 */
const SEAT_W = 76;
const SEAT_H = 68;
/** 번호 · 이름 두 줄이 들어가는 최소 칸 — 이보다 좁으면 번호만 적는 축소 배치도로 바꾼다 */
const MIN_SEAT_W = 44;
const MIN_SEAT_H = 46;
const PADS = [4, 2] as const;
const COMPACT_PAD = 1.5;
const ROW_GAP = 8;
const COMPACT_ROW_GAP = 5;
const BORDER = 1.5;

const MARK_LABEL: Record<SeatMark, string> = { unknown: '', confirmed: '확인', held: '보류' };

/** 좌석 · 비품이 놓인 범위만 남긴다 — 바깥 빈 줄 · 빈 칸이 폭을 잡아먹지 않게 */
function trimmed(grid: SeatingGrid): SeatingGrid {
  const used = grid.cells.filter((cell) => cell.type !== 'empty');
  if (used.length === 0) return grid;
  const top = Math.min(...used.map((cell) => cell.row));
  const left = Math.min(...used.map((cell) => cell.col));
  const bottom = Math.max(...used.map((cell) => cell.row));
  const right = Math.max(...used.map((cell) => cell.col));
  return {
    rows: bottom - top + 1,
    cols: right - left + 1,
    cells: used.map((cell) => ({ ...cell, row: cell.row - top, col: cell.col - left })),
  };
}

interface Layout {
  seatW: number;
  seatH: number;
  pad: number;
  rowGap: number;
  compact: boolean;
}

function layoutOf(cols: number, width: number): Layout {
  const per = Math.floor(width / Math.max(1, cols));
  for (const pad of PADS) {
    const seatW = Math.min(SEAT_W, per - pad * 2);
    if (seatW >= MIN_SEAT_W) {
      return { seatW, seatH: Math.max(MIN_SEAT_H, Math.round(seatW * (SEAT_H / SEAT_W))), pad, rowGap: ROW_GAP, compact: false };
    }
  }
  const seatW = Math.max(16, per - COMPACT_PAD * 2);
  return { seatW, seatH: Math.max(38, Math.round(seatW * 1.5)), pad: COMPACT_PAD, rowGap: COMPACT_ROW_GAP, compact: true };
}

/**
 * 좌석 배치도 — 웹 `features/seating/SeatingScreen.tsx` 의 SeatGrid 와 같은 그림.
 * 같은 책상(groupId)과 맞닿은 변은 테두리 · 여백 · 모서리를 지워 한 덩어리로 잇는다.
 * 폰 폭에 이름까지 다 넣을 수 없으면 번호만 적고, 칸을 누르면 아래에 이름을 보인다.
 */
export function SeatGrid({
  grid: source,
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
  const grid = useMemo(() => trimmed(source), [source]);
  const layout = layoutOf(grid.cols, width);
  const { seatW, seatH, pad, rowGap, compact } = layout;
  const track = seatW + pad * 2;
  const mapW = track * grid.cols;
  const mapH = grid.rows * seatH + Math.max(0, grid.rows - 1) * rowGap;
  const [picked, setPicked] = useState<string | null>(null);

  const seatOf = (cell: SeatingCell) => {
    const userId = cell.type === 'seat' ? seatUserIds[cell.seatId] : undefined;
    return {
      userId,
      name: cell.type === 'seat' ? seatNames[cell.seatId] : undefined,
      mark: userId !== undefined && markOf ? markOf(userId) : ('unknown' as SeatMark),
    };
  };
  const mineCell = highlightUserId ? grid.cells.find((cell) => cell.type === 'seat' && seatUserIds[cell.seatId] === highlightUserId) : undefined;
  const pickedCell = picked ? grid.cells.find((cell) => cell.type === 'seat' && cell.seatId === picked) : undefined;

  return (
    <View style={{ alignItems: 'center', gap: compact ? 10 : 12 }}>
      {compact && mineCell ? (
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
          <View style={{ width: 10, height: 10, borderRadius: 3, backgroundColor: palette.primary }} />
          <Text style={{ fontSize: 13, fontWeight: '700', color: palette.text }}>
            {highlightCaption}: {mineCell.label}번{seatOf(mineCell).name ? ` · ${seatOf(mineCell).name}` : ''}
          </Text>
        </View>
      ) : null}
      <Text style={{ fontSize: 12, fontWeight: '600', color: palette.textSecondary }}>▲ 강사석 방향</Text>
      <View style={{ width: mapW, height: mapH }}>
        {grid.cells.map((cell) => {
          const { userId, name, mark } = seatOf(cell);
          return (
            <Cell
              key={`${cell.row}-${cell.col}`}
              grid={grid}
              cell={cell}
              frame={frameOf(grid, cell, track, layout)}
              name={name}
              occupied={userId !== undefined}
              mine={userId !== undefined && userId === highlightUserId}
              picked={compact && cell.type === 'seat' && cell.seatId === picked}
              caption={!compact && seatH >= 58 ? highlightCaption : undefined}
              mark={mark}
              layout={layout}
              onPress={compact && cell.type === 'seat' ? () => setPicked((prev) => (prev === cell.seatId ? null : cell.seatId)) : undefined}
            />
          );
        })}
      </View>
      {compact ? (
        <View
          style={{
            alignSelf: 'stretch',
            flexDirection: 'row',
            alignItems: 'center',
            gap: 8,
            minHeight: 40,
            paddingHorizontal: 12,
            borderRadius: 10,
            backgroundColor: palette.surfaceVariant,
          }}
        >
          <MaterialIcons name={pickedCell ? 'event-seat' : 'touch-app'} size={18} color={pickedCell ? palette.primary : palette.textHint} />
          {pickedCell ? (
            <Text style={{ flex: 1, fontSize: 14, fontWeight: '600', color: palette.text }} numberOfLines={1}>
              {pickedCell.label}번 · {seatOf(pickedCell).name || '빈 자리'}
              {MARK_LABEL[seatOf(pickedCell).mark] ? (
                <Text style={{ color: seatOf(pickedCell).mark === 'confirmed' ? palette.success : palette.warning }}> · {MARK_LABEL[seatOf(pickedCell).mark]}</Text>
              ) : null}
            </Text>
          ) : (
            <Text style={{ flex: 1, fontSize: 13, color: palette.textSecondary }}>자리를 누르면 이름이 보여요</Text>
          )}
        </View>
      ) : null}
    </View>
  );
}

function frameOf(grid: SeatingGrid, cell: SeatingCell, track: number, { seatW, seatH, pad, rowGap, compact }: Layout): ViewStyle {
  const e = edgesOf(grid, cell);
  const joinLeft = sameGroup(grid, cell, cell.row, cell.col - 1);
  const joinRight = sameGroup(grid, cell, cell.row, cell.col + 1);
  const r = compact ? 6 : 10;
  return {
    position: 'absolute',
    top: cell.row * (seatH + rowGap),
    left: cell.col * track + (joinLeft ? 0 : pad),
    width: seatW + (joinLeft ? pad : 0) + (joinRight ? pad : 0),
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
  picked,
  caption,
  mark,
  layout,
  onPress,
}: {
  grid: SeatingGrid;
  cell: SeatingCell;
  frame: ViewStyle;
  name?: string;
  occupied: boolean;
  mine: boolean;
  picked: boolean;
  /** 칸이 낮으면 비워 둔다 — 강조색만으로 구분된다 */
  caption?: string;
  mark: SeatMark;
  layout: Layout;
  onPress?: () => void;
}) {
  const { palette } = useTheme();
  const { compact, seatW } = layout;
  const small = seatW < 60;

  if (cell.type === 'instructor' || cell.type === 'door') {
    const door = cell.type === 'door';
    // 두 칸짜리 비품은 왼쪽 칸에만 글씨를 적고, 두 칸 폭을 덮어 가운데에 세운다
    const leader = !sameGroup(grid, cell, cell.row, cell.col - 1);
    const spans = sameGroup(grid, cell, cell.row, cell.col + 1);
    const fg = door ? '#b45309' : palette.textSecondary;
    const roomy = (spans ? seatW * 2 : seatW) >= 40;
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
          <View style={{ position: 'absolute', top: 0, bottom: 0, left: 0, width: spans ? '200%' : '100%', alignItems: 'center', justifyContent: 'center', gap: 2 }}>
            <MaterialIcons name={door ? 'door-front' : 'person'} size={compact ? 14 : 16} color={fg} />
            {roomy ? (
              <Text style={{ fontSize: compact ? 9 : 11, fontWeight: '700', color: fg }} numberOfLines={1}>
                {door ? '출입문' : '강사'}
              </Text>
            ) : null}
          </View>
        ) : null}
      </View>
    );
  }

  if (cell.type !== 'seat') return null;

  const filled = occupied && name !== undefined && name !== '';
  const markColor = mark === 'confirmed' ? palette.success : palette.warning;
  const seatStyle = [
    frame,
    {
      alignItems: 'center' as const,
      justifyContent: 'center' as const,
      gap: compact ? 0 : 2,
      padding: compact ? 1 : 3,
      overflow: 'hidden' as const,
      borderColor: mine ? palette.primaryDark : picked ? palette.text : `${palette.primary}59`,
      backgroundColor: mine ? palette.primary : filled || !compact ? palette.primaryLight : palette.surface,
    },
    (mine || picked) && {
      borderLeftWidth: frame.borderLeftWidth ? 2.5 : 0,
      borderRightWidth: frame.borderRightWidth ? 2.5 : 0,
      borderTopWidth: frame.borderTopWidth ? 2.5 : 0,
      borderBottomWidth: frame.borderBottomWidth ? 2.5 : 0,
      zIndex: 2,
    },
    mine && {
      shadowColor: palette.primary,
      shadowOpacity: 0.45,
      shadowRadius: 8,
      shadowOffset: { width: 0, height: 0 },
      elevation: 4,
    },
  ];

  if (compact) {
    return (
      <Pressable accessibilityRole="button" accessibilityLabel={`${cell.label}번 ${filled ? name : '빈 자리'}`} onPress={onPress} style={seatStyle}>
        <Text
          style={{ fontSize: 8, fontWeight: '600', color: mine ? '#fff' : palette.textSecondary }}
          numberOfLines={1}
          adjustsFontSizeToFit
          minimumFontScale={0.7}
        >
          {cell.label}
        </Text>
        <Text
          style={{
            alignSelf: 'stretch',
            textAlign: 'center',
            fontSize: 10,
            fontWeight: mine ? '800' : '600',
            color: mine ? '#fff' : filled ? palette.text : palette.textHint,
          }}
          numberOfLines={1}
          adjustsFontSizeToFit
          minimumFontScale={0.45}
        >
          {filled ? name : '—'}
        </Text>
        {mark !== 'unknown' ? (
          <View style={{ position: 'absolute', top: 2, right: 2, width: 6, height: 6, borderRadius: 3, backgroundColor: markColor }} />
        ) : null}
      </Pressable>
    );
  }

  return (
    <View style={seatStyle}>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 2 }}>
        {mark !== 'unknown' ? (
          <MaterialIcons name={mark === 'confirmed' ? 'check-circle' : 'pause-circle'} size={small ? 10 : 12} color={markColor} />
        ) : null}
        <Text style={{ fontSize: small ? 9 : 10, fontWeight: '600', color: mine ? '#fff' : palette.textSecondary }}>{cell.label}번</Text>
      </View>
      <Text
        numberOfLines={1}
        adjustsFontSizeToFit
        minimumFontScale={0.7}
        style={{ fontSize: small ? 10 : 11, fontWeight: mine ? '800' : '500', color: mine ? '#fff' : filled ? palette.text : palette.textSecondary }}
      >
        {filled ? name : '—'}
      </Text>
      {mine && caption ? <Text style={{ fontSize: 10, fontWeight: '700', color: '#fff' }} numberOfLines={1}>{caption}</Text> : null}
    </View>
  );
}
