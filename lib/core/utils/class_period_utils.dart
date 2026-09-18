/// 교시별 자리 확인 시간표
/// - 09:00 ~ 17:50
/// - 정각 시작, :50 쉬는시간
/// - 12:50 ~ 14:00 점심 (교시 없음)
abstract final class ClassPeriodUtils {
  static const lunchStartHour = 12;
  static const lunchStartMinute = 50;
  static const lunchEndHour = 14;
  static const lunchEndMinute = 0;
  static const periodEndMinute = 50;

  /// 하루 교시 (시작 시각 기준 id)
  static const periods = <ClassPeriod>[
    ClassPeriod(id: '09', startHour: 9, label: '09:00'),
    ClassPeriod(id: '10', startHour: 10, label: '10:00'),
    ClassPeriod(id: '11', startHour: 11, label: '11:00'),
    ClassPeriod(id: '12', startHour: 12, label: '12:00'),
    ClassPeriod(id: '14', startHour: 14, label: '14:00'),
    ClassPeriod(id: '15', startHour: 15, label: '15:00'),
    ClassPeriod(id: '16', startHour: 16, label: '16:00'),
    ClassPeriod(id: '17', startHour: 17, label: '17:00'),
  ];

  static ClassPeriod? byId(String id) {
    for (final p in periods) {
      if (p.id == id) return p;
    }
    return null;
  }

  static bool isSameDay(DateTime a, DateTime b) =>
      a.year == b.year && a.month == b.month && a.day == b.day;

  static bool isLunchTime(DateTime now) {
    final mins = now.hour * 60 + now.minute;
    final start = lunchStartHour * 60 + lunchStartMinute;
    final end = lunchEndHour * 60 + lunchEndMinute;
    return mins >= start && mins < end;
  }

  /// 쉬는시간(:50~:59) 또는 점심이면 null
  static ClassPeriod? activePeriodAt(DateTime now) {
    if (isLunchTime(now)) return null;
    if (now.minute >= periodEndMinute) return null;
    return byId(now.hour.toString().padLeft(2, '0'));
  }

  /// 화면 기본 선택 교시
  static ClassPeriod suggestedPeriod({
    required DateTime day,
    DateTime? now,
  }) {
    final n = now ?? DateTime.now();
    if (!isSameDay(day, n)) return periods.first;

    final active = activePeriodAt(n);
    if (active != null) return active;

    // 쉬는시간·점심: 이미 시작한 마지막 교시
    final mins = n.hour * 60 + n.minute;
    ClassPeriod? lastStarted;
    for (final p in periods) {
      final start = p.startHour * 60;
      if (start <= mins) lastStarted = p;
    }
    return lastStarted ?? periods.first;
  }

  static String statusHint(DateTime now) {
    if (isLunchTime(now)) {
      return '점심시간 (12:50~14:00) — 자리 확인 없음';
    }
    if (now.minute >= periodEndMinute) {
      final nextHour = now.hour + 1;
      final next = byId(nextHour.toString().padLeft(2, '0'));
      if (next != null) {
        return '쉬는시간 — 다음 교시 ${next.label}';
      }
      return '쉬는시간';
    }
    final active = activePeriodAt(now);
    if (active != null) return '진행 중: ${active.label} 교시';
    return '';
  }

  static String rollCallDocId(String dateKey, String periodId) =>
      '${dateKey}_p$periodId';

  static String providerKey(String dateKey, String periodId) =>
      '$dateKey|$periodId';

  /// 직전 교시 (09 ← null, 14 ← 12)
  static ClassPeriod? previousPeriod(String periodId) {
    final i = periods.indexWhere((p) => p.id == periodId);
    if (i <= 0) return null;
    return periods[i - 1];
  }
}

class ClassPeriod {
  const ClassPeriod({
    required this.id,
    required this.startHour,
    required this.label,
  });

  final String id;
  final int startHour;
  final String label;

  String get endLabel =>
      '${startHour.toString().padLeft(2, '0')}:${ClassPeriodUtils.periodEndMinute}';

  String get rangeLabel => '$label ~ $endLabel';
}
