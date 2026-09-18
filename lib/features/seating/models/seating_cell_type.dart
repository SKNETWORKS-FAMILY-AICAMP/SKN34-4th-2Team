/// 좌석 그리드 칸 타입
enum SeatingCellType {
  empty('empty'),
  seat('seat'),
  instructor('instructor'),
  door('door');

  const SeatingCellType(this.value);
  final String value;

  static SeatingCellType fromString(String? raw) {
    if (raw == 'aisle') return SeatingCellType.empty;
    return SeatingCellType.values.firstWhere(
      (e) => e.value == raw,
      orElse: () => SeatingCellType.empty,
    );
  }

  String get label {
    return switch (this) {
      SeatingCellType.empty => '빈칸',
      SeatingCellType.seat => '좌석',
      SeatingCellType.instructor => '강사석',
      SeatingCellType.door => '출입문',
    };
  }
}
