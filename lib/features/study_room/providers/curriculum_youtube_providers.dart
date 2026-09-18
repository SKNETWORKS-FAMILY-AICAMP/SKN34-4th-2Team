import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../shared/providers/cohort_providers.dart';
import '../data/curriculum_youtube_models.dart';
import '../data/curriculum_youtube_service.dart';

/// 현재 기수 — 커리큘럼 주차 YouTube 추천
final curriculumYoutubeRecommendationsProvider =
    FutureProvider.autoDispose<CurriculumYoutubeRecommendations>((ref) async {
  final cohortId = ref.watch(effectiveCohortIdProvider);
  if (cohortId == null) {
    return const CurriculumYoutubeRecommendations(
      message: '기수 정보가 없습니다.',
    );
  }
  return ref.watch(curriculumYoutubeServiceProvider).fetch(cohortId: cohortId);
});
