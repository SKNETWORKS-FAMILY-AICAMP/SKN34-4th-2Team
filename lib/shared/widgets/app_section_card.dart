import 'package:flutter/material.dart';

import '../../core/theme/app_colors.dart';
import '../../core/theme/app_space.dart';

/// 화이트 서피스 카드 — border + soft shadow
class AppSectionCard extends StatelessWidget {
  const AppSectionCard({
    super.key,
    required this.child,
    EdgeInsetsGeometry? padding,
    this.margin = EdgeInsets.zero,
    this.onTap,
  }) : _padding = padding;

  final Widget child;
  final EdgeInsetsGeometry? _padding;

  /// 비워 두면 기본 여백. 밀도 설정에 따라 줄어든다.
  EdgeInsetsGeometry get padding => _padding ?? EdgeInsets.all(AppSpace.s(16));
  final EdgeInsetsGeometry margin;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final content = Padding(padding: padding, child: child);

    return Container(
      margin: margin,
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: AppColors.border),
        boxShadow: [
          BoxShadow(
            color: AppColors.shadow,
            blurRadius: 16,
            offset: Offset(0, 4),
          ),
        ],
      ),
      clipBehavior: Clip.antiAlias,
      child: onTap == null
          ? content
          : Material(
              color: Colors.transparent,
              child: InkWell(onTap: onTap, child: content),
            ),
    );
  }
}

/// 섹션 타이틀
class AppSectionTitle extends StatelessWidget {
  const AppSectionTitle(
    this.text, {
    super.key,
    this.compact = false,
    this.trailing,
  });

  final String text;
  final bool compact;
  final Widget? trailing;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.only(bottom: AppSpace.s(10)),
      child: Row(
        children: [
          Expanded(
            child: Text(
              text,
              style: TextStyle(
                fontWeight: FontWeight.w700,
                fontSize: compact ? 14 : 16,
                color: AppColors.textPrimary,
              ),
            ),
          ),
          ?trailing,
        ],
      ),
    );
  }
}
