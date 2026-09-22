import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../shared/data/lms_api_client.dart';
import '../models/qual_exam_schedule_model.dart';

class QualExamScheduleService {
  QualExamScheduleService(this._api);

  final LmsApiClient _api;

  Future<QualExamScheduleResult> fetchSchedules({int? year}) async {
    final targetYear = year ?? DateTime.now().year;
    final payload = await _api.getJson('/qual-exams?year=$targetYear');
    final rows = payload['items'] as List? ?? [];
    Map<String, dynamic>? data;
    DateTime? syncedAtDate;
    for (final raw in rows) {
      final row = Map<String, dynamic>.from(raw as Map);
      final inner = row['data'] is Map
          ? Map<String, dynamic>.from(row['data'] as Map)
          : row;
      if ('${row['key']}'.contains('$targetYear') || inner['year'] == targetYear) {
        data = inner;
        syncedAtDate = DateTime.tryParse('${row['syncedAt'] ?? inner['syncedAt'] ?? ''}');
        break;
      }
    }
    if (data == null) {
      throw StateError('$targetYear년 시험 일정이 아직 등록되지 않았습니다.');
    }
    final itemsRaw = data['items'] as List<dynamic>? ?? [];
    final items = itemsRaw
        .map((e) => QualExamScheduleModel.fromJson(Map<String, dynamic>.from(e as Map)))
        .toList()
      ..sort(
        (a, b) => (a.nextExamDate ?? '99991231').compareTo(b.nextExamDate ?? '99991231'),
      );
    return QualExamScheduleResult(
      year: data['year'] as int? ?? targetYear,
      totalCount: data['totalCount'] as int? ?? items.length,
      items: items,
      syncedAt: syncedAtDate,
    );
  }
}

final qualExamScheduleServiceProvider = Provider<QualExamScheduleService>((ref) {
  return QualExamScheduleService(lmsApiClient);
});
