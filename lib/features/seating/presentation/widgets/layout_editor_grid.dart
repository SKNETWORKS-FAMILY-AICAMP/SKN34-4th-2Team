import 'package:flutter/material.dart';

import '../../../../core/theme/app_colors.dart';
import '../../models/layout_drag_payload.dart';
import '../../models/seat_group_helper.dart';
import '../../models/seating_layout_model.dart';
import '../../../../core/theme/app_space.dart';

/// 관리자 — 드래그로 테이블·강사석·출입문 배치
class LayoutEditorGrid extends StatelessWidget {
  const LayoutEditorGrid({
    super.key,
    required this.layout,
    required this.onLayoutChanged,
    required this.newGroupId,
  });

  final SeatingLayoutModel layout;
  final ValueChanged<SeatingLayoutModel> onLayoutChanged;
  final String Function() newGroupId;

  static const double _cellW = 76;
  static const double _cellH = 68;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        const _PaletteBar(),
        SizedBox(height: AppSpace.s(10)),
        _TrashDropTarget(
          onDeleteGroup: (groupId) =>
              onLayoutChanged(layout.removeGroup(groupId)),
        ),
        SizedBox(height: AppSpace.s(12)),
        Center(
          child: Text(
            '▲ 강사석 방향',
            style: TextStyle(
              fontSize: 12,
              fontWeight: FontWeight.w600,
              color: AppColors.textSecondary,
            ),
          ),
        ),
        SizedBox(height: AppSpace.s(8)),
        ...List.generate(layout.rows, (row) {
          return Padding(
            padding: EdgeInsets.only(bottom: AppSpace.s(8)),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: List.generate(layout.cols, (col) {
                final cell = layout.cellAt(row, col);
                if (cell == null) {
                  return const SizedBox(width: _cellW, height: _cellH);
                }
                return _buildCell(cell, row, col);
              }),
            ),
          );
        }),
      ],
    );
  }

  Widget _buildCell(SeatingCell cell, int row, int col) {
    final hPadLeft = col > 0 && sameCellGroup(layout, cell, row, col - 1)
        ? 0.0
        : 4.0;
    final hPadRight =
        col < layout.cols - 1 && sameCellGroup(layout, cell, row, col + 1)
        ? 0.0
        : 4.0;

    Widget child;
    if (cell.isInstructor) {
      child = _fixtureWidget(
        cell: cell,
        row: row,
        col: col,
        label: '강사석',
        icon: Icons.person,
        fixtureKind: 'instructor',
        bg: AppColors.tint(const Color(0xFFF1F5F9)),
        border: const Color(0xFF64748B),
      );
    } else if (cell.isDoor) {
      child = _fixtureWidget(
        cell: cell,
        row: row,
        col: col,
        label: '출입문',
        icon: Icons.door_front_door_outlined,
        fixtureKind: 'door',
        bg: AppColors.tint(const Color(0xFFFEF3C7)),
        border: const Color(0xFFF59E0B),
      );
    } else if (cell.isSeat) {
      child = _seatWidget(cell);
    } else {
      child = _emptyDropTarget(row, col);
    }

    return Padding(
      padding: EdgeInsets.only(left: hPadLeft, right: hPadRight),
      child: child,
    );
  }

  Widget _emptyDropTarget(int row, int col) {
    return DragTarget<LayoutDragPayload>(
      onWillAcceptWithDetails: (d) => _canAccept(d.data, row, col),
      onAcceptWithDetails: (d) => _handleDrop(d.data, row, col),
      builder: (context, candidate, _) {
        final hover = candidate.isNotEmpty;
        return Container(
          width: _cellW,
          height: _cellH,
          decoration: BoxDecoration(
            color: hover
                ? AppColors.primaryLight
                : AppColors.tint(const Color(0xFFFAFAFA)),
            borderRadius: BorderRadius.circular(8),
            border: Border.all(
              color: hover
                  ? AppColors.primary
                  : AppColors.tint(const Color(0xFFE2E8F0)),
              width: hover ? 2 : 1,
            ),
          ),
        );
      },
    );
  }

  Widget _fixtureWidget({
    required SeatingCell cell,
    required int row,
    required int col,
    required String label,
    required IconData icon,
    required String fixtureKind,
    required Color bg,
    required Color border,
  }) {
    final edges = computeGroupEdges(layout, cell);
    final leader = isFixtureLeader(layout, cell);

    final content = Container(
      width: _cellW,
      height: _cellH,
      decoration: BoxDecoration(
        color: bg,
        borderRadius: edges.borderRadius,
        border: groupBorder(edges, border, width: 1.5),
      ),
      child: leader
          ? Stack(
              children: [
                Center(
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Icon(icon, size: 18, color: border),
                      SizedBox(height: AppSpace.s(2)),
                      Text(
                        label,
                        style: TextStyle(
                          fontSize: 10,
                          fontWeight: FontWeight.w600,
                          color: border,
                        ),
                      ),
                    ],
                  ),
                ),
                const Positioned(
                  right: 2,
                  top: 2,
                  child: Icon(
                    Icons.drag_indicator,
                    size: 12,
                    color: Colors.grey,
                  ),
                ),
              ],
            )
          : null,
    );

    if (!leader) return content;

    return Draggable<LayoutDragPayload>(
      data: LayoutDragPayload(
        fixtureKind: fixtureKind,
        fixtureFromRow: row,
        fixtureFromCol: col,
      ),
      feedback: Material(
        elevation: 6,
        borderRadius: BorderRadius.circular(8),
        child: Opacity(
          opacity: 0.92,
          child: Container(
            width: _cellW * 2 + 8,
            height: _cellH,
            alignment: Alignment.center,
            decoration: BoxDecoration(
              color: bg,
              borderRadius: BorderRadius.circular(8),
              border: Border.all(color: border, width: 2),
            ),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Icon(icon, size: 18, color: border),
                SizedBox(width: AppSpace.s(6)),
                Text(
                  label,
                  style: TextStyle(fontWeight: FontWeight.w600, color: border),
                ),
              ],
            ),
          ),
        ),
      ),
      childWhenDragging: Opacity(opacity: 0.25, child: content),
      child: DragTarget<LayoutDragPayload>(
        onWillAcceptWithDetails: (d) => _canAccept(d.data, row, col),
        onAcceptWithDetails: (d) => _handleDrop(d.data, row, col),
        builder: (context, candidate, _) => content,
      ),
    );
  }

  Widget _seatWidget(SeatingCell cell) {
    final edges = computeGroupEdges(layout, cell);
    final group = cell.groupId != null
        ? layout.cellsInGroup(cell.groupId!)
        : [cell];
    group.sort((a, b) {
      final dr = a.row.compareTo(b.row);
      return dr != 0 ? dr : a.col.compareTo(b.col);
    });
    final isGroupLeader = group.isNotEmpty && group.first.seatId == cell.seatId;

    final content = Container(
      width: _cellW,
      height: _cellH,
      padding: EdgeInsets.all(AppSpace.s(4)),
      decoration: BoxDecoration(
        color: edges.isGrouped
            ? AppColors.primaryLight
            : AppColors.tint(const Color(0xFFF8FAFC)),
        borderRadius: edges.borderRadius,
        border: edges.isGrouped
            ? groupBorder(edges, AppColors.primary.withValues(alpha: 0.35))
            : Border.all(color: AppColors.border),
      ),
      child: Stack(
        children: [
          Center(
            child: cell.label.isNotEmpty
                ? Text(
                    '${cell.label}번',
                    style: TextStyle(
                      fontSize: 10,
                      color: AppColors.textSecondary,
                      fontWeight: FontWeight.w600,
                    ),
                  )
                : null,
          ),
          if (edges.isGrouped && isGroupLeader)
            Positioned(
              right: 0,
              top: 0,
              child: Icon(
                Icons.drag_indicator,
                size: 14,
                color: AppColors.textSecondary,
              ),
            ),
        ],
      ),
    );

    if (cell.groupId == null || !isGroupLeader) return content;

    return Draggable<LayoutDragPayload>(
      data: LayoutDragPayload(groupId: cell.groupId),
      feedback: Material(
        elevation: 6,
        borderRadius: BorderRadius.circular(8),
        child: _groupFeedback(cell.groupId!),
      ),
      childWhenDragging: Opacity(opacity: 0.3, child: content),
      child: content,
    );
  }

  Widget _groupFeedback(String groupId) {
    final group = layout.cellsInGroup(groupId)
      ..sort((a, b) {
        final dr = a.row.compareTo(b.row);
        return dr != 0 ? dr : a.col.compareTo(b.col);
      });
    return Container(
      padding: EdgeInsets.all(AppSpace.s(8)),
      decoration: BoxDecoration(
        color: AppColors.primaryLight,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: AppColors.primary.withValues(alpha: 0.35), width: 2),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          for (var i = 0; i < group.length; i++) ...[
            if (i > 0) SizedBox(width: AppSpace.s(4)),
            Container(
              width: 56,
              height: AppSpace.row(48),
              alignment: Alignment.center,
              decoration: BoxDecoration(
                color: AppColors.surface,
                borderRadius: BorderRadius.circular(6),
                border: Border.all(color: AppColors.primary.withValues(alpha: 0.35)),
              ),
              child: Text(
                group[i].label.isNotEmpty ? '${group[i].label}번' : '좌석',
                style: const TextStyle(
                  fontSize: 10,
                  fontWeight: FontWeight.w600,
                ),
              ),
            ),
          ],
        ],
      ),
    );
  }

  bool _canAccept(LayoutDragPayload payload, int row, int col) {
    if (payload.isFromPalette) {
      return switch (payload.paletteItem!) {
        LayoutPaletteItem.instructor => layout.canPlaceInstructor(row, col),
        LayoutPaletteItem.door => layout.canPlaceDoor(row, col),
        LayoutPaletteItem.table2 => layout.canPlaceTable2(row, col),
        LayoutPaletteItem.table3 => layout.canPlaceTable3(row, col),
      };
    }
    if (payload.isFixtureMove) {
      return switch (payload.fixtureKind) {
        'instructor' => layout.canPlaceInstructor(row, col, moving: true),
        'door' => layout.canPlaceDoor(row, col, moving: true),
        _ => false,
      };
    }
    if (payload.isTableMove) {
      final group = layout.cellsInGroup(payload.groupId!);
      if (group.isEmpty) return false;
      final minR = group.map((c) => c.row).reduce((a, b) => a < b ? a : b);
      final minC = group.map((c) => c.col).reduce((a, b) => a < b ? a : b);
      final dR = row - minR;
      final dC = col - minC;
      for (final c in group) {
        final nr = c.row + dR;
        final nc = c.col + dC;
        final target = layout.cellAt(nr, nc);
        if (target == null) return false;
        if (target.isEmpty) continue;
        if (target.groupId == payload.groupId) continue;
        return false;
      }
      return true;
    }
    return false;
  }

  void _handleDrop(LayoutDragPayload payload, int row, int col) {
    SeatingLayoutModel? next;

    if (payload.isFromPalette) {
      next = switch (payload.paletteItem!) {
        LayoutPaletteItem.instructor => layout.placeInstructor(row, col),
        LayoutPaletteItem.door => layout.placeDoor(row, col),
        LayoutPaletteItem.table2 => layout.placeTable(
          row,
          col,
          2,
          newGroupId(),
        ),
        LayoutPaletteItem.table3 => layout.placeTable(
          row,
          col,
          3,
          newGroupId(),
        ),
      };
    } else if (payload.isFixtureMove) {
      final fixtureId = payload.fixtureKind == 'instructor'
          ? kInstructorFixtureId
          : kDoorFixtureId;
      next = layout.moveFixture(fixtureId, row, col);
    } else if (payload.isTableMove) {
      next = layout.moveGroup(payload.groupId!, row, col);
    }

    if (next != null) onLayoutChanged(next);
  }
}

class _TrashDropTarget extends StatelessWidget {
  const _TrashDropTarget({required this.onDeleteGroup});

  final ValueChanged<String> onDeleteGroup;

  @override
  Widget build(BuildContext context) {
    return DragTarget<LayoutDragPayload>(
      onWillAcceptWithDetails: (details) => details.data.isTableMove,
      onAcceptWithDetails: (details) {
        final groupId = details.data.groupId;
        if (groupId != null) onDeleteGroup(groupId);
      },
      builder: (context, candidates, _) {
        final hovering = candidates.isNotEmpty;
        return AnimatedContainer(
          duration: const Duration(milliseconds: 150),
          height: AppSpace.row(48),
          decoration: BoxDecoration(
            color: hovering
                ? AppColors.error.withValues(alpha: 0.12)
                : AppColors.tint(const Color(0xFFFFF7F7)),
            borderRadius: BorderRadius.circular(10),
            border: Border.all(
              color: hovering ? AppColors.error : AppColors.border,
              width: hovering ? 2 : 1,
            ),
          ),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Icon(
                Icons.delete_outline,
                color: hovering ? AppColors.error : AppColors.textSecondary,
              ),
              SizedBox(width: AppSpace.s(6)),
              Text(
                hovering ? '놓아서 좌석 삭제' : '좌석을 이곳에 끌어 놓아 삭제',
                style: TextStyle(
                  fontWeight: FontWeight.w600,
                  color: hovering ? AppColors.error : AppColors.textSecondary,
                ),
              ),
            ],
          ),
        );
      },
    );
  }
}

class _PaletteBar extends StatelessWidget {
  const _PaletteBar();

  @override
  Widget build(BuildContext context) {
    return Wrap(
      spacing: 10,
      runSpacing: 8,
      crossAxisAlignment: WrapCrossAlignment.center,
      children: [
        const Text(
          '끌어다 놓기:',
          style: TextStyle(fontSize: 13, fontWeight: FontWeight.w600),
        ),
        _paletteChip(
          label: '강사석 (2칸)',
          icon: Icons.person,
          data: const LayoutDragPayload(
            paletteItem: LayoutPaletteItem.instructor,
          ),
        ),
        _paletteChip(
          label: '출입문 (2칸)',
          icon: Icons.door_front_door_outlined,
          data: const LayoutDragPayload(paletteItem: LayoutPaletteItem.door),
        ),
        _paletteChip(
          label: '2인 테이블',
          icon: Icons.table_restaurant,
          data: const LayoutDragPayload(paletteItem: LayoutPaletteItem.table2),
        ),
        _paletteChip(
          label: '3인 테이블',
          icon: Icons.table_bar,
          data: const LayoutDragPayload(paletteItem: LayoutPaletteItem.table3),
        ),
      ],
    );
  }

  Widget _paletteChip({
    required String label,
    required IconData icon,
    required LayoutDragPayload data,
  }) {
    return Draggable<LayoutDragPayload>(
      data: data,
      feedback: Material(
        elevation: 4,
        borderRadius: BorderRadius.circular(8),
        child: Container(
          padding: EdgeInsets.symmetric(horizontal: AppSpace.s(12), vertical: AppSpace.s(8)),
          decoration: BoxDecoration(
            color: AppColors.surface,
            borderRadius: BorderRadius.circular(8),
            border: Border.all(color: AppColors.border),
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(icon, size: 18),
              SizedBox(width: AppSpace.s(6)),
              Text(label, style: const TextStyle(fontWeight: FontWeight.w600)),
            ],
          ),
        ),
      ),
      childWhenDragging: Opacity(
        opacity: 0.4,
        child: _chipBody(label, icon),
      ),
      child: _chipBody(label, icon),
    );
  }

  Widget _chipBody(String label, IconData icon) {
    return Container(
      padding: EdgeInsets.symmetric(horizontal: AppSpace.s(12), vertical: AppSpace.s(8)),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: AppColors.border),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 18, color: AppColors.textSecondary),
          SizedBox(width: AppSpace.s(6)),
          Text(label),
          SizedBox(width: AppSpace.s(4)),
          Icon(Icons.drag_indicator, size: 16, color: AppColors.textHint),
        ],
      ),
    );
  }
}
