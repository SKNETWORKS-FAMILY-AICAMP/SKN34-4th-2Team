import '../../core/constants/role.dart';
import '../models/user_model.dart';

/// 로컬 데모 모드 — Firebase 없이 테스트 계정으로 UI 확인
/// 기본은 실제 Firebase를 쓴다. 온보딩 캡처·녹화처럼 실데이터가 나오면 안 될 때만
/// `--dart-define=DEMO_MODE=true`로 켠다.
abstract final class DemoConfig {
  static const enabled = bool.fromEnvironment('DEMO_MODE');

  static const cohortId = 'cohort_34';
  static const cohortName = 'SK네트웍스 Family AI 캠프 34기';
}

/// 테스트 계정 (debug 빌드 전용)
abstract final class DemoAccounts {
  static const adminEmail = 'admin@playdata.co.kr';
  static const adminPassword = 'Playdata123!';

  static const studentEmail = 'student@playdata.co.kr';
  static const studentPassword = 'Playdata123!';

  static const instructorEmail = 'instructor@playdata.co.kr';
  static const instructorPassword = 'Playdata123!';

  static const adminUid = 'demo-admin-001';
  static const studentUid = 'demo-student-001';
  static const instructorUid = 'demo-instructor-001';

  static UserModel get admin => UserModel(
    uid: adminUid,
    email: adminEmail,
    displayName: 'PLAYDATA 관리자',
    role: UserRole.admin,
    cohortId: DemoConfig.cohortId,
    cohortName: DemoConfig.cohortName,
    isActive: true,
    mustChangePassword: false,
  );

  static UserModel get student => UserModel(
    uid: studentUid,
    email: studentEmail,
    personalEmail: 'student@gmail.com',
    displayName: '문성호',
    role: UserRole.student,
    cohortId: DemoConfig.cohortId,
    cohortName: DemoConfig.cohortName,
    skills: const ['Flutter', 'Python', 'SQL'],
    isActive: true,
    mustChangePassword: false,
  );

  static UserModel get instructor => UserModel(
    uid: instructorUid,
    email: instructorEmail,
    displayName: 'PLAYDATA 강사',
    role: UserRole.instructor,
    cohortId: DemoConfig.cohortId,
    cohortName: DemoConfig.cohortName,
    isActive: true,
    mustChangePassword: false,
  );

  /// 이메일/비밀번호로 데모 유저 조회
  static UserModel? tryLogin(String email, String password) {
    final e = email.trim().toLowerCase();
    if (e == adminEmail && password == adminPassword) return admin;
    if (e == studentEmail && password == studentPassword) return student;
    if (e == instructorEmail && password == instructorPassword) {
      return instructor;
    }
    return null;
  }

  static bool isDemoUid(String uid) =>
      uid == adminUid || uid == studentUid || uid == instructorUid;
}
