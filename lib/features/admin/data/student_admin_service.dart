import 'package:cloud_functions/cloud_functions.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../shared/data/lms_api_client.dart';
import '../../../shared/models/student_intake_model.dart';

class CreateStudentResult {
  const CreateStudentResult({
    required this.uid,
    required this.email,
    required this.password,
    required this.displayName,
  });

  final String uid;
  final String email;
  final String password;
  final String displayName;

  factory CreateStudentResult.fromMap(Map<String, dynamic> data) {
    return CreateStudentResult(
      uid: data['uid'] as String? ?? '',
      email: data['email'] as String? ?? '',
      password: data['password'] as String? ?? '',
      displayName: data['displayName'] as String? ?? '',
    );
  }
}

class ResetPasswordResult {
  const ResetPasswordResult({
    required this.password,
    required this.passwordChanged,
  });

  final String password;
  final bool passwordChanged;

  factory ResetPasswordResult.fromMap(Map<String, dynamic> data) {
    return ResetPasswordResult(
      password: data['password'] as String? ?? '',
      passwordChanged: data['passwordChanged'] as bool? ?? false,
    );
  }
}

/// 관리자 — 학생 상담 등록 / 계정 관리
class StudentAdminService {
  StudentAdminService(this._api, this._functions);

  final LmsApiClient _api;
  final FirebaseFunctions _functions;

  Future<Map<String, int>> seedDemo34Roster() async {
    return const {'active': 0, 'hidden': 0, 'classDays': 0};
  }
  Stream<List<StudentIntakeModel>> watchCohortIntakes(String cohortId) async* {
    if (_api.snapshot.isEmpty) {
      try {
        await _api.bootstrap();
      } catch (_) {}
    }
    List<StudentIntakeModel> pick() => _api
        .list('studentIntakes')
        .where((row) => '${row['cohortId']}' == cohortId)
        .map((row) => StudentIntakeModel(
              uid: '${row['uid'] ?? row['id']}',
              email: row['email'] as String? ?? '',
              displayName: row['displayName'] as String? ?? '',
              cohortId: cohortId,
              cohortName: row['cohortName'] as String? ?? '',
              initialPassword: row['initialPassword'] as String? ?? '',
            ))
        .toList();
    yield pick();
    await for (final _ in _api.changes) {
      yield pick();
    }
  }

  Stream<StudentIntakeModel?> watchIntake(String uid) async* {
    await for (final list in watchCohortIntakes('')) {
      yield list.where((item) => item.uid == uid).firstOrNull;
    }
  }

  Future<CreateStudentResult> createStudentWithIntake(
    StudentIntakeFormData form,
  ) async {
    final callable = _functions.httpsCallable(
      'createStudentAccount',
      options: HttpsCallableOptions(timeout: const Duration(seconds: 60)),
    );
    final result = await callable.call<Map<String, dynamic>>(form.toJson());
    return CreateStudentResult.fromMap(result.data);
  }

  Future<ResetPasswordResult> resetStudentPassword(String uid) async {
    final callable = _functions.httpsCallable('resetStudentPassword');
    final result = await callable.call<Map<String, dynamic>>({'uid': uid});
    return ResetPasswordResult.fromMap(result.data);
  }

  Future<void> updateStudentWithIntake(
    String uid,
    StudentIntakeFormData form,
  ) async {
    final callable = _functions.httpsCallable(
      'updateStudentAccount',
      options: HttpsCallableOptions(timeout: const Duration(seconds: 60)),
    );
    await callable.call<Map<String, dynamic>>(form.toUpdateJson(uid));
  }

  Future<void> setStudentActiveStatus({
    required String uid,
    required bool active,
  }) async {
    final callable = _functions.httpsCallable('setStudentActiveStatus');
    await callable.call<Map<String, dynamic>>({
      'uid': uid,
      'active': active,
    });
  }
}

final studentAdminServiceProvider = Provider<StudentAdminService>((ref) {
  return StudentAdminService(
    lmsApiClient,
    FirebaseFunctions.instanceFor(region: 'asia-northeast3'),
  );
});
