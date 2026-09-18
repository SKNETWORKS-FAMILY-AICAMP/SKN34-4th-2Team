import 'package:flutter/material.dart';

import '../../core/theme/app_layout.dart';
import '../../core/theme/app_space.dart';

/// 페이지 콘텐츠 래퍼 — 중앙 정렬 + 패딩 + 선택적 maxWidth
class AppPageScaffold extends StatelessWidget {
  const AppPageScaffold({
    super.key,
    required this.child,
    this.maxWidth = AppLayout.page,
    this.padding,
    this.scrollable = true,
    this.physics,
  });

  final Widget child;
  final double? maxWidth;
  final EdgeInsetsGeometry? padding;
  final bool scrollable;
  final ScrollPhysics? physics;

  @override
  Widget build(BuildContext context) {
    final width = MediaQuery.sizeOf(context).width;
    final edge = padding ??
        EdgeInsets.symmetric(
          horizontal: width >= AppSpace.s(900) ? AppSpace.s(24) : AppSpace.s(16),
          vertical: AppSpace.s(20),
        );

    final body = Align(
      alignment: Alignment.topCenter,
      child: ConstrainedBox(
        constraints: BoxConstraints(
          maxWidth: maxWidth ?? double.infinity,
        ),
        child: Padding(padding: edge, child: child),
      ),
    );

    if (!scrollable) return body;

    return SingleChildScrollView(
      physics: physics ?? const AlwaysScrollableScrollPhysics(),
      child: body,
    );
  }
}
