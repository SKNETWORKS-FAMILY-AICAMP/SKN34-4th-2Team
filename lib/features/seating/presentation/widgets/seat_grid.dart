import 'package:flutter/material.dart';

import '../../../../core/theme/app_colors.dart';
import '../../models/seat_drag_payload.dart';
import '../../models/seat_group_helper.dart';
import '../../models/seating_layout_model.dart';
import '../../../../core/theme/app_space.dart';

/// 좌석 그리드 (배치 편집 / 학생 조회)
class SeatGrid extends StatelessWidget {
  const SeatGrid({
    super.key,
    required this.layout,
    required this.seatUserIds,
    required this.seatDisplayNames,
    this.highlightUserId,
    this.highlightCaption,
    this.pulseHighlight = false,
    this.editable = false,
    this.compact = false,
    this.showInstructorHint = true,
    this.rotate180 = false,
    this.inactiveSeatIds = const {},
    this.confirmedUserIds = const {},
    this.heldUserIds = const {},
    this.seatTintColors = const {},
    this.onAssign,
    this.onSwap,
  });

  final SeatingLayoutModel layout;
  final Map<String, String> seatUserIds;
  final Map<String, String> seatDisplayNames;
  final String? highlightUserId;
  final String? highlightCaption;
  final bool pulseHighlight;
  final bool editable;
  final bool compact;
  final bool showInstructorHint;
  final bool rotate180;
  final Set<String> inactiveSeatIds;
  final Set<String> confirmedUserIds;
  final Set<String> heldUserIds;

  /// seatId → 팀 등 연한 배경색 (배치 확인용)
  final Map<String, Color> seatTintColors;
  final void Function(String seatId, SeatDragPayload payload)? onAssign;
  final void Function(String fromSeatId, String toSeatId)? onSwap;

  double get _cellW => compact ? 34.0 : 76.0;
  double get _cellH => compact ? 30.0 : 68.0;
  double get _rowGap => compact ? 3.0 : 8.0;
  double get _groupGap => compact ? 2.0 : 4.0;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: compact
          ? CrossAxisAlignment.center
          : CrossAxisAlignment.stretch,
      mainAxisSize: MainAxisSize.min,
      children: [
        if (showInstructorHint)
          Center(
            child: Padding(
              padding: EdgeInsets.only(bottom: compact ? AppSpace.s(4) : AppSpace.s(12)),
              child: Text(
                rotate180 ? '▼ 강사석 방향' : '▲ 강사석 방향',
                style: TextStyle(
                  fontSize: compact ? 8 : 12,
                  fontWeight: FontWeight.w600,
                  color: AppColors.textSecondary,
                ),
              ),
            ),
          ),
        ...List.generate(layout.rows, (row) {
          final sourceRow = rotate180 ? layout.rows - 1 - row : row;
          return Padding(
            padding: EdgeInsets.only(bottom: _rowGap),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.center,
              mainAxisSize: MainAxisSize.min,
              children: List.generate(layout.cols, (col) {
                final sourceCol = rotate180 ? layout.cols - 1 - col : col;
                final cell = layout.cellAt(sourceRow, sourceCol);
                if (cell == null || cell.isEmpty) {
                  return SizedBox(width: _cellW, height: _cellH);
                }

                final sourceColToVisualLeft = rotate180
                    ? sourceCol + 1
                    : sourceCol - 1;
                final sourceColToVisualRight = rotate180
                    ? sourceCol - 1
                    : sourceCol + 1;
                final hPadLeft =
                    col > 0 &&
                        sameCellGroup(
                          layout,
                          cell,
                          sourceRow,
                          sourceColToVisualLeft,
                        )
                    ? 0.0
                    : _groupGap;
                final hPadRight =
                    col < layout.cols - 1 &&
                        sameCellGroup(
                          layout,
                          cell,
                          sourceRow,
                          sourceColToVisualRight,
                        )
                    ? 0.0
                    : _groupGap;

                return Padding(
                  padding: EdgeInsets.only(left: hPadLeft, right: hPadRight),
                  child: _SeatCell(
                    layout: layout,
                    cell: cell,
                    displayName: seatDisplayNames[cell.seatId] ?? '',
                    userId: seatUserIds[cell.seatId],
                    isHighlighted:
                        highlightUserId != null &&
                        seatUserIds[cell.seatId] == highlightUserId,
                    isConfirmed: confirmedUserIds.contains(
                      seatUserIds[cell.seatId],
                    ),
                    isHeld: heldUserIds.contains(
                      seatUserIds[cell.seatId],
                    ),
                    isInactive: inactiveSeatIds.contains(cell.seatId),
                    teamTint: seatTintColors[cell.seatId],
                    highlightCaption: highlightCaption,
                    pulseHighlight: pulseHighlight,
                    editable: editable,
                    compact: compact,
                    rotate180: rotate180,
                    cellW: _cellW,
                    cellH: _cellH,
                    onAssign: onAssign,
                    onSwap: onSwap,
                  ),
                );
              }),
            ),
          );
        }),
      ],
    );
  }
}

class _SeatCell extends StatelessWidget {
  const _SeatCell({
    required this.layout,
    required this.cell,
    required this.displayName,
    required this.userId,
    required this.isHighlighted,
    required this.isConfirmed,
    required this.isHeld,
    required this.isInactive,
    required this.highlightCaption,
    required this.pulseHighlight,
    required this.editable,
    required this.compact,
    required this.rotate180,
    required this.cellW,
    required this.cellH,
    this.teamTint,
    this.onAssign,
    this.onSwap,
  });

  final SeatingLayoutModel layout;
  final SeatingCell cell;
  final String displayName;
  final String? userId;
  final bool isHighlighted;
  final bool isConfirmed;
  final bool isHeld;
  final bool isInactive;
  final Color? teamTint;
  final String? highlightCaption;
  final bool pulseHighlight;
  final bool editable;
  final bool compact;
  final bool rotate180;
  final double cellW;
  final double cellH;
  final void Function(String seatId, SeatDragPayload payload)? onAssign;
  final void Function(String fromSeatId, String toSeatId)? onSwap;

  SeatGroupEdges _visualGroupEdges() {
    final edges = computeGroupEdges(layout, cell);
    if (!rotate180) return edges;
    return SeatGroupEdges(
      top: edges.bottom,
      bottom: edges.top,
      left: edges.right,
      right: edges.left,
      isGrouped: edges.isGrouped,
    );
  }

  @override
  Widget build(BuildContext context) {
    if (cell.isInstructor || cell.isDoor) {
      return _fixtureCell(
        label: cell.isInstructor ? '강사' : '출입문',
        icon: cell.isInstructor ? Icons.person : Icons.door_front_door_outlined,
        bg: cell.isInstructor
            ? AppColors.tint(const Color(0xFFF1F5F9))
            : AppColors.tint(const Color(0xFFFEF3C7)),
        border: cell.isInstructor ? AppColors.border : const Color(0xFFF59E0B),
      );
    }

    final edges = _visualGroupEdges();
    final hasStudent = displayName.isNotEmpty && userId != null;
    final mineFill = isHighlighted && !pulseHighlight;

    Color bgColor;
    if (isHighlighted) {
      bgColor = pulseHighlight
          ? AppColors.tint(const Color(0xFFFEF3C7))
          : AppColors.primary;
    } else if (isConfirmed) {
      bgColor = AppColors.tint(const Color(0xFFDCFCE7));
    } else if (isHeld) {
      bgColor = AppColors.tint(const Color(0xFFFFEDD5));
    } else if (isInactive) {
      bgColor = AppColors.tint(const Color(0xFFFEE2E2));
    } else if (teamTint != null) {
      bgColor = teamTint!;
    } else if (edges.isGrouped) {
      bgColor = AppColors.primaryLight;
    } else if (hasStudent) {
      bgColor = AppColors.surface;
    } else {
      bgColor = AppColors.tint(const Color(0xFFF8FAFC));
    }

    final borderColor = isHighlighted
        ? (pulseHighlight ? const Color(0xFFF59E0B) : AppColors.primaryDark)
        : isConfirmed
        ? const Color(0xFF22C55E)
        : isHeld
        ? const Color(0xFFF97316)
        : isInactive
        ? const Color(0xFFEF4444)
        : teamTint != null
        ? Color.lerp(teamTint, Colors.black, 0.22)!
        : edges.isGrouped
        ? AppColors.primary.withValues(alpha: 0.35)
        : AppColors.border;

    final borderWidth = isHighlighted
        ? (compact ? 2.0 : 2.5)
        : (compact ? 1.0 : 1.5);
    final onMine = mineFill ? Colors.white : null;
    final labelColor = onMine ?? AppColors.textSecondary;
    final nameColor =
        onMine ??
        (isHighlighted
            ? (pulseHighlight ? const Color(0xFFB45309) : AppColors.primaryDark)
            : AppColors.textPrimary);

    Widget seatContent = Container(
      width: cellW,
      height: cellH,
      padding: EdgeInsets.all(compact ? AppSpace.s(1) : AppSpace.s(4)),
      decoration: BoxDecoration(
        color: bgColor,
        borderRadius: edges.borderRadius,
        border: edges.isGrouped
            ? groupBorder(edges, borderColor, width: borderWidth)
            : Border.all(color: borderColor, width: borderWidth),
        boxShadow: isHighlighted
            ? [
                BoxShadow(
                  color:
                      (pulseHighlight
                              ? const Color(0xFFF59E0B)
                              : AppColors.primary)
                          .withValues(alpha: 0.4),
                  blurRadius: compact ? 5 : 10,
                  spreadRadius: compact ? 0.5 : 1.5,
                ),
              ]
            : null,
      ),
      child: Stack(
        clipBehavior: Clip.none,
        children: [
          Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Text(
                '${cell.label}번',
                style: TextStyle(
                  fontSize: compact ? 7 : 10,
                  color: labelColor.withValues(
                    alpha: onMine != null ? 0.85 : 1,
                  ),
                  fontWeight: FontWeight.w600,
                ),
              ),
              if (!compact) SizedBox(height: AppSpace.s(2)),
              Expanded(
                child: Center(
                  child: Text(
                    hasStudent ? displayName : '—',
                    textAlign: TextAlign.center,
                    maxLines: compact ? 1 : 2,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                      fontSize: compact ? 6 : 11,
                      fontWeight: isHighlighted
                          ? FontWeight.w800
                          : FontWeight.w500,
                      color: nameColor,
                    ),
                  ),
                ),
              ),
              if (isHighlighted && !compact)
                Text(
                  highlightCaption ?? '내 자리',
                  style: TextStyle(
                    fontSize: 9,
                    fontWeight: FontWeight.w700,
                    color: pulseHighlight
                        ? const Color(0xFFD97706)
                        : Colors.white.withValues(alpha: 0.95),
                  ),
                )
              else if (isConfirmed && !compact && !isHighlighted)
                const Text(
                  '확인',
                  style: TextStyle(
                    fontSize: 9,
                    fontWeight: FontWeight.w700,
                    color: Color(0xFF15803D),
                  ),
                )
              else if (isHeld && !compact && !isHighlighted)
                const Text(
                  '보류',
                  style: TextStyle(
                    fontSize: 9,
                    fontWeight: FontWeight.w700,
                    color: Color(0xFFC2410C),
                  ),
                ),
            ],
          ),
          if (isHighlighted && compact)
            Positioned(
              right: -1,
              top: -1,
              child: Container(
                padding: EdgeInsets.symmetric(horizontal: AppSpace.s(3), vertical: AppSpace.s(1)),
                decoration: BoxDecoration(
                  color: pulseHighlight
                      ? const Color(0xFFF59E0B)
                      : AppColors.primaryDark,
                  borderRadius: BorderRadius.circular(4),
                ),
                child: Text(
                  '나',
                  style: TextStyle(
                    fontSize: 6,
                    fontWeight: FontWeight.w800,
                    color: Colors.white,
                    height: 1,
                  ),
                ),
              ),
            ),
        ],
      ),
    );

    if (isHighlighted && pulseHighlight) {
      seatContent = _PulseGlow(child: seatContent);
    }

    if (!editable) return seatContent;

    if (hasStudent) {
      seatContent = Draggable<SeatDragPayload>(
        data: SeatDragPayload(
          userId: userId!,
          displayName: displayName,
          fromSeatId: cell.seatId,
        ),
        feedback: Material(
          elevation: 4,
          borderRadius: BorderRadius.circular(8),
          child: _dragChip(displayName),
        ),
        childWhenDragging: Opacity(opacity: 0.35, child: seatContent),
        child: seatContent,
      );
    }

    return DragTarget<SeatDragPayload>(
      onWillAcceptWithDetails: (_) => cell.isSeat,
      onAcceptWithDetails: (d) {
        final payload = d.data;
        if (payload.fromSeatId == null) {
          onAssign?.call(cell.seatId, payload);
        } else if (payload.fromSeatId != cell.seatId) {
          if (hasStudent) {
            onSwap?.call(payload.fromSeatId!, cell.seatId);
          } else {
            onAssign?.call(cell.seatId, payload);
          }
        }
      },
      builder: (context, candidate, _) {
        final isHover = candidate.isNotEmpty;
        return AnimatedContainer(
          duration: const Duration(milliseconds: 120),
          decoration: isHover
              ? BoxDecoration(
                  borderRadius: BorderRadius.circular(8),
                  border: Border.all(color: AppColors.primary, width: 2),
                )
              : null,
          child: seatContent,
        );
      },
    );
  }

  Widget _fixtureCell({
    required String label,
    required IconData icon,
    required Color bg,
    required Color border,
  }) {
    final edges = _visualGroupEdges();
    final leader = edges.left;
    return Container(
      width: cellW,
      height: cellH,
      alignment: Alignment.center,
      decoration: BoxDecoration(
        color: bg,
        borderRadius: edges.borderRadius,
        border: groupBorder(edges, border),
      ),
      child: leader
          ? Column(
              mainAxisAlignment: MainAxisAlignment.center,
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(icon, size: compact ? 10 : 16, color: border),
                if (!compact) SizedBox(height: AppSpace.s(2)),
                Text(
                  label,
                  style: TextStyle(
                    fontSize: compact ? 7 : 10,
                    color: border,
                  ),
                ),
              ],
            )
          : null,
    );
  }

  Widget _dragChip(String name) {
    return Container(
      padding: EdgeInsets.symmetric(horizontal: AppSpace.s(12), vertical: AppSpace.s(8)),
      decoration: BoxDecoration(
        color: AppColors.primaryLight,
        borderRadius: BorderRadius.circular(8),
      ),
      child: Text(name, style: const TextStyle(fontWeight: FontWeight.w600)),
    );
  }
}

class _PulseGlow extends StatefulWidget {
  const _PulseGlow({required this.child});

  final Widget child;

  @override
  State<_PulseGlow> createState() => _PulseGlowState();
}

class _PulseGlowState extends State<_PulseGlow>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller = AnimationController(
    vsync: this,
    duration: const Duration(milliseconds: 900),
  )..repeat(reverse: true);

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: _controller,
      builder: (context, child) {
        final t = _controller.value;
        return Container(
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(10),
            boxShadow: [
              BoxShadow(
                color: const Color(
                  0xFFF59E0B,
                ).withValues(alpha: 0.25 + t * 0.45),
                blurRadius: 8 + t * 14,
                spreadRadius: 1 + t * 3,
              ),
            ],
          ),
          child: child,
        );
      },
      child: widget.child,
    );
  }
}
