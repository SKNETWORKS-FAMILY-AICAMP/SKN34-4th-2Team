import 'package:firebase_auth/firebase_auth.dart';

import '../../../shared/data/lms_api_client.dart';
import '../../../shared/demo/demo_accounts.dart';
import '../../../shared/demo/demo_session.dart';
import '../../../core/errors/app_exception.dart';
import '../../../shared/models/user_model.dart';
import 'auth_repository.dart';

/// Firebase Auth + Django 프로필
class AuthRepositoryImpl implements AuthRepository {
  AuthRepositoryImpl({
    required FirebaseAuth auth,
    required LmsApiClient api,
  })  : _auth = auth,
        _api = api;

  final FirebaseAuth _auth;
  final LmsApiClient _api;

  @override
  Stream<User?> get authStateChanges => _auth.authStateChanges();

  @override
  User? get currentFirebaseUser => _auth.currentUser;

  @override
  Future<UserModel> signIn({
    required String email,
    required String password,
  }) async {
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
      _api.firebaseUid = uid;
      await _api.bootstrap();
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
      await _api.command('touchLastLogin', {});
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
    _api.firebaseUid = '';
    await _auth.signOut();
  }

  @override
  Stream<UserModel?> watchUserProfile(String uid) async* {
    if (DemoConfig.enabled && DemoAccounts.isDemoUid(uid)) {
      yield DemoSession.instance.currentUser;
      return;
    }
    _api.firebaseUid = uid;
    yield await getUserProfile(uid);
    await for (final _ in _api.changes) {
      yield await getUserProfile(uid);
    }
  }

  @override
  Future<UserModel?> getUserProfile(String uid) async {
    if (_api.snapshot.isEmpty) {
      try {
        await _api.bootstrap();
      } catch (_) {
        return null;
      }
    }
    final me = _api.snapshot['me'];
    if (me is Map && '${me['uid'] ?? me['firebaseUid']}' == uid) {
      return UserModel.fromMap(uid, Map<String, dynamic>.from(me));
    }
    final row = _api.list('users').where((item) => '${item['uid']}' == uid).firstOrNull;
    if (row == null) return null;
    return UserModel.fromMap(uid, row);
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
      await _api.command('updateProfile', {
        'uid': uid,
        'mustChangePassword': false,
        'password': newPassword,
      });
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
      await _api.command('updateProfile', {
        'uid': uid,
        'mustChangePassword': false,
        'password': newPassword,
      });
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
    await _api.command('updateProfile', {
      'uid': uid,
      'mustChangePassword': false,
    });
  }

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
