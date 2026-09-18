import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

/// 로그인 ↔ 셸 전환용 페이드 페이지 (Hero 비행과 함께 사용)
CustomTransitionPage<void> fadePage({
  required LocalKey key,
  required Widget child,
  Duration duration = const Duration(milliseconds: 560),
}) {
  return CustomTransitionPage<void>(
    key: key,
    child: child,
    transitionDuration: duration,
    reverseTransitionDuration: duration,
    transitionsBuilder: (context, animation, secondaryAnimation, child) {
      final curved = CurvedAnimation(
        parent: animation,
        curve: Curves.easeOutCubic,
        reverseCurve: Curves.easeInCubic,
      );
      return FadeTransition(
        opacity: curved,
        child: child,
      );
    },
  );
}
