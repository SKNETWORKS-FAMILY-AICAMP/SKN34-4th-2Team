import 'dart:math' as math;
import 'dart:ui' show lerpDouble;

import 'package:flutter/material.dart';

/// 로그인 시네마틱 브랜드 스테이지 (다크 궤도)
class LoginBrandStage extends StatefulWidget {
  const LoginBrandStage({
    super.key,
    this.exiting = false,
    this.exitProgress,
    this.canvasSize,
  });

  /// 로그인 성공 퇴장 중
  final bool exiting;

  /// 0→1: PLAYDATA 패널 확대(속으로 진입) 진행도
  final Animation<double>? exitProgress;

  /// 궤도·로고 배치 기준. 생략하면 [LoginFixedFrame]이 넣어 준 캔버스 크기.
  final Size? canvasSize;

  @override
  State<LoginBrandStage> createState() => _LoginBrandStageState();
}

class _LoginBrandStageState extends State<LoginBrandStage>
    with TickerProviderStateMixin {
  late final AnimationController _pulse;
  late final AnimationController _orbit;
  Offset _pointer = Offset.zero;

  @override
  void initState() {
    super.initState();
    _pulse = AnimationController(
      vsync: this,
      duration: const Duration(seconds: 8),
    )..repeat(reverse: true);
    _orbit = AnimationController(
      vsync: this,
      duration: const Duration(seconds: 28),
    )..repeat();
  }

  @override
  void didUpdateWidget(covariant LoginBrandStage oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.exiting && !oldWidget.exiting) {
      _pulse.stop();
      _orbit.stop();
    }
  }

  @override
  void dispose() {
    _pulse.dispose();
    _orbit.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return MouseRegion(
      onHover: widget.exiting
          ? null
          : (e) {
              final size = widget.canvasSize ?? MediaQuery.sizeOf(context);
              setState(() {
                _pointer = Offset(
                  (e.localPosition.dx / size.width - 0.5).clamp(-0.5, 0.5),
                  (e.localPosition.dy / size.height - 0.5).clamp(-0.5, 0.5),
                );
              });
            },
      onExit: widget.exiting
          ? null
          : (_) => setState(() => _pointer = Offset.zero),
      child: AnimatedBuilder(
        animation: Listenable.merge([
          _pulse,
          _orbit,
          if (widget.exitProgress != null) widget.exitProgress!,
        ]),
        builder: (context, _) {
          return _DarkOrbitStage(
            canvasSize: widget.canvasSize ?? MediaQuery.sizeOf(context),
            pulse: Curves.easeInOut.transform(_pulse.value),
            orbit: _orbit.value,
            pointer: widget.exiting ? Offset.zero : _pointer,
            exiting: widget.exiting,
            exitT: widget.exitProgress?.value ?? 0,
          );
        },
      ),
    );
  }
}

class _DarkOrbitStage extends StatelessWidget {
  const _DarkOrbitStage({
    required this.canvasSize,
    required this.pulse,
    required this.orbit,
    required this.pointer,
    required this.exiting,
    required this.exitT,
  });

  final Size canvasSize;
  final double pulse;
  final double orbit;
  final Offset pointer;
  final bool exiting;
  final double exitT;

  @override
  Widget build(BuildContext context) {
    final size = canvasSize;
    final parallax = Offset(pointer.dx * 22, pointer.dy * 14);

    final cx = size.width * 0.72 + parallax.dx;
    final cy = size.height * 0.48 + parallax.dy;
    final rx = size.width * 0.16;
    final ry = size.height * 0.22;

    Offset onOrbit(double turn, {double radiusScale = 1}) {
      final a = orbit * math.pi * 2 + turn;
      return Offset(
        cx + math.cos(a) * rx * radiusScale,
        cy + math.sin(a) * ry * radiusScale + pulse * 4,
      );
    }

    final skPos = onOrbit(0.15, radiusScale: 1.05);
    final encorePos = onOrbit(math.pi * 0.95, radiusScale: 0.92);
    const hubW = 260.0;
    const hubH = 150.0;

    // 패널 중심 → 화면 중심으로 이동하며 확대
    final zoomT = Curves.easeInCubic.transform(exitT.clamp(0.0, 1.0));
    final hubLeft0 = cx - hubW / 2;
    final hubTop0 = cy - hubH / 2 + (exiting ? 0 : pulse * 6);
    final hubLeft1 = (size.width - hubW) / 2;
    final hubTop1 = (size.height - hubH) / 2;
    final hubLeft = lerpDouble(hubLeft0, hubLeft1, zoomT)!;
    final hubTop = lerpDouble(hubTop0, hubTop1, zoomT)!;
    final hubScale = lerpDouble(1, 22, zoomT)!;
    final washOpacity = Curves.easeIn.transform(((exitT - 0.45) / 0.55).clamp(0.0, 1.0));
    final satelliteOpacity = (1 - exitT * 1.6).clamp(0.0, 1.0);

    return Stack(
      fit: StackFit.expand,
      children: [
        Positioned(
          left: cx - 160,
          top: cy - 160,
          child: IgnorePointer(
            child: Opacity(
              opacity: satelliteOpacity,
              child: Container(
                width: 320,
                height: 320,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  gradient: RadialGradient(
                    colors: [
                      const Color(0xFF00C2D4).withValues(alpha: 0.18),
                      const Color(0xFF7B5CFF).withValues(alpha: 0.08),
                      Colors.transparent,
                    ],
                  ),
                ),
              ),
            ),
          ),
        ),
        Positioned(
          left: cx - rx,
          top: cy - ry,
          child: Opacity(
            opacity: satelliteOpacity,
            child: CustomPaint(
              size: Size(rx * 2, ry * 2),
              painter: _OrbitRingPainter(progress: orbit),
            ),
          ),
        ),
        // PLAYDATA — 확대되며 화면으로 진입
        Positioned(
          left: hubLeft,
          top: hubTop,
          child: Transform.scale(
            scale: hubScale,
            alignment: Alignment.center,
            child: Container(
              width: hubW,
              height: hubH,
              decoration: BoxDecoration(
                color: Colors.white,
                borderRadius: BorderRadius.circular(
                  lerpDouble(22, 4, zoomT)!,
                ),
                boxShadow: [
                  BoxShadow(
                    color: const Color(0xFF00C2D4).withValues(
                      alpha: lerpDouble(0.32, 0.55, zoomT)!,
                    ),
                    blurRadius: lerpDouble(28, 80, zoomT)!,
                    spreadRadius: lerpDouble(1, 12, zoomT)!,
                  ),
                ],
              ),
              clipBehavior: Clip.antiAlias,
              child: Stack(
                fit: StackFit.expand,
                children: [
                  const _LogoFace(
                    asset: 'assets/brand/playdata.jpg',
                    padding: 20,
                  ),
                  // 진입 말미: 화이트 워시로 "속으로" 느낌
                  IgnorePointer(
                    child: ColoredBox(
                      color: Colors.white.withValues(alpha: washOpacity),
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
        _BrandPanel(
          left: skPos.dx - 74,
          top: skPos.dy - 74,
          width: 148,
          height: 148,
          rotation: 0.2 + orbit * 0.4,
          elevation: 16,
          glow: const Color(0xFFF15A22),
          opacity: satelliteOpacity,
          child: const _LogoFace(
            asset: 'assets/brand/sk_networks.jpg',
            padding: 14,
          ),
        ),
        _BrandPanel(
          left: encorePos.dx - 68,
          top: encorePos.dy - 68,
          width: 136,
          height: 136,
          rotation: -0.12 - orbit * 0.3,
          elevation: 14,
          glow: const Color(0xFF2BBBAD),
          opacity: satelliteOpacity,
          child: const _LogoFace(
            asset: 'assets/brand/encore.jpg',
            padding: 12,
          ),
        ),
        if (satelliteOpacity > 0.05)
          ...List.generate(6, (i) {
            final p = onOrbit(i * (math.pi * 2 / 6) + 0.4, radiusScale: 1.25);
            return Positioned(
              left: p.dx,
              top: p.dy,
              child: Opacity(
                opacity: satelliteOpacity,
                child: Container(
                  width: 6,
                  height: 6,
                  decoration: BoxDecoration(
                    shape: BoxShape.circle,
                    color: i.isEven
                        ? const Color(0xFF00C2D4).withValues(alpha: 0.7)
                        : const Color(0xFF7B5CFF).withValues(alpha: 0.65),
                    boxShadow: [
                      BoxShadow(
                        color: const Color(0xFF00C2D4).withValues(alpha: 0.35),
                        blurRadius: 8,
                      ),
                    ],
                  ),
                ),
              ),
            );
          }),
        // 전체 시안 글로우 마무리
        if (washOpacity > 0)
          Positioned.fill(
            child: IgnorePointer(
              child: DecoratedBox(
                decoration: BoxDecoration(
                  gradient: RadialGradient(
                    colors: [
                      const Color(0xFF00C2D4).withValues(alpha: washOpacity * 0.35),
                      Colors.white.withValues(alpha: washOpacity * 0.85),
                    ],
                  ),
                ),
              ),
            ),
          ),
      ],
    );
  }
}

class _OrbitRingPainter extends CustomPainter {
  _OrbitRingPainter({required this.progress});

  final double progress;

  @override
  void paint(Canvas canvas, Size size) {
    final rect = Offset.zero & size;
    final paint = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1.2
      ..color = Colors.white.withValues(alpha: 0.12);
    canvas.drawOval(rect.deflate(2), paint);

    final accent = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = 2
      ..strokeCap = StrokeCap.round
      ..color = const Color(0xFF00C2D4).withValues(alpha: 0.45);
    canvas.drawArc(
      rect.deflate(2),
      progress * math.pi * 2,
      1.1,
      false,
      accent,
    );
  }

  @override
  bool shouldRepaint(covariant _OrbitRingPainter oldDelegate) =>
      oldDelegate.progress != progress;
}

class LoginStageWash extends StatelessWidget {
  const LoginStageWash({super.key, this.child});

  final Widget? child;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: const BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [
            Color(0xFF05070F),
            Color(0xFF0B1224),
            Color(0xFF12102A),
            Color(0xFF1A0F18),
          ],
          stops: [0.0, 0.35, 0.7, 1.0],
        ),
      ),
      child: child,
    );
  }
}

class _BrandPanel extends StatelessWidget {
  const _BrandPanel({
    required this.left,
    required this.top,
    required this.width,
    required this.height,
    required this.rotation,
    required this.child,
    this.elevation = 12,
    this.glow,
    this.opacity = 1,
  });

  final double left;
  final double top;
  final double width;
  final double height;
  final double rotation;
  final Widget child;
  final double elevation;
  final Color? glow;
  final double opacity;

  @override
  Widget build(BuildContext context) {
    return Positioned(
      left: left,
      top: top,
      child: Opacity(
        opacity: opacity,
        child: Transform(
          alignment: Alignment.center,
          transform: Matrix4.identity()
            ..setEntry(3, 2, 0.0012)
            ..rotateZ(rotation)
            ..rotateY(-0.18)
            ..rotateX(0.12),
          child: Container(
            width: width,
            height: height,
            decoration: BoxDecoration(
              color: Colors.white,
              borderRadius: BorderRadius.circular(22),
              border: Border.all(
                color: Colors.white.withValues(alpha: 0.9),
              ),
              boxShadow: [
                BoxShadow(
                  color: Colors.black.withValues(alpha: 0.28),
                  blurRadius: elevation,
                  offset: Offset(elevation * 0.2, elevation * 0.45),
                ),
                if (glow != null)
                  BoxShadow(
                    color: glow!.withValues(alpha: 0.32),
                    blurRadius: 28,
                    spreadRadius: 1,
                  ),
              ],
            ),
            clipBehavior: Clip.antiAlias,
            child: child,
          ),
        ),
      ),
    );
  }
}

class _LogoFace extends StatelessWidget {
  const _LogoFace({required this.asset, this.padding = 16});

  final String asset;
  final double padding;

  @override
  Widget build(BuildContext context) {
    return ColoredBox(
      color: Colors.white,
      child: Padding(
        padding: EdgeInsets.all(padding),
        child: Image.asset(
          asset,
          fit: BoxFit.contain,
          filterQuality: FilterQuality.high,
        ),
      ),
    );
  }
}
