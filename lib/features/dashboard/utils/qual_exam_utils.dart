import '../../../shared/models/qual_exam_schedule_model.dart';

/// 국가자격 시험일정 표시·필터 유틸
abstract final class QualExamUtils {
  static int todayYmd() {
    final now = DateTime.now();
    return now.year * 10000 + now.month * 100 + now.day;
  }

  static int? parseYmd(String? ymd) {
    if (ymd == null || ymd.length < 8) return null;
    return int.tryParse(ymd.substring(0, 8));
  }

  static bool isUpcoming(QualExamScheduleModel item) {
    final ymd = parseYmd(item.nextExamDate);
    if (ymd == null) return false;
    return ymd >= todayYmd();
  }

  static int daysUntil(String? ymd) {
    final parsed = parseYmd(ymd);
    if (parsed == null) return 9999;
    final y = parsed ~/ 10000;
    final m = (parsed ~/ 100) % 100;
    final d = parsed % 100;
    final exam = DateTime(y, m, d);
    final now = DateTime.now();
    final today = DateTime(now.year, now.month, now.day);
    return exam.difference(today).inDays;
  }

  static String ddayLabel(String? ymd) {
    final days = daysUntil(ymd);
    if (days == 9999) return '—';
    if (days == 0) return 'D-DAY';
    if (days > 0) return 'D-$days';
    return '종료';
  }

  /// API description 원문 우선 — 회차·종목 구분용
  static String displayTitle(QualExamScheduleModel item) {
    final desc = item.description.trim();
    if (desc.isNotEmpty) return desc;
    if (item.qualgbNm.isNotEmpty) {
      return '${item.qualgbNm} ${item.implYy}년 ${item.implSeq}회';
    }
    return '자격 시험 ${item.implSeq}회';
  }

  static String _searchHaystack(QualExamScheduleModel item) {
    return [
      item.description,
      item.qualgbNm,
      item.qualgbCd,
      displayTitle(item),
      item.nextExamLabel,
      item.implSeq.toString(),
      item.implYy,
    ].join(' ').toLowerCase();
  }

  static bool matchesKeyword(QualExamScheduleModel item, String? keyword) {
    final q = keyword?.trim().toLowerCase();
    if (q == null || q.isEmpty) return true;
    return _searchHaystack(item).contains(q);
  }

  static List<QualExamScheduleModel> prepareUpcoming(
    List<QualExamScheduleModel> items, {
    String? keyword,
  }) {
    var list = items.where(isUpcoming).toList();
    list = list.where((e) => matchesKeyword(e, keyword)).toList();
    list.sort(
      (a, b) => (parseYmd(a.nextExamDate) ?? 99991231)
          .compareTo(parseYmd(b.nextExamDate) ?? 99991231),
    );
    return list;
  }

  static Map<String, List<QualExamScheduleModel>> groupByMonth(
    List<QualExamScheduleModel> items,
  ) {
    final map = <String, List<QualExamScheduleModel>>{};
    for (final item in items) {
      final ymd = parseYmd(item.nextExamDate);
      final label = ymd != null ? _monthLabel(ymd) : '일정 미정';
      map.putIfAbsent(label, () => []).add(item);
    }
    return map;
  }

  static String _monthLabel(int ymd) {
    final y = ymd ~/ 10000;
    final m = (ymd ~/ 100) % 100;
    return '$y년 $m월';
  }
}
