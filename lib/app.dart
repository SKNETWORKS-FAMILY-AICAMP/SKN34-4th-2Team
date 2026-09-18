import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'core/constants/app_constants.dart';
import 'core/routing/app_router.dart';
import 'core/theme/app_colors.dart';
import 'core/theme/app_space.dart';
import 'core/widgets/compact_text_scale.dart';
import 'features/auth/providers/auth_providers.dart';
import 'features/resume/ai_coach/presentation/review_dock.dart';
import 'core/theme/app_theme.dart';
import 'shared/providers/app_appearance_provider.dart';
import 'shared/providers/side_rail_theme_provider.dart';

/// MaterialApp.router 루트 위젯
class PlaydataApp extends ConsumerWidget {
  const PlaydataApp({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final router = ref.watch(appRouterProvider);

    // 로그인하기 전에는 화면 설정을 적용하지 않는다. 로그인 화면은 누구에게나
    // 처음 모습 그대로여야 한다. 설정은 이 기기에 저장되므로, 그대로 두면 앞
    // 사람이 고른 전체 다크나 좁은 글씨가 다음 사람의 로그인 화면에 남는다.
    final signedIn = ref.watch(currentUserProvider).value != null;
    final palette = signedIn
        ? ref.watch(sideRailDarkPaletteProvider)
        : kSideRailDarkPalettes.first;
    final mode = signedIn
        ? ref.watch(appThemeModeProvider)
        : AppThemeMode.light;
    final density = signedIn ? ref.watch(appDensityProvider) : AppDensity.auto;
    final dense = density == AppDensity.compact;

    // 색 이름 하나하나가 이 값을 보고 답을 바꾼다. 테마를 만들기 전에 알려 준다.
    AppSpace.apply(compact: dense);
    if (signedIn) {
      AppColors.apply(
        dark: mode.isDark,
        accent: palette.action,
        accentDark: palette.actionDark,
        accentLight: palette.actionLight,
        rail: palette.background,
      );
    } else {
      AppColors.apply(dark: false);
    }

    return MaterialApp.router(
      // 색이 바뀌면 화면을 통째로 새로 그린다. 이미 만들어져 자리를 잡은
      // 위젯은 색을 다시 묻지 않기 때문에, 키를 바꿔 다시 만들게 한다.
      key: ValueKey('$signedIn/${mode.name}/${palette.id}/${density.name}'),
      title: AppConstants.appName,
      debugShowCheckedModeBanner: false,
      // 테마를 거치는 색과 화면 코드가 직접 부르는 색이 같은 값을 보게 한다.
      theme: AppTheme.light(
        primary: signedIn ? AppColors.primary : palette.action,
        primaryLight: signedIn ? AppColors.primaryLight : palette.actionLight,
        dark: mode.isDark,
        dense: dense,
        visualDensity: !signedIn
            ? null
            : switch (density) {
                // 자동이면 기기에 맡긴다. 데스크톱은 촘촘하게, 폰은 손가락 크기로.
                AppDensity.auto => VisualDensity.adaptivePlatformDensity,
                AppDensity.comfortable => VisualDensity.standard,
                AppDensity.compact => VisualDensity.compact,
              },
      ),
      // 좁게면 여백과 함께 글자도 줄인다. 폭은 그대로라 목록이 비지 않는다.
      // 첨삭 창은 화면을 옮겨도 살아 있어야 해서 Navigator 위 층에 띄운다.
      builder: (context, child) => CompactTextScale(
        compact: dense,
        child: ReviewDockHost(child: child ?? const SizedBox.shrink()),
      ),
      routerConfig: router,
    );
  }
}
