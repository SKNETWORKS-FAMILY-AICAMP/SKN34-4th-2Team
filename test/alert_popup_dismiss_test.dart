import 'package:flutter_test/flutter_test.dart';
import 'package:playdata_lms/shared/providers/alert_popup_providers.dart';
import 'package:playdata_lms/shared/services/alert_popup_dismiss_store.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  setUp(() {
    AlertPopupDismissStore.debugReset();
    SharedPreferences.setMockInitialValues({});
  });

  test('오늘 다시 보지 않기 후 당일에는 숨김', () async {
    await AlertPopupDismissStore.dismissToday(
      uid: 'u1',
      popupId: 'p1',
      dateKey: '2026-09-03',
    );

    expect(
      await AlertPopupDismissStore.isDismissedToday(
        uid: 'u1',
        popupId: 'p1',
        dateKey: '2026-09-03',
      ),
      isTrue,
    );
    expect(
      await AlertPopupDismissStore.isDismissedToday(
        uid: 'u1',
        popupId: 'p1',
        dateKey: '2026-09-04',
      ),
      isFalse,
    );
  });

  test('늦게 도착한 빈 prefs 읽기가 메모리 기록을 지우지 않는다', () async {
    await AlertPopupDismissStore.dismissToday(
      uid: 'u1',
      popupId: 'p1',
      dateKey: '2026-09-03',
    );

    SharedPreferences.setMockInitialValues({});
    final ids = await AlertPopupDismissStore.dismissedIdsToday(
      uid: 'u1',
      popupIds: ['p1'],
      dateKey: '2026-09-03',
    );

    expect(ids, contains('p1'));
  });

  test('로컬·원격 기록을 당일 기준으로 합친다', () {
    final ids = alertPopupIdsDismissedToday(
      local: {'a': '2026-09-03', 'b': '2026-09-02'},
      remote: {'c': '2026-09-03', 'b': '2026-09-03'},
      dateKey: '2026-09-03',
    );
    expect(ids, {'a', 'b', 'c'});
  });
}
