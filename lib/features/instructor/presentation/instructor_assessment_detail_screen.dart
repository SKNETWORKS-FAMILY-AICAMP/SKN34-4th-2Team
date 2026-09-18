import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/routing/route_paths.dart';
import '../../../core/theme/app_colors.dart';
import '../../../core/widgets/loading_widgets.dart';
import '../../../shared/providers/lms_providers.dart';
import 'instructor_assessments_screen.dart';
import '../../../core/theme/app_space.dart';

/// 강사 — 평가 상세 (결과 목록 + 수정/삭제)
class InstructorAssessmentDetailScreen extends ConsumerWidget {
  const InstructorAssessmentDetailScreen({
    super.key,
    required this.assessmentId,
  });

  final String assessmentId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final assessment = ref.watch(assessmentProvider(assessmentId));
    final submissions = ref.watch(assessmentSubmissionsProvider(assessmentId));

    return Scaffold(
      appBar: AppBar(
        title: assessment.when(
          data: (a) => Text(a?.title ?? '평가'),
          loading: () => const Text('평가'),
          error: (_, __) => const Text('평가'),
        ),
        actions: [
          TextButton(
            onPressed: () => context.push(
              RoutePaths.instructorAssessmentEditPath(assessmentId),
            ),
            child: const Text('수정'),
          ),
          IconButton(
            tooltip: '삭제',
            onPressed: () async {
              final a = assessment.asData?.value;
              if (a == null) return;
              final deleted = await confirmAndDeleteAssessment(
                context: context,
                ref: ref,
                assessmentId: assessmentId,
                title: a.title,
              );
              if (deleted && context.mounted) context.pop();
            },
            icon: Icon(Icons.delete_outline, color: AppColors.error),
          ),
        ],
      ),
      body: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          assessment.when(
            loading: () => const LinearProgressIndicator(),
            error: (e, _) => Padding(
              padding: EdgeInsets.all(AppSpace.s(16)),
              child: Text('$e'),
            ),
            data: (a) {
              if (a == null) return const SizedBox.shrink();
              return Padding(
                padding: EdgeInsets.fromLTRB(AppSpace.s(16), AppSpace.s(12), AppSpace.s(16), AppSpace.s(8)),
                child: Text(
                  '${a.statusLabel} · ${a.questionCount}문제 · ${a.maxScore}점 · ${a.periodLabel}',
                  style: TextStyle(color: AppColors.textSecondary),
                ),
              );
            },
          ),
          Padding(
            padding: EdgeInsets.fromLTRB(AppSpace.s(16), AppSpace.s(8), AppSpace.s(16), AppSpace.s(4)),
            child: Text(
              '응시 결과',
              style: TextStyle(fontWeight: FontWeight.w700, fontSize: 16),
            ),
          ),
          Expanded(
            child: submissions.when(
              loading: () => const Center(child: CircularProgressIndicator()),
              error: (e, _) => ErrorView(
                message: e.toString(),
                onRetry: () =>
                    ref.invalidate(assessmentSubmissionsProvider(assessmentId)),
              ),
              data: (list) {
                if (list.isEmpty) {
                  return const EmptyView(
                    message: '아직 제출이 없습니다.',
                    icon: Icons.assignment_outlined,
                  );
                }
                final sorted = [...list]
                  ..sort(
                    (a, b) => (b.submittedAt ?? DateTime(0)).compareTo(
                      a.submittedAt ?? DateTime(0),
                    ),
                  );
                return ListView.separated(
                  padding: EdgeInsets.fromLTRB(AppSpace.s(16), AppSpace.s(8), AppSpace.s(16), AppSpace.s(24)),
                  itemCount: sorted.length,
                  separatorBuilder: (_, __) => const Divider(height: 1),
                  itemBuilder: (context, i) {
                    final s = sorted[i];
                    return ListTile(
                      title: Text(s.userDisplayName),
                      subtitle: Text('${s.totalScore}점'),
                      trailing: const Icon(Icons.chevron_right),
                      onTap: () => context.push(
                        RoutePaths.instructorAssessmentSubmissionPath(
                          assessmentId,
                          s.id,
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
}
