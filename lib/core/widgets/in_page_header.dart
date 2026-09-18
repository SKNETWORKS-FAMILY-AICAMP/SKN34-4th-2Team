import 'package:flutter/material.dart';

import '../theme/app_colors.dart';
import '../../core/theme/app_space.dart';

/// Shell이 이미 AppBar를 가진 페이지용 — 중첩 AppBar 대신 쓰는 툴바/탭 헤더.
class InPageHeader extends StatelessWidget {
  const InPageHeader({
    super.key,
    this.title,
    this.actions = const [],
    this.bottom,
  });

  final String? title;
  final List<Widget> actions;
  final Widget? bottom;

  @override
  Widget build(BuildContext context) {
    final hasTitle = title != null && title!.trim().isNotEmpty;
    final hasActions = actions.isNotEmpty;

    return Material(
      color: AppColors.surface,
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (hasTitle || hasActions)
            SizedBox(
              height: kToolbarHeight,
              child: Padding(
                padding: EdgeInsets.symmetric(horizontal: AppSpace.s(8)),
                child: Row(
                  children: [
                    if (hasTitle) ...[
                      SizedBox(width: AppSpace.s(8)),
                      Expanded(
                        child: Text(
                          title!,
                          style: Theme.of(context).textTheme.titleLarge?.copyWith(
                                fontWeight: FontWeight.w700,
                                color: AppColors.textPrimary,
                              ),
                          overflow: TextOverflow.ellipsis,
                        ),
                      ),
                    ] else
                      const Spacer(),
                    ...actions,
                  ],
                ),
              ),
            ),
          ?bottom,
          Divider(height: 1, color: AppColors.border),
        ],
      ),
    );
  }
}
