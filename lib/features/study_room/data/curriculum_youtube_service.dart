import 'package:cloud_functions/cloud_functions.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../shared/demo/demo_accounts.dart';
import 'curriculum_youtube_models.dart';

final curriculumYoutubeServiceProvider = Provider<CurriculumYoutubeService>((ref) {
  return CurriculumYoutubeService();
});

class CurriculumYoutubeService {
  CurriculumYoutubeService({FirebaseFunctions? functions})
      : _functions = functions ??
            FirebaseFunctions.instanceFor(region: 'asia-northeast3');

  final FirebaseFunctions _functions;

  Future<CurriculumYoutubeRecommendations> fetch({
    required String cohortId,
  }) async {
    if (DemoConfig.enabled) {
      return const CurriculumYoutubeRecommendations(
        // 데모 모드(온보딩 캡처용)에서는 함수를 부르지 않는다. 문구는 사용자 안내서에 그대로 찍힌다.
        message: '이번 주 추천 영상이 준비되면 여기에 표시됩니다.',
      );
    }
    final result = await _functions
        .httpsCallable(
          'getCurriculumYoutubeRecommendations',
          options: HttpsCallableOptions(timeout: const Duration(seconds: 60)),
        )
        .call({'cohortId': cohortId});

    final data = Map<String, dynamic>.from(result.data as Map);
    return CurriculumYoutubeRecommendations.fromMap(data);
  }
}
