import 'package:flutter/foundation.dart';
import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../../../core/routing/route_paths.dart';
import '../../../../core/theme/app_colors.dart';
import '../../../../shared/widgets/app_section_card.dart';
import '../../../study_room/data/curriculum_youtube_models.dart';
import '../../../study_room/providers/curriculum_youtube_providers.dart';
import '../../../../core/theme/app_space.dart';

/// 대시보드 — 이번 주 커리큘럼 기반 학습 추천 (LXP 1순위)
class WeeklyLearningRecommendSection extends ConsumerWidget {
  const WeeklyLearningRecommendSection({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final async = ref.watch(curriculumYoutubeRecommendationsProvider);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        AppSectionTitle(
          '이번 주 학습 추천',
          trailing: TextButton(
            onPressed: () => context.go(RoutePaths.studyRoom),
            style: TextButton.styleFrom(
              foregroundColor: AppColors.primary,
              visualDensity: VisualDensity.compact,
            ),
            child: const Text('학습실'),
          ),
        ),
        AppSectionCard(
          padding: EdgeInsets.fromLTRB(AppSpace.s(14), AppSpace.s(12), AppSpace.s(14), AppSpace.s(14)),
          child: async.when(
            loading: () => const SizedBox(
              height: 88,
              child: Center(
                child: SizedBox(
                  width: 22,
                  height: 22,
                  child: CircularProgressIndicator(strokeWidth: 2),
                ),
              ),
            ),
            error: (e, _) => _RecommendEmpty(
              message: '추천을 불러오지 못했습니다. 학습실에서 다시 확인해 보세요.',
              onOpenStudyRoom: () => context.go(RoutePaths.studyRoom),
            ),
            data: (data) {
              if (data.videos.isEmpty) {
                return _RecommendEmpty(
                  message: data.message ?? '이번 주 커리큘럼에 맞는 추천이 아직 없습니다.',
                  onOpenStudyRoom: () => context.go(RoutePaths.studyRoom),
                );
              }
              return _RecommendBody(data: data);
            },
          ),
        ),
      ],
    );
  }
}

class _RecommendBody extends StatefulWidget {
  const _RecommendBody({required this.data});

  final CurriculumYoutubeRecommendations data;

  @override
  State<_RecommendBody> createState() => _RecommendBodyState();
}

class _RecommendBodyState extends State<_RecommendBody> {
  final _hScroll = ScrollController();

  @override
  void dispose() {
    _hScroll.dispose();
    super.dispose();
  }

  void _scrollBy(double delta) {
    if (!_hScroll.hasClients) return;
    final target = (_hScroll.offset + delta).clamp(
      0.0,
      _hScroll.position.maxScrollExtent,
    );
    _hScroll.animateTo(
      target,
      duration: const Duration(milliseconds: 280),
      curve: Curves.easeOutCubic,
    );
  }

  @override
  Widget build(BuildContext context) {
    final data = widget.data;
    final videos = data.videos;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text(
          data.weekLabel != null
              ? '${data.weekLabel} · 지금 배울 주제 영상'
              : '커리큘럼 기준으로 골라둔 추천 영상입니다.',
          style: TextStyle(
            fontSize: 12,
            color: AppColors.textSecondary,
            height: 1.4,
          ),
        ),
        if (data.topics.isNotEmpty) ...[
          SizedBox(height: AppSpace.s(8)),
          Wrap(
            spacing: 6,
            runSpacing: 6,
            children: data.topics.take(5).map((t) {
              return Container(
                padding: EdgeInsets.symmetric(horizontal: AppSpace.s(8), vertical: AppSpace.s(3)),
                decoration: BoxDecoration(
                  color: AppColors.surfaceVariant,
                  borderRadius: BorderRadius.circular(999),
                ),
                child: Text(
                  t,
                  style: TextStyle(
                    fontSize: 11,
                    fontWeight: FontWeight.w600,
                    color: AppColors.textSecondary,
                  ),
                ),
              );
            }).toList(),
          ),
        ],
        SizedBox(height: AppSpace.s(8)),
        Row(
          children: [
            Text(
              '좌우로 밀어 더 보기',
              style: TextStyle(fontSize: 11, color: AppColors.textHint),
            ),
            const Spacer(),
            IconButton(
              tooltip: '이전',
              onPressed: () => _scrollBy(-200),
              visualDensity: VisualDensity.compact,
              icon: const Icon(Icons.chevron_left_rounded),
            ),
            IconButton(
              tooltip: '다음',
              onPressed: () => _scrollBy(200),
              visualDensity: VisualDensity.compact,
              icon: const Icon(Icons.chevron_right_rounded),
            ),
          ],
        ),
        SizedBox(height: AppSpace.s(4)),
        SizedBox(
          height: 160,
          child: ScrollConfiguration(
            behavior: ScrollConfiguration.of(context).copyWith(
              scrollbars: true,
              dragDevices: {
                PointerDeviceKind.touch,
                PointerDeviceKind.mouse,
                PointerDeviceKind.trackpad,
                PointerDeviceKind.stylus,
              },
            ),
            child: Scrollbar(
              controller: _hScroll,
              thumbVisibility: kIsWeb,
              trackVisibility: kIsWeb,
              notificationPredicate: (n) => n.depth == 0,
              child: ListView.separated(
                controller: _hScroll,
                scrollDirection: Axis.horizontal,
                physics: const BouncingScrollPhysics(
                  parent: AlwaysScrollableScrollPhysics(),
                ),
                padding: EdgeInsets.only(bottom: AppSpace.s(10), right: AppSpace.s(4)),
                itemCount: videos.length,
                separatorBuilder: (_, __) => SizedBox(width: AppSpace.s(10)),
                itemBuilder: (context, i) => _MiniVideoCard(video: videos[i]),
              ),
            ),
          ),
        ),
      ],
    );
  }
}

class _MiniVideoCard extends StatelessWidget {
  const _MiniVideoCard({required this.video});

  final CurriculumYoutubeVideo video;

  Future<void> _open() async {
    final uri = Uri.parse(video.youtubeUrl);
    await launchUrl(uri, mode: LaunchMode.externalApplication);
  }

  @override
  Widget build(BuildContext context) {
    return Material(
      color: AppColors.surfaceVariant,
      borderRadius: BorderRadius.circular(10),
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: _open,
        borderRadius: BorderRadius.circular(10),
        child: SizedBox(
          width: 176,
          height: 148,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              SizedBox(
                height: 99,
                child: video.thumbnailUrl.isEmpty
                    ? Container(
                        color: AppColors.tint(const Color(0xFFE5E7EB)),
                        alignment: Alignment.center,
                        child: const Icon(Icons.play_circle_outline),
                      )
                    : Image.network(
                        video.thumbnailUrl,
                        fit: BoxFit.cover,
                        width: double.infinity,
                        height: 99,
                        errorBuilder: (_, __, ___) => Container(
                          color: AppColors.tint(const Color(0xFFE5E7EB)),
                          alignment: Alignment.center,
                          child: const Icon(Icons.play_circle_outline),
                        ),
                      ),
              ),
              Expanded(
                child: Padding(
                  padding: EdgeInsets.fromLTRB(AppSpace.s(8), AppSpace.s(6), AppSpace.s(8), AppSpace.s(6)),
                  child: Align(
                    alignment: Alignment.topLeft,
                    child: Text(
                      video.title,
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(
                        fontSize: 12,
                        fontWeight: FontWeight.w600,
                        height: 1.25,
                        color: AppColors.textPrimary,
                      ),
                    ),
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _RecommendEmpty extends StatelessWidget {
  const _RecommendEmpty({
    required this.message,
    required this.onOpenStudyRoom,
  });

  final String message;
  final VoidCallback onOpenStudyRoom;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.symmetric(vertical: AppSpace.s(8)),
      child: Column(
        children: [
          Text(
            message,
            textAlign: TextAlign.center,
            style: TextStyle(
              fontSize: 13,
              color: AppColors.textSecondary,
              height: 1.4,
            ),
          ),
          SizedBox(height: AppSpace.s(10)),
          OutlinedButton(
            onPressed: onOpenStudyRoom,
            child: const Text('학습실 바로가기'),
          ),
        ],
      ),
    );
  }
}
