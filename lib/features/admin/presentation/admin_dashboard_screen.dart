import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/constants/mileage_constants.dart';
import '../../../core/routing/route_paths.dart';
import '../../../core/theme/app_colors.dart';
import '../../../core/widgets/loading_widgets.dart';
import '../../../shared/models/form_task_model.dart';
import '../../../shared/models/mileage_models.dart';
import '../../../shared/models/resume_model.dart';
import '../../../shared/models/submission_model.dart';
import '../../../shared/providers/lms_providers.dart';
import '../../../shared/providers/mileage_providers.dart';
import '../../auth/providers/auth_providers.dart';
import '../../../core/theme/app_space.dart';

/// 관리자 대시보드 — 승인 대기 요약 + 승인 현황 사이드바
class AdminDashboardScreen extends ConsumerWidget {
  const AdminDashboardScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final userAsync = ref.watch(currentUserProvider);

    return userAsync.when(
      loading: () => const Center(child: CircularProgressIndicator()),
      error: (e, _) => ErrorView(message: e.toString()),
      data: (_) => const _AdminDashboardBody(),
    );
  }
}

class _AdminDashboardBody extends ConsumerWidget {
  const _AdminDashboardBody();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final submissions = ref.watch(allSubmissionsProvider);
    final resumes = ref.watch(cohortResumesProvider);
    final formTasks = ref.watch(allFormTasksAdminProvider);
    final purchaseRequests = ref.watch(allPurchaseRequestsProvider);

    return RefreshIndicator(
      onRefresh: () async {
        ref.invalidate(allSubmissionsProvider);
        ref.invalidate(cohortResumesProvider);
        ref.invalidate(cohortStudentsProvider);
        ref.invalidate(allFormTasksAdminProvider);
        ref.invalidate(allPurchaseRequestsProvider);
      },
      child: LayoutBuilder(
        builder: (context, constraints) {
          final wide = constraints.maxWidth >= 960;
          final main = _PendingSummary(
            submissions: submissions,
            resumes: resumes,
            formTasks: formTasks,
            purchaseRequests: purchaseRequests,
          );
          final sidebar = Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              const Text(
                '승인 현황',
                style: TextStyle(fontSize: 14, fontWeight: FontWeight.w600),
              ),
              SizedBox(height: AppSpace.s(8)),
              submissions.when(
                loading: () => const _ShimmerCard(),
                error: (e, _) => InlineErrorCard(
                  error: e,
                  onRetry: () => ref.invalidate(allSubmissionsProvider),
                ),
                data: (list) => _RecentSubmissions(submissions: list),
              ),
            ],
          );

          if (!wide) {
            return SingleChildScrollView(
              physics: const AlwaysScrollableScrollPhysics(),
              padding: EdgeInsets.all(AppSpace.s(16)),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  main,
                  SizedBox(height: AppSpace.s(16)),
                  sidebar,
                ],
              ),
            );
          }

          return SingleChildScrollView(
            physics: const AlwaysScrollableScrollPhysics(),
            padding: EdgeInsets.all(AppSpace.s(16)),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Expanded(child: main),
                SizedBox(width: AppSpace.s(16)),
                SizedBox(width: 320, child: sidebar),
              ],
            ),
          );
        },
      ),
    );
  }
}

class _PendingSummary extends StatelessWidget {
  const _PendingSummary({
    required this.submissions,
    required this.resumes,
    required this.formTasks,
    required this.purchaseRequests,
  });

  final AsyncValue<List<SubmissionModel>> submissions;
  final AsyncValue<List<ResumeModel>> resumes;
  final AsyncValue<List<FormTaskModel>> formTasks;
  final AsyncValue<List<PurchaseRequestModel>> purchaseRequests;

  @override
  Widget build(BuildContext context) {
    final pendingRecords = submissions.maybeWhen(
      data: (list) => list.where((s) => s.isPending).length,
      orElse: () => 0,
    );
    final pendingResumes = resumes.maybeWhen(
      data: (list) =>
          list.where((r) => r.isSubmitted && !r.isApproved).length,
      orElse: () => 0,
    );
    final pendingMileage = purchaseRequests.maybeWhen(
      data: (list) => list
          .where(
            (r) =>
                r.status == PurchaseRequestStatus.pending ||
                r.status == PurchaseRequestStatus.modifyRequested,
          )
          .length,
      orElse: () => 0,
    );
    final activeForms = formTasks.maybeWhen(
      data: (list) => list.where((t) => t.published).length,
      orElse: () => null,
    );

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text(
          '관리자 대시보드',
          style: TextStyle(
            fontSize: 22,
            fontWeight: FontWeight.bold,
            color: AppColors.textPrimary,
          ),
        ),
        SizedBox(height: AppSpace.s(6)),
        Text(
          '승인 대기 항목을 확인하고 처리하세요.',
          style: TextStyle(fontSize: 13, color: AppColors.textSecondary),
        ),
        SizedBox(height: AppSpace.s(20)),
        Row(
          children: [
            Expanded(
              child: _SummaryCard(
                icon: Icons.history,
                label: '기록실 승인 대기',
                count: pendingRecords,
                color: AppColors.primary,
                onTap: () => context.go(RoutePaths.adminRecords),
              ),
            ),
            SizedBox(width: AppSpace.s(12)),
            Expanded(
              child: _SummaryCard(
                icon: Icons.description,
                label: '이력서 검토 대기',
                count: pendingResumes,
                color: AppColors.primary,
                onTap: () => context.go(RoutePaths.adminResumes),
              ),
            ),
          ],
        ),
        SizedBox(height: AppSpace.s(12)),
        _SummaryCard(
          icon: Icons.calendar_month,
          label: '기수 관리',
          count: null,
          color: AppColors.info,
          onTap: () => context.go(RoutePaths.adminCohorts),
          fullWidth: true,
        ),
        SizedBox(height: AppSpace.s(12)),
        _SummaryCard(
          icon: Icons.groups,
          label: '학생 관리 — 상담 등록 / 계정',
          count: null,
          color: AppColors.primary,
          onTap: () => context.go(RoutePaths.adminStudents),
          fullWidth: true,
        ),
        SizedBox(height: AppSpace.s(12)),
        _SummaryCard(
          icon: Icons.fact_check_outlined,
          label: '출석관리 — 기수별 전원 / 폼 반영',
          count: null,
          color: const Color(0xFF0F766E),
          onTap: () => context.go(RoutePaths.adminAttendance),
          fullWidth: true,
        ),
        SizedBox(height: AppSpace.s(12)),
        _SummaryCard(
          icon: Icons.event_seat,
          label: '좌석 배치 — 틀 설정 / 확정',
          count: null,
          color: const Color(0xFF0D9488),
          onTap: () => context.go(RoutePaths.adminSeating),
          fullWidth: true,
        ),
        SizedBox(height: AppSpace.s(12)),
        _SummaryCard(
          icon: Icons.card_giftcard_outlined,
          label: '마일리지 관리',
          count: pendingMileage,
          color: AppColors.primary,
          onTap: () => context.go(RoutePaths.adminMileage),
          fullWidth: true,
        ),
        SizedBox(height: AppSpace.s(12)),
        _SummaryCard(
          icon: Icons.ballot_outlined,
          label: '설문 · 제출 관리',
          count: activeForms,
          countSuffix: activeForms != null ? '개 운영' : null,
          color: AppColors.warning,
          onTap: () => context.go(RoutePaths.adminFormTasks),
          fullWidth: true,
        ),
      ],
    );
  }
}

class _SummaryCard extends StatelessWidget {
  const _SummaryCard({
    required this.icon,
    required this.label,
    required this.color,
    required this.onTap,
    this.count,
    this.countSuffix,
    this.fullWidth = false,
  });

  final IconData icon;
  final String label;
  final Color color;
  final VoidCallback onTap;
  final int? count;
  final String? countSuffix;
  final bool fullWidth;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: AppColors.surface,
      elevation: 0,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(12),
        side: BorderSide(color: AppColors.border),
      ),
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: onTap,
        child: Padding(
          padding: EdgeInsets.all(AppSpace.s(16)),
          child: Row(
            children: [
              Container(
                width: 40,
                height: AppSpace.row(40),
                decoration: BoxDecoration(
                  color: color.withValues(alpha: 0.12),
                  borderRadius: BorderRadius.circular(10),
                ),
                child: Icon(icon, color: color, size: 22),
              ),
              SizedBox(width: AppSpace.s(12)),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      label,
                      style: const TextStyle(
                        fontWeight: FontWeight.w600,
                        fontSize: 13,
                      ),
                    ),
                    if (count != null)
                      Text(
                        countSuffix != null
                            ? '$count$countSuffix'
                            : '$count건 대기',
                        style: TextStyle(
                          fontSize: 12,
                          color: count! > 0 ? color : AppColors.textSecondary,
                          fontWeight:
                              count! > 0 ? FontWeight.w600 : FontWeight.normal,
                        ),
                      ),
                  ],
                ),
              ),
              Icon(Icons.chevron_right, color: AppColors.textHint),
            ],
          ),
        ),
      ),
    );
  }
}

class _RecentSubmissions extends StatelessWidget {
  const _RecentSubmissions({required this.submissions});

  final List<SubmissionModel> submissions;

  @override
  Widget build(BuildContext context) {
    final pending = submissions.where((s) => s.isPending).take(5).toList();
    if (pending.isEmpty) {
      return Card(
        margin: EdgeInsets.zero,
        child: Padding(
          padding: EdgeInsets.all(AppSpace.s(20)),
          child: Center(
            child: Text(
              '승인 대기 항목이 없습니다',
              style: TextStyle(
                fontSize: 12,
                color: AppColors.textSecondary.withValues(alpha: 0.9),
              ),
            ),
          ),
        ),
      );
    }

    return Card(
      margin: EdgeInsets.zero,
      child: Column(
        children: pending
            .map(
              (s) => ListTile(
                dense: true,
                title: Text(
                  s.title,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(fontSize: 13),
                ),
                subtitle: Text(
                  '${s.typeLabel} · ${s.userDisplayName}',
                  style: const TextStyle(fontSize: 11),
                ),
                trailing: const Icon(Icons.chevron_right, size: 18),
                onTap: () => context.go(RoutePaths.adminRecords),
              ),
            )
            .toList(),
      ),
    );
  }
}

class _ShimmerCard extends StatelessWidget {
  const _ShimmerCard();

  @override
  Widget build(BuildContext context) {
    return Card(
      margin: EdgeInsets.zero,
      child: Padding(
        padding: EdgeInsets.all(AppSpace.s(24)),
        child: Center(
          child: SizedBox(
            width: 20,
            height: 20,
            child: CircularProgressIndicator(strokeWidth: 2),
          ),
        ),
      ),
    );
  }
}
