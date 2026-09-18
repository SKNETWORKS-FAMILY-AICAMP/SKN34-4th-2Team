import 'dart:async';

import '../models/user_model.dart';

/// 데모 로그인 세션 — Firebase Auth 대체
class DemoSession {
  DemoSession._();
  static final instance = DemoSession._();

  UserModel? _user;
  final _uidController = StreamController<String?>.broadcast();

  UserModel? get currentUser => _user;
  bool get isLoggedIn => _user != null;

  Stream<String?> get uidStream async* {
    yield _user?.uid;
    yield* _uidController.stream;
  }

  void login(UserModel user) {
    _user = user;
    _uidController.add(user.uid);
  }

  void logout() {
    _user = null;
    _uidController.add(null);
  }

  void updateCurrentUser(UserModel user) {
    _user = user;
    _uidController.add(user.uid);
  }
}
