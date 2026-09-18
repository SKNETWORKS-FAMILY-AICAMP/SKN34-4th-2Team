import 'package:flutter/widgets.dart';

/// targetId → GlobalKey 레지스트리 (역할·화면 공통)
class OnboardingTargetRegistry {
  OnboardingTargetRegistry._();

  static final Map<String, GlobalKey> _keys = {};

  static GlobalKey keyOf(String targetId) =>
      _keys.putIfAbsent(targetId, GlobalKey.new);

  static Rect? rectOf(String targetId) {
    final ctx = _keys[targetId]?.currentContext;
    if (ctx == null) return null;
    final box = ctx.findRenderObject() as RenderBox?;
    if (box == null || !box.hasSize || !box.attached) return null;
    final topLeft = box.localToGlobal(Offset.zero);
    return topLeft & box.size;
  }

  static bool isMounted(String targetId) =>
      _keys[targetId]?.currentContext != null;
}
