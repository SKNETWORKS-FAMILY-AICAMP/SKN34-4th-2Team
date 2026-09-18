import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/utils/date_utils.dart';
import '../../features/auth/providers/auth_providers.dart';
import '../services/alert_popup_dismiss_store.dart';
import 'lms_providers.dart';

/// 이번 로그인에서 「닫기」한 팝업. 로그아웃하면 리셋.
class AlertPopupSessionClosed extends Notifier<Set<String>> {
  @override
  Set<String> build() {
    ref.watch(sessionUidProvider.select((s) => s.value));
    return {};
  }

  void close(String popupId) => state = {...state, popupId};
}

final alertPopupSessionClosedProvider =
    NotifierProvider<AlertPopupSessionClosed, Set<String>>(
  AlertPopupSessionClosed.new,
);

/// 「오늘 다시 보지 않기」 — popupId → dateKey
class AlertPopupLocalDismissed extends Notifier<Map<String, String>> {
  @override
  Map<String, String> build() {
    final uid = ref.watch(sessionUidProvider.select((s) => s.value));
    if (uid == null) return {};

    final cached = AlertPopupDismissStore.cachedMap(uid);
    Future<void>(() async {
      final loaded = await AlertPopupDismissStore.loadMap(uid);
      if (!ref.mounted) return;
      if (ref.read(sessionUidProvider).value != uid) return;
      state = {...loaded, ...state};
    });
    return cached;
  }

  void dismiss(String popupId, String dateKey) {
    state = {...state, popupId: dateKey};
  }
}

final alertPopupLocalDismissedProvider =
    NotifierProvider<AlertPopupLocalDismissed, Map<String, String>>(
  AlertPopupLocalDismissed.new,
);

/// Firestore에 저장된 숨김 기록 (다른 기기·새로고침용)
final alertPopupRemoteDismissedProvider =
    StreamProvider<Map<String, String>>((ref) {
  final uid = ref.watch(sessionUidProvider).value;
  if (uid == null) return Stream.value(const {});
  return ref.watch(lmsRepositoryProvider).watchAlertPopupDismissals(uid)
      as Stream<Map<String, String>>;
});

Set<String> alertPopupIdsDismissedToday({
  required Map<String, String> local,
  required Map<String, String> remote,
  required String dateKey,
}) {
  final ids = <String>{};
  void collect(Map<String, String> map) {
    map.forEach((id, saved) {
      if (saved == dateKey) ids.add(id);
    });
  }

  collect(remote);
  collect(local);
  return ids;
}

String alertPopupTodayKey([DateTime? now]) =>
    AppDateUtils.toDateKey(now ?? DateTime.now());
