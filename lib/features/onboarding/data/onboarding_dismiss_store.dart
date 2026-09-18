import 'package:shared_preferences/shared_preferences.dart';

/// 온보딩 「다시 보지 않기」 — 영구 dismiss (버전별로 재노출 가능)
///
/// 키: `onboarding_{tourId}_v{version}_{uid}`
/// 메모리 캐시가 소스 오브 트루스다.
class OnboardingDismissStore {
  OnboardingDismissStore._();

  static final Map<String, bool> _cache = {};

  static String prefsKey({
    required String tourId,
    required int version,
    required String uid,
  }) =>
      'onboarding_${tourId}_v${version}_$uid';

  static void _remember(String key, bool value) {
    _cache[key] = value;
  }

  static Future<bool> isDismissed({
    required String tourId,
    required int version,
    required String uid,
  }) async {
    final key = prefsKey(tourId: tourId, version: version, uid: uid);
    if (_cache.containsKey(key)) return _cache[key]!;
    try {
      final prefs = await SharedPreferences.getInstance();
      final saved = prefs.getBool(key) ?? false;
      _remember(key, saved);
      return saved;
    } catch (_) {
      return _cache[key] ?? false;
    }
  }

  static Future<void> dismiss({
    required String tourId,
    required int version,
    required String uid,
  }) async {
    final key = prefsKey(tourId: tourId, version: version, uid: uid);
    _remember(key, true);
    try {
      final prefs = await SharedPreferences.getInstance();
      await prefs.setBool(key, true);
    } catch (_) {}
  }

  /// 마이페이지 「온보딩 다시 보기」용
  static Future<void> clear({
    required String tourId,
    required int version,
    required String uid,
  }) async {
    final key = prefsKey(tourId: tourId, version: version, uid: uid);
    _remember(key, false);
    try {
      final prefs = await SharedPreferences.getInstance();
      await prefs.remove(key);
    } catch (_) {}
  }

  /// 테스트용
  static void debugReset() => _cache.clear();
}
