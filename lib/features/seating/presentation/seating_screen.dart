import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/theme/app_colors.dart';
import '../../../core/theme/app_layout.dart';
import '../../../core/widgets/in_page_header.dart';
import '../../../core/widgets/loading_widgets.dart';
import '../../../shared/providers/lms_providers.dart';
import '../../auth/providers/auth_providers.dart';
import '../providers/seating_providers.dart';
import 'widgets/seat_grid.dart';
import '../../../core/theme/app_space.dart';

/// 학생 — 확정된 좌석 배치표 조회
class SeatingScreen extends ConsumerWidget {
  const SeatingScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final layoutAsync = ref.watch(publishedSeatingLayoutProvider);
    final assignmentAsync = ref.watch(publishedSeatingAssignmentProvider);
    final currentUser = ref.watch(currentUserProvider);
    final cohortName = ref.watch(effectiveCohortNameProvider);

    return Scaffold(
      body: Column(
        children: [
          InPageHeader(
            title: _title(
              cohortName,
              layoutAsync.asData?.value?.roomNumber,
            ),
          ),
          Expanded(
            child: layoutAsync.when(
              loading: () => const Center(child: CircularProgressIndicator()),
              error: (e, _) => ErrorView(
                message: e.toString(),
                onRetry: () {
                  ref.invalidate(publishedSeatingLayoutProvider);
                  ref.invalidate(publishedSeatingAssignmentProvider);
                },
              ),
              data: (layout) {
                return assignmentAsync.when(
                  loading: () =>
                      const Center(child: CircularProgressIndicator()),
                  error: (e, _) => ErrorView(
                    message: e.toString(),
                    onRetry: () =>
                        ref.invalidate(publishedSeatingAssignmentProvider),
                  ),
                  data: (assignment) {
                    if (layout == null) {
                      return const Center(
                        child: Text('좌석 배치가 아직 준비되지 않았습니다.'),
                      );
                    }

                    if (assignment == null || !assignment.isPublished) {
                      return Center(
                        child: Padding(
                          padding: EdgeInsets.all(AppSpace.s(32)),
                          child: Column(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              Icon(
                                Icons.event_seat_outlined,
                                size: 48,
                                color:
                                    AppColors.textHint.withValues(alpha: 0.6),
                              ),
                              SizedBox(height: AppSpace.s(12)),
                              const Text(
                                '좌석 배치 확정 대기 중',
                                style: TextStyle(
                                  fontSize: 16,
                                  fontWeight: FontWeight.w600,
                                ),
                              ),
                              SizedBox(height: AppSpace.s(8)),
                              Text(
                                '관리자가 배치를 확정하면 이곳에서 확인할 수 있습니다.',
                                textAlign: TextAlign.center,
                                style: TextStyle(
                                  color: AppColors.textSecondary
                                      .withValues(alpha: 0.9),
                                ),
                              ),
                            ],
                          ),
                        ),
                      );
                    }

                    final seatUserIds = assignment.assignments;
                    final seatDisplayNames = assignment.seatNames.isNotEmpty
                        ? assignment.seatNames
                        : {
                            for (final e in ref
                                .watch(seatingAssignedStudentsProvider)
                                .entries)
                              e.key: e.value.displayName,
                          };
                    final myUid = currentUser.asData?.value?.uid;

                    return SingleChildScrollView(
                      padding: EdgeInsets.all(AppSpace.s(16)),
                      child: Align(
                        alignment: Alignment.topCenter,
                        child: ConstrainedBox(
                          constraints: const BoxConstraints(maxWidth: AppLayout.seating),
                          child: Column(
                            children: [
                              SeatGrid(
                                layout: layout,
                                seatUserIds: seatUserIds,
                                seatDisplayNames: seatDisplayNames,
                                highlightUserId: myUid,
                                editable: false,
                              ),
                            ],
                          ),
                        ),
                      ),
                    );
                  },
                );
              },
            ),
          ),
        ],
      ),
    );
  }

  String _title(String? cohortName, String? roomNumber) {
    final parts = <String>['자리 배치'];
    if (cohortName != null) parts.add(cohortName);
    final room = roomNumber?.trim();
    if (room != null && room.isNotEmpty) parts.add(room);
    return parts.join(' · ');
  }
}
