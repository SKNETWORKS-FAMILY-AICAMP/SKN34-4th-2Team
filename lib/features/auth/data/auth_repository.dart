import 'package:firebase_auth/firebase_auth.dart';

import '../../../shared/models/user_model.dart';

/// Auth Repository 인터페이스 — SOLID: 구현체 교체 가능
abstract class AuthRepository {
  /// Firebase Auth 상태 변화 스트림 (자동 로그인 Persistence 포함)
  Stream<User?> get authStateChanges;

  /// 현재 Firebase Auth 유저
  User? get currentFirebaseUser;

  /// 이메일/비밀번호 로그인
  Future<UserModel> signIn({required String email, required String password});

  /// 로그아웃
  Future<void> signOut();

  /// Firestore users/{uid} 프로필 실시간 구독
  Stream<UserModel?> watchUserProfile(String uid);

  /// Firestore users/{uid} 프로필 1회 조회
  Future<UserModel?> getUserProfile(String uid);

  /// 비밀번호 변경 (mustChangePassword 플래그 해제 포함)
  Future<void> changePassword({
    required String newPassword,
    required String uid,
  });

  /// 현재 비밀번호 확인 후 변경 (마이페이지용)
  Future<void> changePasswordWithReauth({
    required String email,
    required String currentPassword,
    required String newPassword,
    required String uid,
  });

  /// 최초 로그인 비밀번호 변경 건너뛰기
  Future<void> skipMandatoryPasswordChange({required String uid});
}
