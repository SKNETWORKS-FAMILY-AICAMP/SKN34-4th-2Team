import 'package:flutter/foundation.dart';
import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../../../core/theme/app_colors.dart';
import '../../../../shared/providers/cohort_providers.dart';
import '../../../../shared/providers/lms_providers.dart';
import '../../../../shared/widgets/status_badge.dart';
import '../../../auth/providers/auth_providers.dart';
import '../../data/curriculum_youtube_models.dart';
import '../../providers/curriculum_youtube_providers.dart';
import '../../../../core/theme/app_space.dart';

/// 학습실 — 이번 주 커리큘럼 기반 YouTube 추천
class YoutubeRecommendationSection extends ConsumerStatefulWidget {
  const YoutubeRecommendationSection({super.key});

  @override
  ConsumerState<YoutubeRecommendationSection> createState() =>
      _YoutubeRecommendationSectionState();
}

class _YoutubeRecommendationSectionState
    extends ConsumerState<YoutubeRecommendationSection> {
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
    final async = ref.watch(curriculumYoutubeRecommendationsProvider);
    final sheetAsync = ref.watch(latestCurriculumSheetProvider);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Row(
          children: [
            Expanded(
              child: Text(
                '이번 주 커리큘럼 추천',
                style: TextStyle(
                  fontSize: 16,
                  fontWeight: FontWeight.w700,
                  color: AppColors.textPrimary,
                ),
              ),
            ),
            IconButton(
              tooltip: '새로고침',
              onPressed: () =>
                  ref.invalidate(curriculumYoutubeRecommendationsProvider),
              icon: const Icon(Icons.refresh_rounded, size: 20),
            ),
          ],
        ),
        SizedBox(height: AppSpace.s(4)),
        Text(
          sheetAsync.maybeWhen(
            data: (sheet) => sheet == null
                ? '커리큘럼 일정에 맞는 YouTube 강의가 표시됩니다.'
                : '「${sheet.title}」 기준으로 이번 주 주제 영상을 추천합니다.',
            orElse: () => '커리큘럼 일정에 맞는 YouTube 강의가 표시됩니다.',
          ),
          style: TextStyle(fontSize: 12, color: AppColors.textSecondary),
        ),
        SizedBox(height: AppSpace.s(12)),
        async.when(
          loading: () => Padding(
            padding: EdgeInsets.symmetric(vertical: AppSpace.s(32)),
            child: Center(child: CircularProgressIndicator(strokeWidth: 2)),
          ),
          error: (e, _) => _ErrorCard(
            message: _friendlyError(e),
            onRetry: () =>
                ref.invalidate(curriculumYoutubeRecommendationsProvider),
          ),
          data: (data) {
            if (data.videos.isEmpty) {
              return _EmptyCard(
                message: data.message ?? '이번 주 커리큘럼에 해당하는 추천 영상이 없습니다.',
              );
            }
            return Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                if (data.weekLabel != null || data.topics.isNotEmpty) ...[
                  Wrap(
                    spacing: 6,
                    runSpacing: 6,
                    children: [
                      if (data.weekLabel != null)
                        StatusBadge(
                          label: data.weekLabel!,
                          color: AppColors.primary,
                        ),
                      StatusBadge(
                        label: '${data.videos.length}개 추천',
                        color: AppColors.badgeOpen,
                      ),
                      ...data.topics
                          .take(8)
                          .map(
                            (t) => StatusBadge(
                              label: t,
                              color: AppColors.badgeClosed,
                            ),
                          ),
                    ],
                  ),
                  SizedBox(height: AppSpace.s(8)),
                ],
                Row(
                  children: [
                    Text(
                      '좌우로 밀어 더 보기',
                      style: TextStyle(
                        fontSize: 11,
                        color: AppColors.textHint,
                      ),
                    ),
                    const Spacer(),
                    IconButton(
                      tooltip: '이전',
                      onPressed: () => _scrollBy(-280),
                      visualDensity: VisualDensity.compact,
                      icon: const Icon(Icons.chevron_left_rounded),
                    ),
                    IconButton(
                      tooltip: '다음',
                      onPressed: () => _scrollBy(280),
                      visualDensity: VisualDensity.compact,
                      icon: const Icon(Icons.chevron_right_rounded),
                    ),
                  ],
                ),
                SizedBox(height: AppSpace.s(4)),
                SizedBox(
                  height: 268,
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
                      child: ListView.separated(
                        controller: _hScroll,
                        scrollDirection: Axis.horizontal,
                        physics: const BouncingScrollPhysics(
                          parent: AlwaysScrollableScrollPhysics(),
                        ),
                        padding: EdgeInsets.only(bottom: AppSpace.s(8), right: AppSpace.s(4)),
                        itemCount: data.videos.length,
                        separatorBuilder: (_, _) => SizedBox(width: AppSpace.s(12)),
                        itemBuilder: (context, i) {
                          return _CurriculumYoutubeCard(
                            video: data.videos[i],
                          );
                        },
                      ),
                    ),
                  ),
                ),
              ],
            );
          },
        ),
      ],
    );
  }

  String _friendlyError(Object e) {
    final raw = e.toString();
    if (raw.contains('YOUTUBE_API_KEY') ||
        raw.contains('failed-precondition')) {
      return 'YouTube API 키가 설정되지 않았습니다. 관리자에게 문의하세요.';
    }
    if (raw.contains('permission-denied')) {
      return '추천을 불러올 권한이 없습니다.';
    }
    if (raw.contains('unavailable') || raw.contains('UNAVAILABLE')) {
      return 'YouTube 추천 서버에 일시적으로 연결할 수 없습니다.';
    }
    return '추천을 불러오지 못했습니다.';
  }
}

class _EmptyCard extends StatelessWidget {
  const _EmptyCard({required this.message});

  final String message;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: EdgeInsets.symmetric(vertical: AppSpace.s(28), horizontal: AppSpace.s(16)),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: AppColors.border),
      ),
      child: Text(
        message,
        textAlign: TextAlign.center,
        style: TextStyle(color: AppColors.textSecondary),
      ),
    );
  }
}

class _ErrorCard extends StatelessWidget {
  const _ErrorCard({required this.message, required this.onRetry});

  final String message;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: EdgeInsets.all(AppSpace.s(20)),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: AppColors.border),
      ),
      child: Column(
        children: [
          Text(
            message,
            textAlign: TextAlign.center,
            style: TextStyle(color: AppColors.textSecondary),
          ),
          SizedBox(height: AppSpace.s(12)),
          TextButton.icon(
            onPressed: onRetry,
            icon: const Icon(Icons.refresh, size: 18),
            label: const Text('다시 시도'),
          ),
        ],
      ),
    );
  }
}

class _CurriculumYoutubeCard extends ConsumerWidget {
  const _CurriculumYoutubeCard({required this.video});

  final CurriculumYoutubeVideo video;

  Future<void> _open(BuildContext context, WidgetRef ref) async {
    final uri = Uri.tryParse(video.youtubeUrl);
    if (uri == null) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('올바르지 않은 링크입니다.')),
      );
      return;
    }

    final cohortId = ref.read(effectiveCohortIdProvider);
    final user = ref.read(currentUserProvider).value;
    if (cohortId != null && user != null) {
      try {
        await ref
            .read(lmsRepositoryProvider)
            .logRecommendationEvent(
              cohortId: cohortId,
              userId: user.uid,
              videoDocId: video.videoId,
              youtubeVideoId: video.videoId,
              userSkills: const [],
              matchedTags: [
                if (video.topicLabel.isNotEmpty) video.topicLabel,
              ],
              action: 'open',
            );
      } catch (_) {}
    }

    final ok = await launchUrl(uri, mode: LaunchMode.externalApplication);
    if (!ok && context.mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('영상을 열 수 없습니다.')),
      );
    }
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return SizedBox(
      width: 260,
      child: Material(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(14),
        clipBehavior: Clip.antiAlias,
        child: InkWell(
          onTap: () => _open(context, ref),
          child: Container(
            decoration: BoxDecoration(
              borderRadius: BorderRadius.circular(14),
              border: Border.all(color: AppColors.border),
              boxShadow: [
                BoxShadow(
                  color: AppColors.shadow,
                  blurRadius: 12,
                  offset: Offset(0, 4),
                ),
              ],
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                AspectRatio(
                  aspectRatio: 16 / 9,
                  child: Stack(
                    fit: StackFit.expand,
                    children: [
                      if (video.thumbnailUrl.isNotEmpty)
                        Image.network(
                          video.thumbnailUrl,
                          fit: BoxFit.cover,
                          errorBuilder: (_, _, _) => Container(
                            color: AppColors.primaryLight,
                            child: Icon(
                              Icons.play_circle_outline,
                              size: 40,
                              color: AppColors.primary,
                            ),
                          ),
                        )
                      else
                        Container(
                          color: AppColors.primaryLight,
                          child: Icon(
                            Icons.play_circle_outline,
                            size: 40,
                            color: AppColors.primary,
                          ),
                        ),
                      Center(
                        child: Icon(
                          Icons.play_circle_filled,
                          size: 44,
                          color: Colors.white,
                        ),
                      ),
                    ],
                  ),
                ),
                Expanded(
                  child: Padding(
                    padding: EdgeInsets.fromLTRB(AppSpace.s(12), AppSpace.s(8), AppSpace.s(12), AppSpace.s(8)),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          video.title,
                          maxLines: 2,
                          overflow: TextOverflow.ellipsis,
                          style: const TextStyle(
                            fontSize: 13,
                            fontWeight: FontWeight.w700,
                            height: 1.25,
                          ),
                        ),
                        SizedBox(height: AppSpace.s(2)),
                        Text(
                          video.channelTitle,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: TextStyle(
                            fontSize: 11,
                            color: AppColors.textSecondary,
                          ),
                        ),
                        SizedBox(height: AppSpace.s(6)),
                        if (video.topicLabel.isNotEmpty)
                          StatusBadge(
                            label: video.topicLabel,
                            color: AppColors.primary,
                          ),
                      ],
                    ),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
