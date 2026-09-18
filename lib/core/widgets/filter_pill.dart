import 'package:flutter/material.dart';

import '../theme/app_colors.dart';
import '../../core/theme/app_space.dart';

/// 왼쪽 정렬 뷰 전환 칩 (재원/퇴소, 기수 상태, 좌석 탭 등)
class FilterPill extends StatelessWidget {
  const FilterPill({
    super.key,
    required this.label,
    required this.selected,
    required this.onTap,
    this.count,
  });

  final String label;
  final int? count;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final text = count == null ? label : '$label $count';
    return Material(
      color: selected ? AppColors.primaryLight : AppColors.surfaceVariant,
      borderRadius: BorderRadius.circular(20),
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(20),
        child: Container(
          padding: EdgeInsets.symmetric(horizontal: AppSpace.s(14), vertical: AppSpace.s(8)),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(20),
            border: Border.all(
              color: selected
                  ? AppColors.primary.withValues(alpha: 0.35)
                  : AppColors.border,
            ),
          ),
          child: Text(
            text,
            style: TextStyle(
              fontSize: 13,
              fontWeight: selected ? FontWeight.w700 : FontWeight.w500,
              color: selected ? AppColors.primary : AppColors.textSecondary,
            ),
          ),
        ),
      ),
    );
  }
}

/// 필터 칩 + 우측 CTA를 한 줄에 배치하는 페이지 헤더
class FilterPillHeader extends StatelessWidget {
  const FilterPillHeader({
    super.key,
    required this.pills,
    this.trailing,
    this.title,
  });

  final List<Widget> pills;
  final Widget? trailing;
  final String? title;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: AppColors.surface,
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          if (title != null && title!.trim().isNotEmpty)
            Padding(
              padding: EdgeInsets.fromLTRB(AppSpace.s(16), AppSpace.s(12), AppSpace.s(16), AppSpace.s(0)),
              child: Text(
                title!,
                style: Theme.of(context).textTheme.titleMedium?.copyWith(
                      fontWeight: FontWeight.w700,
                      color: AppColors.textPrimary,
                    ),
                overflow: TextOverflow.ellipsis,
              ),
            ),
          Padding(
            padding: EdgeInsets.fromLTRB(
              AppSpace.s(16),
              title != null && title!.trim().isNotEmpty ? AppSpace.s(10) : AppSpace.s(12),
              AppSpace.s(8),
              AppSpace.s(12),
            ),
            child: Row(
              children: [
                Expanded(
                  child: SingleChildScrollView(
                    scrollDirection: Axis.horizontal,
                    child: Row(
                      children: [
                        for (var i = 0; i < pills.length; i++) ...[
                          if (i > 0) SizedBox(width: AppSpace.s(8)),
                          pills[i],
                        ],
                      ],
                    ),
                  ),
                ),
                if (trailing != null) ...[
                  SizedBox(width: AppSpace.s(8)),
                  trailing!,
                  SizedBox(width: AppSpace.s(8)),
                ],
              ],
            ),
          ),
          Divider(height: 1, color: AppColors.border),
        ],
      ),
    );
  }
}
