import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/routing/route_paths.dart';
import '../../../core/theme/app_colors.dart';
import '../../../core/widgets/loading_widgets.dart';
import '../../../shared/models/notice_model.dart';
import '../../../shared/providers/cohort_providers.dart';
import '../../../shared/providers/lms_providers.dart';
import '../../hub/presentation/widgets/board_ui.dart';
import '../../hub/presentation/widgets/notice_list_widgets.dart';
import '../../onboarding/domain/onboarding_target_registry.dart';
import '../../onboarding/instructor/instructor_onboarding_keys.dart';
import '../../../core/theme/app_space.dart';

/// 강사 — 게시물 작성 (공지 등록·본인 글 수정)
class InstructorBoardScreen extends ConsumerWidget {
  const InstructorBoardScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final notices = ref.watch(noticesStreamProvider);
    final uid = ref.watch(currentUserSyncProvider)?.uid;
    final cohortName = ref.watch(effectiveCohortNameProvider);

    return ColoredBox(
      color: BoardUi.listBackground,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          BoardPageHeader(
            title: '게시판 관리',
            subtitle:
                '${cohortName ?? '담당 기수'} · 본인이 등록한 글만 수정할 수 있습니다.',
            action: KeyedSubtree(
              key: OnboardingTargetRegistry.keyOf(
                InstructorOnboardingTargets.boardCreate,
              ),
              child: FilledButton.icon(
                onPressed: () =>
                    context.push(RoutePaths.instructorBoardCreate),
                style: BoardUi.primaryButtonStyle(),
                icon: const Icon(Icons.add, size: 18),
                label: const Text('공지 작성'),
              ),
            ),
          ),
          Expanded(
            child: Align(
              alignment: Alignment.topCenter,
              child: ConstrainedBox(
                constraints:
                    const BoxConstraints(maxWidth: BoardUi.contentMaxWidth),
                child: RefreshIndicator(
                  onRefresh: () async =>
                      ref.invalidate(noticesStreamProvider),
                  child: notices.when(
                    loading: () =>
                        const Center(child: CircularProgressIndicator()),
                    error: (e, _) => ErrorView(
                      message: e.toString(),
                      onRetry: () => ref.invalidate(noticesStreamProvider),
                    ),
                    data: (list) {
                      if (list.isEmpty) {
                        return ListView(
                          physics: const AlwaysScrollableScrollPhysics(),
                          children: [
                            SizedBox(height: AppSpace.s(48)),
                            EmptyView(
                              message: '등록된 공지가 없습니다.',
                              icon: Icons.campaign_outlined,
                            ),
                          ],
                        );
                      }

                      final favorites =
                          list.where((n) => n.isFavorite).toList();
                      final regular =
                          list.where((n) => !n.isFavorite).toList();

                      Widget? editTrailing(NoticeModel notice) {
                        if (uid == null || notice.authorId != uid) {
                          return null;
                        }
                        return IconButton(
                          tooltip: '수정',
                          visualDensity: VisualDensity.compact,
                          padding: EdgeInsets.zero,
                          constraints: const BoxConstraints(
                            minWidth: 28,
                            minHeight: 28,
                          ),
                          icon: Icon(
                            Icons.edit_outlined,
                            size: 16,
                            color: AppColors.textHint,
                          ),
                          onPressed: () => context.push(
                            RoutePaths.instructorBoardNoticeEditPath(
                              notice.id,
                            ),
                          ),
                        );
                      }

                      return ListView(
                        physics: const AlwaysScrollableScrollPhysics(),
                        padding: EdgeInsets.fromLTRB(AppSpace.s(20), AppSpace.s(16), AppSpace.s(20), AppSpace.s(28)),
                        children: [
                          if (favorites.isNotEmpty) ...[
                            const _SectionHeader(
                              icon: Icons.star_rounded,
                              iconColor: BoardUi.favorite,
                              title: '중요 공지',
                            ),
                            SizedBox(height: AppSpace.s(8)),
                            StudentNoticeRowList(
                              notices: favorites,
                              onTap: (notice) =>
                                  NoticeDetailSheet.show(context, notice),
                              trailingBuilder: editTrailing,
                            ),
                            SizedBox(height: AppSpace.s(20)),
                          ],
                          if (regular.isNotEmpty) ...[
                            const _SectionHeader(
                              icon: Icons.campaign_outlined,
                              title: '전체 공지',
                            ),
                            SizedBox(height: AppSpace.s(8)),
                            StudentNoticeRowList(
                              notices: regular,
                              onTap: (notice) =>
                                  NoticeDetailSheet.show(context, notice),
                              trailingBuilder: editTrailing,
                            ),
                          ],
                        ],
                      );
                    },
                  ),
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _SectionHeader extends StatelessWidget {
  const _SectionHeader({
    required this.icon,
    required this.title,
    this.iconColor,
  });

  final IconData icon;
  final String title;
  final Color? iconColor;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Icon(icon, size: 16, color: iconColor ?? AppColors.textSecondary),
        SizedBox(width: AppSpace.s(6)),
        Text(
          title,
          style: TextStyle(
            fontWeight: FontWeight.w600,
            fontSize: 14,
            color: AppColors.textPrimary,
          ),
        ),
      ],
    );
  }
}
