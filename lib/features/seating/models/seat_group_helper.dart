import 'package:flutter/material.dart';

import 'seating_layout_model.dart';

class SeatGroupEdges {
  const SeatGroupEdges({
    required this.top,
    required this.bottom,
    required this.left,
    required this.right,
    required this.isGrouped,
  });

  final bool top;
  final bool bottom;
  final bool left;
  final bool right;
  final bool isGrouped;

  BorderRadius get borderRadius {
    if (!isGrouped) return BorderRadius.circular(8);
    return BorderRadius.only(
      topLeft: (top && left) ? const Radius.circular(8) : Radius.zero,
      topRight: (top && right) ? const Radius.circular(8) : Radius.zero,
      bottomLeft: (bottom && left) ? const Radius.circular(8) : Radius.zero,
      bottomRight: (bottom && right) ? const Radius.circular(8) : Radius.zero,
    );
  }
}

bool sameCellGroup(SeatingLayoutModel layout, SeatingCell a, int row, int col) {
  final other = layout.cellAt(row, col);
  if (other == null) return false;
  final ga = a.groupId;
  final gb = other.groupId;
  if (ga == null || ga.isEmpty || ga != gb) return false;
  return a.type == other.type;
}

bool sameSeatGroup(SeatingLayoutModel layout, SeatingCell a, int row, int col) {
  if (!a.isSeat) return false;
  final other = layout.cellAt(row, col);
  return other != null && other.isSeat && sameCellGroup(layout, a, row, col);
}

SeatGroupEdges computeGroupEdges(SeatingLayoutModel layout, SeatingCell cell) {
  if (cell.groupId == null || cell.groupId!.isEmpty) {
    return const SeatGroupEdges(
      top: true,
      bottom: true,
      left: true,
      right: true,
      isGrouped: false,
    );
  }
  return SeatGroupEdges(
    top: !sameCellGroup(layout, cell, cell.row - 1, cell.col),
    bottom: !sameCellGroup(layout, cell, cell.row + 1, cell.col),
    left: !sameCellGroup(layout, cell, cell.row, cell.col - 1),
    right: !sameCellGroup(layout, cell, cell.row, cell.col + 1),
    isGrouped: true,
  );
}

Border groupBorder(SeatGroupEdges edges, Color color, {double width = 1.5}) {
  final side = BorderSide(color: color, width: width);
  return Border(
    top: edges.top ? side : BorderSide.none,
    bottom: edges.bottom ? side : BorderSide.none,
    left: edges.left ? side : BorderSide.none,
    right: edges.right ? side : BorderSide.none,
  );
}

bool isFixtureLeader(SeatingLayoutModel layout, SeatingCell cell) {
  if (!cell.isInstructor && !cell.isDoor) return true;
  final left = layout.cellAt(cell.row, cell.col - 1);
  if (left == null) return true;
  return !(left.type == cell.type && left.groupId == cell.groupId);
}
