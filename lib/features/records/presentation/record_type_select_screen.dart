import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/constants/record_types.dart';
import '../../../core/routing/route_paths.dart';
import '../../../core/theme/app_colors.dart';
import '../../../shared/providers/cohort_providers.dart';
import '../../../shared/providers/lms_providers.dart';
import 'widgets/record_page_layout.dart';
import '../../../core/theme/app_space.dart';

/// Record type selection
class RecordTypeSelectScreen extends ConsumerWidget {
  const RecordTypeSelectScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final user = ref.watch(currentUserSyncProvider);
    final cohortName = ref.watch(effectiveCohortNameProvider);

    if (user == null) {
      return const Center(child: Text('로그인이 필요합니다'));
    }

    return RecordPageScaffold(
      user: user,
      cohortName: cohortName,
      body: SingleChildScrollView(
        padding: EdgeInsets.only(bottom: AppSpace.s(24)),
        child: RecordFormPanel(
          title: '새로운 기록 추가',
          child: Column(
            children: [
              _TypeCard(
                icon: Icons.menu_book_outlined,
                title: RecordTypes.labels[RecordTypes.studyCert]!,
                description: RecordTypes.descriptions[RecordTypes.studyCert]!,
                onTap: () => context.push(RoutePaths.recordsCreateStudyCert),
              ),
              SizedBox(height: AppSpace.s(12)),
              _TypeCard(
                icon: Icons.quiz_outlined,
                title: RecordTypes.labels[RecordTypes.precourseQuiz]!,
                description:
                    RecordTypes.descriptions[RecordTypes.precourseQuiz]!,
                onTap: () =>
                    context.push(RoutePaths.recordsCreatePrecourseQuiz),
              ),
              SizedBox(height: AppSpace.s(12)),
              _TypeCard(
                icon: Icons.workspace_premium_outlined,
                title: RecordTypes.labels[RecordTypes.certification]!,
                description:
                    RecordTypes.descriptions[RecordTypes.certification]!,
                onTap: () => context.push(RoutePaths.recordsCreateCert),
              ),
              SizedBox(height: AppSpace.s(12)),
              _TypeCard(
                icon: Icons.groups_outlined,
                title: RecordTypes.labels[RecordTypes.study]!,
                description: RecordTypes.descriptions[RecordTypes.study]!,
                onTap: () => context.push(RoutePaths.recordsCreateStudy),
              ),
              SizedBox(height: AppSpace.s(12)),
              _TypeCard(
                icon: Icons.article_outlined,
                title: RecordTypes.labels[RecordTypes.blog]!,
                description: RecordTypes.descriptions[RecordTypes.blog]!,
                onTap: () => context.push(RoutePaths.recordsCreateBlog),
              ),
            ],
          ),
          actions: RecordFormActions(
            onBack: () => context.pop(),
          ),
        ),
      ),
    );
  }
}

class _TypeCard extends StatelessWidget {
  const _TypeCard({
    required this.icon,
    required this.title,
    required this.description,
    required this.onTap,
  });

  final IconData icon;
  final String title;
  final String description;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: AppColors.surface,
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
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Container(
                padding: EdgeInsets.all(AppSpace.s(10)),
                decoration: BoxDecoration(
                  color: AppColors.primaryLight,
                  borderRadius: BorderRadius.circular(10),
                ),
                child: Icon(icon, color: AppColors.primary, size: 22),
              ),
              SizedBox(width: AppSpace.s(14)),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      title,
                      style: const TextStyle(
                        fontSize: 15,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                    SizedBox(height: AppSpace.s(6)),
                    Text(
                      description,
                      style: TextStyle(
                        fontSize: 13,
                        color: AppColors.textSecondary,
                        height: 1.4,
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
