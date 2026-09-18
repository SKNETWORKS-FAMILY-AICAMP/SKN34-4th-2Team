import 'package:flutter/material.dart';

import '../theme/app_colors.dart';
import '../../core/theme/app_space.dart';

/// Shimmer 로딩 박스 — Firestore 데이터 로딩 중 표시
class ShimmerBox extends StatefulWidget {
  const ShimmerBox({
    super.key,
    this.width,
    this.height = 16,
    this.borderRadius = 8,
  });

  final double? width;
  final double height;
  final double borderRadius;

  @override
  State<ShimmerBox> createState() => _ShimmerBoxState();
}

class _ShimmerBoxState extends State<ShimmerBox>
    with SingleTickerProviderStateMixin {
  late AnimationController _controller;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1200),
    )..repeat();
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: _controller,
      builder: (context, child) {
        return Container(
          width: widget.width,
          height: widget.height,
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(widget.borderRadius),
            gradient: LinearGradient(
              begin: Alignment(-1 + 2 * _controller.value, 0),
              end: Alignment(1 + 2 * _controller.value, 0),
              colors: [
                AppColors.surfaceVariant,
                AppColors.border,
                AppColors.surfaceVariant,
              ],
            ),
          ),
        );
      },
    );
  }
}

/// 전체 화면 로딩 오버레이
class LoadingOverlay extends StatelessWidget {
  const LoadingOverlay({super.key, this.message});

  final String? message;

  @override
  Widget build(BuildContext context) {
    return Container(
      color: Colors.black26,
      child: Center(
        child: Card(
          child: Padding(
            padding: EdgeInsets.all(AppSpace.s(24)),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                CircularProgressIndicator(color: AppColors.primary),
                if (message != null) ...[
                  SizedBox(height: AppSpace.s(16)),
                  Text(message!, style: const TextStyle(fontSize: 14)),
                ],
              ],
            ),
          ),
        ),
      ),
    );
  }
}

/// 에러 상태 위젯 — 재시도 버튼 포함
class ErrorView extends StatelessWidget {
  const ErrorView({super.key, required this.message, this.onRetry});

  final String message;
  final VoidCallback? onRetry;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: EdgeInsets.all(AppSpace.s(24)),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.error_outline, size: 48, color: AppColors.error),
            SizedBox(height: AppSpace.s(12)),
            Text(
              message,
              textAlign: TextAlign.center,
              style: TextStyle(color: AppColors.textSecondary),
            ),
            if (onRetry != null) ...[
              SizedBox(height: AppSpace.s(16)),
              FilledButton(onPressed: onRetry, child: const Text('다시 시도')),
            ],
          ],
        ),
      ),
    );
  }
}

/// 빈 목록/미등록 상태 — ErrorView와 대칭
class EmptyView extends StatelessWidget {
  const EmptyView({
    super.key,
    required this.message,
    this.icon = Icons.inbox_outlined,
    this.actionLabel,
    this.onAction,
  });

  final String message;
  final IconData icon;
  final String? actionLabel;
  final VoidCallback? onAction;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: EdgeInsets.all(AppSpace.s(24)),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(
              icon,
              size: 48,
              color: AppColors.textHint.withValues(alpha: 0.7),
            ),
            SizedBox(height: AppSpace.s(12)),
            Text(
              message,
              textAlign: TextAlign.center,
              style: TextStyle(
                color: AppColors.textSecondary,
                height: 1.4,
              ),
            ),
            if (actionLabel != null && onAction != null) ...[
              SizedBox(height: AppSpace.s(16)),
              FilledButton(onPressed: onAction, child: Text(actionLabel!)),
            ],
          ],
        ),
      ),
    );
  }
}

/// 사이드바/섹션용 컴팩트 오류 카드
class InlineErrorCard extends StatelessWidget {
  const InlineErrorCard({super.key, required this.error, this.onRetry});

  final Object error;
  final VoidCallback? onRetry;

  @override
  Widget build(BuildContext context) {
    return Card(
      margin: EdgeInsets.zero,
      child: Padding(
        padding: EdgeInsets.symmetric(horizontal: AppSpace.s(16), vertical: AppSpace.s(18)),
        child: Column(
          children: [
            Icon(
              Icons.error_outline,
              size: 22,
              color: AppColors.error.withValues(alpha: 0.85),
            ),
            SizedBox(height: AppSpace.s(8)),
            Text(
              friendlyErrorMessage(error),
              textAlign: TextAlign.center,
              style: TextStyle(
                fontSize: 12,
                color: AppColors.textSecondary,
                height: 1.4,
              ),
            ),
            if (onRetry != null) ...[
              SizedBox(height: AppSpace.s(10)),
              TextButton(
                onPressed: onRetry,
                style: TextButton.styleFrom(
                  visualDensity: VisualDensity.compact,
                  foregroundColor: AppColors.primary,
                ),
                child: const Text('다시 시도', style: TextStyle(fontSize: 12)),
              ),
            ],
          ],
        ),
      ),
    );
  }
}

String friendlyErrorMessage(Object error) {
  final raw = error.toString();
  if (raw.contains('permission-denied')) {
    return '이 기수 데이터를 불러올 권한이 없습니다.';
  }
  if (raw.contains('unavailable') || raw.contains('network')) {
    return '네트워크 연결을 확인하고 다시 시도해 주세요.';
  }
  return '데이터를 불러오지 못했습니다.';
}

/// 기수 뱃지 칩
class CohortBadge extends StatelessWidget {
  const CohortBadge({super.key, required this.cohortName});

  final String cohortName;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: EdgeInsets.symmetric(horizontal: AppSpace.s(10), vertical: AppSpace.s(4)),
      decoration: BoxDecoration(
        color: AppColors.primaryLight,
        borderRadius: BorderRadius.circular(20),
      ),
      child: Text(
        cohortName,
        style: TextStyle(
          color: AppColors.primary,
          fontSize: 12,
          fontWeight: FontWeight.w600,
        ),
      ),
    );
  }
}
