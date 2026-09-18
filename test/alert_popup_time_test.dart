import 'package:flutter_test/flutter_test.dart';
import 'package:playdata_lms/shared/models/alert_popup_model.dart';

void main() {
  AlertPopupModel popup({String? start, String? end}) {
    return AlertPopupModel(
      id: '1',
      title: 't',
      content: 'c',
      authorName: 'a',
      startTime: start,
      endTime: end,
    );
  }

  test('종일이면 항상 표시', () {
    final p = popup();
    expect(p.isVisibleAt(DateTime(2026, 9, 3, 0, 0)), isTrue);
    expect(p.isVisibleAt(DateTime(2026, 9, 3, 15, 30)), isTrue);
    expect(p.isVisibleAt(DateTime(2026, 9, 3, 23, 59)), isTrue);
  });

  test('빈 문자열 시간도 종일로 취급', () {
    final p = popup(start: '  ', end: '');
    expect(p.hasTimeWindow, isFalse);
    expect(p.isVisibleAt(DateTime(2026, 9, 3, 16, 2)), isTrue);
  });

  test('08:30~18:00 구간', () {
    final p = popup(start: '08:30', end: '18:00');
    expect(p.isVisibleAt(DateTime(2026, 9, 3, 8, 29)), isFalse);
    expect(p.isVisibleAt(DateTime(2026, 9, 3, 8, 30)), isTrue);
    expect(p.isVisibleAt(DateTime(2026, 9, 3, 12, 0)), isTrue);
    expect(p.isVisibleAt(DateTime(2026, 9, 3, 18, 0)), isTrue);
    expect(p.isVisibleAt(DateTime(2026, 9, 3, 18, 1)), isFalse);
  });

  test('자정 넘는 구간 22:00~06:00', () {
    final p = popup(start: '22:00', end: '06:00');
    expect(p.isVisibleAt(DateTime(2026, 9, 3, 21, 59)), isFalse);
    expect(p.isVisibleAt(DateTime(2026, 9, 3, 22, 0)), isTrue);
    expect(p.isVisibleAt(DateTime(2026, 9, 3, 23, 30)), isTrue);
    expect(p.isVisibleAt(DateTime(2026, 9, 4, 0, 10)), isTrue);
    expect(p.isVisibleAt(DateTime(2026, 9, 4, 6, 0)), isTrue);
    expect(p.isVisibleAt(DateTime(2026, 9, 4, 6, 1)), isFalse);
    expect(p.isVisibleAt(DateTime(2026, 9, 4, 12, 0)), isFalse);
  });
}
