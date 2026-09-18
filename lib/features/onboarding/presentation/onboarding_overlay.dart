import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../../../core/theme/app_colors.dart';
import '../domain/onboarding_step.dart';
import '../domain/onboarding_target_registry.dart';
import '../../../core/theme/app_space.dart';

/// 딤 + 하이라이트 구멍 + 설명 카드
class OnboardingOverlay extends StatefulWidget {
  const OnboardingOverlay({
    super.key,
    required this.step,
    required this.stepIndex,
    required this.totalSteps,
    required this.onNext,
    required this.onPrevious,
    required this.onDismissForever,
    required this.onSkipMissing,
  });

  final OnboardingStep step;
  final int stepIndex;
  final int totalSteps;
  final VoidCallback onNext;

  /// 첫 단계에서는 null. 그때는 되돌아갈 곳이 없다.
  final VoidCallback? onPrevious;
  final VoidCallback onDismissForever;
  final VoidCallback onSkipMissing;

  @override
  State<OnboardingOverlay> createState() => _OnboardingOverlayState();
}

class _OnboardingOverlayState extends State<OnboardingOverlay> {
  static const _holePadding = 10.0;
  static const _holeRadius = 12.0;
  static const _maxRetries = 12;

  Rect? _targetRect;
  String? _resolvedStepId;
  var _retries = 0;
  var _resolving = false;
  var _ensuredVisible = false;
  // 첫 자리를 잡기 전에는 카드를 내보내지 않는다. 자리를 모르는 채로 그리면
  // 화면 한가운데에 떴다가 제자리로 튄다.
  var _settled = false;

  /// 방금 잰 자리. 한 번 더 재서 같을 때만 옮긴다.
  Rect? _measuring;

  @override
  void initState() {
    super.initState();
    _scheduleResolve();
  }

  @override
  void didUpdateWidget(covariant OnboardingOverlay oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.step.id != widget.step.id) {
      // 카드 위치는 유지하되 이전 단계의 강조는 새 위치가 확정될 때까지
      // 숨긴다. 스크롤된 목록 위에 이전 좌표의 구멍을 남기면 다른 메뉴를 비춘다.
      _retries = 0;
      _measuring = null;
      _ensuredVisible = false;
      _scheduleResolve();
    }
  }

  void _scheduleResolve() {
    if (_resolving) return;
    _resolving = true;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _resolving = false;
      if (!mounted) return;
      _resolveTarget();
    });
    // 프레임이 끝난 뒤 부르는 약속이라, 다음 프레임이 예약돼 있지 않으면 영영
    // 불리지 않는다. 화면이 멈춰 있으면 아무도 예약하지 않는다. 직접 예약해야
    // 자리를 다시 재러 돌아온다.
    WidgetsBinding.instance.scheduleFrame();
  }

  /// 스크롤 영역 밖으로 가려진 만큼만 이동한다. 이미 보이면 그대로 둔다.
  Future<void> _scrollIntoView(String targetId) async {
    final ctx = OnboardingTargetRegistry.keyOf(targetId).currentContext;
    if (ctx == null) return;
    try {
      await Scrollable.ensureVisible(
        ctx,
        duration: Duration.zero,
        alignmentPolicy: ScrollPositionAlignmentPolicy.keepVisibleAtEnd,
      );
      if (!mounted || widget.step.targetId != targetId || !ctx.mounted) return;
      await Scrollable.ensureVisible(
        ctx,
        duration: Duration.zero,
        alignmentPolicy: ScrollPositionAlignmentPolicy.keepVisibleAtStart,
      );
    } catch (_) {}
  }

  /// 한 프레임 뒤에 다시 잰다.
  void _remeasureNextFrame() {
    _measuring = null;
    _retries++;
    _scheduleResolve();
  }

  Future<void> _resolveTarget() async {
    if (!mounted) return;
    final step = widget.step;
    final size = MediaQuery.sizeOf(context);
    final padding = MediaQuery.paddingOf(context);
    final visible = Rect.fromLTRB(
      0,
      padding.top,
      size.width,
      size.height - padding.bottom,
    );

    final rect = OnboardingTargetRegistry.rectOf(step.targetId);
    final found = rect != null && rect.width > 0 && rect.height > 0;

    if (found) {
      // 자리가 멎을 때까지 기다린다. 단계가 바뀌면 화면이 함께 바뀌고
      // 사이드바가 펼쳐지며 메뉴가 밀린다. 멎기 전에 손대면 그때마다 따라간다.
      if (_measuring != rect && _retries < _maxRetries - 1) {
        _measuring = rect;
        _retries++;
        _scheduleResolve();
        return;
      }

      // 프로필 위의 실제 스크롤 영역을 기준으로 가려진 항목만 드러낸다.
      if (!_ensuredVisible && _retries < _maxRetries - 1) {
        _ensuredVisible = true;
        await _scrollIntoView(step.targetId);
        if (!mounted || widget.step != step) return;
        _remeasureNextFrame();
        return;
      }

      if (rect.overlaps(visible)) {
        setState(() {
          _resolvedStepId = step.id;
          _targetRect = rect;
          _settled = true;
        });
        return;
      }
    }

    _retries++;
    if (_retries >= _maxRetries) {
      if (widget.step.skippableIfMissing) {
        widget.onSkipMissing();
        return;
      }
      setState(() {
        _resolvedStepId = step.id;
        _targetRect = null;
        _settled = true;
      });
      return;
    }
    _scheduleResolve();
  }

  @override
  Widget build(BuildContext context) {
    final size = MediaQuery.sizeOf(context);
    final padding = MediaQuery.paddingOf(context);
    final isLast = widget.stepIndex >= widget.totalSteps - 1;
    // 첫 자리를 잡기 전에만 감춘다. 그 뒤로는 앞 단계의 자리에 그대로 머물다
    // 새 자리가 정해지는 순간 한 번에 옮겨 간다.
    //
    // 미끄러뜨려도 보고 감췄다가 내보내도 봤는데 둘 다 나빴다. 미끄러지는
    // 동안에는 카드를 매 프레임 통째로 다시 만들어(그림자까지) 화면이 끊겼고,
    // 감추면 감춰지는 동안 카드가 화면 한가운데로 흘러가 깜빡였다. 제자리에
    // 머물다 한 번 바뀌는 것이 가장 조용하다.
    final hole = _settled ? _targetRect?.inflate(_holePadding) : null;

    return Material(
      type: MaterialType.transparency,
      child: _stack(hole, size, padding, isLast),
    );
  }

  Widget _stack(Rect? spot, Size size, EdgeInsets padding, bool isLast) =>
      Stack(
        children: [
          Positioned.fill(
            child: CustomPaint(
              painter: _SpotlightPainter(
                hole: _resolvedStepId == widget.step.id ? spot : null,
                radius: _holeRadius,
              ),
            ),
          ),
          const Positioned.fill(
            child: AbsorbPointer(absorbing: true, child: SizedBox.expand()),
          ),
          if (spot != null && _resolvedStepId == widget.step.id)
            Positioned(
              key: const ValueKey('onboarding-highlight'),
              left: spot.left,
              top: spot.top,
              width: spot.width,
              height: spot.height,
              child: IgnorePointer(
                child: DecoratedBox(
                  decoration: BoxDecoration(
                    borderRadius: BorderRadius.circular(_holeRadius),
                    border: Border.all(color: AppColors.primary, width: 2),
                  ),
                ),
              ),
            ),
          _TooltipCard(
            step: widget.step,
            stepIndex: widget.stepIndex,
            totalSteps: widget.totalSteps,
            safePadding: padding,
            targetRect: spot,
            visible: _settled,
            isLast: isLast,
            onNext: widget.onNext,
            onPrevious: widget.onPrevious,
            onDismissForever: widget.onDismissForever,
          ),
        ],
      );
}

class _SpotlightPainter extends CustomPainter {
  _SpotlightPainter({required this.hole, required this.radius});

  final Rect? hole;
  final double radius;

  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()..color = Colors.black.withValues(alpha: 0.55);
    if (hole == null) {
      canvas.drawRect(Offset.zero & size, paint);
      return;
    }
    final path = Path()
      ..fillType = PathFillType.evenOdd
      ..addRect(Offset.zero & size)
      ..addRRect(
        RRect.fromRectAndRadius(hole!, Radius.circular(radius)),
      );
    canvas.drawPath(path, paint);
  }

  @override
  bool shouldRepaint(covariant _SpotlightPainter oldDelegate) =>
      oldDelegate.hole != hole || oldDelegate.radius != radius;
}

class _TooltipCard extends StatelessWidget {
  const _TooltipCard({
    required this.step,
    required this.stepIndex,
    required this.totalSteps,
    required this.safePadding,
    required this.targetRect,
    required this.visible,
    required this.isLast,
    required this.onNext,
    required this.onPrevious,
    required this.onDismissForever,
  });

  final OnboardingStep step;
  final int stepIndex;
  final int totalSteps;
  final EdgeInsets safePadding;
  final Rect? targetRect;
  final bool visible;
  final bool isLast;
  final VoidCallback onNext;
  final VoidCallback? onPrevious;
  final VoidCallback onDismissForever;

  @override
  Widget build(BuildContext context) {
    return Positioned.fill(
      child: CustomSingleChildLayout(
        delegate: _TooltipPositionDelegate(
          targetRect: targetRect,
          safePadding: safePadding,
        ),
        child: AnimatedOpacity(
          opacity: visible ? 1 : 0,
          duration: const Duration(milliseconds: 120),
          child: Material(
            color: AppColors.surface,
            elevation: 8,
            shadowColor: AppColors.shadow,
            borderRadius: BorderRadius.circular(14),
            child: SingleChildScrollView(
              child: Padding(
                padding: EdgeInsets.fromLTRB(AppSpace.s(16), AppSpace.s(14), AppSpace.s(16), AppSpace.s(12)),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Row(
                      children: [
                        Expanded(
                          child: Text(
                            step.title,
                            style: TextStyle(
                              fontSize: 16,
                              fontWeight: FontWeight.w700,
                              color: AppColors.textPrimary,
                            ),
                          ),
                        ),
                        Text(
                          '${stepIndex + 1} / $totalSteps',
                          style: TextStyle(
                            fontSize: 12,
                            fontWeight: FontWeight.w600,
                            color: AppColors.textHint,
                          ),
                        ),
                      ],
                    ),
                    SizedBox(height: AppSpace.s(8)),
                    Text(
                      step.body,
                      style: TextStyle(
                        fontSize: 13,
                        height: 1.4,
                        color: AppColors.textSecondary,
                      ),
                    ),
                    SizedBox(height: AppSpace.s(14)),
                    Row(
                      children: [
                        TextButton(
                          onPressed: onDismissForever,
                          child: const Text('다시 보지 않기'),
                        ),
                        const Spacer(),
                        if (onPrevious != null) ...[
                          TextButton(
                            onPressed: onPrevious,
                            child: const Text('이전'),
                          ),
                          SizedBox(width: AppSpace.s(4)),
                        ],
                        FilledButton(
                          onPressed: onNext,
                          style: FilledButton.styleFrom(
                            backgroundColor: AppColors.primary,
                            padding: EdgeInsets.symmetric(
                              horizontal: AppSpace.s(18),
                              vertical: AppSpace.s(10),
                            ),
                          ),
                          child: Text(isLast ? '완료' : '다음'),
                        ),
                      ],
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

/// 레이아웃 중에 실제 카드 크기를 받아 한 번에 배치한다.
class _TooltipPositionDelegate extends SingleChildLayoutDelegate {
  const _TooltipPositionDelegate({
    required this.targetRect,
    required this.safePadding,
  });

  final Rect? targetRect;
  final EdgeInsets safePadding;
  static const _cardWidth = 320.0;
  static const _gap = 12.0;
  static const _margin = 16.0;

  @override
  BoxConstraints getConstraintsForChild(BoxConstraints constraints) {
    final width = math.min(
      _cardWidth,
      math.max(
        0.0,
        constraints.maxWidth - safePadding.horizontal - 2 * _margin,
      ),
    );
    return BoxConstraints(
      minWidth: width,
      maxWidth: width,
      maxHeight: math.max(
        0.0,
        constraints.maxHeight - safePadding.vertical - 2 * _margin,
      ),
    );
  }

  @override
  Offset getPositionForChild(Size size, Size childSize) {
    final minLeft = safePadding.left + _margin;
    final minTop = safePadding.top + _margin;
    final right = size.width - safePadding.right - _margin;
    final bottom = size.height - safePadding.bottom - _margin;
    final maxLeft = math.max(minLeft, right - childSize.width);
    final maxTop = math.max(minTop, bottom - childSize.height);
    final target = targetRect;
    double left;
    double top;

    if (target == null) {
      left = (size.width - childSize.width) / 2;
      top = (size.height - childSize.height) / 2;
    } else if (target.center.dx < size.width * 0.38 &&
        target.right + _gap + childSize.width <= right) {
      // 하단 메뉴도 옆에 둔다. 화면 밖으로 나가는 만큼만 위로 조정한다.
      left = target.right + _gap;
      top = target.center.dy - childSize.height / 2;
    } else {
      left = target.center.dx - childSize.width / 2;
      final below = target.bottom + _gap;
      final above = target.top - childSize.height - _gap;
      top = below + childSize.height <= bottom ? below : above;
    }
    return Offset(left.clamp(minLeft, maxLeft), top.clamp(minTop, maxTop));
  }

  @override
  bool shouldRelayout(covariant _TooltipPositionDelegate oldDelegate) =>
      oldDelegate.targetRect != targetRect ||
      oldDelegate.safePadding != safePadding;
}
