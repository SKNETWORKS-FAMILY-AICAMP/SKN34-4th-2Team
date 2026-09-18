import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/routing/route_paths.dart';
import '../../../core/theme/app_layout.dart';
import '../../../core/theme/app_theme.dart';
import '../../../shared/providers/cohort_providers.dart';
import '../../../shared/providers/lms_providers.dart';
import '../../assessments/presentation/widgets/assessment_card.dart';
import '../../../core/widgets/loading_widgets.dart';
import '../../onboarding/domain/onboarding_target_registry.dart';
import '../../onboarding/instructor/instructor_onboarding_keys.dart';
import '../../../core/theme/app_space.dart';

Future<bool> confirmAndDeleteAssessment({
  required BuildContext context,
  required WidgetRef ref,
  required String assessmentId,
  required String title,
}) async {
  final ok = await showDialog<bool>(
    context: context,
    builder: (ctx) => AlertDialog(
      title: const Text('평가 삭제'),
      content: Text(
        '"$title" 평가와 문항을 삭제합니다.\n이 작업은 되돌릴 수 없습니다.',
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.pop(ctx, false),
          child: const Text('취소'),
        ),
        FilledButton(
          onPressed: () => Navigator.pop(ctx, true),
          style: AppTheme.destructiveFilled,
          child: const Text('삭제'),
        ),
      ],
    ),
  );
  if (ok != true || !context.mounted) return false;

  final cohortId = ref.read(effectiveCohortIdProvider);
  if (cohortId == null) {
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(content: Text('기수 정보가 없습니다.')),
    );
    return false;
  }

  try {
    await ref.read(lmsRepositoryProvider).deleteAssessment(
          cohortId: cohortId,
          assessmentId: assessmentId,
        );
    if (!context.mounted) return true;
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(content: Text('평가를 삭제했습니다.')),
    );
    return true;
  } catch (e) {
    if (!context.mounted) return false;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text('삭제 실패: $e')),
    );
    return false;
  }
}

Future<bool> confirmAndPublishAssessment({
  required BuildContext context,
  required WidgetRef ref,
  required String assessmentId,
  required String title,
}) async {
  final ok = await showDialog<bool>(
    context: context,
    builder: (ctx) => AlertDialog(
      title: const Text('평가 발행'),
      content: Text(
        '"$title" 평가를 학생에게 공개합니다.\n응시 기간이 맞는지 확인하세요.',
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.pop(ctx, false),
          child: const Text('취소'),
        ),
        FilledButton(
          onPressed: () => Navigator.pop(ctx, true),
          child: const Text('발행'),
        ),
      ],
    ),
  );
  if (ok != true || !context.mounted) return false;

  final cohortId = ref.read(effectiveCohortIdProvider);
  if (cohortId == null) {
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(content: Text('기수 정보가 없습니다.')),
    );
    return false;
  }

  try {
    await ref.read(lmsRepositoryProvider).publishAssessment(
          cohortId: cohortId,
          assessmentId: assessmentId,
        );
    if (!context.mounted) return true;
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(content: Text('평가를 발행했습니다.')),
    );
    return true;
  } catch (e) {
    if (!context.mounted) return false;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text('발행 실패: $e')),
    );
    return false;
  }
}

/// 강사 — 평가 목록
class InstructorAssessmentsScreen extends ConsumerWidget {
  const InstructorAssessmentsScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final assessments = ref.watch(assessmentsProvider);

    return Scaffold(
      floatingActionButton: KeyedSubtree(
        key: OnboardingTargetRegistry.keyOf(
          InstructorOnboardingTargets.assessmentsCreate,
        ),
        child: FloatingActionButton.extended(
          onPressed: () =>
              context.push(RoutePaths.instructorAssessmentsCreate),
          icon: const Icon(Icons.add),
          label: const Text('평가 만들기'),
        ),
      ),
      body: assessments.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => ErrorView(
          message: e.toString(),
          onRetry: () => ref.invalidate(assessmentsProvider),
        ),
        data: (list) {
          if (list.isEmpty) {
            return EmptyView(
              message: '아직 만든 평가가 없습니다.',
              icon: Icons.quiz_outlined,
              actionLabel: '평가 만들기',
              onAction: () =>
                  context.push(RoutePaths.instructorAssessmentsCreate),
            );
          }
          return ListView.separated(
            padding: EdgeInsets.fromLTRB(AppSpace.s(16), AppSpace.s(12), AppSpace.s(16), AppSpace.s(88)),
            itemCount: list.length,
            separatorBuilder: (_, __) => SizedBox(height: AppSpace.s(8)),
            itemBuilder: (context, i) {
              final a = list[i];
              return Center(
                child: ConstrainedBox(
                  constraints: AppLayout.listConstraints(),
                  child: AssessmentCard(
                    assessment: a,
                    onTap: () => context.push(
                      RoutePaths.instructorAssessmentDetailPath(a.id),
                    ),
                    onEdit: () => context.push(
                      RoutePaths.instructorAssessmentEditPath(a.id),
                    ),
                    onPublish: a.published
                        ? null
                        : () => confirmAndPublishAssessment(
                              context: context,
                              ref: ref,
                              assessmentId: a.id,
                              title: a.title,
                            ),
                    onDelete: () => confirmAndDeleteAssessment(
                      context: context,
                      ref: ref,
                      assessmentId: a.id,
                      title: a.title,
                    ),
                  ),
                ),
              );
            },
          );
        },
      ),
    );
  }
}
