import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';

const _kThemeModeKey = 'app_theme_mode_v1';
const _kDensityKey = 'app_density_v1';

/// 화면 테마.
///
/// 사이드바만 어둡게 하는 중간 단계를 둔다. 밝은 본문에 어두운 사이드바가
/// 붙은 모양을 오래 써 왔고, 그 조합을 좋아하는 사람이 있다.
enum AppThemeMode {
  light('라이트', '전체를 밝게'),
  railDark('사이드바 다크', '본문은 밝게, 사이드바만 어둡게'),
  dark('전체 다크', '전체를 어둡게');

  const AppThemeMode(this.label, this.description);

  final String label;
  final String description;

  /// 본문까지 어두운가.
  bool get isDark => this == AppThemeMode.dark;

  /// 사이드바가 어두운가. 전체 다크면 사이드바도 당연히 어둡다.
  bool get isRailDark => this != AppThemeMode.light;
}

/// 화면 밀도.
enum AppDensity {
  auto('자동', '화면 크기에 맞춥니다'),
  comfortable('보통', '여유 있게'),
  compact('좁게', '한 화면에 더 많이');

  const AppDensity(this.label, this.description);

  final String label;
  final String description;

  /// 자동일 때는 화면이 정한 값을 따른다.
  bool resolve({required bool byScreen}) => switch (this) {
    AppDensity.auto => byScreen,
    AppDensity.comfortable => false,
    AppDensity.compact => true,
  };
}

class AppThemeModeNotifier extends Notifier<AppThemeMode> {
  @override
  AppThemeMode build() {
    Future<void>(() async {
      final prefs = await SharedPreferences.getInstance();
      if (!ref.mounted) return;
      final saved = prefs.getString(_kThemeModeKey);
      if (saved != null) {
        state = AppThemeMode.values.firstWhere(
          (mode) => mode.name == saved,
          orElse: () => AppThemeMode.light,
        );
        return;
      }
      // 예전에는 사이드바만 어둡게 하는 스위치 하나였다. 그 값을 물려받는다.
      if (prefs.getBool('sidebar_dark_mode') ??
          prefs.getBool('app_dark_mode') ??
          false) {
        state = AppThemeMode.railDark;
      }
    });
    return AppThemeMode.light;
  }

  Future<void> set(AppThemeMode mode) async {
    if (state == mode) return;
    state = mode;
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_kThemeModeKey, mode.name);
  }
}

final appThemeModeProvider =
    NotifierProvider<AppThemeModeNotifier, AppThemeMode>(
      AppThemeModeNotifier.new,
    );

class AppDensityNotifier extends Notifier<AppDensity> {
  @override
  AppDensity build() {
    Future<void>(() async {
      final prefs = await SharedPreferences.getInstance();
      if (!ref.mounted) return;
      final saved = prefs.getString(_kDensityKey);
      if (saved == null) return;
      state = AppDensity.values.firstWhere(
        (density) => density.name == saved,
        orElse: () => AppDensity.auto,
      );
    });
    return AppDensity.auto;
  }

  Future<void> set(AppDensity density) async {
    if (state == density) return;
    state = density;
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_kDensityKey, density.name);
  }
}

final appDensityProvider = NotifierProvider<AppDensityNotifier, AppDensity>(
  AppDensityNotifier.new,
);
