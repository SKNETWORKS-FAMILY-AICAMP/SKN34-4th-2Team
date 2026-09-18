import 'package:cloud_functions/cloud_functions.dart';

/// 예약 공지 Cloud Functions 호출
class ScheduledNoticeAdminService {
  ScheduledNoticeAdminService(this._functions);

  final FirebaseFunctions _functions;

  Future<int> publishSelected({
    required String cohortId,
    required List<String> scheduledIds,
  }) async {
    final callable = _functions.httpsCallable('publishScheduledNoticesNow');
    final result = await callable.call<Map<String, dynamic>>({
      'cohortId': cohortId,
      'scheduledIds': scheduledIds,
    });
    final data = result.data;
    return (data['published'] as num?)?.toInt() ?? 0;
  }
}
