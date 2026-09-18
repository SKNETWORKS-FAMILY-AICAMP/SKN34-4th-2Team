import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:playdata_lms/core/constants/attendance_status.dart';
import 'package:playdata_lms/features/dashboard/presentation/widgets/attendance_calendar_card.dart';

void main() {
  for (final width in [320.0, 220.0, 160.0]) {
    for (final compact in [false, true]) {
      testWidgets('legend stays on one line at $width px (compact: $compact)', (
        tester,
      ) async {
        await tester.pumpWidget(
          MaterialApp(
            home: Scaffold(
              body: Center(
                child: SizedBox(
                  width: width,
                  child: AttendanceStatusLegend(compact: compact),
                ),
              ),
            ),
          ),
        );

        // 여섯 가지가 모두 보인다.
        for (final status in AttendanceStatus.all) {
          expect(find.text(AttendanceStatus.labelOf(status)), findsOneWidget);
        }
        // 전부 같은 줄에 있다. 두 줄로 갈라지면 위아래 위치가 달라진다.
        final tops = {
          for (final status in AttendanceStatus.all)
            tester
                .getTopLeft(find.text(AttendanceStatus.labelOf(status)))
                .dy
                .round(),
        };
        expect(tops, hasLength(1));
        // 칸 밖으로 넘치지도 않는다.
        expect(tester.takeException(), isNull);
        final legend = tester.getRect(find.byType(AttendanceStatusLegend));
        expect(legend.width, lessThanOrEqualTo(width + 0.5));
      });
    }
  }
}
