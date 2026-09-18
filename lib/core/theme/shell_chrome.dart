import 'package:flutter/material.dart';

import 'app_colors.dart';
import '../../shared/providers/side_rail_theme_provider.dart';

/// 상단 바 색. 본문 바탕을 따른다.
abstract final class ShellChrome {
  /// 넓은 화면의 사이드바 폭. 상단 바의 사이드바 칸과 로고 칸이 이 값에 맞춘다.
  static const railWidth = 208.0;

  // 상단 바는 사이드바 색을 따라가지 않는다. 본문 바탕을 따른다.
  //
  // 예전에는 사이드바를 어둡게 하면 상단 바도 사이드바 팔레트 색으로 칠했다.
  // 사이드바 색을 바꿀 때마다 화면 위쪽 전체가 같이 바뀌어 산만했다. 이제
  // 사이드바 색은 사이드바에만 남고, 상단 바는 본문 바탕과 이어진다. 인자는 호출하는 곳을 건드리지 않으려고 남겨 두었다.

  /// 본문 바탕과 같은 색. 카드 색(surface)으로 칠하면 상단 바·사이드바·본문이
  /// 세 덩어리로 갈라져 보인다.
  static Color appBarBackground(bool isDark, [SideRailDarkPalette? palette]) =>
      AppColors.background;

  static Color appBarForeground(bool isDark) => AppColors.textPrimary;

  static Color appBarMuted(bool isDark) => AppColors.textSecondary;

  static Color appBarBorder(bool isDark) => AppColors.border;

  /// 상단 바의 기수 선택·프로필 칩. 본문 카드와 같은 바탕·테두리를 쓴다.
  ///
  /// 예전에는 옅은 회색이라 같은 화면의 흰 카드들과 색이 달랐다. 기수 선택은
  /// 사이드바 다크일 때 흰색 10%를 깔았는데, 상단 바가 본문처럼 밝아진 뒤로는
  /// 밝은 바탕에 묻혀 칩이 보이지 않았다.
  static Color chipFill(bool isDark) => AppColors.surface;

  static Color chipBorder(bool isDark) => AppColors.border;

  /// 사이드바 바탕색. 사이드바 레일과 그 위 상단 바 칸이 같은 값을 쓴다.
  static Color railBackground(bool railDark, SideRailDarkPalette palette) =>
      railDark ? palette.background : AppColors.surface;

  /// 넓은 화면에서 상단 바 중 사이드바 위에 걸친 칸을 사이드바 색으로 칠한다.
  ///
  /// 상단 바는 화면 전체 폭으로 깔리므로, 그대로 두면 사이드바 머리 자리까지
  /// 상단 바 색이 차지해 사이드바가 로고 아래에서 끊겨 보인다.
  static Widget railCorner({
    required bool railDark,
    required SideRailDarkPalette palette,
    double width = railWidth,
  }) => Row(
    children: [
      Container(
        width: width,
        decoration: BoxDecoration(
          color: railBackground(railDark, palette),
          // 밝은 사이드바는 레일에 가장자리 선이 있다. 위 칸에도 이어 준다.
          border: railDark
              ? null
              : Border(right: BorderSide(color: AppColors.border)),
        ),
      ),
      const Expanded(child: SizedBox.shrink()),
    ],
  );

  /// 출결 폼 같은 상단 버튼 글씨. 버튼·링크처럼 고른 강조색을 따른다.
  static Color actionForeground(bool isDark, [SideRailDarkPalette? palette]) =>
      AppColors.primary;
}
