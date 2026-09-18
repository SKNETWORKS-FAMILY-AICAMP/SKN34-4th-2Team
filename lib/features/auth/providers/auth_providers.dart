import 'package:firebase_auth/firebase_auth.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../shared/demo/demo_accounts.dart';
import '../../../shared/demo/demo_session.dart';
import '../../../shared/models/user_model.dart';
import '../../../shared/providers/firebase_providers.dart';
import '../data/auth_repository.dart';
import '../data/auth_repository_impl.dart';

/// AuthRepository DI
final authRepositoryProvider = Provider<AuthRepository>((ref) {
  return AuthRepositoryImpl(
    auth: ref.watch(firebaseAuthProvider),
    firestore: ref.watch(firestoreProvider),
  );
});

/// 세션 UID 스트림 — 데모/Firebase 통합
final sessionUidProvider = StreamProvider<String?>((ref) {
  if (DemoConfig.enabled) {
    return DemoSession.instance.uidStream;
  }
  return ref
      .watch(authRepositoryProvider)
      .authStateChanges
      .map((user) => user?.uid);
});

/// Firebase Auth 상태 (Firebase 모드 전용)
final authStateProvider = StreamProvider<User?>((ref) {
  if (DemoConfig.enabled) {
    return DemoSession.instance.uidStream.map(
      (uid) => uid != null ? ref.read(firebaseAuthProvider).currentUser : null,
    );
  }
  return ref.watch(authRepositoryProvider).authStateChanges;
});

/// Firestore UserModel 실시간 스트림
final currentUserProvider = StreamProvider<UserModel?>((ref) {
  final sessionUid = ref.watch(sessionUidProvider);

  return sessionUid.when(
    data: (uid) {
      if (uid == null) return Stream.value(null);
      if (DemoConfig.enabled && DemoAccounts.isDemoUid(uid)) {
        return Stream.value(DemoSession.instance.currentUser);
      }
      return ref.watch(authRepositoryProvider).watchUserProfile(uid);
    },
    loading: () => Stream.value(null),
    error: (_, _) => Stream.value(null),
  );
});

/// 로그인 AsyncNotifier
class SignInNotifier extends AsyncNotifier<void> {
  @override
  Future<void> build() async {}

  Future<UserModel> signIn(String email, String password) async {
    state = const AsyncLoading();
    try {
      final profile = await ref
          .read(authRepositoryProvider)
          .signIn(email: email, password: password);
      state = const AsyncData(null);
      return profile;
    } catch (e, st) {
      state = AsyncError(e, st);
      rethrow;
    }
  }
}

final signInProvider = AsyncNotifierProvider<SignInNotifier, void>(
  SignInNotifier.new,
);

/// 로그아웃
final signOutProvider = FutureProvider.autoDispose((ref) async {
  await ref.read(authRepositoryProvider).signOut();
});

/// 비밀번호 변경
class ChangePasswordNotifier extends AsyncNotifier<void> {
  @override
  Future<void> build() async {}

  Future<void> changePassword(String newPassword) async {
    state = const AsyncLoading();
    try {
      final uid = ref.read(firebaseAuthProvider).currentUser!.uid;
      await ref
          .read(authRepositoryProvider)
          .changePassword(newPassword: newPassword, uid: uid);
      state = const AsyncData(null);
    } catch (e, st) {
      state = AsyncError(e, st);
      rethrow;
    }
  }

  Future<void> changePasswordWithReauth({
    required String email,
    required String currentPassword,
    required String newPassword,
  }) async {
    state = const AsyncLoading();
    try {
      final uid = ref.read(firebaseAuthProvider).currentUser!.uid;
      await ref.read(authRepositoryProvider).changePasswordWithReauth(
            email: email,
            currentPassword: currentPassword,
            newPassword: newPassword,
            uid: uid,
          );
      state = const AsyncData(null);
    } catch (e, st) {
      state = AsyncError(e, st);
      rethrow;
    }
  }

  Future<void> skipMandatoryPasswordChange() async {
    state = const AsyncLoading();
    try {
      final uid = ref.read(firebaseAuthProvider).currentUser!.uid;
      await ref
          .read(authRepositoryProvider)
          .skipMandatoryPasswordChange(uid: uid);
      state = const AsyncData(null);
    } catch (e, st) {
      state = AsyncError(e, st);
      rethrow;
    }
  }
}

final changePasswordProvider =
    AsyncNotifierProvider<ChangePasswordNotifier, void>(
      ChangePasswordNotifier.new,
    );
