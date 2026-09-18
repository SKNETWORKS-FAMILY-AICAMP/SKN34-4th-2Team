import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:playdata_lms/core/theme/app_colors.dart';
import 'package:playdata_lms/core/theme/app_theme.dart';
import 'package:playdata_lms/core/theme/shell_chrome.dart';
import 'package:playdata_lms/features/settings/presentation/appearance_settings_screen.dart';
import 'package:playdata_lms/shared/providers/app_appearance_provider.dart';
import 'package:playdata_lms/shared/providers/side_rail_theme_provider.dart';
import 'package:playdata_lms/shared/widgets/app_side_rail.dart';
import 'package:shared_preferences/shared_preferences.dart';

Future<ProviderContainer> _pumpSettings(WidgetTester tester) async {
  SharedPreferences.setMockInitialValues({});
  // 설정이 세 묶음이라 기본 시험 화면(800x600)에는 다 안 들어간다. 아래쪽
  // 항목이 화면 밖에 있으면 아예 만들어지지 않아 누를 수도 없다.
  tester.view.physicalSize = const Size(1000, 2400);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.resetPhysicalSize);
  addTearDown(tester.view.resetDevicePixelRatio);
  final container = ProviderContainer();
  addTearDown(container.dispose);
  await tester.pumpWidget(
    UncontrolledProviderScope(
      container: container,
      child: const MaterialApp(home: AppearanceSettingsScreen()),
    ),
  );
  await tester.pumpAndSettle();
  return container;
}

Future<void> _tapInList(WidgetTester tester, String label) async {
  await tester.tap(find.text(label));
  await tester.pumpAndSettle();
}

void main() {
  setUp(() => AppColors.apply(dark: false));
  tearDown(() => AppColors.apply(dark: false));

  testWidgets('picking a theme sticks, and the rail follows it', (
    tester,
  ) async {
    final container = await _pumpSettings(tester);
    expect(container.read(appThemeModeProvider), AppThemeMode.light);
    expect(container.read(sideRailDarkModeProvider), isFalse);

    await tester.tap(find.text('사이드바 다크'));
    await tester.pumpAndSettle();
    expect(container.read(appThemeModeProvider), AppThemeMode.railDark);
    // 사이드바는 따로 스위치를 두지 않고 이 설정을 따라간다.
    expect(container.read(sideRailDarkModeProvider), isTrue);

    await tester.tap(find.text('전체 다크'));
    await tester.pumpAndSettle();
    expect(container.read(appThemeModeProvider), AppThemeMode.dark);
    expect(container.read(sideRailDarkModeProvider), isTrue);
  });

  testWidgets('the chosen theme survives a restart', (tester) async {
    await _pumpSettings(tester);
    await tester.tap(find.text('전체 다크'));
    await tester.pumpAndSettle();

    // 앱을 다시 연 셈이다. 저장해 둔 값을 읽어야 한다.
    final reopened = ProviderContainer();
    addTearDown(reopened.dispose);
    expect(reopened.read(appThemeModeProvider), AppThemeMode.light);
    await tester.pump(const Duration(milliseconds: 50));
    expect(reopened.read(appThemeModeProvider), AppThemeMode.dark);
  });

  testWidgets('density can be set, and auto defers to the screen', (
    tester,
  ) async {
    final container = await _pumpSettings(tester);
    expect(container.read(appDensityProvider), AppDensity.auto);
    expect(AppDensity.auto.resolve(byScreen: true), isTrue);
    expect(AppDensity.auto.resolve(byScreen: false), isFalse);

    await _tapInList(tester, '좁게');
    expect(container.read(appDensityProvider), AppDensity.compact);
    // 고르고 나면 화면 크기와 무관하게 그 값을 쓴다.
    expect(AppDensity.compact.resolve(byScreen: false), isTrue);
    expect(AppDensity.comfortable.resolve(byScreen: true), isFalse);
  });

  testWidgets('the sidebar palette can be picked here', (tester) async {
    final container = await _pumpSettings(tester);
    expect(container.read(sideRailDarkPaletteIndexProvider), 0);

    await _tapInList(tester, kSideRailDarkPalettes[2].label);
    expect(container.read(sideRailDarkPaletteIndexProvider), 2);
    expect(
      container.read(sideRailDarkPaletteProvider).id,
      kSideRailDarkPalettes[2].id,
    );
  });

  test('turning the dark screen on changes what the color names answer', () {
    AppColors.apply(dark: false);
    final lightSurface = AppColors.surface;
    final lightText = AppColors.textPrimary;

    AppColors.apply(dark: true);
    expect(AppColors.surface, isNot(lightSurface));
    expect(AppColors.textPrimary, isNot(lightText));
    // 어두운 바탕 위의 글씨는 바탕보다 밝아야 한다.
    expect(
      AppColors.textPrimary.computeLuminance(),
      greaterThan(AppColors.surface.computeLuminance()),
    );
    // 로그인 화면의 시네마틱 색은 원래 어두워서 테마를 타지 않는다.
    expect(AppColors.cinematicBg, const Color(0xFF05070F));
  });

  test('the chosen palette reaches every place that asks for primary', () {
    final violet = kSideRailDarkPalettes.firstWhere(
      (p) => p.id == 'soft_cinematic',
    );
    AppColors.apply(
      dark: false,
      accent: violet.action,
      accentDark: violet.actionDark,
      accentLight: violet.actionLight,
      rail: violet.background,
    );
    // 예전에는 테마를 거치는 버튼만 보라가 되고, 이 이름을 직접 부르는
    // 칩·링크·마일리지 카드는 파랑에 머물렀다.
    expect(AppColors.primary, violet.action);
    expect(AppColors.primaryLight, violet.actionLight);
    expect(AppColors.sidebar, violet.background);
    // 공가 같은 뜻 있는 파랑은 따라가지 않는다. 강조색이 청록이면 외출과 겹친다.
    expect(AppColors.info, const Color(0xFF0055FF));

    // 어두운 화면에서도 색조는 그대로다.
    AppColors.apply(dark: true, accent: violet.action);
    expect(
      HSLColor.fromColor(AppColors.primary).hue,
      closeTo(HSLColor.fromColor(violet.action).hue, 1),
    );

    // 강조색을 넘기지 않으면 원래 파랑으로 돌아간다.
    AppColors.apply(dark: false);
    expect(AppColors.primary, const Color(0xFF0055FF));
  });

  test('compact density shrinks buttons and inputs, not just one card', () {
    final roomy = AppTheme.light(visualDensity: VisualDensity.standard);
    final tight = AppTheme.light(
      dense: true,
      visualDensity: VisualDensity.compact,
    );

    // 예전에는 대시보드 달력 한 곳만 바뀌어 골라도 달라진 게 없어 보였다.
    expect(tight.visualDensity, VisualDensity.compact);
    final roomyPad = roomy.inputDecorationTheme.contentPadding!.resolve(
      TextDirection.ltr,
    );
    final tightPad = tight.inputDecorationTheme.contentPadding!.resolve(
      TextDirection.ltr,
    );
    expect(tightPad.vertical, lessThan(roomyPad.vertical));

    final roomyButton = roomy.filledButtonTheme.style!.minimumSize!.resolve(
      {},
    )!;
    final tightButton = tight.filledButtonTheme.style!.minimumSize!.resolve(
      {},
    )!;
    expect(tightButton.height, lessThan(roomyButton.height));
  });

  test('the top bar ignores the sidebar color and follows the page', () {
    // 사이드바 색을 바꿀 때마다 화면 위쪽 전체가 같이 바뀌었다.
    for (final palette in kSideRailDarkPalettes) {
      AppColors.apply(dark: false, accent: palette.action);
      expect(ShellChrome.appBarBackground(true, palette), AppColors.background);
      expect(
        ShellChrome.appBarBackground(false, palette),
        AppColors.background,
      );
      expect(ShellChrome.appBarForeground(true), AppColors.textPrimary);
    }
    // 전체 다크에서는 본문처럼 어둡다.
    AppColors.apply(dark: true);
    // 본문 바탕과 이어진다. 카드 색이면 세 덩어리로 갈라져 보였다.
    expect(ShellChrome.appBarBackground(true), AppColors.background);
    expect(
      AppColors.background.computeLuminance(),
      lessThan(0.05),
    );
  });

  test('the corner above the rail is painted exactly like the rail', () {
    // 상단 바가 사이드바 머리 자리까지 차지해 사이드바가 로고 아래에서 끊겨 보였다.
    // 위 칸과 레일이 다른 계산을 하면 경계가 다시 생긴다.
    for (final dark in [false, true]) {
      AppColors.apply(dark: dark);
      for (final palette in kSideRailDarkPalettes) {
        for (final railDark in [false, true]) {
          final rail = SideRailStyle.palette(
            isDark: railDark,
            darkPalette: palette,
            child: const SizedBox.shrink(),
          );
          expect(
            ShellChrome.railBackground(railDark, palette),
            rail.background,
            reason: '${palette.id} railDark=$railDark dark=$dark',
          );
        }
      }
    }
  });

  double contrast(Color a, Color b) {
    final la = a.computeLuminance(), lb = b.computeLuminance();
    final hi = la > lb ? la : lb, lo = la > lb ? lb : la;
    return (hi + 0.05) / (lo + 0.05);
  }

  test('top bar chips look like the cards on the page', () {
    // 기수 선택·프로필 칩이 옅은 회색이라 본문의 흰 카드들과 색이 달랐다.
    // 기수 선택은 사이드바 다크에서 흰색 10%라 밝은 상단 바에 묻혔다.
    for (final dark in [false, true]) {
      for (final palette in kSideRailDarkPalettes) {
        AppColors.apply(
          dark: dark,
          accent: palette.action,
          accentDark: palette.actionDark,
          accentLight: palette.actionLight,
          rail: palette.background,
        );
        final fill = ShellChrome.chipFill(true);
        expect(fill, AppColors.surface);
        expect(ShellChrome.chipBorder(true), AppColors.border);
        expect(
          contrast(ShellChrome.appBarForeground(true), fill),
          greaterThanOrEqualTo(4.5),
          reason: '${palette.id} dark=$dark 이름',
        );
        expect(
          contrast(ShellChrome.appBarMuted(true), fill),
          greaterThanOrEqualTo(3),
          reason: '${palette.id} dark=$dark 기수',
        );
      }
    }
  });

  test(
    'in dark mode, accents carry white text and still show on the dark ground',
    () {
      // 너무 밝히면 챗봇 머리처럼 흰 글씨가 사라지고, 너무 어두우면 바탕에 묻힌다.
      for (final palette in kSideRailDarkPalettes) {
        AppColors.apply(dark: true, accent: palette.action);
        for (final (name, fill) in [
          ('primary', AppColors.primary),
          ('success', AppColors.success),
          ('error', AppColors.error),
          ('info', AppColors.info),
        ]) {
          expect(
            contrast(fill, Colors.white),
            greaterThanOrEqualTo(4.5),
            reason: '${palette.id} $name 위의 흰 글씨',
          );
          expect(
            contrast(fill, AppColors.surface),
            greaterThanOrEqualTo(3),
            reason: '${palette.id} $name 이 어두운 바탕에서',
          );
        }
      }
    },
  );
}
