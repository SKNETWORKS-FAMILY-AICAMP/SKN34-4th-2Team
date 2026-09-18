import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/routing/route_paths.dart';
import '../../../core/theme/app_layout.dart';
import '../../../core/widgets/loading_widgets.dart';
import '../../../shared/providers/lms_providers.dart';
import '../../assessments/presentation/widgets/assessment_card.dart';
import '../../instructor/presentation/instructor_assessments_screen.dart';
import '../../../core/theme/app_space.dart';

/// 관리자 — 성취도평가 결과 조회
class AdminAssessmentsScreen extends ConsumerWidget {
  const AdminAssessmentsScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final assessments = ref.watch(assessmentsProvider);

    return Scaffold(
      body: assessments.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => ErrorView(
          message: e.toString(),
          onRetry: () => ref.invalidate(assessmentsProvider),
        ),
        data: (list) {
          if (list.isEmpty) {
            return const EmptyView(
              message: '등록된 평가가 없습니다.',
              icon: Icons.quiz_outlined,
            );
          }
          return ListView.separated(
            padding: EdgeInsets.fromLTRB(AppSpace.s(16), AppSpace.s(12), AppSpace.s(16), AppSpace.s(24)),
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
                      RoutePaths.adminAssessmentDetailPath(a.id),
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
