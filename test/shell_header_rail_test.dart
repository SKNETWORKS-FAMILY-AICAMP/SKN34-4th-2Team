import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:playdata_lms/core/theme/app_space.dart';
import 'package:playdata_lms/core/theme/shell_chrome.dart';
import 'package:playdata_lms/features/shell/widgets/app_shell_header.dart';
import 'package:playdata_lms/shared/models/cohort_model.dart';
import 'package:playdata_lms/shared/providers/cohort_providers.dart';
import 'package:playdata_lms/shared/providers/lms_providers.dart';
import 'package:playdata_lms/shared/providers/side_rail_theme_provider.dart';

void main() {
  tearDown(() => AppSpace.apply(compact: false));

  for (final compact in [false, true]) {
    testWidgets(
      'cohort selector starts right of the rail (compact: $compact)',
      (tester) async {
        // 로고 칸이 글자 폭만큼만 차지하면 기수 선택이 사이드바 경계 위에 걸친다.
        // 좁게면 로고가 작아져 더 왼쪽으로 파고들었다.
        AppSpace.apply(compact: compact);
        tester.view.physicalSize = const Size(1280, 800);
        tester.view.devicePixelRatio = 1;
        addTearDown(tester.view.resetPhysicalSize);
        addTearDown(tester.view.resetDevicePixelRatio);

        await tester.pumpWidget(
          ProviderScope(
            overrides: [
              isAdminProvider.overrideWithValue(true),
              sideRailDarkModeProvider.overrideWithValue(true),
              effectiveCohortIdProvider.overrideWithValue('c34'),
              cohortsStreamProvider.overrideWith(
                (ref) => Stream.value(const [
                  CohortModel(cohortId: 'c34', name: 'SK네트웍스 Family AI 캠프 34기'),
                ]),
              ),
            ],
            child: MaterialApp(
              // 시험 글꼴(Ahem)은 글자마다 정사각형이라 실제 글꼴보다 훨씬 넓다.
              // 그대로면 로고 글자만으로 사이드바 폭을 넘겨 겹침이 재현되지 않는다.
              builder: (context, child) => MediaQuery(
                data: MediaQuery.of(
                  context,
                ).copyWith(textScaler: const TextScaler.linear(0.5)),
                child: child!,
              ),
              home: Scaffold(
                appBar: AppBar(
                  automaticallyImplyLeading: false,
                  title: const AppShellHeader(overRail: true),
                ),
              ),
            ),
          ),
        );
        await tester.pumpAndSettle();

        final selectorLeft = tester.getTopLeft(find.byType(MenuAnchor)).dx;
        expect(selectorLeft, greaterThanOrEqualTo(ShellChrome.railWidth));
      },
    );
  }
}
