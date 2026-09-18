import 'package:cloud_firestore/cloud_firestore.dart';

import 'seating_cell_type.dart';

const int kMaxCohortStudents = 30;
const int kLayoutRows = 8;
const int kLayoutCols = 10;
const String kInstructorFixtureId = '__instructor__';
const String kDoorFixtureId = '__door__';

/// 좌석 배치 그리드 한 칸
class SeatingCell {
  const SeatingCell({
    required this.seatId,
    required this.row,
    required this.col,
    required this.label,
    required this.type,
    this.groupId,
  });

  final String seatId;
  final int row;
  final int col;
  final String label;
  final SeatingCellType type;
  final String? groupId;

  bool get isSeat => type == SeatingCellType.seat;
  bool get isEmpty => type == SeatingCellType.empty;
  bool get isInstructor => type == SeatingCellType.instructor;
  bool get isDoor => type == SeatingCellType.door;

  factory SeatingCell.fromMap(Map<String, dynamic> data) {
    return SeatingCell(
      seatId: data['seatId'] as String? ?? '',
      row: data['row'] as int? ?? 0,
      col: data['col'] as int? ?? 0,
      label: data['label'] as String? ?? '',
      type: SeatingCellType.fromString(data['type'] as String?),
      groupId: data['groupId'] as String?,
    );
  }

  Map<String, dynamic> toMap() => {
        'seatId': seatId,
        'row': row,
        'col': col,
        'label': label,
        'type': type.value,
        if (groupId != null && groupId!.isNotEmpty) 'groupId': groupId,
      };

  SeatingCell copyWith({
    SeatingCellType? type,
    String? label,
    String? seatId,
    String? groupId,
    bool clearGroupId = false,
    int? row,
    int? col,
  }) {
    return SeatingCell(
      seatId: seatId ?? this.seatId,
      row: row ?? this.row,
      col: col ?? this.col,
      label: label ?? this.label,
      type: type ?? this.type,
      groupId: clearGroupId ? null : (groupId ?? this.groupId),
    );
  }
}

/// `cohorts/{cohortId}/seating/layout`
class SeatingLayoutModel {
  const SeatingLayoutModel({
    required this.rows,
    required this.cols,
    required this.cells,
    this.roomNumber,
    this.maxStudents = kMaxCohortStudents,
    this.updatedAt,
    this.updatedBy,
  });

  final int rows;
  final int cols;
  final String? roomNumber;
  final int maxStudents;
  final List<SeatingCell> cells;
  final DateTime? updatedAt;
  final String? updatedBy;

  List<SeatingCell> get seatCells =>
      cells.where((c) => c.isSeat).toList(growable: false);

  int get seatCount => seatCells.length;

  SeatingCell? cellAt(int row, int col) {
    for (final cell in cells) {
      if (cell.row == row && cell.col == col) return cell;
    }
    return null;
  }

  List<SeatingCell> cellsInGroup(String groupId) =>
      cells.where((c) => c.groupId == groupId).toList(growable: false);

  SeatingLayoutModel copyWith({
    List<SeatingCell>? cells,
    String? roomNumber,
    bool clearRoomNumber = false,
  }) {
    return SeatingLayoutModel(
      rows: rows,
      cols: cols,
      cells: cells ?? this.cells,
      roomNumber: clearRoomNumber ? null : (roomNumber ?? this.roomNumber),
      maxStudents: maxStudents,
      updatedAt: updatedAt,
      updatedBy: updatedBy,
    );
  }

  factory SeatingLayoutModel.fromFirestore(
    DocumentSnapshot<Map<String, dynamic>> doc,
  ) {
    final data = doc.data() ?? {};
    final rawCells = data['cells'] as List<dynamic>? ?? [];
    return SeatingLayoutModel(
      rows: data['rows'] as int? ?? kLayoutRows,
      cols: data['cols'] as int? ?? kLayoutCols,
      roomNumber: data['roomNumber'] as String?,
      maxStudents: data['maxStudents'] as int? ??
          data['maxSeats'] as int? ??
          kMaxCohortStudents,
      cells: rawCells
          .map((e) => SeatingCell.fromMap(e as Map<String, dynamic>))
          .toList(),
      updatedAt: (data['updatedAt'] as Timestamp?)?.toDate(),
      updatedBy: data['updatedBy'] as String?,
    );
  }

  Map<String, dynamic> toFirestore({String? updatedBy}) => {
        'rows': rows,
        'cols': cols,
        'maxStudents': maxStudents,
        if (roomNumber != null && roomNumber!.trim().isNotEmpty)
          'roomNumber': roomNumber!.trim(),
        'cells': cells.map((c) => c.toMap()).toList(),
        'updatedAt': FieldValue.serverTimestamp(),
        if (updatedBy != null) 'updatedBy': updatedBy,
      };

  /// 8×10 빈 그리드
  factory SeatingLayoutModel.defaultGrid() {
    return SeatingLayoutModel.defaultGridSized(
      rows: kLayoutRows,
      cols: kLayoutCols,
    );
  }

  factory SeatingLayoutModel.defaultGridSized({
    required int rows,
    required int cols,
  }) {
    final cells = <SeatingCell>[];
    for (var r = 0; r < rows; r++) {
      for (var c = 0; c < cols; c++) {
        cells.add(
          SeatingCell(
            seatId: '',
            row: r,
            col: c,
            label: '',
            type: SeatingCellType.empty,
          ),
        );
      }
    }
    return SeatingLayoutModel(rows: rows, cols: cols, cells: cells);
  }

  SeatingLayoutModel relabeled() {
    var num = 1;
    final sortedSeats = seatCells.toList()
      ..sort((a, b) {
        final dr = a.row.compareTo(b.row);
        return dr != 0 ? dr : a.col.compareTo(b.col);
      });
    final idByPos = <String, String>{};
    for (final c in sortedSeats) {
      idByPos['${c.row},${c.col}'] = '$num';
      num++;
    }
    final grid = cells.map((c) {
      if (!c.isSeat) return c;
      final id = idByPos['${c.row},${c.col}'] ?? '';
      return c.copyWith(seatId: id, label: id);
    }).toList();
    return copyWith(cells: grid);
  }

  bool _isEmptyAt(List<SeatingCell> grid, int row, int col) {
    if (row < 0 || col < 0 || row >= rows || col >= cols) return false;
    final cell = grid.firstWhere(
      (c) => c.row == row && c.col == col,
      orElse: () => const SeatingCell(
        seatId: '',
        row: -1,
        col: -1,
        label: '',
        type: SeatingCellType.empty,
      ),
    );
    return cell.row >= 0 && cell.isEmpty;
  }

  bool _canOccupy(
    int row,
    int col, {
    String? ignoreGroupId,
    String? ignoreFixtureId,
  }) {
    final cell = cellAt(row, col);
    if (cell == null) return false;
    if (cell.isEmpty) return true;
    if (ignoreGroupId != null && cell.groupId == ignoreGroupId) return true;
    if (ignoreFixtureId != null && cell.groupId == ignoreFixtureId) {
      return true;
    }
    return false;
  }

  bool canPlaceSpan(
    int row,
    int col,
    int width, {
    String? ignoreGroupId,
    String? ignoreFixtureId,
  }) {
    if (col + width > cols) return false;
    for (var i = 0; i < width; i++) {
      if (!_canOccupy(
        row,
        col + i,
        ignoreGroupId: ignoreGroupId,
        ignoreFixtureId: ignoreFixtureId,
      )) {
        return false;
      }
    }
    return true;
  }

  bool canPlaceTable2(int row, int col, {String? ignoreGroupId}) =>
      canPlaceSpan(row, col, 2, ignoreGroupId: ignoreGroupId);

  bool canPlaceTable3(int row, int col, {String? ignoreGroupId}) =>
      canPlaceSpan(row, col, 3, ignoreGroupId: ignoreGroupId);

  bool canPlaceInstructor(int row, int col, {bool moving = false}) =>
      canPlaceSpan(
        row,
        col,
        2,
        ignoreFixtureId: moving ? kInstructorFixtureId : null,
      );

  bool canPlaceDoor(int row, int col, {bool moving = false}) => canPlaceSpan(
        row,
        col,
        2,
        ignoreFixtureId: moving ? kDoorFixtureId : null,
      );

  SeatingLayoutModel _clearFixture(String fixtureId) {
    final grid = cells.map((c) {
      if (c.groupId == fixtureId) {
        return c.copyWith(
          type: SeatingCellType.empty,
          seatId: '',
          label: '',
          clearGroupId: true,
        );
      }
      return c;
    }).toList();
    return copyWith(cells: grid);
  }

  SeatingLayoutModel placeInstructor(int row, int col) {
    if (!canPlaceInstructor(row, col)) return this;
    var layout = _clearFixture(kInstructorFixtureId);
    final grid = layout.cells.map((c) {
      if (c.row == row && (c.col == col || c.col == col + 1)) {
        return c.copyWith(
          type: SeatingCellType.instructor,
          groupId: kInstructorFixtureId,
          seatId: '',
          label: '',
          clearGroupId: false,
        );
      }
      return c;
    }).toList();
    return layout.copyWith(cells: grid);
  }

  SeatingLayoutModel placeDoor(int row, int col) {
    if (!canPlaceDoor(row, col)) return this;
    var layout = _clearFixture(kDoorFixtureId);
    final grid = layout.cells.map((c) {
      if (c.row == row && (c.col == col || c.col == col + 1)) {
        return c.copyWith(
          type: SeatingCellType.door,
          groupId: kDoorFixtureId,
          seatId: '',
          label: '',
        );
      }
      return c;
    }).toList();
    return layout.copyWith(cells: grid);
  }

  SeatingLayoutModel placeTable(int row, int col, int width, String groupId) {
    final can = switch (width) {
      2 => canPlaceTable2(row, col),
      3 => canPlaceTable3(row, col),
      _ => false,
    };
    if (!can) return this;
    final grid = cells.map((c) {
      if (c.row == row && c.col >= col && c.col < col + width) {
        return c.copyWith(type: SeatingCellType.seat, groupId: groupId);
      }
      return c;
    }).toList();
    return copyWith(cells: grid).relabeled();
  }

  /// 테이블 그룹 전체를 좌석 틀에서 제거하고 남은 좌석 번호를 다시 매긴다.
  SeatingLayoutModel removeGroup(String groupId) {
    final grid = cells.map((cell) {
      if (cell.groupId != groupId) return cell;
      return cell.copyWith(
        type: SeatingCellType.empty,
        seatId: '',
        label: '',
        clearGroupId: true,
      );
    }).toList();
    return copyWith(cells: grid).relabeled();
  }

  SeatingLayoutModel? moveGroup(String groupId, int targetRow, int targetCol) {
    final group = cellsInGroup(groupId);
    if (group.isEmpty) return null;

    final minR = group.map((c) => c.row).reduce((a, b) => a < b ? a : b);
    final minC = group.map((c) => c.col).reduce((a, b) => a < b ? a : b);
    final dR = targetRow - minR;
    final dC = targetCol - minC;
    if (dR == 0 && dC == 0) return this;

    final grid = List<SeatingCell>.from(cells);

    for (var i = 0; i < grid.length; i++) {
      if (grid[i].groupId == groupId) {
        grid[i] = grid[i].copyWith(
          type: SeatingCellType.empty,
          seatId: '',
          label: '',
          clearGroupId: true,
        );
      }
    }

    for (final c in group) {
      final nr = c.row + dR;
      final nc = c.col + dC;
      if (!_isEmptyAt(grid, nr, nc)) return null;
    }

    for (final c in group) {
      final nr = c.row + dR;
      final nc = c.col + dC;
      final idx = grid.indexWhere((x) => x.row == nr && x.col == nc);
      if (idx < 0) return null;
      grid[idx] = grid[idx].copyWith(
        type: SeatingCellType.seat,
        groupId: groupId,
      );
    }

    return copyWith(cells: grid).relabeled();
  }

  SeatingLayoutModel? moveFixture(String fixtureId, int toRow, int toCol) {
    if (fixtureId == kInstructorFixtureId) {
      if (!canPlaceInstructor(toRow, toCol, moving: true)) return null;
      return placeInstructor(toRow, toCol);
    }
    if (fixtureId == kDoorFixtureId) {
      if (!canPlaceDoor(toRow, toCol, moving: true)) return null;
      return placeDoor(toRow, toCol);
    }
    return null;
  }
}
