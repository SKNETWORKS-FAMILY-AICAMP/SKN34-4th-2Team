/// 누가 무엇을 할 수 있나.
///
/// 강사는 관리자가 아니다. 이 둘을 같은 것으로 보다가 강사가 학생용 화면을 받았고,
/// 남의 이력서에 저장을 시도해 'permission-denied' 가 났다.
library;

import 'package:flutter_test/flutter_test.dart';
import 'package:playdata_lms/shared/models/resume_model.dart';
import 'package:playdata_lms/core/constants/role.dart';

ResumeModel _resume({String status = 'writing'}) => ResumeModel(
      id: 'r1',
      userId: 'u1',
      title: '이력서',
      status: status,
      sections: const {},
    );

void main() {
  group('역할', () {
    test('강사는 검토할 수 있지만 관리자는 아니다', () {
      expect(UserRole.instructor.canReviewResumes, isTrue);
      expect(UserRole.instructor.isAdmin, isFalse,
          reason: '이 둘을 섞으면 강사가 학생용 화면을 받는다');
    });

    test('관리자도 검토할 수 있다', () {
      expect(UserRole.admin.canReviewResumes, isTrue);
    });

    test('학생은 검토할 수 없다', () {
      expect(UserRole.student.canReviewResumes, isFalse);
    });
  });

  group('승인 뒤에도 고칠 수 있다', () {
    test('승인 전', () {
      expect(_resume(status: 'submitted').canStudentEdit, isTrue);
    });

    test('승인 뒤 — 승인은 "여기까지 봤다"는 표시지 잠금이 아니다', () {
      expect(_resume(status: 'approved').canStudentEdit, isTrue);
      expect(_resume(status: 'completed').canStudentEdit, isTrue);
    });

    test('승인 상태는 그대로 남는다', () {
      expect(_resume(status: 'approved').isApproved, isTrue);
      expect(_resume(status: 'approved').statusLabel, '승인 완료');
    });
  });
}
