import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:playdata_lms/features/auth/providers/auth_providers.dart';
import 'package:playdata_lms/features/resume/ai_coach/data/ai_job_coach_repository.dart';
import 'package:playdata_lms/features/resume/ai_coach/data/job_recommend_api_client.dart';
import 'package:playdata_lms/features/resume/ai_coach/models/ai_job_coach_result.dart';
import 'package:playdata_lms/features/resume/ai_coach/presentation/ai_job_coach_panel.dart';
import 'package:playdata_lms/features/resume/ai_coach/presentation/job_recommendation_loading.dart';
import 'package:playdata_lms/shared/models/job_preferences.dart';
import 'package:playdata_lms/shared/models/resume_content.dart';

const _resume = ResumeContent(
  basicInfo: ResumeBasicInfo(name: '지원자', email: 'test@example.com'),
  education: [ResumeEducationItem(id: 'e1', school: '대학교', major: '컴퓨터공학')],
  techStack: [ResumeTechStackItem(id: 's1', name: 'Python')],
);
const _result = AiJobCoachResult(
  testMode: false,
  notice: '추천 요청 완료',
  recommendations: [],
  selectedJob: null,
  skillJudgements: [],
  resumeFeedback: [],
  learningRecommendations: [],
  analysisId: '',
  fromServer: true,
);

class _Repository implements AiJobCoachRepository {
  var response = Completer<AiJobCoachResult>();
  void Function(String, String?)? progress;

  @override
  Future<AiJobCoachResult> analyzeAndMatch({
    required ResumeContent draftContent,
    JobPreferences preferences = const JobPreferences(),
    ResumeContent? focus,
    void Function(String stage, String? detail)? onProgress,
  }) {
    progress = onProgress;
    return response.future;
  }
}

Future<void> _panel(
  WidgetTester tester,
  _Repository repository, {
  ValueNotifier<ResumeContent>? draft,
  bool reduceMotion = false,
}) async {
  Widget panel(ResumeContent content) => AiJobCoachPanel(
    resumeId: 'resume',
    draftContent: content,
    isSidebar: true,
    onClose: () {},
  );
  await tester.pumpWidget(
    ProviderScope(
      overrides: [
        aiJobCoachRepositoryProvider.overrideWithValue(repository),
        currentUserProvider.overrideWith((ref) => Stream.value(null)),
      ],
      child: MaterialApp(
        home: MediaQuery(
          data: MediaQueryData(disableAnimations: reduceMotion),
          child: Scaffold(
            body: SizedBox(
              width: 380,
              child: draft == null
                  ? panel(_resume)
                  : ValueListenableBuilder(
                      valueListenable: draft,
                      builder: (context, content, child) => panel(content),
                    ),
            ),
          ),
        ),
      ),
    ),
  );
  await tester.tap(find.text('맞춤 공고 추천'));
  await tester.pump();
  expect(find.byType(JobRecommendationLoading), findsOneWidget);
}

class _LinkedJobApi extends JobRecommendApiClient {
  _LinkedJobApi() : super(baseUrl: 'http://test');

  final response = Completer<JobChatResponse>();

  @override
  Future<JobChatResponse> chat({
    required String message,
    JobChatFilters? filters,
    int topK = 5,
    String? jobId,
    String? resumeText,
    List<String> lastJobIds = const [],
    List<String> lastAnswerJobIds = const [],
    List<String> seenJobIds = const [],
  }) => response.future;
}

void _noop() {}

void main() {
  testWidgets('linked job lookup shows a short line, not the recommendation robot', (
    tester,
  ) async {
    final api = _LinkedJobApi();
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          jobRecommendApiClientProvider.overrideWithValue(api),
          currentUserProvider.overrideWith((ref) => Stream.value(null)),
        ],
        child: const MaterialApp(
          home: Scaffold(
            body: SizedBox(
              width: 380,
              child: AiJobCoachPanel(
                resumeId: 'resume',
                draftContent: _resume,
                isSidebar: true,
                linkedJobId: 'job-1',
                onClose: _noop,
              ),
            ),
          ),
        ),
      ),
    );
    await tester.tap(find.text('맞춤 공고 보기'));
    await tester.pump();
    // 새로 추천하는 게 아니라 연결된 공고 하나를 읽는다. 4단계 로봇과 "분석 중"은 띄우지 않는다.
    expect(find.byType(JobRecommendationLoading), findsNothing);
    expect(find.text('이 이력서와 연결된 공고를 불러오는 중이에요'), findsOneWidget);
    expect(find.text('분석 중'), findsNothing);
    api.response.complete(JobChatResponse.fromMap({
      'mode': '공고',
      'reply': '',
      'jobs': [
        {'job_id': 'job-1', 'company': '(주)토마토에이아이', 'title': 'AI 엔지니어'},
      ],
    }));
    await tester.pump();
    expect(find.text('이 이력서와 연결된 공고를 불러오는 중이에요'), findsNothing);
    expect(find.text('맞춤 공고'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('unknown progress stays pending and long server details fit', (
    tester,
  ) async {
    Future<void> loading(String? stage, Map<String, String> results) =>
        tester.pumpWidget(
          MaterialApp(
            home: Scaffold(
              body: SingleChildScrollView(
                child: SizedBox(
                  width: 240,
                  child: MediaQuery(
                    data: const MediaQueryData(
                      textScaler: TextScaler.linear(1.5),
                    ),
                    child: JobRecommendationLoading(
                      current: stage,
                      results: results,
                    ),
                  ),
                ),
              ),
            ),
          ),
        );
    await loading(null, {});
    expect(find.text('추천을 준비하고 있어요'), findsOneWidget);
    expect(find.text('진행 중'), findsNothing);
    await loading('search', {'resume': '이력서에서 Python과 프로젝트 경험을 확인했습니다. ' * 6});
    expect(find.text('공고 찾기 진행 중'), findsOneWidget);
    expect(find.text('완료'), findsOneWidget);
    expect(tester.takeException(), isNull);
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('success checks all steps, drops the robot, then shows results', (
    tester,
  ) async {
    final repository = _Repository();
    await _panel(tester, repository);
    repository.progress!('search', null);
    await tester.pump();
    expect(find.text('공고 찾기 진행 중'), findsOneWidget);
    repository.response.complete(_result);
    await tester.pump();
    expect(find.text('추천 준비 완료!'), findsOneWidget);
    expect(find.text('맞춤 공고 Ranking'), findsNothing);
    final robot = find.byKey(const ValueKey('recommendation-loading-robot'));
    final start = tester.getTopLeft(robot);
    await tester.pump(const Duration(milliseconds: 800));
    expect(tester.getTopLeft(robot).dy, greaterThan(start.dy + 20));
    await tester.pump(const Duration(milliseconds: 550));
    expect(find.byType(JobRecommendationLoading), findsNothing);
    expect(find.text('맞춤 공고 Ranking'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets(
    'error bursts without text and immediate retry resets the robot',
    (tester) async {
      final repository = _Repository();
      await _panel(tester, repository);
      repository.response.completeError(
        const JobRecommendApiException('연결 실패'),
      );
      await tester.pump();
      expect(find.text('추천 준비 완료!'), findsNothing);
      expect(find.text('연결 실패'), findsOneWidget);
      expect(find.text('빵!'), findsNothing);
      final burst = find.byKey(const ValueKey('recommendation-error-burst'));
      expect(burst, findsOneWidget);
      final before = tester.widget<CustomPaint>(burst).painter;
      await tester.pump(const Duration(milliseconds: 500));
      expect(tester.widget<CustomPaint>(burst).painter, isNot(same(before)));
      repository.response = Completer<AiJobCoachResult>();
      await tester.ensureVisible(find.text('다시 시도'));
      await tester.tap(find.text('다시 시도'));
      await tester.pump();
      expect(burst, findsNothing);
      expect(find.text('연결 실패'), findsNothing);
      expect(
        find.byKey(const ValueKey('recommendation-loading-robot')),
        findsOneWidget,
      );
      expect(find.text('추천을 준비하고 있어요'), findsOneWidget);
      repository.response.complete(_result);
      await tester.pump();
      await tester.pump(JobRecommendationLoading.completionDuration);
      expect(find.text('맞춤 공고 Ranking'), findsOneWidget);
      expect(tester.takeException(), isNull);
    },
  );

  testWidgets('error and retry stay visible after fragments disappear', (
    tester,
  ) async {
    final repository = _Repository();
    await _panel(tester, repository);
    repository.response.completeError(StateError('unexpected failure'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 1400));
    expect(
      find.byKey(const ValueKey('recommendation-error-burst')),
      findsNothing,
    );
    expect(find.textContaining('unexpected failure'), findsOneWidget);
    expect(find.text('다시 시도'), findsOneWidget);
    expect(find.text('진행 중'), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('reduced motion leaves error actions without explosion', (
    tester,
  ) async {
    final repository = _Repository();
    await _panel(tester, repository, reduceMotion: true);
    repository.response.completeError(const JobRecommendApiException('서버 오류'));
    await tester.pump();
    expect(find.text('서버 오류'), findsOneWidget);
    expect(find.text('다시 시도'), findsOneWidget);
    expect(
      find.byKey(const ValueKey('recommendation-error-burst')),
      findsNothing,
    );
    expect(tester.takeException(), isNull);
  });

  testWidgets('closing the panel during the burst disposes its ticker', (
    tester,
  ) async {
    final repository = _Repository();
    await _panel(tester, repository);
    repository.response.completeError(const JobRecommendApiException('서버 오류'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 400));
    await tester.pumpWidget(const SizedBox());
    await tester.pump(const Duration(seconds: 2));
    expect(tester.takeException(), isNull);
  });

  testWidgets('long errors fit a narrow panel with larger text', (
    tester,
  ) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: SingleChildScrollView(
            child: SizedBox(
              width: 240,
              child: MediaQuery(
                data: const MediaQueryData(textScaler: TextScaler.linear(1.5)),
                child: JobRecommendationLoading(
                  current: 'search',
                  results: const {},
                  errorMessage: '연결에 실패했습니다. 잠시 후 다시 시도해 주세요. ' * 12,
                  onRetry: () {},
                ),
              ),
            ),
          ),
        ),
      ),
    );
    await tester.pump(const Duration(milliseconds: 1400));
    expect(find.text('다시 시도'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('draft changes during the drop do not expose stale results', (
    tester,
  ) async {
    final draft = ValueNotifier(_resume);
    addTearDown(draft.dispose);
    final repository = _Repository();
    await _panel(tester, repository, draft: draft);
    repository.response.complete(_result);
    await tester.pump();
    draft.value = _resume.copyWith(
      techStack: const [ResumeTechStackItem(id: 's2', name: 'Java')],
    );
    await tester.pump();
    await tester.pump(JobRecommendationLoading.completionDuration);
    expect(find.text('맞춤 공고 Ranking'), findsNothing);
    expect(find.text('추천 중 이력서가 변경됐습니다. 저장 후 다시 추천해 주세요.'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('reduced motion shows results without the completion delay', (
    tester,
  ) async {
    final repository = _Repository();
    await _panel(tester, repository, reduceMotion: true);
    repository.response.complete(_result);
    await tester.pump();
    expect(find.byType(JobRecommendationLoading), findsNothing);
    expect(find.text('맞춤 공고 Ranking'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('closing the panel during completion disposes its animations', (
    tester,
  ) async {
    final repository = _Repository();
    await _panel(tester, repository);
    repository.response.complete(_result);
    await tester.pump();
    await tester.pumpWidget(const SizedBox());
    await tester.pump(JobRecommendationLoading.completionDuration);
    expect(tester.takeException(), isNull);
  });
}
