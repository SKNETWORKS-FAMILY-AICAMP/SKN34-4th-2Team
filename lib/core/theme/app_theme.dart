import 'package:flutter/material.dart';

import 'app_colors.dart';
import '../widgets/app_dropdown.dart';

abstract final class AppTheme {
  /// 앱 글꼴. `ThemeData.fontFamily`는 textTheme에만 붙고, 칩·채움 버튼·스낵바·
  /// 하단 내비 라벨처럼 테마에 TextStyle을 직접 주는 부품은 이 값을 따로 받아야
  /// 기본 글꼴로 떨어지지 않는다(글자가 칩 안에서 눌리거나 다른 글꼴로 보인다).
  static const fontFamily = 'Paperlogy';

  /// 삭제·위험 액션용 FilledButton 스타일
  static ButtonStyle get destructiveFilled => FilledButton.styleFrom(
    backgroundColor: AppColors.error,
    foregroundColor: Colors.white,
    disabledBackgroundColor: AppColors.error.withValues(alpha: 0.45),
    disabledForegroundColor: Colors.white,
  );

  /// [dark]는 `AppColors`가 이미 어두운 값을 돌려주고 있다는 뜻이다.
  /// 여기서는 밝기만 알려 주면 나머지 색은 저절로 따라온다.
  /// [dense]면 버튼·입력칸의 높이와 안쪽 여백을 줄인다. [visualDensity]는
  /// 목록 줄·체크박스처럼 Material이 알아서 줄이는 부품에 쓰인다.
  static ThemeData light({
    Color? primary,
    Color? primaryLight,
    bool dark = false,
    bool dense = false,
    VisualDensity? visualDensity,
  }) {
    primary ??= AppColors.primary;
    primaryLight ??= AppColors.primaryLight;
    final colorScheme = ColorScheme(
      brightness: dark ? Brightness.dark : Brightness.light,
      primary: primary,
      onPrimary: Colors.white,
      primaryContainer: primaryLight,
      onPrimaryContainer: primary,
      secondary: AppColors.secondary,
      onSecondary: Colors.white,
      surface: AppColors.surface,
      onSurface: AppColors.textPrimary,
      error: AppColors.error,
      onError: Colors.white,
    );

    return ThemeData(
      useMaterial3: true,
      brightness: dark ? Brightness.dark : Brightness.light,
      visualDensity: visualDensity,
      fontFamily: fontFamily,
      colorScheme: colorScheme,
      scaffoldBackgroundColor: AppColors.background,
      dividerColor: AppColors.divider,
      appBarTheme: AppBarTheme(
        backgroundColor: AppColors.surface,
        foregroundColor: AppColors.textPrimary,
        elevation: 0,
        scrolledUnderElevation: 0,
        centerTitle: false,
        surfaceTintColor: Colors.transparent,
      ),
      cardTheme: CardThemeData(
        color: AppColors.surface,
        elevation: 0,
        shadowColor: AppColors.shadow,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(14),
          side: BorderSide(color: AppColors.border),
        ),
      ),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: AppColors.surface,
        hintStyle: TextStyle(color: AppColors.textHint, fontSize: 14),
        labelStyle: TextStyle(
          color: AppColors.textSecondary,
          fontSize: 13,
        ),
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(10),
          borderSide: BorderSide(color: AppColors.border),
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(10),
          borderSide: BorderSide(color: AppColors.border),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(10),
          borderSide: BorderSide(color: primary, width: 1.5),
        ),
        contentPadding: EdgeInsets.symmetric(
          horizontal: dense ? 12 : 16,
          vertical: dense ? 10 : 14,
        ),
      ),
      filledButtonTheme: FilledButtonThemeData(
        style: FilledButton.styleFrom(
          backgroundColor: primary,
          foregroundColor: Colors.white,
          disabledBackgroundColor: primary.withValues(alpha: 0.45),
          disabledForegroundColor: Colors.white,
          minimumSize: Size(64, dense ? 34 : 40),
          padding: EdgeInsets.symmetric(
            horizontal: dense ? 12 : 16,
            vertical: dense ? 8 : 12,
          ),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(10),
          ),
          elevation: 0,
          textStyle: const TextStyle(
            fontFamily: fontFamily,
            fontSize: 14,
            fontWeight: FontWeight.w600,
          ),
        ),
      ),
      elevatedButtonTheme: ElevatedButtonThemeData(
        style: ElevatedButton.styleFrom(
          backgroundColor: primary,
          foregroundColor: Colors.white,
          disabledBackgroundColor: primary.withValues(alpha: 0.45),
          disabledForegroundColor: Colors.white,
          minimumSize: Size(double.infinity, dense ? 42 : 50),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(12),
          ),
          elevation: 0,
          textStyle: const TextStyle(
            fontFamily: fontFamily,
            fontSize: 16,
            fontWeight: FontWeight.w600,
          ),
        ),
      ),
      outlinedButtonTheme: OutlinedButtonThemeData(
        style: OutlinedButton.styleFrom(
          foregroundColor: AppColors.textPrimary,
          side: BorderSide(color: AppColors.border),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(10),
          ),
        ),
      ),
      textButtonTheme: TextButtonThemeData(
        style: TextButton.styleFrom(
          foregroundColor: primary,
        ),
      ),
      navigationBarTheme: NavigationBarThemeData(
        backgroundColor: AppColors.surface,
        indicatorColor: primaryLight,
        elevation: 0,
        height: 64,
        labelTextStyle: WidgetStateProperty.resolveWith((states) {
          if (states.contains(WidgetState.selected)) {
            return TextStyle(
              fontFamily: fontFamily,
              color: primary,
              fontWeight: FontWeight.w600,
              fontSize: 12,
            );
          }
          return TextStyle(
            fontFamily: fontFamily,
            color: AppColors.textSecondary,
            fontSize: 12,
          );
        }),
      ),
      navigationRailTheme: NavigationRailThemeData(
        backgroundColor: AppColors.surface,
        selectedIconTheme: IconThemeData(color: primary, size: 24),
        unselectedIconTheme: IconThemeData(
          color: AppColors.textSecondary,
          size: 24,
        ),
        indicatorColor: primaryLight,
      ),
      drawerTheme: DrawerThemeData(
        backgroundColor: AppColors.surface,
      ),
      tabBarTheme: TabBarThemeData(
        labelColor: primary,
        unselectedLabelColor: AppColors.textSecondary,
        indicatorColor: primary,
        dividerColor: AppColors.border,
      ),
      chipTheme: ChipThemeData(
        backgroundColor: primaryLight,
        labelStyle: TextStyle(
          fontFamily: fontFamily,
          color: primary,
          fontSize: 12,
        ),
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(8),
          side: BorderSide(color: AppColors.border),
        ),
        side: BorderSide.none,
      ),
      menuTheme: MenuThemeData(style: AppMenuStyles.panel),
      popupMenuTheme: AppMenuStyles.popupTheme,
      checkboxTheme: CheckboxThemeData(
        fillColor: WidgetStateProperty.resolveWith((states) {
          if (states.contains(WidgetState.selected)) {
            return primary;
          }
          return null;
        }),
      ),
      progressIndicatorTheme: ProgressIndicatorThemeData(
        color: primary,
      ),
      snackBarTheme: SnackBarThemeData(
        behavior: SnackBarBehavior.floating,
        backgroundColor: AppColors.textPrimary,
        elevation: 2,
        width: 420,
        insetPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
        contentTextStyle: TextStyle(
          fontFamily: fontFamily,
          fontSize: 14,
          fontWeight: FontWeight.w500,
          color: Colors.white,
        ),
      ),
    );
  }
}
