import 'package:cloud_firestore/cloud_firestore.dart';
import 'package:cloud_functions/cloud_functions.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/constants/firestore_paths.dart';
import '../../../shared/models/student_intake_model.dart';
import '../../../shared/providers/firebase_providers.dart';

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
  StudentAdminService(this._firestore, this._functions);

  final FirebaseFirestore _firestore;
  final FirebaseFunctions _functions;

  Future<Map<String, int>> seedDemo34Roster() async {
    const cohortId = 'cohort_34';
    const names = <String>[
      '김태윤', '전진영', '채정석', '황호순', '김현지', '홍지윤', '이성민', '송승재',
      '김동섭', '김건우', '임형준', '김기호', '최대원', '김대호', '문성호', '김진화',
      '윤성호', '이홍규', '김재현', '황수빈', '정예린', '전진환', '최성욱', '최인영',
      '이현준',
    ];
    const moonAttendance = <String, List<String>>{
      '2026-06-16': ['present', '08:59', '17:51'],
      '2026-06-17': ['present', '08:46', '17:51'],
      '2026-06-18': ['present', '08:52', '17:51'],
      '2026-06-19': ['present', '08:57', '17:51'],
      '2026-06-22': ['present', '09:01', '17:51'],
      '2026-06-23': ['present', '08:49', '17:52'],
      '2026-06-24': ['present', '08:51', '17:51'],
      '2026-06-25': ['present', '08:58', '17:56'],
      '2026-06-26': ['present', '08:56', '17:52'],
      '2026-06-29': ['present', '08:58', '17:57'],
      '2026-06-30': ['present', '08:59', '17:55'],
      '2026-07-01': ['late', '12:10', '17:53'],
      '2026-07-02': ['present', '08:58', '17:51'],
      '2026-07-03': ['present', '08:58', '17:51'],
      '2026-07-06': ['late', '09:19', '17:51'],
      '2026-07-07': ['present', '08:59', '17:51'],
      '2026-07-08': ['present', '08:57', '17:51'],
      '2026-07-09': ['present', '09:00', '17:52'],
      '2026-07-10': ['present', '08:58', '17:56'],
      '2026-07-13': ['present', '08:56', '17:51'],
      '2026-07-14': ['present', '09:00', '17:51'],
      '2026-07-15': ['present', '08:59', '17:52'],
      '2026-07-16': ['present', '08:57', '17:53'],
      '2026-07-20': ['present', '09:09', '18:02'],
      '2026-07-21': ['present', '08:59', '17:55'],
      '2026-07-22': ['present', '09:09', '17:52'],
      '2026-07-23': ['present', '09:08', '17:56'],
      '2026-07-24': ['present', '08:56', '17:52'],
      '2026-07-27': ['present', '09:00', '17:51'],
      '2026-07-28': ['absent'],
      '2026-07-29': ['late', '13:15', '18:59'],
      '2026-07-30': ['late', '12:01', '18:53'],
      '2026-07-31': ['present', '09:01', '17:52'],
      '2026-08-03': ['late', '11:09', '17:52'],
      '2026-08-04': ['present', '08:58', '17:54'],
      '2026-08-05': ['late', '13:31', '17:52'],
      '2026-08-06': ['present', '08:54', '17:51'],
      '2026-08-07': ['late', '12:14', '17:51'],
      '2026-08-10': ['present', '08:18', '17:51'],
      '2026-08-11': ['late', '10:55', '17:53'],
      '2026-08-12': ['present', '09:06', '18:31'],
      '2026-08-13': ['present', '08:57', '19:00'],
      '2026-08-14': ['present', '09:08', '17:52'],
      '2026-08-18': ['late', '10:05', '17:52'],
      '2026-08-19': ['present', '09:08', '17:51'],
      '2026-08-20': ['present', '08:57', '17:51'],
      '2026-08-21': ['present', '09:00', '18:09'],
      '2026-08-24': ['officialLeave', 'sick'],
      '2026-08-25': ['present', '09:00', '17:53'],
      '2026-08-26': ['late', '13:44', '17:52'],
      '2026-08-27': ['present', '08:55', '17:52'],
      '2026-08-28': ['present', '08:56', '17:51'],
      '2026-08-31': ['present', '09:08', '17:52'],
      '2026-09-01': ['late', '09:24', '18:19'],
      '2026-09-02': ['present', '08:55', '18:07'],
      '2026-09-03': ['present', '08:57', '17:52'],
      '2026-09-04': ['officialLeave', 'vacation'],
      '2026-09-07': ['present', '08:54', '17:53'],
      '2026-09-08': ['present', '09:08', '18:02'],
      '2026-09-09': ['late', '14:01', '17:54'],
      '2026-09-10': ['late', '10:26', '18:23'],
      '2026-09-11': ['late', '11:34', '17:52'],
      '2026-09-14': ['present', '08:58', '18:48'],
      '2026-09-15': ['absent'],
    };

    final snapshot = await _firestore
        .collection(FirestorePaths.users)
        .where('cohortId', isEqualTo: cohortId)
        .where('role', isEqualTo: 'student')
        .get();
    final docs = snapshot.docs.toList()
      ..sort((a, b) => a.id.compareTo(b.id));
    final demoAccount = docs
        .where((d) => d.data()['email'] == 'student@playdata.co.kr')
        .firstOrNull;
    final eligibleDocs = docs.where((d) => d.id != demoAccount?.id).toList();
    if (eligibleDocs.length < names.length) {
      throw StateError(
        '빠른 로그인 계정을 제외한 34기 학생 계정이 ${eligibleDocs.length}개뿐이라 25명을 배정할 수 없습니다.',
      );
    }
    final moon = eligibleDocs
        .where((d) => d.data()['displayName'] == '문성호')
        .firstOrNull;
    final available = eligibleDocs.where((d) => d.id != moon?.id).toList();
    final selected = <DocumentSnapshot<Map<String, dynamic>>>[];
    final assignments = <String, String>{};
    if (moon != null) {
      selected.add(moon);
      assignments[moon.id] = '문성호';
    }
    for (final name in names.where((n) => n != '문성호')) {
      final doc = available.removeAt(0);
      selected.add(doc);
      assignments[doc.id] = name;
    }

    var batch = _firestore.batch();
    var operations = 0;
    Future<void> flush() async {
      if (operations == 0) return;
      await batch.commit();
      batch = _firestore.batch();
      operations = 0;
    }
    void update(DocumentReference<Map<String, dynamic>> ref, Map<String, dynamic> data) {
      batch.set(ref, data, SetOptions(merge: true));
      operations++;
    }

    for (final doc in selected) {
      final name = assignments[doc.id]!;
      final common = <String, dynamic>{
        'displayName': name,
        'cohortName': 'SK네트웍스 Family AI 캠프 34기',
        'isActive': true,
        'seatNumber': FieldValue.delete(),
        'updatedAt': FieldValue.serverTimestamp(),
      };
      update(doc.reference, common);
      update(_firestore.collection(FirestorePaths.studentIntakes).doc(doc.id), common);
    }

    final selectedIds = selected.map((d) => d.id).toSet();
    final extras = eligibleDocs
        .where((d) => !selectedIds.contains(d.id))
        .toList();
    for (final doc in extras) {
      final hidden = <String, dynamic>{
        'cohortId': '__archived_demo',
        'cohortName': '숨김 처리된 시연 계정',
        'isActive': false,
        'updatedAt': FieldValue.serverTimestamp(),
      };
      update(doc.reference, hidden);
      update(_firestore.collection(FirestorePaths.studentIntakes).doc(doc.id), hidden);
    }

    final start = DateTime(2026, 6, 16);
    final end = DateTime(2026, 9, 15);
    var classDay = 0;
    for (var day = start; !day.isAfter(end); day = day.add(const Duration(days: 1))) {
      if (day.weekday > DateTime.friday) continue;
      classDay++;
      final dateKey = '${day.year.toString().padLeft(4, '0')}-${day.month.toString().padLeft(2, '0')}-${day.day.toString().padLeft(2, '0')}';
      for (var i = 0; i < selected.length; i++) {
        final doc = selected[i];
        final isMoon = assignments[doc.id] == '문성호';
        final moonRecord = moonAttendance[dateKey];
        if (isMoon && moonRecord == null) continue;
        final status = isMoon
            ? moonRecord!.first
            : (classDay + i) % 17 == 0
            ? 'absent'
            : (classDay + i) % 11 == 0
            ? 'late'
            : 'present';
        final attendance = <String, dynamic>{
          'userId': doc.id,
          'userDisplayName': assignments[doc.id],
          'dateKey': dateKey,
          'status': status,
          'type': 'status',
          'statusSource': 'demo',
          'timestamp': FieldValue.serverTimestamp(),
          'updatedAt': FieldValue.serverTimestamp(),
        };
        if (isMoon && moonRecord!.length >= 3) {
          attendance['checkInTime'] = moonRecord[1];
          attendance['checkOutTime'] = moonRecord[2];
          attendance['checkInSource'] = 'demo';
        }
        if (isMoon && status == 'officialLeave') {
          attendance['officialLeaveUsed'] = true;
          attendance['officialLeaveType'] = moonRecord![1];
        }
        update(
          _firestore.collection('cohorts').doc(cohortId).collection('attendances').doc('${doc.id}_$dateKey'),
          attendance,
        );
        if (operations >= 400) await flush();
      }
    }
    update(_firestore.collection('cohorts').doc(cohortId), {'studentCount': 25});
    await flush();
    return {'active': selected.length, 'hidden': extras.length, 'classDays': classDay};
  }

  Stream<List<StudentIntakeModel>> watchCohortIntakes(String cohortId) {
    return _firestore
        .collection(FirestorePaths.studentIntakes)
        .where('cohortId', isEqualTo: cohortId)
        .orderBy('createdAt', descending: true)
        .snapshots()
        .map(
          (snap) => snap.docs.map(StudentIntakeModel.fromFirestore).toList(),
        );
  }

  Stream<StudentIntakeModel?> watchIntake(String uid) {
    return _firestore
        .collection(FirestorePaths.studentIntakes)
        .doc(uid)
        .snapshots()
        .map((doc) {
      if (!doc.exists) return null;
      return StudentIntakeModel.fromFirestore(doc);
    });
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
    ref.watch(firestoreProvider),
    FirebaseFunctions.instanceFor(region: 'asia-northeast3'),
  );
});
