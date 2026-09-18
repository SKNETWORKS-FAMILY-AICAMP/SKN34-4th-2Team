import 'package:shared_preferences/shared_preferences.dart';

/// 알림 팝업 「오늘 다시 보지 않기」 — 당일(dateKey)만 유효
///
/// 메모리 캐시가 소스 오브 트루스다. SharedPreferences 읽기가 늦게 도착해도
/// 이미 숨긴 기록을 빈 값으로 덮어쓰지 않는다.
class AlertPopupDismissStore {
  AlertPopupDismissStore._();

  static final Map<String, String> _cache = {};

  static String _key(String uid, String popupId) =>
      'alert_popup_dismiss_${uid}_$popupId';

  static String _prefix(String uid) => 'alert_popup_dismiss_${uid}_';

  static void _remember(String key, String dateKey) {
    _cache[key] = dateKey;
  }

  /// 프로세스 메모리에 있는 uid별 popupId → dateKey
  static Map<String, String> cachedMap(String uid) {
    final prefix = _prefix(uid);
    final map = <String, String>{};
    _cache.forEach((key, dateKey) {
      if (key.startsWith(prefix)) {
        map[key.substring(prefix.length)] = dateKey;
      }
    });
    return map;
  }

  static Future<void> dismissToday({
    required String uid,
    required String popupId,
    required String dateKey,
  }) async {
    _remember(_key(uid, popupId), dateKey);
    try {
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString(_key(uid, popupId), dateKey);
    } catch (_) {}
  }

  static Future<bool> isDismissedToday({
    required String uid,
    required String popupId,
    required String dateKey,
  }) async {
    final map = await loadMap(uid);
    return map[popupId] == dateKey;
  }

  /// prefs를 캐시에 합친 뒤 반환. prefs에 없는 키는 캐시에서 지우지 않는다.
  static Future<Map<String, String>> loadMap(String uid) async {
    final prefix = _prefix(uid);
    try {
      final prefs = await SharedPreferences.getInstance();
      for (final key in prefs.getKeys()) {
        if (!key.startsWith(prefix)) continue;
        final saved = prefs.getString(key);
        if (saved != null && saved.isNotEmpty) {
          _remember(key, saved);
        }
      }
    } catch (_) {}
    return cachedMap(uid);
  }

  static Future<Set<String>> dismissedIdsToday({
    required String uid,
    required List<String> popupIds,
    required String dateKey,
  }) async {
    final map = await loadMap(uid);
    return {
      for (final id in popupIds)
        if (map[id] == dateKey) id,
    };
  }

  /// 테스트용
  static void debugReset() => _cache.clear();
}
