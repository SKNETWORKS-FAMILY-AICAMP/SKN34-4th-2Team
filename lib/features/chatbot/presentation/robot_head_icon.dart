import 'dart:ui' show lerpDouble;

import 'package:flutter/material.dart';

/// The default robot head briefly stretches wide whenever [bounce] changes.
class RobotHeadIcon extends StatefulWidget {
  const RobotHeadIcon({
    super.key,
    this.size = 40,
    this.bounce = 0,
    this.inverted = false,
  });

  final double size;
  final int bounce;

  /// 몸과 얼굴 화면의 색을 맞바꾼 머리. 이력서 화면의 AI 코치가 쓴다.
  ///
  /// 학생 챗봇은 흰 몸에 남색 얼굴 화면이다. 같은 화면 오른쪽 아래에 학생
  /// 챗봇이 떠 있어서, 코치까지 같은 머리면 어느 쪽과 대화하는지 헷갈린다.
  /// 모양은 두고 색만 뒤집는다: 강조색 몸, 흰 얼굴 화면, 강조색 눈과 입.
  final bool inverted;

  @override
  State<RobotHeadIcon> createState() => _RobotHeadIconState();
}

class _RobotHeadIconState extends State<RobotHeadIcon>
    with SingleTickerProviderStateMixin {
  late final _controller = AnimationController(
    vsync: this,
    duration: const Duration(milliseconds: 700),
  );

  @override
  void didUpdateWidget(RobotHeadIcon oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.bounce != widget.bounce &&
        !MediaQuery.disableAnimationsOf(context)) {
      _controller.forward(from: 0);
    }
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (MediaQuery.disableAnimationsOf(context)) _controller.reset();
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return ExcludeSemantics(
      child: AnimatedBuilder(
        animation: _controller,
        builder: (context, child) => CustomPaint(
          size: Size.square(widget.size),
          painter: _RobotHeadPainter(
            progress: _controller.value,
            primary: scheme.primary,
            primaryLight: scheme.primaryContainer,
            inverted: widget.inverted,
          ),
        ),
      ),
    );
  }
}

class _RobotHeadPainter extends CustomPainter {
  const _RobotHeadPainter({
    required this.progress,
    required this.primary,
    required this.primaryLight,
    this.inverted = false,
  });

  final double progress;
  final Color primary;
  final Color primaryLight;
  final bool inverted;

  static const _navy = Color(0xFF0B2A6F);

  double get _stretch {
    const stops = [0.0, .28, .45, .70, .86, 1.0];
    const values = [0.0, 1.33, 1.0, -.33, .17, 0.0];
    for (var i = 1; i < stops.length; i++) {
      if (progress <= stops[i]) {
        final t = (progress - stops[i - 1]) / (stops[i] - stops[i - 1]);
        return lerpDouble(
          values[i - 1],
          values[i],
          Curves.easeInOut.transform(t),
        )!;
      }
    }
    return 0;
  }

  @override
  void paint(Canvas canvas, Size size) {
    final stretch = _stretch;
    double morph(double start, double end) => start + (end - start) * stretch;
    canvas.save();
    final scale = size.width / 104;
    canvas.translate(0, (size.height - 96 * scale) / 2);
    canvas.scale(scale);
    final head = Rect.fromLTWH(
      morph(14, 8),
      morph(28, 32),
      morph(76, 88),
      morph(55, 48),
    );
    final stroke = Paint()
      ..color = primary
      ..style = PaintingStyle.stroke
      ..strokeWidth = 2.2
      ..strokeCap = StrokeCap.round;
    void shape(Rect rect, double radius, Color color, {bool outline = true}) {
      final rounded = RRect.fromRectAndRadius(rect, Radius.circular(radius));
      canvas.drawRRect(rounded, Paint()..color = color);
      if (outline) canvas.drawRRect(rounded, stroke);
    }

    // The ears retract into the shell while it takes the wide form.
    final earVisibility = (1 - stretch).clamp(0.0, 1.0);
    if (earVisibility > 0) {
      for (final right in [false, true]) {
        final ear = Rect.fromLTWH(
          right ? head.right - 1 : head.left - 6 * earVisibility,
          head.top + 17,
          7 * earVisibility,
          18,
        );
        shape(ear, 4, primaryLight);
      }
    }
    final antennaTop = head.top - morph(14, 10);
    canvas.drawLine(Offset(52, head.top), Offset(52, antennaTop), stroke);
    canvas.drawCircle(
      Offset(52, antennaTop - 2),
      4,
      Paint()..color = primary,
    );
    final shell = inverted ? primary : Colors.white;
    final screen = inverted ? Colors.white : _navy;
    final face = inverted ? primary : Colors.white;
    shape(head, morph(20, 17), shell);
    final mask = Rect.fromLTRB(
      head.left + 9,
      head.top + morph(10, 9),
      head.right - 9,
      head.bottom - morph(10, 9),
    );
    shape(mask, morph(13, 11), screen, outline: false);
    for (final right in [false, true]) {
      final x = right
          ? mask.right - morph(12, 17) - 6
          : mask.left + morph(12, 17);
      shape(
        Rect.fromLTWH(x, mask.top + morph(10, 8), 6, morph(8, 7)),
        3,
        face,
        outline: false,
      );
    }
    final mouthWidth = morph(14, 10);
    canvas.drawArc(
      Rect.fromLTWH(
        52 - mouthWidth / 2,
        mask.top + morph(17, 14),
        mouthWidth,
        morph(12, 9),
      ),
      0,
      3.141592653589793,
      false,
      Paint()
        ..color = face
        ..style = PaintingStyle.stroke
        ..strokeWidth = inverted ? 2.2 : 2
        ..strokeCap = StrokeCap.round,
    );
    canvas.restore();
  }

  @override
  bool shouldRepaint(_RobotHeadPainter oldDelegate) =>
      progress != oldDelegate.progress ||
      primary != oldDelegate.primary ||
      primaryLight != oldDelegate.primaryLight ||
      inverted != oldDelegate.inverted;
}
