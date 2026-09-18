import 'package:flutter/material.dart';

import '../../../../core/theme/app_colors.dart';
import '../../../../core/theme/app_layout.dart';
import '../../../../core/theme/app_space.dart';

/// 게시판 UI 공통 색상·스타일
abstract final class BoardUi {
  static const favorite = Color(0xFFF59E0B);
  static Color get favoriteBadgeBg => AppColors.tint(const Color(0xFFFEF3C7));
  static const favoriteBadgeText = Color(0xFFB45309);
  static const favoriteBorder = Color(0xFFFDE68A);
  static Color get discordChipBg => AppColors.primaryLight;
  static Color get discordChipText => AppColors.primary;
  static Color get activeBadgeBg => AppColors.tint(const Color(0xFFDCFCE7));
  static Color get activeBadgeText => AppColors.success;
  static Color get listBackground => AppColors.background;
  static const contentMaxWidth = AppLayout.list;

  static BoxDecoration cardDecoration({
    bool isFavorite = false,
    bool isDiscord = false,
  }) {
    return BoxDecoration(
      color: AppColors.surface,
      borderRadius: BorderRadius.circular(14),
      border: Border.all(
        color: isFavorite
            ? favoriteBorder
            : isDiscord
            ? AppColors.primary.withValues(alpha: 0.35)
            : AppColors.border,
      ),
      boxShadow: [
        BoxShadow(
          color: AppColors.shadow,
          blurRadius: 12,
          offset: const Offset(0, 4),
        ),
      ],
    );
  }

  static ButtonStyle primaryButtonStyle() {
    return FilledButton.styleFrom(
      backgroundColor: AppColors.primary,
      foregroundColor: Colors.white,
      padding: EdgeInsets.symmetric(horizontal: AppSpace.s(16), vertical: AppSpace.s(10)),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      elevation: 0,
    );
  }
}

/// 관리자/강사 게시판 공통 페이지 헤더
class BoardPageHeader extends StatelessWidget {
  const BoardPageHeader({
    super.key,
    required this.title,
    required this.subtitle,
    this.action,
  });

  final String title;
  final String subtitle;
  final Widget? action;

  @override
  Widget build(BuildContext context) {
    return Container(
      color: AppColors.surface,
      padding: EdgeInsets.fromLTRB(AppSpace.s(24), AppSpace.s(20), AppSpace.s(24), AppSpace.s(16)),
      child: Align(
        alignment: Alignment.topCenter,
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: BoardUi.contentMaxWidth),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      title,
                      style: TextStyle(
                        fontSize: 22,
                        fontWeight: FontWeight.bold,
                        color: AppColors.textPrimary,
                      ),
                    ),
                    SizedBox(height: AppSpace.s(4)),
                    Text(
                      subtitle,
                      style: TextStyle(
                        fontSize: 13,
                        color: AppColors.textSecondary,
                      ),
                    ),
                  ],
                ),
              ),
              if (action != null) ...[
                SizedBox(width: AppSpace.s(12)),
                action!,
              ],
            ],
          ),
        ),
      ),
    );
  }
}

/// 게시판 탭 바 (밑줄 스타일)
class BoardTabBar extends StatelessWidget {
  const BoardTabBar({
    super.key,
    required this.tabs,
    required this.controller,
  });

  final List<String> tabs;
  final TabController controller;

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: controller,
      builder: (context, _) {
        return Container(
          decoration: BoxDecoration(
            color: AppColors.surface,
            border: Border(bottom: BorderSide(color: AppColors.border)),
          ),
          child: Row(
            children: List.generate(tabs.length, (i) {
              final selected = controller.index == i;
              return GestureDetector(
                onTap: () => controller.animateTo(i),
                child: Container(
                  padding: EdgeInsets.symmetric(
                    horizontal: AppSpace.s(20),
                    vertical: AppSpace.s(14),
                  ),
                  decoration: BoxDecoration(
                    border: Border(
                      bottom: BorderSide(
                        color: selected
                            ? AppColors.primary
                            : Colors.transparent,
                        width: 2,
                      ),
                    ),
                  ),
                  child: Text(
                    tabs[i],
                    style: TextStyle(
                      fontSize: 14,
                      fontWeight: selected ? FontWeight.w700 : FontWeight.w500,
                      color: selected
                          ? AppColors.textPrimary
                          : AppColors.textHint,
                    ),
                  ),
                ),
              );
            }),
          ),
        );
      },
    );
  }
}

class BoardMetaChip extends StatelessWidget {
  const BoardMetaChip({
    super.key,
    required this.label,
    this.variant = BoardMetaChipVariant.neutral,
  });

  final String label;
  final BoardMetaChipVariant variant;

  @override
  Widget build(BuildContext context) {
    final (bg, fg) = switch (variant) {
      BoardMetaChipVariant.neutral => (
        AppColors.primaryLight,
        AppColors.textSecondary,
      ),
      BoardMetaChipVariant.favorite => (
        BoardUi.favoriteBadgeBg,
        BoardUi.favoriteBadgeText,
      ),
      BoardMetaChipVariant.discord => (
        BoardUi.discordChipBg,
        BoardUi.discordChipText,
      ),
      BoardMetaChipVariant.active => (
        BoardUi.activeBadgeBg,
        BoardUi.activeBadgeText,
      ),
      BoardMetaChipVariant.schedule => (
        AppColors.surfaceVariant,
        AppColors.textSecondary,
      ),
    };

    return Container(
      padding: EdgeInsets.symmetric(horizontal: AppSpace.s(8), vertical: AppSpace.s(3)),
      decoration: BoxDecoration(
        color: bg,
        borderRadius: BorderRadius.circular(6),
      ),
      child: Text(
        label,
        style: TextStyle(
          fontSize: 11,
          fontWeight: FontWeight.w600,
          color: fg,
        ),
      ),
    );
  }
}

enum BoardMetaChipVariant { neutral, favorite, discord, active, schedule }

class BoardScheduleChip extends StatelessWidget {
  const BoardScheduleChip({
    super.key,
    required this.icon,
    required this.label,
    this.variant = BoardMetaChipVariant.schedule,
  });

  final IconData icon;
  final String label;
  final BoardMetaChipVariant variant;

  @override
  Widget build(BuildContext context) {
    final (bg, fg) = switch (variant) {
      BoardMetaChipVariant.favorite => (
        BoardUi.favoriteBadgeBg,
        BoardUi.favoriteBadgeText,
      ),
      BoardMetaChipVariant.active => (
        BoardUi.activeBadgeBg,
        BoardUi.activeBadgeText,
      ),
      _ => (AppColors.surfaceVariant, AppColors.textSecondary),
    };

    return Container(
      padding: EdgeInsets.symmetric(horizontal: AppSpace.s(8), vertical: AppSpace.s(4)),
      decoration: BoxDecoration(
        color: bg,
        borderRadius: BorderRadius.circular(6),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 13, color: fg),
          SizedBox(width: AppSpace.s(4)),
          Text(
            label,
            style: TextStyle(
              fontSize: 11,
              fontWeight: FontWeight.w500,
              color: fg,
            ),
          ),
        ],
      ),
    );
  }
}
