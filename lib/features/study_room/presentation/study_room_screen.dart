import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'package:go_router/go_router.dart';

import '../../../core/routing/route_paths.dart';
import '../../../core/theme/app_colors.dart';
import '../../../core/widgets/loading_widgets.dart';
import '../../../shared/providers/lms_providers.dart';
import '../../auth/providers/auth_providers.dart';
import '../providers/curriculum_youtube_providers.dart';
import 'widgets/inflearn_package_card.dart';
import 'widgets/study_room_layout.dart';
import 'widgets/youtube_recommendation_section.dart';
import '../../../core/theme/app_space.dart';

/// 학습실 — 배정된 인프런 강의 패키지 (학생)
class StudyRoomScreen extends ConsumerStatefulWidget {
  const StudyRoomScreen({super.key});

  @override
  ConsumerState<StudyRoomScreen> createState() => _StudyRoomScreenState();
}

class _StudyRoomScreenState extends ConsumerState<StudyRoomScreen> {
  final _searchController = TextEditingController();
  String _query = '';

  @override
  void dispose() {
    _searchController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final userAsync = ref.watch(currentUserProvider);
    final cohortName = ref.watch(effectiveCohortNameProvider);
    final packages = ref.watch(publishedInflearnPackagesProvider);

    return userAsync.when(
      loading: () => const Center(child: CircularProgressIndicator()),
      error: (e, _) => ErrorView(message: e.toString()),
      data: (user) {
        if (user == null) return const SizedBox.shrink();

        return RefreshIndicator(
          onRefresh: () async {
            ref.invalidate(publishedInflearnPackagesProvider);
            ref.invalidate(publishedYoutubeRecommendationsProvider);
            ref.invalidate(curriculumYoutubeRecommendationsProvider);
          },
          child: SingleChildScrollView(
            physics: const AlwaysScrollableScrollPhysics(),
            child: studyRoomContentWrapper(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  StudyRoomPageHeader(
                    user: user,
                    cohortName: cohortName,
                    subtitle: '배정된 인프런 강의와 이번 주 커리큘럼 YouTube 추천을 확인하세요.',
                  ),
                  SizedBox(height: AppSpace.s(20)),
                  const _StudyRoomEntryCard(),
                  SizedBox(height: AppSpace.s(20)),
                  const YoutubeRecommendationSection(),
                  SizedBox(height: AppSpace.s(28)),
                  Text(
                    '배정된 인프런 강의',
                    style: TextStyle(
                      fontSize: 16,
                      fontWeight: FontWeight.w700,
                      color: AppColors.textPrimary,
                    ),
                  ),
                  SizedBox(height: AppSpace.s(12)),
                  StudyRoomSearchBar(
                    controller: _searchController,
                    hintText: '교과목·강의명 검색',
                    onChanged: (v) => setState(() => _query = v.trim()),
                  ),
                  SizedBox(height: AppSpace.s(16)),
                  packages.when(
                    loading: () => Padding(
                      padding: EdgeInsets.all(AppSpace.s(40)),
                      child: Center(child: CircularProgressIndicator()),
                    ),
                    error: (e, _) => ErrorView(message: e.toString()),
                    data: (list) {
                      final filtered = list.where((p) {
                        if (_query.isEmpty) return true;
                        final q = _query.toLowerCase();
                        if (p.title.toLowerCase().contains(q)) return true;
                        if (p.subject.toLowerCase().contains(q)) return true;
                        if (p.summary?.toLowerCase().contains(q) ?? false) {
                          return true;
                        }
                        for (final unit in p.units) {
                          if (unit.name.toLowerCase().contains(q)) return true;
                          for (final c in unit.courses) {
                            if (c.title.toLowerCase().contains(q)) return true;
                          }
                        }
                        for (final c in p.courses) {
                          if (c.title.toLowerCase().contains(q)) return true;
                        }
                        return false;
                      }).toList();

                      if (filtered.isEmpty) {
                        return Padding(
                          padding: EdgeInsets.symmetric(vertical: AppSpace.s(48)),
                          child: Center(
                            child: Column(
                              children: [
                                Icon(
                                  Icons.menu_book_outlined,
                                  size: 48,
                                  color: AppColors.textHint,
                                ),
                                SizedBox(height: AppSpace.s(12)),
                                Text(
                                  '배정된 인프런 강의가 없습니다',
                                  style: TextStyle(
                                    color: AppColors.textSecondary,
                                  ),
                                ),
                                SizedBox(height: AppSpace.s(6)),
                                Text(
                                  '강의 배정 후 이곳에 표시됩니다.',
                                  style: TextStyle(
                                    fontSize: 12,
                                    color: AppColors.textHint,
                                  ),
                                ),
                              ],
                            ),
                          ),
                        );
                      }

                      return Column(
                        children: [
                          for (final p in filtered) ...[
                            InflearnPackageCard(package: p),
                            SizedBox(height: AppSpace.s(16)),
                          ],
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

class _StudyRoomEntryCard extends StatelessWidget {
  const _StudyRoomEntryCard();

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: EdgeInsets.all(AppSpace.s(16)),
      decoration: BoxDecoration(
        color: AppColors.primaryLight,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: AppColors.primary.withValues(alpha: 0.2)),
      ),
      child: Row(
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  '공부방',
                  style: TextStyle(
                    fontSize: 16,
                    fontWeight: FontWeight.w800,
                    color: AppColors.textPrimary,
                  ),
                ),
                SizedBox(height: AppSpace.s(4)),
                Text(
                  '수업 저장소에서 날짜·폴더·파일을 골라 복습 노트를 만듭니다.',
                  style: TextStyle(
                    fontSize: 13,
                    color: AppColors.textSecondary,
                  ),
                ),
              ],
            ),
          ),
          SizedBox(width: AppSpace.s(12)),
          FilledButton(
            onPressed: () => context.go(RoutePaths.studyRoomNotes),
            child: const Text('공부방 열기'),
          ),
        ],
      ),
    );
  }
}
