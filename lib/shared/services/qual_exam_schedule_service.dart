import 'package:cloud_firestore/cloud_firestore.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/constants/firestore_paths.dart';
import '../models/qual_exam_schedule_model.dart';
import '../providers/firebase_providers.dart';

/// Firestore 캐시에서 국가자격 시험일정 조회 (Cloud Function 경유 없음)
class QualExamScheduleService {
  QualExamScheduleService(this._firestore);

  final FirebaseFirestore _firestore;

  Future<QualExamScheduleResult> fetchSchedules({int? year}) async {
    final targetYear = year ?? DateTime.now().year;
    final doc = await _firestore
        .doc(FirestorePaths.qualExamSchedules(targetYear))
        .get();

    if (!doc.exists || doc.data() == null) {
      throw StateError(
        '$targetYear년 시험 일정이 아직 등록되지 않았습니다.',
      );
    }

    final data = doc.data()!;
    final itemsRaw = data['items'] as List<dynamic>? ?? [];
    final items = itemsRaw
        .map(
          (e) => QualExamScheduleModel.fromJson(
            Map<String, dynamic>.from(e as Map),
          ),
        )
        .toList()
      ..sort(
        (a, b) => (a.nextExamDate ?? '99991231')
            .compareTo(b.nextExamDate ?? '99991231'),
      );

    final syncedAt = data['syncedAt'];
    DateTime? syncedAtDate;
    if (syncedAt is Timestamp) {
      syncedAtDate = syncedAt.toDate();
    }

    return QualExamScheduleResult(
      year: data['year'] as int? ?? targetYear,
      totalCount: data['totalCount'] as int? ?? items.length,
      items: items,
      syncedAt: syncedAtDate,
    );
  }
}

final qualExamScheduleServiceProvider = Provider<QualExamScheduleService>((ref) {
  return QualExamScheduleService(ref.watch(firestoreProvider));
});
