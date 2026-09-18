import 'package:cloud_functions/cloud_functions.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

class InstructorAccountResult {
  const InstructorAccountResult({
    required this.uid,
    required this.email,
    required this.password,
    required this.displayName,
  });

  final String uid;
  final String email;
  final String password;
  final String displayName;

  factory InstructorAccountResult.fromMap(Map<String, dynamic> data) {
    return InstructorAccountResult(
      uid: data['uid'] as String? ?? '',
      email: data['email'] as String? ?? '',
      password: data['password'] as String? ?? '',
      displayName: data['displayName'] as String? ?? '',
    );
  }
}

class InstructorAdminService {
  InstructorAdminService(this._functions);

  final FirebaseFunctions _functions;

  Future<InstructorAccountResult> createInstructor({
    required String displayName,
    required String cohortId,
    required String cohortName,
    String? email,
  }) async {
    final callable = _functions.httpsCallable(
      'createInstructorAccount',
      options: HttpsCallableOptions(timeout: const Duration(seconds: 60)),
    );
    final result = await callable.call<Map<String, dynamic>>({
      'displayName': displayName,
      'cohortId': cohortId,
      'cohortName': cohortName,
      if (email != null && email.trim().isNotEmpty) 'email': email.trim(),
    });
    return InstructorAccountResult.fromMap(result.data);
  }

  Future<void> updateInstructor({
    required String uid,
    required String displayName,
    required String cohortId,
    required String cohortName,
  }) async {
    final callable = _functions.httpsCallable('updateInstructorAccount');
    await callable.call<Map<String, dynamic>>({
      'uid': uid,
      'displayName': displayName,
      'cohortId': cohortId,
      'cohortName': cohortName,
    });
  }

  Future<InstructorAccountResult> resetPassword(String uid) async {
    final callable = _functions.httpsCallable('resetInstructorPassword');
    final result = await callable.call<Map<String, dynamic>>({'uid': uid});
    return InstructorAccountResult.fromMap(result.data);
  }

  Future<void> setActiveStatus({
    required String uid,
    required bool active,
  }) async {
    final callable = _functions.httpsCallable('setInstructorActiveStatus');
    await callable.call<Map<String, dynamic>>({
      'uid': uid,
      'active': active,
    });
  }
}

final instructorAdminServiceProvider = Provider<InstructorAdminService>((ref) {
  return InstructorAdminService(
    FirebaseFunctions.instanceFor(region: 'asia-northeast3'),
  );
});
