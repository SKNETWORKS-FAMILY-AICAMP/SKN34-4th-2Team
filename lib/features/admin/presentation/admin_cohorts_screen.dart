import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/constants/cohort_status.dart';
import '../../../core/routing/route_paths.dart';
import '../../../core/theme/app_colors.dart';
import '../../../core/theme/app_layout.dart';
import '../../../core/widgets/filter_pill.dart';
import '../../../core/widgets/loading_widgets.dart';
import '../../../shared/models/cohort_model.dart';
import '../../../shared/providers/cohort_providers.dart';
import '../../../shared/providers/lms_providers.dart';
import '../../../core/theme/app_space.dart';

/// 관리자 — 기수 목록 / 선택 / 상태 관리
class AdminCohortsScreen extends ConsumerStatefulWidget {
  const AdminCohortsScreen({super.key});

  @override
  ConsumerState<AdminCohortsScreen> createState() => _AdminCohortsScreenState();
}

class _AdminCohortsScreenState extends ConsumerState<AdminCohortsScreen> {
  /// 0: 진행중, 1: 예정, 2: 종료
  int _filter = 0;

  @override
  Widget build(BuildContext context) {
    final cohorts = ref.watch(allCohortsAdminProvider);
    final selectedId = ref.watch(effectiveCohortIdProvider);

    final list = cohorts.asData?.value;
    final activeCount =
        list?.where((c) => c.status == CohortStatus.active).length;
    final upcomingCount =
        list?.where((c) => c.status == CohortStatus.upcoming).length;
    final archivedCount =
        list?.where((c) => c.status == CohortStatus.archived).length;

    return Scaffold(
      body: Column(
        children: [
          FilterPillHeader(
            pills: [
              FilterPill(
                label: '진행중',
                count: activeCount,
                selected: _filter == 0,
                onTap: () => setState(() => _filter = 0),
              ),
              FilterPill(
                label: '예정',
                count: upcomingCount,
                selected: _filter == 1,
                onTap: () => setState(() => _filter = 1),
              ),
              FilterPill(
                label: '종료',
                count: archivedCount,
                selected: _filter == 2,
                onTap: () => setState(() => _filter = 2),
              ),
            ],
            trailing: FilledButton.icon(
              onPressed: () => context.push(RoutePaths.adminCohortsCreate),
              icon: const Icon(Icons.add, size: 18),
              label: const Text('기수 생성'),
            ),
          ),
          Expanded(
            child: cohorts.when(
              loading: () => const Center(child: CircularProgressIndicator()),
              error: (e, _) => ErrorView(
                message: e.toString(),
                onRetry: () => ref.invalidate(allCohortsAdminProvider),
              ),
              data: (list) {
                final filtered = switch (_filter) {
                  1 => list
                      .where((c) => c.status == CohortStatus.upcoming)
                      .toList(),
                  2 => list
                      .where((c) => c.status == CohortStatus.archived)
                      .toList(),
                  _ => list
                      .where((c) => c.status == CohortStatus.active)
                      .toList(),
                };
                final emptyMessage = switch (_filter) {
                  1 => '예정된 기수가 없습니다',
                  2 => '종료된 기수가 없습니다',
                  _ => '진행 중인 기수가 없습니다',
                };
                return _CohortList(
                  cohorts: filtered,
                  selectedId: selectedId,
                  emptyMessage: emptyMessage,
                );
              },
            ),
          ),
        ],
      ),
    );
  }
}

class _CohortList extends ConsumerWidget {
  const _CohortList({
    required this.cohorts,
    required this.selectedId,
    required this.emptyMessage,
  });

  final List<CohortModel> cohorts;
  final String? selectedId;
  final String emptyMessage;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    if (cohorts.isEmpty) {
      return Center(
        child: Text(
          emptyMessage,
          style: TextStyle(color: AppColors.textSecondary),
        ),
      );
    }

    return RefreshIndicator(
      onRefresh: () async => ref.invalidate(allCohortsAdminProvider),
      child: ListView.builder(
        physics: const AlwaysScrollableScrollPhysics(),
        padding: EdgeInsets.all(AppSpace.s(16)),
        itemCount: cohorts.length,
        itemBuilder: (_, i) {
          final c = cohorts[i];
          final isSelected = c.cohortId == selectedId;
          final students = ref.watch(cohortStudentsByIdProvider(c.cohortId));
          final actualStudentCount = students.asData?.value.length;
          return Align(
            alignment: Alignment.topCenter,
            child: ConstrainedBox(
              constraints: AppLayout.listConstraints(),
              child: Card(
                margin: EdgeInsets.only(bottom: AppSpace.s(10)),
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(12),
                  side: BorderSide(
                    color: isSelected ? AppColors.primary : AppColors.border,
                    width: isSelected ? 1.5 : 1,
                  ),
                ),
                child: InkWell(
                  borderRadius: BorderRadius.circular(12),
                  onTap: () => context.push(
                    RoutePaths.adminCohortEditPath(c.cohortId),
                  ),
                  child: Padding(
                    padding: EdgeInsets.all(AppSpace.s(16)),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        Row(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Expanded(
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Row(
                                    children: [
                                      _StatusChip(status: c.status),
                                      if (isSelected) ...[
                                        SizedBox(width: AppSpace.s(8)),
                                        Container(
                                          padding: EdgeInsets.symmetric(
                                            horizontal: AppSpace.s(8),
                                            vertical: AppSpace.s(2),
                                          ),
                                          decoration: BoxDecoration(
                                            color: AppColors.primaryLight,
                                            borderRadius:
                                                BorderRadius.circular(6),
                                          ),
                                          child: const Text(
                                            '현재 선택',
                                            style: TextStyle(
                                              fontSize: 11,
                                              fontWeight: FontWeight.w600,
                                            ),
                                          ),
                                        ),
                                      ],
                                    ],
                                  ),
                                  SizedBox(height: AppSpace.s(8)),
                                  Text(
                                    c.name,
                                    style: const TextStyle(
                                      fontSize: 16,
                                      fontWeight: FontWeight.w600,
                                    ),
                                  ),
                                  SizedBox(height: AppSpace.s(4)),
                                  Text(
                                    c.periodLabel,
                                    style: TextStyle(
                                      fontSize: 12,
                                      color: AppColors.textSecondary,
                                    ),
                                  ),
                                ],
                              ),
                            ),
                            Column(
                              crossAxisAlignment: CrossAxisAlignment.end,
                              children: [
                                Text(
                                  actualStudentCount == null
                                      ? '…명'
                                      : '$actualStudentCount명',
                                  style: const TextStyle(
                                    fontWeight: FontWeight.w600,
                                  ),
                                ),
                                Text(
                                  '학생',
                                  style: TextStyle(
                                    fontSize: 11,
                                    color: AppColors.textSecondary,
                                  ),
                                ),
                              ],
                            ),
                          ],
                        ),
                        SizedBox(height: AppSpace.s(12)),
                        Wrap(
                          spacing: 8,
                          runSpacing: 8,
                          children: [
                            if (c.isSelectable && !isSelected)
                              OutlinedButton(
                                onPressed: () {
                                  selectCohort(ref, c.cohortId);
                                  ScaffoldMessenger.of(context).showSnackBar(
                                    SnackBar(
                                      content: Text('「${c.name}」 기수를 선택했습니다'),
                                    ),
                                  );
                                },
                                child: const Text('이 기수로 전환'),
                              ),
                            OutlinedButton(
                              onPressed: () => context.push(
                                RoutePaths.adminCohortEditPath(c.cohortId),
                              ),
                              child: const Text('수정'),
                            ),
                          ],
                        ),
                      ],
                    ),
                  ),
                ),
              ),
            ),
          );
        },
      ),
    );
  }
}

class _StatusChip extends StatelessWidget {
  const _StatusChip({required this.status});

  final CohortStatus status;

  @override
  Widget build(BuildContext context) {
    final color = switch (status) {
      CohortStatus.active => AppColors.success,
      CohortStatus.upcoming => AppColors.info,
      CohortStatus.archived => AppColors.textSecondary,
    };

    return Container(
      padding: EdgeInsets.symmetric(horizontal: AppSpace.s(8), vertical: AppSpace.s(3)),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(6),
      ),
      child: Text(
        status.label,
        style: TextStyle(
          fontSize: 11,
          fontWeight: FontWeight.w600,
          color: color,
        ),
      ),
    );
  }
}
