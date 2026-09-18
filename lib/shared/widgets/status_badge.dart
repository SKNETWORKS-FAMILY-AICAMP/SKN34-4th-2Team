import 'package:flutter/material.dart';

import '../../core/theme/app_colors.dart';
import '../../core/theme/app_space.dart';

/// 상태 pill 뱃지 — 대시보드/목록/기록/평가 공통
class StatusBadge extends StatelessWidget {
  const StatusBadge({
    super.key,
    required this.label,
    required this.color,
    this.icon,
  });

  final String label;
  final Color color;
  final IconData? icon;

  factory StatusBadge.success(String label, {IconData? icon}) =>
      StatusBadge(label: label, color: AppColors.success, icon: icon);

  factory StatusBadge.warning(String label, {IconData? icon}) =>
      StatusBadge(label: label, color: AppColors.warning, icon: icon);

  factory StatusBadge.error(String label, {IconData? icon}) =>
      StatusBadge(label: label, color: AppColors.error, icon: icon);

  factory StatusBadge.info(String label, {IconData? icon}) =>
      StatusBadge(label: label, color: AppColors.primary, icon: icon);

  factory StatusBadge.neutral(String label, {IconData? icon}) =>
      StatusBadge(label: label, color: AppColors.badgeClosed, icon: icon);

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: EdgeInsets.symmetric(
        horizontal: icon != null ? AppSpace.s(8) : AppSpace.s(8),
        vertical: icon != null ? AppSpace.s(4) : AppSpace.s(3),
      ),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(20),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (icon != null) ...[
            Icon(icon, size: 13, color: color),
            SizedBox(width: AppSpace.s(3)),
          ],
          Flexible(
            child: Text(
              label,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(
                fontSize: 11,
                fontWeight: FontWeight.w700,
                color: color,
                height: 1.2,
              ),
            ),
          ),
        ],
      ),
    );
  }
}
