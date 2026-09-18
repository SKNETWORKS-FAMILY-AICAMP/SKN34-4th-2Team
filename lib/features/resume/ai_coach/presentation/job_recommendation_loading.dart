import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../../../../core/theme/app_colors.dart';
import '../../../../core/theme/app_space.dart';

part 'job_recommendation_error.dart';

/// Server-driven progress; only a successful response releases the robot.
class JobRecommendationLoading extends StatefulWidget {
  const JobRecommendationLoading({
    super.key,
    required this.current,
    required this.results,
    this.completed = false,
    this.errorMessage,
    this.onRetry,
  });

  static const completionDuration = Duration(milliseconds: 1300);
  final String? current;
  final Map<String, String> results;
  final bool completed;
  final String? errorMessage;
  final VoidCallback? onRetry;

  @override
  State<JobRecommendationLoading> createState() =>
      _JobRecommendationLoadingState();
}

class _JobRecommendationLoadingState extends State<JobRecommendationLoading>
    with TickerProviderStateMixin {
  static const _steps = [
    ('resume', '이력서 읽기', '기술과 프로젝트 경험을 살펴봐요'),
    ('search', '공고 찾기', '내 경험과 맞는 공고를 찾아요'),
    ('filter', '지원 조건 비교', '희망 조건과 지원 자격을 비교해요'),
    ('judge', '직무 근거 비교', '이력서와 공고의 연결점을 확인해요'),
  ];

  late final _sway = AnimationController(
    vsync: this,
    duration: const Duration(milliseconds: 3100),
  );
  late final _fall = AnimationController(
    vsync: this,
    duration: JobRecommendationLoading.completionDuration,
  );
  late final _burst = AnimationController(
    vsync: this,
    duration: const Duration(milliseconds: 1300),
  );
  bool _reduceMotion = false;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _reduceMotion = MediaQuery.disableAnimationsOf(context);
    _syncMotion();
  }

  @override
  void didUpdateWidget(JobRecommendationLoading oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.completed != widget.completed ||
        oldWidget.errorMessage != widget.errorMessage) {
      _syncMotion();
    }
  }

  void _syncMotion() {
    if (widget.errorMessage != null) {
      _sway.stop();
      _fall.reset();
      if (_reduceMotion) {
        _burst.value = 1;
      } else if (!_burst.isAnimating && !_burst.isCompleted) {
        _burst.forward();
      }
      return;
    }
    _burst.reset();
    if (widget.completed) {
      _sway.stop();
      if (_reduceMotion) {
        _fall.value = 1;
      } else if (!_fall.isAnimating && !_fall.isCompleted) {
        _fall.forward();
      }
    } else {
      _fall.reset();
      if (_reduceMotion) {
        _sway.stop();
        _sway.value = 0;
      } else if (!_sway.isAnimating) {
        _sway.repeat();
      }
    }
  }

  @override
  void dispose() {
    _sway.dispose();
    _fall.dispose();
    _burst.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final index = _steps.indexWhere((step) => step.$1 == widget.current);
    final status = widget.errorMessage != null
        ? '다시 시도할 수 있어요'
        : widget.completed
        ? '추천 준비 완료'
        : index < 0
        ? '추천을 준비하고 있어요'
        : widget.results.containsKey(_steps[index].$1)
        ? '${_steps[index].$2} 완료'
        : '${_steps[index].$2} 진행 중';

    return Align(
      alignment: Alignment.center,
      heightFactor: 1,
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 385),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            ClipRect(
              clipper: const _RobotMotionClipper(),
              child: Stack(
                children: [
                  Padding(
                    padding: EdgeInsets.fromLTRB(
                      AppSpace.s(48),
                      AppSpace.s(22),
                      AppSpace.s(48),
                      AppSpace.s(16),
                    ),
                    child: Stack(
                      clipBehavior: Clip.none,
                      children: [
                        Container(
                          // 글에 맞춰 줄어든다. 가장 긴 줄이 카드 너비를 정한다.
                          constraints: const BoxConstraints(minHeight: 244),
                          padding: EdgeInsets.fromLTRB(AppSpace.s(15), AppSpace.s(25), AppSpace.s(15), AppSpace.s(17)),
                          decoration: BoxDecoration(
                            color: AppColors.surface,
                            border: Border.all(
                              color: AppColors.primary,
                              width: 1.5,
                            ),
                            borderRadius: BorderRadius.circular(12),
                            boxShadow: [
                              BoxShadow(
                                color: AppColors.primaryLight,
                                offset: Offset(4, 5),
                              ),
                            ],
                          ),
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(
                                widget.errorMessage != null
                                    ? '공고를 불러오지 못했어요'
                                    : widget.completed
                                    ? '추천 준비 완료!'
                                    : '공고를 고르고 있어요',
                                style: TextStyle(
                                  fontSize: 13,
                                  fontWeight: FontWeight.w600,
                                  // 사이드바 색은 어두워서 전체 다크의 카드 위에서는 묻힌다.
                                  color: AppColors.isDark
                                      ? AppColors.textPrimary
                                      : AppColors.sidebar,
                                ),
                              ),
                              SizedBox(height: AppSpace.s(15)),
                              if (widget.errorMessage != null)
                                _RecommendationError(
                                  message: widget.errorMessage!,
                                  onRetry: widget.onRetry,
                                )
                              else ...[
                                if (index < 0 && !widget.completed) ...[
                                  SizedBox(
                                    width: 196,
                                    child: LinearProgressIndicator(
                                      minHeight: 2,
                                      color: AppColors.primary,
                                    ),
                                  ),
                                  SizedBox(height: AppSpace.s(12)),
                                ],
                                for (var i = 0; i < _steps.length; i++)
                                  _ChecklistStep(
                                    label: _steps[i].$2,
                                    done:
                                        widget.completed ||
                                        widget.results.containsKey(
                                          _steps[i].$1,
                                        ) ||
                                        (index >= 0 && i < index),
                                    running:
                                        !widget.completed &&
                                        i == index &&
                                        !widget.results.containsKey(
                                          _steps[i].$1,
                                        ),
                                    detail:
                                        widget.results[_steps[i].$1] ??
                                        (!widget.completed && i == index
                                            ? _steps[i].$3
                                            : null),
                                    last: i == _steps.length - 1,
                                  ),
                              ],
                            ],
                          ),
                        ),
                        const Positioned(
                          top: -15,
                          left: 0,
                          right: 0,
                          child: Center(child: _ClipboardClip()),
                        ),
                      ],
                    ),
                  ),
                  Positioned(
                    left: 0,
                    top: 72,
                    child: ExcludeSemantics(
                      child: AnimatedBuilder(
                        animation: Listenable.merge([_sway, _fall, _burst]),
                        builder: (context, child) {
                          if (widget.errorMessage != null) {
                            if (_burst.isCompleted) {
                              return const SizedBox.shrink();
                            }
                            return CustomPaint(
                              key: const ValueKey('recommendation-error-burst'),
                              size: const Size(58, 92),
                              painter: _RobotBurstPainter(
                                progress: _burst.value,
                              ),
                            );
                          }
                          if (_fall.isCompleted) return const SizedBox.shrink();
                          final release = ((_fall.value - .19) / .81).clamp(
                            0.0,
                            1.0,
                          );
                          final descent = ((release - .15) / .85).clamp(
                            0.0,
                            1.0,
                          );
                          final dy = release < .15
                              ? -7 * math.sin(release / .15 * math.pi / 2)
                              : -7 + 480 * descent * descent;
                          return Transform.translate(
                            offset: Offset(-14 * release, dy),
                            child: CustomPaint(
                              key: const ValueKey(
                                'recommendation-loading-robot',
                              ),
                              size: const Size(58, 92),
                              painter: _HangingRobotPainter(
                                phase: _sway.value,
                                release: release,
                                completed: widget.completed,
                              ),
                            ),
                          );
                        },
                      ),
                    ),
                  ),
                ],
              ),
            ),
            Padding(
              padding: EdgeInsets.zero,
              child: Semantics(
                liveRegion: true,
                child: Text(
                  status,
                  textAlign: TextAlign.center,
                  style: TextStyle(
                    fontSize: 12,
                    color: widget.completed
                        ? AppColors.primary
                        : AppColors.textSecondary,
                  ),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

// Allow horizontal motion without adding layout space that shifts the group.
// Keep the lower edge clipped so the completed robot falls out of view.
class _RobotMotionClipper extends CustomClipper<Rect> {
  const _RobotMotionClipper();

  @override
  Rect getClip(Size size) =>
      Rect.fromLTRB(-48, 0, size.width + 48, size.height);

  @override
  bool shouldReclip(_RobotMotionClipper oldClipper) => false;
}

class _ClipboardClip extends StatelessWidget {
  const _ClipboardClip();

  @override
  Widget build(BuildContext context) => SizedBox(
    width: 49,
    height: 23,
    child: Stack(
      alignment: Alignment.topCenter,
      children: [
        Positioned(
          top: 8,
          left: 0,
          right: 0,
          bottom: 0,
          child: DecoratedBox(
            decoration: BoxDecoration(
              color: AppColors.primary,
              borderRadius: BorderRadius.circular(5),
            ),
          ),
        ),
        Container(
          width: 16,
          height: 16,
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            color: AppColors.surface,
            border: Border.all(color: AppColors.primary, width: 4),
          ),
        ),
      ],
    ),
  );
}

class _ChecklistStep extends StatelessWidget {
  const _ChecklistStep({
    required this.label,
    required this.done,
    required this.running,
    required this.detail,
    required this.last,
  });

  final String label;
  final bool done;
  final bool running;
  final String? detail;
  final bool last;

  @override
  Widget build(BuildContext context) => Padding(
    padding: EdgeInsets.only(bottom: last ? AppSpace.s(0) : AppSpace.s(13)),
    child: Row(
      // 카드가 글에 맞춰 줄어들어야 하므로 줄도 제 너비만 차지한다.
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Padding(
          padding: EdgeInsets.only(top: AppSpace.s(1)),
          child: SizedBox(
            width: 16,
            height: 16,
            child: done
                ? Icon(
                    Icons.check_circle,
                    size: 16,
                    color: AppColors.primary,
                  )
                : running
                ? Padding(
                    padding: EdgeInsets.all(AppSpace.s(1)),
                    child: CircularProgressIndicator(
                      strokeWidth: 1.7,
                      color: AppColors.primary,
                    ),
                  )
                : Icon(
                    Icons.circle_outlined,
                    size: 9,
                    color: AppColors.textHint,
                  ),
          ),
        ),
        SizedBox(width: AppSpace.s(9)),
        Flexible(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Wrap(
                spacing: 8,
                crossAxisAlignment: WrapCrossAlignment.center,
                children: [
                  Text(
                    label,
                    style: TextStyle(
                      fontSize: 12,
                      color: running
                          ? AppColors.primary
                          : AppColors.textSecondary,
                    ),
                  ),
                  Text(
                    done
                        ? '완료'
                        : running
                        ? '진행 중'
                        : '대기',
                    style: TextStyle(
                      fontSize: 11,
                      color: running
                          ? AppColors.primary
                          : AppColors.textSecondary,
                    ),
                  ),
                ],
              ),
              if (detail != null) ...[
                SizedBox(height: AppSpace.s(4)),
                Text(
                  detail!,
                  style: TextStyle(
                    fontSize: 11,
                    color: AppColors.textSecondary,
                  ),
                ),
              ],
            ],
          ),
        ),
      ],
    ),
  );
}

/// Small outlined robot, pivoting at the hand gripping the clipboard edge.
class _HangingRobotPainter extends CustomPainter {
  const _HangingRobotPainter({
    required this.phase,
    required this.release,
    required this.completed,
  });

  final double phase;
  final double release;
  final bool completed;

  @override
  void paint(Canvas canvas, Size size) {
    canvas.save();
    canvas.translate(8, 4);
    canvas.scale(.68);
    final swing = math.sin(phase * 2 * math.pi);
    canvas.translate(57, 0);
    canvas.rotate(completed ? release * .3 : swing * .095);
    canvas.translate(-57, 0);
    final outline = Paint()
      ..color = AppColors.primary
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1.7
      ..strokeCap = StrokeCap.round;
    // 로봇은 어느 테마에서나 하얀 몸이다. 카드 바탕색·옅은 강조색을 따르면 전체
    // 다크에서 몸이 카드에 묻히고, 어두운 얼굴 화면 위의 눈·입까지 어두워져
    // 얼굴이 보이지 않았다.
    const body = Colors.white;
    final tint = AppColors.isDark
        ? Color.alphaBlend(AppColors.primary.withValues(alpha: .22), body)
        : AppColors.primaryLight;
    void shape(Rect rect, double radius, [Color? color]) {
      color ??= body;
      final rrect = RRect.fromRectAndRadius(rect, Radius.circular(radius));
      canvas.drawRRect(rrect, Paint()..color = color);
      canvas.drawRRect(rrect, outline);
    }

    // Raised arm and fingers stay on the grip point while the body sways.
    canvas.save();
    canvas.translate(57, 0);
    canvas.rotate(.3 - release * .5);
    shape(const Rect.fromLTWH(-5, 0, 10, 63), 5);
    shape(const Rect.fromLTWH(-6, -4, 13, 12), 5, tint);
    canvas.drawLine(const Offset(0, 1), const Offset(5, 1), outline);
    canvas.restore();

    for (var i = 0; i < 2; i++) {
      canvas.save();
      canvas.translate(i == 0 ? 18 : 35, 88);
      canvas.rotate(
        completed ? (i == 0 ? -.25 : .33) : swing * (i == 0 ? .2 : -.2),
      );
      shape(const Rect.fromLTWH(-5, 0, 10, 27), 5, tint);
      shape(const Rect.fromLTWH(-9, 23, 17, 8), 4);
      canvas.restore();
    }
    canvas.save();
    canvas.translate(9, 64);
    canvas.rotate(completed ? release * 2.1 : .4 + swing * .12);
    shape(const Rect.fromLTWH(-5, 0, 10, 28), 5);
    shape(const Rect.fromLTWH(-5, 24, 10, 10), 5, tint);
    canvas.restore();
    shape(const Rect.fromLTWH(19, 49, 13, 9), 3, tint);
    shape(const Rect.fromLTWH(10, 56, 33, 35), 10);
    canvas.drawCircle(
      const Offset(26, 71),
      7,
      Paint()..color = tint,
    );
    canvas.drawLine(const Offset(26, 67), const Offset(26, 75), outline);
    canvas.drawLine(const Offset(22, 71), const Offset(30, 71), outline);
    canvas.save();
    canvas.translate(25, 36);
    canvas.rotate(.13);
    canvas.translate(-25, -36);
    canvas.drawLine(const Offset(24, 18), const Offset(24, 9), outline);
    canvas.drawCircle(
      const Offset(24, 7),
      3,
      Paint()..color = AppColors.primary,
    );
    shape(const Rect.fromLTWH(-2, 28, 6, 12), 3, tint);
    shape(const Rect.fromLTWH(46, 28, 6, 12), 3, tint);
    shape(const Rect.fromLTWH(3, 18, 44, 34), 14);
    canvas.drawRRect(
      RRect.fromRectAndRadius(
        const Rect.fromLTWH(8, 23, 34, 24),
        const Radius.circular(9),
      ),
      Paint()..color = AppColors.sidebar,
    );
    final blink = !completed && phase > .74 && phase < .79;
    for (final x in [16.0, 30.0]) {
      canvas.drawRRect(
        RRect.fromRectAndRadius(
          Rect.fromLTWH(x, 30, 4, blink ? 1 : 5),
          const Radius.circular(2),
        ),
        Paint()..color = body,
      );
    }
    final mouth = Paint()
      ..color = body
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1.3;
    if (completed) {
      canvas.drawOval(const Rect.fromLTWH(23, 37, 5, 6), mouth);
    } else {
      canvas.drawArc(
        const Rect.fromLTWH(21, 35, 9, 6),
        0,
        math.pi,
        false,
        mouth,
      );
    }
    canvas.restore();
    canvas.restore();
  }

  @override
  bool shouldRepaint(_HangingRobotPainter oldDelegate) =>
      phase != oldDelegate.phase ||
      release != oldDelegate.release ||
      completed != oldDelegate.completed;
}
