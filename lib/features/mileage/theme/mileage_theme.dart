import 'package:flutter/material.dart';

import '../../../core/theme/app_colors.dart';
import '../../../core/theme/app_layout.dart';
import '../../../core/theme/app_space.dart';

/// 마일리지 화면 전용 accent (AppColors 기반)
abstract final class MileageColors {
  static Color get primary => AppColors.primary;
  static Color get primaryDark => AppColors.primaryDark;
  static Color get primaryLight => AppColors.primary;
  static Color get cardGradientStart => AppColors.primaryDark;
  static Color get cardGradientEnd => AppColors.sidebar;
  static Color get chipBg => AppColors.primaryLight;
  static Color get infoBanner => AppColors.primaryLight;
  static Color get infoBannerBorder => AppColors.primary.withValues(alpha: 0.35);

  static const gifticonTag = Color(0xFFEA580C);
  static const bookTag = Color(0xFF16A34A);
  static Color get courseTag => AppColors.primary;

  static Color categoryTagColor(String category) => switch (category) {
    'gifticon' => gifticonTag,
    'book' => bookTag,
    'onlineCourse' => courseTag,
    _ => primary,
  };

  static Color statusColor(String status) => switch (status) {
    'approved' => AppColors.success,
    'pending' => AppColors.primary,
    'modify_requested' => AppColors.warning,
    'rejected' => AppColors.error,
    'cancelled' => AppColors.textSecondary,
    _ => AppColors.textSecondary,
  };
}

/// 마일리지 화면 공통 레이아웃 상수
abstract final class MileageLayout {
  static const pagePaddingH = 20.0;
  static const sectionGap = 12.0;
  static const maxContentWidth = AppLayout.reading;
  static const cardHeight = 140.0;
  static const buttonHeight = 36.0;
}

ButtonStyle mileagePrimaryButtonStyle({double? minHeight}) {
  return FilledButton.styleFrom(
    backgroundColor: MileageColors.primary,
    foregroundColor: Colors.white,
    minimumSize: Size(0, minHeight ?? MileageLayout.buttonHeight),
    padding: EdgeInsets.symmetric(horizontal: AppSpace.s(16), vertical: AppSpace.s(8)),
    textStyle: const TextStyle(fontSize: 13, fontWeight: FontWeight.w600),
    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
  );
}

ButtonStyle mileageOutlinedButtonStyle({double? minHeight}) {
  return OutlinedButton.styleFrom(
    foregroundColor: MileageColors.primary,
    minimumSize: Size(0, minHeight ?? MileageLayout.buttonHeight),
    padding: EdgeInsets.symmetric(horizontal: AppSpace.s(12), vertical: AppSpace.s(8)),
    textStyle: const TextStyle(fontSize: 13, fontWeight: FontWeight.w500),
    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
  );
}

String formatMileageAmount(int n) => n.abs().toString().replaceAllMapped(
  RegExp(r'(\d{1,3})(?=(\d{3})+(?!\d))'),
  (m) => '${m[1]},',
);

String formatMileageSigned(int n) {
  final prefix = n >= 0 ? '+ ' : '- ';
  return '$prefix${formatMileageAmount(n)} P';
}

String formatMileageM(int n) => '${formatMileageAmount(n)}M';
