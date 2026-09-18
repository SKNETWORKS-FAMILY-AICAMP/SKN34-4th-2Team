import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/routing/route_paths.dart';
import '../../../core/widgets/loading_widgets.dart';
import '../../../shared/providers/lms_providers.dart';
import '../../../core/theme/app_space.dart';

/// 관리자 — 평가별 학생 점수 목록 (조회만)
class AdminAssessmentDetailScreen extends ConsumerWidget {
  const AdminAssessmentDetailScreen({
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
          data: (a) => Text(a?.title ?? '평가 결과'),
          loading: () => const Text('평가 결과'),
          error: (_, __) => const Text('평가 결과'),
        ),
      ),
      body: submissions.when(
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
            ..sort((a, b) => a.userDisplayName.compareTo(b.userDisplayName));
          return ListView.separated(
            padding: EdgeInsets.all(AppSpace.s(16)),
            itemCount: sorted.length,
            separatorBuilder: (_, __) => const Divider(height: 1),
            itemBuilder: (context, i) {
              final s = sorted[i];
              return ListTile(
                title: Text(s.userDisplayName),
                subtitle: Text('${s.totalScore}점'),
                trailing: const Icon(Icons.chevron_right),
                onTap: () => context.push(
                  RoutePaths.adminAssessmentSubmissionPath(
                    assessmentId,
                    s.id,
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
