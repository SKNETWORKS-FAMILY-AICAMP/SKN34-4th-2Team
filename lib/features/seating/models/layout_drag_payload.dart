/// 틀 설정 — 팔레트/그리드 드래그 데이터
enum LayoutPaletteItem {
  instructor,
  door,
  table2,
  table3,
}

class LayoutDragPayload {
  const LayoutDragPayload({
    this.paletteItem,
    this.groupId,
    this.fixtureKind,
    this.fixtureFromRow,
    this.fixtureFromCol,
  });

  final LayoutPaletteItem? paletteItem;

  /// 테이블 이동
  final String? groupId;

  /// `instructor` | `door` — 2칸 고정 배치 이동
  final String? fixtureKind;

  final int? fixtureFromRow;
  final int? fixtureFromCol;

  bool get isFromPalette => paletteItem != null;
  bool get isTableMove => groupId != null;
  bool get isFixtureMove =>
      fixtureKind != null &&
      fixtureFromRow != null &&
      fixtureFromCol != null;
}
