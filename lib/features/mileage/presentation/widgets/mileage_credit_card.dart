import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../../../../core/theme/app_colors.dart';
import '../../theme/mileage_theme.dart';
import '../../../../core/theme/app_space.dart';

/// ISO 7810 ID-1 신용카드 비율
const kMileageCardAspectRatio = 1.586;
const _kCardAspectRatio = kMileageCardAspectRatio;
const _kMaxCardWidth = 420.0;
const _kMaxTiltRadians = 0.14;
/// 카드 face 디자인 기준 높이 (레이아웃·스케일 계산용)
const _kCardDesignHeight = 172.0;

const _kEmbossShadows = [
  Shadow(color: Color(0x66000000), offset: Offset(0, 1.5), blurRadius: 1),
  Shadow(color: Color(0x33FFFFFF), offset: Offset(0, -0.5), blurRadius: 0),
];

/// PLAYDATA 마일리지 — 실카드 레이아웃 + 마우스/터치 3D 기울임
class MileageCreditCard extends StatefulWidget {
  const MileageCreditCard({
    super.key,
    required this.balance,
    this.holderName,
    this.validThru,
    this.enableTilt = true,
    this.padding,
    this.maxWidth = _kMaxCardWidth,
    this.fixedSize,
  });

  final int balance;
  final String? holderName;
  final DateTime? validThru;
  final bool enableTilt;
  /// null이면 기본 페이지 패딩, `EdgeInsets.zero`면 래퍼 없음
  final EdgeInsetsGeometry? padding;
  final double? maxWidth;
  /// 고정 크기 (대시보드 등). 설정 시 [fixedSize] 비율 그대로 렌더
  final Size? fixedSize;

  @override
  State<MileageCreditCard> createState() => _MileageCreditCardState();
}

class _MileageCreditCardState extends State<MileageCreditCard>
    with SingleTickerProviderStateMixin {
  double _tiltX = 0;
  double _tiltY = 0;
  late final AnimationController _resetController;
  Animation<double>? _resetX;
  Animation<double>? _resetY;

  @override
  void initState() {
    super.initState();
    _resetController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 420),
    )..addListener(() {
        if (_resetX != null && _resetY != null) {
          setState(() {
            _tiltX = _resetX!.value;
            _tiltY = _resetY!.value;
          });
        }
      });
  }

  @override
  void dispose() {
    _resetController.dispose();
    super.dispose();
  }

  void _applyTilt(double nx, double ny) {
    if (!widget.enableTilt) return;
    setState(() {
      _tiltY = nx.clamp(-1.0, 1.0) * _kMaxTiltRadians;
      _tiltX = -ny.clamp(-1.0, 1.0) * _kMaxTiltRadians * 0.85;
    });
  }

  void _resetTilt() {
    if (!widget.enableTilt) return;
    _resetController.stop();
    _resetX = Tween<double>(begin: _tiltX, end: 0).animate(
      CurvedAnimation(parent: _resetController, curve: Curves.easeOutCubic),
    );
    _resetY = Tween<double>(begin: _tiltY, end: 0).animate(
      CurvedAnimation(parent: _resetController, curve: Curves.easeOutCubic),
    );
    _resetController.forward(from: 0);
  }

  void _onPointerMove(PointerEvent event, Size size) {
    if (!widget.enableTilt) return;
    _resetController.stop();
    final nx = (event.localPosition.dx / size.width - 0.5) * 2;
    final ny = (event.localPosition.dy / size.height - 0.5) * 2;
    _applyTilt(nx, ny);
  }

  String get _validThruLabel {
    final date = widget.validThru;
    if (date == null) return '--/--';
    return DateFormat('MM/yy').format(date);
  }

  String get _holderLabel {
    final name = widget.holderName?.trim();
    if (name == null || name.isEmpty) return 'PLAYDATA MEMBER';
    return name.toUpperCase();
  }

  @override
  Widget build(BuildContext context) {
    Widget buildCard(Size cardSize) {
      Widget card = _CardFace(
        balance: widget.balance,
        holderLabel: _holderLabel,
        validThruLabel: _validThruLabel,
        glareAlignment: Alignment(
          (_tiltY / _kMaxTiltRadians).clamp(-1.0, 1.0),
          (-_tiltX / (_kMaxTiltRadians * 0.85)).clamp(-1.0, 1.0),
        ),
      );

      if (widget.enableTilt) {
        card = Transform(
          alignment: Alignment.center,
          transform: Matrix4.identity()
            ..setEntry(3, 2, 0.0012)
            ..rotateX(_tiltX)
            ..rotateY(_tiltY),
          child: card,
        );
      }

      return Listener(
        onPointerMove: (e) => _onPointerMove(e, cardSize),
        onPointerUp: (_) => _resetTilt(),
        onPointerCancel: (_) => _resetTilt(),
        child: MouseRegion(
          onExit: (_) => _resetTilt(),
          child: card,
        ),
      );
    }

    final Widget content;
    if (widget.fixedSize != null) {
      final size = widget.fixedSize!;
      if (size.width <= 0 || size.height <= 0) {
        return const SizedBox.shrink();
      }
      content = Center(
        child: SizedBox(
          width: size.width,
          height: size.height,
          child: buildCard(size),
        ),
      );
    } else {
      content = Center(
        child: ConstrainedBox(
          constraints: BoxConstraints(maxWidth: widget.maxWidth ?? _kMaxCardWidth),
          child: LayoutBuilder(
            builder: (context, constraints) {
              final cardWidth = constraints.maxWidth;
              final cardHeight = cardWidth / _kCardAspectRatio;
              final cardSize = Size(cardWidth, cardHeight);

              return AspectRatio(
                aspectRatio: _kCardAspectRatio,
                child: buildCard(cardSize),
              );
            },
          ),
        ),
      );
    }

    if (widget.padding == EdgeInsets.zero) {
      return content;
    }
    return Padding(
      padding: widget.padding ??
          const EdgeInsets.symmetric(horizontal: MileageLayout.pagePaddingH),
      child: content,
    );
  }
}

class _CardFace extends StatelessWidget {
  const _CardFace({
    required this.balance,
    required this.holderLabel,
    required this.validThruLabel,
    required this.glareAlignment,
  });

  final int balance;
  final String holderLabel;
  final String validThruLabel;
  final Alignment glareAlignment;

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        final radius = constraints.maxHeight < 130 ? 10.0 : 16.0;
        final shadowBlur = constraints.maxHeight < 130 ? 12.0 : 28.0;

        return DecoratedBox(
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(radius),
            gradient: LinearGradient(
              begin: Alignment.topLeft,
              end: Alignment.bottomRight,
              colors: [
                MileageColors.cardGradientStart,
                AppColors.sidebar,
                MileageColors.cardGradientEnd,
              ],
              stops: [0.0, 0.45, 1.0],
            ),
            boxShadow: [
              BoxShadow(
                color: MileageColors.primary.withValues(alpha: 0.35),
                blurRadius: shadowBlur,
                offset: Offset(0, shadowBlur / 2),
                spreadRadius: -6,
              ),
              BoxShadow(
                color: Colors.black.withValues(alpha: 0.12),
                blurRadius: 8,
                offset: const Offset(0, 4),
              ),
            ],
          ),
          child: ClipRRect(
            borderRadius: BorderRadius.circular(radius),
            child: Stack(
              fit: StackFit.expand,
              children: [
                const _CardPatternOverlay(),
                Positioned(
                  right: -24,
                  bottom: -20,
                  child: Transform.rotate(
                    angle: -math.pi / 10,
                    child: Text(
                      'PLAYDATA',
                      style: TextStyle(
                        fontSize: 72,
                        fontWeight: FontWeight.w900,
                        letterSpacing: 4,
                        color: Colors.white.withValues(alpha: 0.06),
                      ),
                    ),
                  ),
                ),
                _CardFaceContent(
                  balance: balance,
                  holderLabel: holderLabel,
                  validThruLabel: validThruLabel,
                ),
                _GlareOverlay(alignment: glareAlignment),
              ],
            ),
          ),
        );
      },
    );
  }
}

class _CardFaceContent extends StatelessWidget {
  const _CardFaceContent({
    required this.balance,
    required this.holderLabel,
    required this.validThruLabel,
  });

  final int balance;
  final String holderLabel;
  final String validThruLabel;

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        final height = constraints.maxHeight;
        final width = constraints.maxWidth;
        if (height <= 0 || width <= 0) {
          return const SizedBox.shrink();
        }

        // 실제 슬롯 높이에 맞춰 패딩·폰트·칩 크기를 비율 조정 (overflow 방지)
        final scale = math.min(1.0, height / _kCardDesignHeight);
        final padH = 20.0 * scale;
        final padTop = 18.0 * scale;
        final padBottom = 16.0 * scale;
        final labelGap = 2.0 * scale;
        final nfcGap = 10.0 * scale;

        return Padding(
          padding: EdgeInsets.fromLTRB(padH, padTop, padH, padBottom),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          'PLAYDATA',
                          style: TextStyle(
                            color: Colors.white,
                            letterSpacing: 2.2 * scale,
                            fontSize: 13 * scale,
                            fontWeight: FontWeight.w800,
                            shadows: _kEmbossShadows,
                          ),
                        ),
                        Text(
                          'MILEAGE',
                          style: TextStyle(
                            color: Colors.white70,
                            letterSpacing: 3 * scale,
                            fontSize: 9 * scale,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                      ],
                    ),
                  ),
                  _EmvChip(scale: scale),
                  SizedBox(width: nfcGap),
                  Icon(
                    Icons.contactless_outlined,
                    color: Colors.white.withValues(alpha: 0.75),
                    size: 22 * scale,
                  ),
                ],
              ),
              Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisSize: MainAxisSize.min,
                children: [
                  Text(
                    'TOTAL POINTS',
                    style: TextStyle(
                      color: Colors.white60,
                      fontSize: 9 * scale,
                      letterSpacing: 1.2 * scale,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                  SizedBox(height: labelGap),
                  Text(
                    '${formatMileageAmount(balance)} P',
                    style: TextStyle(
                      color: Colors.white,
                      fontSize: 28 * scale,
                      fontWeight: FontWeight.w700,
                      letterSpacing: 2.5 * scale,
                      fontFamily: 'monospace',
                      shadows: _kEmbossShadows,
                    ),
                  ),
                ],
              ),
              Row(
                children: [
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Text(
                          'CARD HOLDER',
                          style: TextStyle(
                            color: Colors.white54,
                            fontSize: 7 * scale,
                            letterSpacing: 0.8 * scale,
                          ),
                        ),
                        SizedBox(height: labelGap),
                        Text(
                          holderLabel,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: TextStyle(
                            color: Colors.white,
                            fontSize: 12 * scale,
                            fontWeight: FontWeight.w600,
                            letterSpacing: 1.2 * scale,
                            shadows: _kEmbossShadows,
                          ),
                        ),
                      ],
                    ),
                  ),
                  Column(
                    crossAxisAlignment: CrossAxisAlignment.end,
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Text(
                        'VALID THRU',
                        style: TextStyle(
                          color: Colors.white54,
                          fontSize: 7 * scale,
                          letterSpacing: 0.8 * scale,
                        ),
                      ),
                      SizedBox(height: labelGap),
                      Text(
                        validThruLabel,
                        style: TextStyle(
                          color: Colors.white,
                          fontSize: 13 * scale,
                          fontWeight: FontWeight.w600,
                          letterSpacing: 1.5 * scale,
                          fontFamily: 'monospace',
                          shadows: _kEmbossShadows,
                        ),
                      ),
                    ],
                  ),
                ],
              ),
            ],
          ),
        );
      },
    );
  }
}

class _EmvChip extends StatelessWidget {
  const _EmvChip({required this.scale});

  final double scale;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 44 * scale,
      height: 34 * scale,
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(6 * scale),
        gradient: const LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [Color(0xFFE8C547), Color(0xFFC9A227), Color(0xFFF0D875)],
        ),
        boxShadow: const [
          BoxShadow(
            color: Color(0x66000000),
            offset: Offset(0, 2),
            blurRadius: 3,
          ),
        ],
        border: Border.all(color: const Color(0xFFB8860B), width: 0.5),
      ),
      child: Padding(
        padding: EdgeInsets.symmetric(
          horizontal: AppSpace.s(5) * scale,
          vertical: AppSpace.s(6) * scale,
        ),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.spaceEvenly,
          children: List.generate(
            4,
            (_) => Container(
              height: math.max(0.5, scale),
              color: Colors.black.withValues(alpha: 0.22),
            ),
          ),
        ),
      ),
    );
  }
}

class _CardPatternOverlay extends StatelessWidget {
  const _CardPatternOverlay();

  @override
  Widget build(BuildContext context) {
    return CustomPaint(
      painter: _CardPatternPainter(),
    );
  }
}

class _CardPatternPainter extends CustomPainter {
  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = Colors.white.withValues(alpha: 0.04)
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1;

    for (var i = -2; i < 8; i++) {
      canvas.drawCircle(
        Offset(size.width * 0.75, size.height * 0.1 + i * 36.0),
        48 + i * 8.0,
        paint,
      );
    }

    final linePaint = Paint()
      ..shader = LinearGradient(
        begin: Alignment.topLeft,
        end: Alignment.bottomRight,
        colors: [
          Colors.white.withValues(alpha: 0.0),
          Colors.white.withValues(alpha: 0.08),
          Colors.white.withValues(alpha: 0.0),
        ],
      ).createShader(Rect.fromLTWH(0, 0, size.width, size.height));

    canvas.drawRect(
      Rect.fromLTWH(0, 0, size.width, size.height),
      linePaint,
    );
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}

class _GlareOverlay extends StatelessWidget {
  const _GlareOverlay({required this.alignment});

  final Alignment alignment;

  @override
  Widget build(BuildContext context) {
    return IgnorePointer(
      child: DecoratedBox(
        decoration: BoxDecoration(
          gradient: LinearGradient(
            begin: alignment,
            end: alignment * -1,
            colors: [
              Colors.white.withValues(alpha: 0.18),
              Colors.white.withValues(alpha: 0.04),
              Colors.transparent,
            ],
            stops: const [0.0, 0.35, 0.7],
          ),
        ),
      ),
    );
  }
}
