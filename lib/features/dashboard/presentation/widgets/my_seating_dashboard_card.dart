import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../../core/routing/route_paths.dart';
import '../../../../core/theme/app_colors.dart';
import '../../../auth/providers/auth_providers.dart';
import '../../../seating/presentation/widgets/seat_grid.dart';
import '../../../seating/providers/seating_providers.dart';
import '../../../../core/theme/app_space.dart';

/// 대시보드 — 확정 후 3일간만 표시되는 미니 좌석 배치 섹션
class MySeatingDashboardSection extends ConsumerWidget {
  const MySeatingDashboardSection({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final visible = ref.watch(showSeatingDashboardPreviewProvider);
    if (!visible) return const SizedBox.shrink();

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Padding(
          padding: EdgeInsets.only(bottom: AppSpace.s(8)),
          child: Text(
            '내 자리 배치',
            style: TextStyle(fontWeight: FontWeight.bold, fontSize: 14),
          ),
        ),
        MySeatingDashboardCard(),
        SizedBox(height: AppSpace.s(16)),
      ],
    );
  }
}

/// 대시보드 — 미니 좌석 배치표 (탭 시 전체 화면)
class MySeatingDashboardCard extends ConsumerWidget {
  const MySeatingDashboardCard({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final layoutAsync = ref.watch(publishedSeatingLayoutProvider);
    final assignmentAsync = ref.watch(publishedSeatingAssignmentProvider);
    final myUid = ref.watch(currentUserProvider).asData?.value?.uid;

    return layoutAsync.when(
      loading: () => const _SeatingCardShell(
        child: Center(
          child: SizedBox(
            height: 20,
            width: 20,
            child: CircularProgressIndicator(strokeWidth: 2),
          ),
        ),
      ),
      error: (e, _) => _SeatingCardShell(
        onTap: () => context.go(RoutePaths.seating),
        child: Text(
          '불러오기 실패 · 탭하여 다시 보기',
          style: TextStyle(
            fontSize: 12,
            color: AppColors.textSecondary.withValues(alpha: 0.9),
          ),
        ),
      ),
      data: (layout) {
        return assignmentAsync.when(
          loading: () => const _SeatingCardShell(
            child: Center(
              child: SizedBox(
                height: 20,
                width: 20,
                child: CircularProgressIndicator(strokeWidth: 2),
              ),
            ),
          ),
          error: (e, _) => _SeatingCardShell(
            onTap: () => context.go(RoutePaths.seating),
            child: Text(
              '불러오기 실패 · 탭하여 다시 보기',
              style: TextStyle(
                fontSize: 12,
                color: AppColors.textSecondary.withValues(alpha: 0.9),
              ),
            ),
          ),
          data: (assignment) {
            final isReady =
                layout != null && assignment != null && assignment.isPublished;

            if (!isReady) return const SizedBox.shrink();

            final seatUserIds = assignment.assignments;
            final seatDisplayNames = assignment.seatNames.isNotEmpty
                ? assignment.seatNames
                : {
                    for (final e
                        in ref.watch(seatingAssignedStudentsProvider).entries)
                      e.key: e.value.displayName,
                  };

            return _SeatingCardShell(
              onTap: () => context.go(RoutePaths.seating),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  LayoutBuilder(
                    builder: (context, constraints) {
                      return SizedBox(
                        width: constraints.maxWidth,
                        child: FittedBox(
                          fit: BoxFit.scaleDown,
                          alignment: Alignment.topCenter,
                          child: SeatGrid(
                            layout: layout,
                            seatUserIds: seatUserIds,
                            seatDisplayNames: seatDisplayNames,
                            highlightUserId: myUid,
                            compact: true,
                            editable: false,
                          ),
                        ),
                      );
                    },
                  ),
                  SizedBox(height: AppSpace.s(6)),
                  Text(
                    '탭하여 크게 보기',
                    textAlign: TextAlign.center,
                    style: TextStyle(
                      fontSize: 10,
                      color: AppColors.textHint.withValues(alpha: 0.9),
                    ),
                  ),
                ],
              ),
            );
          },
        );
      },
    );
  }
}

class _SeatingCardShell extends StatelessWidget {
  const _SeatingCardShell({required this.child, this.onTap});

  final Widget child;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    return Card(
      margin: EdgeInsets.zero,
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: onTap,
        child: Padding(
          padding: EdgeInsets.fromLTRB(AppSpace.s(10), AppSpace.s(10), AppSpace.s(10), AppSpace.s(8)),
          child: child,
        ),
      ),
    );
  }
}
