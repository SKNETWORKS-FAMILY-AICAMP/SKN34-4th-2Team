part of 'job_recommendation_loading.dart';

class _RecommendationError extends StatelessWidget {
  const _RecommendationError({required this.message, required this.onRetry});

  final String message;
  final VoidCallback? onRetry;

  @override
  Widget build(BuildContext context) => Column(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: [
      Icon(Icons.error_outline, color: AppColors.error, size: 25),
      SizedBox(height: AppSpace.s(12)),
      Semantics(
        liveRegion: true,
        child: Text(
          message,
          style: TextStyle(
            fontSize: 12,
            height: 1.6,
            color: AppColors.textSecondary,
          ),
        ),
      ),
      SizedBox(height: AppSpace.s(18)),
      FilledButton(
        onPressed: onRetry,
        style: FilledButton.styleFrom(
          backgroundColor: AppColors.primary,
          foregroundColor: AppColors.surface,
          minimumSize: const Size(0, 44),
        ),
        child: const Text('다시 시도'),
      ),
    ],
  );
}

/// One brief shake, followed by blue fragments and smoke. No effect text.
class _RobotBurstPainter extends CustomPainter {
  const _RobotBurstPainter({required this.progress});

  final double progress;

  @override
  void paint(Canvas canvas, Size size) {
    const robot = _HangingRobotPainter(phase: 0, release: 0, completed: true);
    const anticipation = .26;
    if (progress < anticipation) {
      canvas.save();
      canvas.translate(47, 2);
      canvas.rotate(math.sin(progress / anticipation * math.pi * 6) * .11);
      canvas.translate(-47, -2);
      robot.paint(canvas, size);
      canvas.restore();
      return;
    }

    final t = ((progress - anticipation) / (1 - anticipation)).clamp(0.0, 1.0);
    final expansion = Curves.easeOutCubic.transform(t);
    final opacity = (1 - t).clamp(0.0, 1.0);
    const center = Offset(27, 43);

    // Soft puffs spread behind the robot pieces and disappear upwards.
    for (var i = 0; i < 3; i++) {
      final direction = i - 1.0;
      canvas.drawCircle(
        center + Offset(direction * (9 + 15 * t), -23 * t - i * 4),
        5 + 18 * expansion,
        Paint()
          ..color = AppColors.primaryLight.withValues(
            alpha: math.sin(math.pi * math.min(t * 3, 1) / 2) * opacity * .85,
          ),
      );
    }

    // Preserve the actual drawn head, arms, torso and legs as they scatter.
    const pieces = <(Rect, Offset, double)>[
      (Rect.fromLTWH(0, -5, 39, 45), Offset(-24, -34), -1.3),
      (Rect.fromLTWH(13, 40, 24, 25), Offset(15, 32), 1.5),
      (Rect.fromLTWH(-8, 40, 21, 25), Offset(-33, 8), -2.3),
      (Rect.fromLTWH(39, -5, 20, 52), Offset(28, -19), 1.8),
      (Rect.fromLTWH(7, 65, 18, 29), Offset(-24, 46), -1.7),
      (Rect.fromLTWH(25, 65, 21, 29), Offset(26, 43), 2.1),
    ];
    for (final (bounds, destination, angle) in pieces) {
      canvas.save();
      canvas.translate(
        destination.dx * expansion + bounds.center.dx,
        destination.dy * expansion + bounds.center.dy,
      );
      canvas.rotate(angle * expansion);
      canvas.scale(1 - .4 * t);
      canvas.translate(-bounds.center.dx, -bounds.center.dy);
      canvas.clipRect(bounds);
      canvas.saveLayer(
        bounds,
        Paint()..color = Colors.white.withValues(alpha: opacity),
      );
      robot.paint(canvas, size);
      canvas.restore();
      canvas.restore();
    }

    for (var i = 0; i < 8; i++) {
      final angle = i * math.pi / 4 - math.pi / 2;
      final radius = 8 + 42 * expansion;
      canvas.save();
      canvas.translate(
        center.dx + math.cos(angle) * radius,
        center.dy + math.sin(angle) * radius,
      );
      canvas.rotate(angle + t * 3);
      canvas.drawRRect(
        RRect.fromRectAndRadius(
          Rect.fromCenter(
            center: Offset.zero,
            width: 4 * (1 - .4 * t),
            height: 7 * (1 - .4 * t),
          ),
          const Radius.circular(1.5),
        ),
        Paint()
          ..color = AppColors.primary.withValues(
            alpha: opacity * (i.isEven ? .9 : .45),
          ),
      );
      canvas.restore();
    }
  }

  @override
  bool shouldRepaint(_RobotBurstPainter oldDelegate) =>
      progress != oldDelegate.progress;
}
