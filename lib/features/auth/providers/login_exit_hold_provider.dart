import 'package:flutter_riverpod/flutter_riverpod.dart';

/// 로그인 성공 연출 중 redirect를 잠시 막아 둠
class LoginExitHold extends Notifier<bool> {
  @override
  bool build() => false;

  void hold() => state = true;

  void release() => state = false;
}

final loginExitHoldProvider =
    NotifierProvider<LoginExitHold, bool>(LoginExitHold.new);
