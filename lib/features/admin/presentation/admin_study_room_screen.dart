import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/routing/route_paths.dart';
import '../../../core/theme/app_colors.dart';
import '../../../core/widgets/loading_widgets.dart';
import '../../../shared/providers/cohort_providers.dart';
import '../../../shared/providers/lms_providers.dart';
import '../../auth/providers/auth_providers.dart';
import '../../study_room/presentation/widgets/inflearn_package_card.dart';
import '../../study_room/presentation/widgets/study_room_layout.dart';
import 'widgets/admin_study_source_panel.dart';
import 'widgets/admin_youtube_recommendation_panel.dart';
import '../../../core/theme/app_space.dart';

/// 관리자 학습실 — 인프런 강의 패키지 관리
class AdminStudyRoomScreen extends ConsumerStatefulWidget {
  const AdminStudyRoomScreen({super.key});

  @override
  ConsumerState<AdminStudyRoomScreen> createState() =>
      _AdminStudyRoomScreenState();
}

class _AdminStudyRoomScreenState extends ConsumerState<AdminStudyRoomScreen> {
  final _searchController = TextEditingController();
  String _query = '';

  @override
  void dispose() {
    _searchController.dispose();
    super.dispose();
  }

  Future<void> _confirmDelete(String packageId, String title) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('패키지 삭제'),
        content: Text('「$title」 패키지를 삭제할까요?'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('취소'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(ctx, true),
            style: FilledButton.styleFrom(backgroundColor: AppColors.error),
            child: const Text('삭제'),
          ),
        ],
      ),
    );
    if (ok != true || !mounted) return;

    final cohortId = ref.read(effectiveCohortIdProvider);
    if (cohortId == null) return;

    try {
      await ref.read(lmsRepositoryProvider).deleteInflearnPackage(
            cohortId: cohortId,
            packageId: packageId,
          );
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('패키지가 삭제되었습니다.')),
        );
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('삭제 실패: $e')),
        );
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final userAsync = ref.watch(currentUserProvider);
    final cohortName = ref.watch(effectiveCohortNameProvider);
    final packages = ref.watch(inflearnPackagesProvider);

    return userAsync.when(
      loading: () => const Center(child: CircularProgressIndicator()),
      error: (e, _) => ErrorView(message: e.toString()),
      data: (user) {
        if (user == null) return const SizedBox.shrink();

        return RefreshIndicator(
          onRefresh: () async {
            ref.invalidate(inflearnPackagesProvider);
            ref.invalidate(youtubeRecommendationsProvider);
            ref.invalidate(studySourcesProvider);
          },
          child: SingleChildScrollView(
            physics: const AlwaysScrollableScrollPhysics(),
            child: studyRoomContentWrapper(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Expanded(
                        child: StudyRoomPageHeader(
                          user: user,
                          cohortName: cohortName,
                          subtitle: '인프런 강의 패키지를 등록하고 기수에 공개하세요.',
                          showProfile: false,
                        ),
                      ),
                      SizedBox(width: AppSpace.s(12)),
                      FilledButton.icon(
                        onPressed: () =>
                            context.push(RoutePaths.adminStudyRoomCreate),
                        icon: const Icon(Icons.add, size: 18),
                        label: const Text('패키지 등록'                        ),
                      ),
                    ],
                  ),
                  SizedBox(height: AppSpace.s(24)),
                  const AdminYoutubeRecommendationPanel(),
                  SizedBox(height: AppSpace.s(28)),
                  const AdminStudySourcePanel(),
                  SizedBox(height: AppSpace.s(28)),
                  const Text(
                    '인프런 패키지',
                    style: TextStyle(
                      fontSize: 16,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                  SizedBox(height: AppSpace.s(12)),
                  StudyRoomSearchBar(
                    controller: _searchController,
                    hintText: '패키지·교과목 검색',
                    onChanged: (v) => setState(() => _query = v.trim()),
                  ),
                  SizedBox(height: AppSpace.s(20)),
                  packages.when(
                    loading: () => Padding(
                      padding: EdgeInsets.all(AppSpace.s(40)),
                      child: Center(child: CircularProgressIndicator()),
                    ),
                    error: (e, _) => ErrorView(message: e.toString()),
                    data: (list) {
                      final filtered = list
                          .where(
                            (p) =>
                                _query.isEmpty ||
                                p.title
                                    .toLowerCase()
                                    .contains(_query.toLowerCase()) ||
                                p.subject
                                    .toLowerCase()
                                    .contains(_query.toLowerCase()),
                          )
                          .toList();

                      if (filtered.isEmpty) {
                        return Padding(
                          padding: EdgeInsets.symmetric(vertical: AppSpace.s(48)),
                          child: Column(
                            children: [
                              Text(
                                '등록된 패키지가 없습니다',
                                style: TextStyle(
                                  color: AppColors.textSecondary,
                                ),
                              ),
                              SizedBox(height: AppSpace.s(12)),
                              OutlinedButton.icon(
                                onPressed: () => context
                                    .push(RoutePaths.adminStudyRoomCreate),
                                icon: const Icon(Icons.add),
                                label: const Text('첫 패키지 만들기'),
                              ),
                            ],
                          ),
                        );
                      }

                      return Column(
                        children: [
                          for (final p in filtered)
                            InflearnPackageListTile(
                              package: p,
                              onTap: () => context.push(
                                RoutePaths.adminStudyRoomPackagePath(p.id),
                              ),
                              onDelete: () => _confirmDelete(p.id, p.title),
                            ),
                        ],
                      );
                    },
                  ),
                ],
              ),
            ),
          ),
        );
      },
    );
  }
}
