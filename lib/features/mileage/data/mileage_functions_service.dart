import 'package:cloud_functions/cloud_functions.dart';

/// 마일리지 Cloud Functions 호출
class MileageFunctionsService {
  MileageFunctionsService(this._functions);

  final FirebaseFunctions _functions;

  Future<Map<String, dynamic>> submitPurchaseRequest({
    required String cohortId,
    String? studentNote,
  }) async {
    final result = await _functions.httpsCallable('submitPurchaseRequest').call({
      'cohortId': cohortId,
      if (studentNote != null && studentNote.isNotEmpty)
        'studentNote': studentNote,
    });
    return Map<String, dynamic>.from(result.data as Map);
  }

  Future<Map<String, dynamic>> reviewPurchaseRequest({
    required String cohortId,
    required String requestId,
    required String status,
    String? managerMemo,
    String? managerPurchaseLink,
  }) async {
    final result =
        await _functions.httpsCallable('reviewPurchaseRequest').call({
      'cohortId': cohortId,
      'requestId': requestId,
      'status': status,
      if (managerMemo != null) 'managerMemo': managerMemo,
      if (managerPurchaseLink != null)
        'managerPurchaseLink': managerPurchaseLink,
    });
    return Map<String, dynamic>.from(result.data as Map);
  }

  Future<Map<String, dynamic>> cancelPurchaseRequest({
    required String cohortId,
    required String requestId,
  }) async {
    final result =
        await _functions.httpsCallable('cancelPurchaseRequest').call({
      'cohortId': cohortId,
      'requestId': requestId,
    });
    return Map<String, dynamic>.from(result.data as Map);
  }

  Future<Map<String, dynamic>> adjustMileage({
    required String cohortId,
    required String userId,
    required int amount,
    required String reason,
  }) async {
    final result = await _functions.httpsCallable('adjustMileage').call({
      'cohortId': cohortId,
      'userId': userId,
      'amount': amount,
      'reason': reason,
    });
    return Map<String, dynamic>.from(result.data as Map);
  }

  /// 관리자 전용 — 종강+14일 소멸 배치 수동 실행 (mockDate: ISO 문자열)
  Future<Map<String, dynamic>> expireMileageNow({String? mockDate}) async {
    final result = await _functions.httpsCallable('expireMileageNow').call({
      if (mockDate != null) 'mockDate': mockDate,
    });
    return Map<String, dynamic>.from(result.data as Map);
  }
}
