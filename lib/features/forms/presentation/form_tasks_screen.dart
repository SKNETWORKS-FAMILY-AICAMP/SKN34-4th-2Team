import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/routing/route_paths.dart';
import '../../../core/theme/app_colors.dart';
import '../../../core/widgets/loading_widgets.dart';
import '../../../shared/providers/lms_providers.dart';
import 'widgets/form_task_card.dart';
import '../../../core/theme/app_space.dart';

/// 학생 — 설문·제출 전체 목록
class FormTasksScreen extends ConsumerWidget {
  const FormTasksScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final tasks = ref.watch(formTasksWithStatusProvider);

    return RefreshIndicator(
      onRefresh: () async => ref.invalidate(formTasksWithStatusProvider),
      child: tasks.when(
        loading: () => ListView(
          physics: const AlwaysScrollableScrollPhysics(),
          children: [
            SizedBox(height: AppSpace.s(120)),
            Center(child: CircularProgressIndicator()),
          ],
        ),
        error: (e, _) => ListView(
          physics: const AlwaysScrollableScrollPhysics(),
          children: [ErrorView(message: e.toString())],
        ),
        data: (list) {
          if (list.isEmpty) {
            return ListView(
              physics: const AlwaysScrollableScrollPhysics(),
              children: [
                SizedBox(height: AppSpace.s(120)),
                Center(
                  child: Text(
                    '등록된 설문·제출 과제가 없습니다.',
                    style: TextStyle(color: AppColors.textSecondary),
                  ),
                ),
              ],
            );
          }

          final pending = list.where((t) => !t.isCompleted).toList();
          final done = list.where((t) => t.isCompleted).toList();

          return ListView(
            physics: const AlwaysScrollableScrollPhysics(),
            padding: EdgeInsets.all(AppSpace.s(16)),
            children: [
              Center(
                child: ConstrainedBox(
                  constraints: const BoxConstraints(maxWidth: 520),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      if (pending.isNotEmpty) ...[
                        const _SectionLabel('해야 할 설문'),
                        ...pending.map((item) => FormTaskCard(item: item)),
                        SizedBox(height: AppSpace.s(16)),
                      ],
                      if (done.isNotEmpty) ...[
                        const _SectionLabel('제출 완료'),
                        ...done.map((item) => FormTaskCard(item: item)),
                      ],
                    ],
                  ),
                ),
              ),
            ],
          );
        },
      ),
    );
  }
}

class FormTasksDashboardSection extends ConsumerWidget {
  const FormTasksDashboardSection({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final tasks = ref.watch(formTasksWithStatusProvider);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            const Expanded(
              child: Text(
                '설문 · 제출',
                style: TextStyle(fontWeight: FontWeight.bold, fontSize: 16),
              ),
            ),
            TextButton(
              onPressed: () => context.go(RoutePaths.forms),
              child: const Text('전체 보기'),
            ),
          ],
        ),
        SizedBox(height: AppSpace.s(8)),
        tasks.when(
          loading: () => Card(
            child: Padding(
              padding: EdgeInsets.all(AppSpace.s(24)),
              child: Center(child: CircularProgressIndicator(strokeWidth: 2)),
            ),
          ),
          error: (e, _) => Text('오류: $e'),
          data: (list) {
            if (list.isEmpty) {
              return Card(
                child: Padding(
                  padding: EdgeInsets.all(AppSpace.s(20)),
                  child: Center(
                    child: Text(
                      '등록된 설문이 없습니다',
                      style: TextStyle(color: AppColors.textSecondary),
                    ),
                  ),
                ),
              );
            }

            final show = list.take(3).toList();
            final pendingCount = list.where((t) => !t.isCompleted).length;

            return Column(
              children: [
                if (pendingCount > 0)
                  Padding(
                    padding: EdgeInsets.only(bottom: AppSpace.s(8)),
                    child: Align(
                      alignment: Alignment.centerLeft,
                      child: Container(
                        padding: EdgeInsets.symmetric(
                          horizontal: AppSpace.s(10),
                          vertical: AppSpace.s(4),
                        ),
                        decoration: BoxDecoration(
                          color: AppColors.badgeLate.withValues(alpha: 0.15),
                          borderRadius: BorderRadius.circular(20),
                        ),
                        child: Text(
                          '미제출 $pendingCount건',
                          style: TextStyle(
                            fontSize: 11,
                            fontWeight: FontWeight.w700,
                            color: AppColors.badgeLate,
                          ),
                        ),
                      ),
                    ),
                  ),
                ...show.map((item) => FormTaskCard(item: item, compact: true)),
              ],
            );
          },
        ),
      ],
    );
  }
}

class _SectionLabel extends StatelessWidget {
  const _SectionLabel(this.text);
  final String text;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.only(bottom: AppSpace.s(8)),
      child: Text(
        text,
        style: TextStyle(
          fontWeight: FontWeight.w600,
          fontSize: 13,
          color: AppColors.textSecondary,
        ),
      ),
    );
  }
}
