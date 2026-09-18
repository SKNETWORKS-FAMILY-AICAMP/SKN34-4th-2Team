import 'package:cloud_firestore/cloud_firestore.dart';
import 'package:firebase_auth/firebase_auth.dart';

import '../../../shared/demo/demo_accounts.dart';
import '../../../shared/demo/demo_session.dart';
import '../../../core/constants/firestore_paths.dart';
import '../../../core/errors/app_exception.dart';
import '../../../shared/models/user_model.dart';
import 'auth_repository.dart';

/// Firebase Auth + Firestore 연동 Repository 구현체
class AuthRepositoryImpl implements AuthRepository {
  AuthRepositoryImpl({
    required FirebaseAuth auth,
    required FirebaseFirestore firestore,
  }) : _auth = auth,
       _firestore = firestore;

  final FirebaseAuth _auth;
  final FirebaseFirestore _firestore;

  @override
  Stream<User?> get authStateChanges => _auth.authStateChanges();

  @override
  User? get currentFirebaseUser => _auth.currentUser;

  @override
  Future<UserModel> signIn({
    required String email,
    required String password,
  }) async {
    // 데모 모드: Firebase 없이 테스트 계정 로그인
    if (DemoConfig.enabled) {
      final demoUser = DemoAccounts.tryLogin(email, password);
      if (demoUser != null) {
        DemoSession.instance.login(demoUser);
        return demoUser;
      }
      throw const AuthException(
        '이메일 또는 비밀번호가 올바르지 않습니다.',
        code: 'invalid-credential',
      );
    }

    try {
      final credential = await _auth.signInWithEmailAndPassword(
        email: email.trim(),
        password: password,
      );

      final uid = credential.user!.uid;
      final profile = await getUserProfile(uid);

      if (profile == null) {
        await _auth.signOut();
        throw const AuthException(
          '사용자 프로필을 찾을 수 없습니다. 관리자에게 문의하세요.',
          code: 'profile-not-found',
        );
      }

      if (!profile.isActive) {
        await _auth.signOut();
        throw const AuthException(
          '비활성화된 계정입니다. 관리자에게 문의하세요.',
          code: 'account-disabled',
        );
      }

      await _firestore.collection(FirestorePaths.users).doc(uid).update({
        'lastLoginAt': FieldValue.serverTimestamp(),
      });

      return profile;
    } on FirebaseAuthException catch (e) {
      throw AuthException(_mapAuthError(e.code), code: e.code);
    }
  }

  @override
  Future<void> signOut() async {
    if (DemoConfig.enabled && DemoSession.instance.isLoggedIn) {
      DemoSession.instance.logout();
      return;
    }
    await _auth.signOut();
  }

  @override
  Stream<UserModel?> watchUserProfile(String uid) {
    if (DemoConfig.enabled && DemoAccounts.isDemoUid(uid)) {
      return Stream.value(DemoSession.instance.currentUser);
    }
    return _firestore
        .collection(FirestorePaths.users)
        .doc(uid)
        .snapshots()
        .map((doc) => doc.exists ? UserModel.fromFirestore(doc) : null);
  }

  @override
  Future<UserModel?> getUserProfile(String uid) async {
    final doc = await _firestore
        .collection(FirestorePaths.users)
        .doc(uid)
        .get();
    if (!doc.exists) return null;
    return UserModel.fromFirestore(doc);
  }

  @override
  Future<void> changePassword({
    required String newPassword,
    required String uid,
  }) async {
    try {
      final user = _auth.currentUser;
      if (user == null) {
        throw const AuthException('로그인 상태가 아닙니다.');
      }

      await user.updatePassword(newPassword);

      await _firestore.collection(FirestorePaths.users).doc(uid).update({
        'mustChangePassword': false,
        'updatedAt': FieldValue.serverTimestamp(),
      });

      // 상담 등록 학생 — 비밀번호 변경 기록 (관리자 화면 표시용)
      final intakeRef =
          _firestore.collection(FirestorePaths.studentIntakes).doc(uid);
      final intakeDoc = await intakeRef.get();
      if (intakeDoc.exists) {
        await intakeRef.update({'passwordChanged': true});
      }
    } on FirebaseAuthException catch (e) {
      throw AuthException(_mapAuthError(e.code), code: e.code);
    }
  }

  @override
  Future<void> changePasswordWithReauth({
    required String email,
    required String currentPassword,
    required String newPassword,
    required String uid,
  }) async {
    try {
      final user = _auth.currentUser;
      if (user == null) {
        throw const AuthException('로그인 상태가 아닙니다.');
      }

      final credential = EmailAuthProvider.credential(
        email: email,
        password: currentPassword,
      );
      await user.reauthenticateWithCredential(credential);
      await user.updatePassword(newPassword);

      await _firestore.collection(FirestorePaths.users).doc(uid).update({
        'mustChangePassword': false,
        'updatedAt': FieldValue.serverTimestamp(),
      });

      final intakeRef =
          _firestore.collection(FirestorePaths.studentIntakes).doc(uid);
      final intakeDoc = await intakeRef.get();
      if (intakeDoc.exists) {
        await intakeRef.update({'passwordChanged': true});
      }
    } on FirebaseAuthException catch (e) {
      throw AuthException(_mapAuthError(e.code), code: e.code);
    }
  }

  @override
  Future<void> skipMandatoryPasswordChange({required String uid}) async {
    if (DemoConfig.enabled && DemoAccounts.isDemoUid(uid)) {
      final user = DemoSession.instance.currentUser;
      if (user != null) {
        DemoSession.instance.updateCurrentUser(
          user.copyWith(mustChangePassword: false),
        );
      }
      return;
    }

    await _firestore.collection(FirestorePaths.users).doc(uid).update({
      'mustChangePassword': false,
      'updatedAt': FieldValue.serverTimestamp(),
    });
  }

  /// Firebase Auth 에러 코드 → 한국어 메시지
  String _mapAuthError(String code) {
    return switch (code) {
      'user-not-found' || 'wrong-password' || 'invalid-credential' =>
        '이메일 또는 비밀번호가 올바르지 않습니다.',
      'user-disabled' => '비활성화된 계정입니다.',
      'too-many-requests' => '너무 많은 시도가 있었습니다. 잠시 후 다시 시도하세요.',
      'weak-password' => '비밀번호는 6자 이상이어야 합니다.',
      'configuration-not-found' || 'operation-not-allowed' =>
        'Firebase Console에서 이메일/비밀번호 로그인을 활성화해 주세요.',
      _ => '로그인 중 오류가 발생했습니다. ($code)',
    };
  }
}
