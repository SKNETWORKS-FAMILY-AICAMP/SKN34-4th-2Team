import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:playdata_lms/features/resume/ai_coach/data/resume_review_api_client.dart';
import 'package:playdata_lms/features/resume/ai_coach/presentation/job_resume_review_dialog.dart';
import 'package:playdata_lms/shared/models/resume_content.dart';

/// 첨삭 서버 대신 답한다. 저장된 글은 [text] 하나로 흉내 낸다.
class FakeReviewClient extends ResumeReviewApiClient {
  FakeReviewClient() : super(token: () async => 'fake');

  String text = '개발 하였습니다.';
  Map<String, dynamic>? applied;
  Map<String, dynamic>? undone;
  Map<String, dynamic>? tailoredRequest;
  Map<String, dynamic>? savedSession;
  int reviews = 0;

  @override
  Future<Map<String, dynamic>> context(
    String cohort,
    String resume, {
    String? job,
    String? tailoredResumeId,
  }) async => {
    'content': {
      'coreCompetencies': {'text': text},
    },
    'input_hash': 'version',
    'job_source': {'snapshot_hash': 'job-version'},
  };

  @override
  Future<Map<String, dynamic>> createTailoredResume(
    Map<String, dynamic> body,
  ) async {
    tailoredRequest = body;
    return {
      'tailored_resume_id': 'tailored',
      'content': {
        'coreCompetencies': {'text': text},
      },
    };
  }

  @override
  Future<Map<String, dynamic>> review(Map<String, dynamic> body) async {
    reviews++;
    return {
      'review_id': 'review',
      'input_hash': 'version',
      'summary': '이력서 문장을 검토했습니다.',
      'job_source': {'company': '회사', 'title': '개발자'},
      'sentence_reviews': [
        {
          'field_path': 'coreCompetencies.text',
          'original_quote': text,
          'suggested_revision': '개발하였습니다.',
          'reason': '띄어쓰기 수정',
          'edit_type': 'spelling',
          'status': 'formatting',
          'evidence_quotes': [text],
        },
      ],
    };
  }

  @override
  Future<Map<String, dynamic>> apply(Map<String, dynamic> body) async {
    applied = body;
    text = '개발하였습니다.';
    return {'operation_id': 'op', 'input_hash': 'updated'};
  }

  @override
  Future<Map<String, dynamic>> undo(Map<String, dynamic> body) async {
    undone = body;
    text = '개발 하였습니다.';
    return {'operation_id': 'undo', 'input_hash': 'version'};
  }

  @override
  Future<void> saveTailoredSession(
    String cohortId,
    String resumeId,
    String tailoredResumeId,
    Map<String, dynamic> state,
  ) async {
    savedSession = Map<String, dynamic>.from(state);
  }
}

Widget _dialog(
  FakeReviewClient client, {
  required ResumeContent draft,
  required ValueChanged<ResumeContent> onChanged,
  bool generalReview = true,
  String tailoredResumeId = '',
  Map<String, dynamic> initialReviewSession = const {},
}) => MaterialApp(
  home: Scaffold(
    body: JobResumeReviewDialog(
      client: client,
      cohortId: 'c',
      resumeId: 'r',
      jobId: 'job',
      generalReview: generalReview,
      tailoredResumeId: tailoredResumeId,
      initialReviewSession: initialReviewSession,
      draft: draft,
      onChanged: onChanged,
    ),
  ),
);

ResumeContent _draft(String text) => ResumeContent.fromMap({
  'coreCompetencies': {'text': text},
});

/// 기본 시험 화면(800x600)에서는 첨삭 대화가 접혀 버튼이 화면 밖으로 나간다.
/// 실제로 쓰는 창 크기를 흉내 내야 눌린다.
Future<void> _wideWindow(WidgetTester tester) async {
  await tester.binding.setSurfaceSize(const Size(1400, 1200));
  addTearDown(() => tester.binding.setSurfaceSize(null));
}

void main() {
  testWidgets('수정안을 반영하면 이력서에 들어가고, 되돌리면 원래대로 온다', (tester) async {
    await _wideWindow(tester);
    final client = FakeReviewClient();
    final changes = <ResumeContent>[];
    await tester.pumpWidget(
      _dialog(client, draft: _draft('개발 하였습니다.'), onChanged: changes.add),
    );

    await tester.ensureVisible(find.text('첨삭 시작'));
    await tester.tap(find.text('첨삭 시작'));
    await tester.pumpAndSettle();
    expect(client.reviews, 1);
    expect(find.text('이 문장으로 바꾸기'), findsOneWidget);
    expect(changes, isEmpty, reason: '검토만으로는 이력서를 건드리지 않는다');

    await tester.ensureVisible(find.text('이 문장으로 바꾸기'));
    await tester.tap(find.text('이 문장으로 바꾸기'));
    await tester.pumpAndSettle();
    expect(client.applied!['selected_indices'], [0], reason: '누른 수정안만 반영한다');
    expect(changes.last.coreCompetencies.text, '개발하였습니다.');

    await tester.tap(find.text('되돌리기'));
    await tester.pumpAndSettle();
    expect(changes.last.coreCompetencies.text, '개발 하였습니다.');
    expect(changes.length, 2, reason: '반영과 되돌리기, 두 번만 알린다');

    client.close();
  });

  testWidgets('화면과 저장본이 다르면 모델을 부르기 전에 멈춘다', (tester) async {
    // 저장 안 한 초안으로 첨삭하면 서버가 읽은 글과 화면의 글이 달라, 엉뚱한
    // 문장을 고치라고 답한다. 부르기 전에 막는다.
    await _wideWindow(tester);
    final client = FakeReviewClient();
    await tester.pumpWidget(
      _dialog(client, draft: ResumeContent.empty(), onChanged: (_) {}),
    );

    await tester.ensureVisible(find.text('첨삭 시작'));
    await tester.tap(find.text('첨삭 시작'));
    await tester.pumpAndSettle();
    expect(client.reviews, 0);
    expect(find.textContaining('화면과 저장된 이력서가 다릅니다'), findsOneWidget);

    client.close();
  });

  testWidgets('공고 첨삭은 기본 이력서를 건드리지 않고 공고별 사본에 쓴다', (tester) async {
    // 공고마다 다른 사본이 서버에 저장된다. 기본 이력서까지 바꾸면 다른 공고용
    // 문장이 함께 바뀐다.
    await _wideWindow(tester);
    final client = FakeReviewClient();
    final changes = <ResumeContent>[];
    await tester.pumpWidget(
      _dialog(
        client,
        draft: _draft('개발 하였습니다.'),
        onChanged: changes.add,
        generalReview: false,
      ),
    );

    await tester.pumpAndSettle();
    expect(
      client.tailoredRequest,
      isNull,
      reason: '추천 공고를 열어보기만 한 경우에는 맞춤 이력서를 만들지 않는다',
    );

    await tester.ensureVisible(find.text('첨삭 시작'));
    await tester.tap(find.text('첨삭 시작'));
    await tester.pumpAndSettle();
    expect(client.tailoredRequest!['selected_job_id'], 'job');

    await tester.ensureVisible(find.text('이 문장으로 바꾸기'));
    await tester.tap(find.text('이 문장으로 바꾸기'));
    await tester.pumpAndSettle();
    expect(client.applied!['tailored_resume_id'], 'tailored');
    expect(changes, isEmpty, reason: '기본 이력서에는 전달하지 않는다');

    client.close();
  });

  testWidgets('공고별 첨삭 진행 상태를 다시 열면 복원한다', (tester) async {
    await _wideWindow(tester);
    final client = FakeReviewClient();
    await tester.pumpWidget(
      _dialog(
        client,
        draft: _draft('개발 하였습니다.'),
        onChanged: (_) {},
        generalReview: false,
      ),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.text('첨삭 시작'));
    await tester.pumpAndSettle();
    final saved = client.savedSession!;

    await tester.pumpWidget(const SizedBox.shrink());
    await tester.pumpWidget(
      _dialog(
        client,
        draft: _draft('개발 하였습니다.'),
        onChanged: (_) {},
        generalReview: false,
        tailoredResumeId: 'tailored',
        initialReviewSession: saved,
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('이 문장으로 바꾸기'), findsOneWidget);
    expect(client.reviews, 1, reason: '재진입할 때 모델을 다시 호출하지 않는다');
    client.close();
  });
}
