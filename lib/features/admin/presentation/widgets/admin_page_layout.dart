import 'package:flutter/material.dart';

import '../../../../core/theme/app_layout.dart';
import '../../../../core/theme/app_colors.dart';
import '../../../../shared/widgets/app_section_card.dart';
import '../../../../core/theme/app_space.dart';

abstract final class AdminPageLayout {
  static const maxWidth = AppLayout.list;
  static const padding = 24.0;
}

Widget adminPageWrapper({required Widget child}) {
  return ColoredBox(
    color: AppColors.background,
    child: Align(
      alignment: Alignment.topCenter,
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: AdminPageLayout.maxWidth),
        child: Padding(
          padding: const EdgeInsets.all(AdminPageLayout.padding),
          child: child,
        ),
      ),
    ),
  );
}

class AdminFormSection extends StatelessWidget {
  const AdminFormSection({
    super.key,
    required this.title,
    required this.children,
  });

  final String title;
  final List<Widget> children;

  @override
  Widget build(BuildContext context) {
    return AppSectionCard(
      margin: EdgeInsets.only(bottom: AppSpace.s(16)),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(
            title,
            style: TextStyle(
              fontSize: 15,
              fontWeight: FontWeight.w700,
              color: AppColors.textPrimary,
            ),
          ),
          SizedBox(height: AppSpace.s(12)),
          ...children,
        ],
      ),
    );
  }
}

class AdminDetailRow extends StatelessWidget {
  const AdminDetailRow({
    super.key,
    required this.label,
    required this.value,
  });

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    if (value.trim().isEmpty) return const SizedBox.shrink();
    return Padding(
      padding: EdgeInsets.only(bottom: AppSpace.s(12)),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            label,
            style: TextStyle(
              fontSize: 12,
              color: AppColors.textSecondary,
              fontWeight: FontWeight.w600,
            ),
          ),
          SizedBox(height: AppSpace.s(4)),
          Text(
            value,
            style: TextStyle(
              fontSize: 14,
              color: AppColors.textPrimary,
            ),
          ),
        ],
      ),
    );
  }
}
