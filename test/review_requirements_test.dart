import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:playdata_lms/features/resume/ai_coach/presentation/job_resume_review_dialog.dart';
import 'package:playdata_lms/shared/models/resume_content.dart';

import 'job_resume_review_dialog_test.dart' show FakeReviewClient;

/// 공고 요건 표와 단계가 붙은 첨삭 응답을 흉내 낸다. "없음"으로 답하면 그 요건을 absent로 돌려준다.
class _RequirementReviewClient extends FakeReviewClient {
  final requests = <Map<String, dynamic>>[];

  @override
  Future<Map<String, dynamic>> review(Map<String, dynamic> body) async {
    requests.add(body);
    reviews++;
    final answered = (body['answers'] as List?)?.isNotEmpty == true;
    return {
      'review_id': 'review-${requests.length}',
      'input_hash': 'version',
      'summary': '공고와 이력서를 비교했습니다.',
      if (answered) 'telemetry': {'model_skipped': 'none_answer'},
      'job_source': {
        'company': '루멘커머스',
        'title': '백엔드 개발자',
        'snapshot_hash': 'job-version',
      },
      'sentence_reviews': const [],
      'requirement_map': [
        {
          'id': 'req-1',
          'group': 'must',
          'label': 'Java·Spring Boot',
          'status': 'met',
          'posting_quote': 'Java, Spring Boot 기반 개발',
          'evidence_paths': ['coreCompetencies.text'],
          'evidence_quotes': ['개발'],
          'source': 'resume',
        },
        {
          'id': 'req-2',
          'group': 'must',
          'label': 'Git 협업',
          'status': answered ? 'absent' : 'unconfirmed',
          'posting_quote': 'Git 브랜치 전략 기반 협업 경험',
          'evidence_paths': const [],
          'evidence_quotes': const [],
          'source': answered ? 'user' : 'none',
        },
      ],
      'questions': [
        if (!answered)
          {
            'question_id': 'q-req',
            'field_path': 'coreCompetencies.text',
            'topic': 'scope',
            'question': "공고 필수 요건인 'Git 협업'과 관련된 실제 경험이 있나요?",
            'reason': 'r',
            'priority': 1,
            'requirement_id': 'req-2',
            'stage': 1,
          },
        {
          // 서버는 응답마다 남은 질문에 새 번호를 매긴다.
          'question_id': answered ? 'q-exp-r${requests.length}' : 'q-exp',
          'field_path': 'coreCompetencies.text',
          'topic': 'action',
          'question': '이 경험에서 직접 한 일은 무엇인가요?',
          'reason': 'r',
          'priority': 2,
          'stage': 3,
        },
      ],
    };
  }
}

/// 첫 첨삭에 표현 수정 3개와 요건 질문 하나를 돌려준다. 묶음 카드에서 고른 것만 적용되는지 본다.
class _PolishReviewClient extends FakeReviewClient {
  final requests = <Map<String, dynamic>>[];

  Map<String, dynamic> _polish(int index, String original, String revision) => {
    'field_path': 'coreCompetencies.text',
    'original_quote': original,
    'suggested_revision': revision,
    'reason': '문장 정리',
    'edit_type': 'clarity',
    'status': 'formatting',
    'stage': 1,
  };

  @override
  Future<Map<String, dynamic>> review(Map<String, dynamic> body) async {
    requests.add(body);
    reviews++;
    return {
      'review_id': 'review-${requests.length}',
      'input_hash': 'version',
      'summary': '공고와 이력서를 비교했습니다.',
      'job_source': {
        'company': '루멘커머스',
        'title': '백엔드 개발자',
        'snapshot_hash': 'job-version',
      },
      'sentence_reviews': [
        _polish(0, '개발 하였습니다.', '개발했습니다.'),
        _polish(1, 'API 설계 가능.', 'API를 설계할 수 있습니다.'),
        _polish(2, '배포 자동화 경험.', '배포를 자동화한 경험이 있습니다.'),
      ],
      'requirement_map': const [],
      'questions': [
        {
          'question_id': 'q-exp',
          'field_path': 'coreCompetencies.text',
          'topic': 'action',
          'question': '이 경험에서 직접 한 일은 무엇인가요?',
          'reason': 'r',
          'priority': 1,
          'stage': 3,
        },
      ],
    };
  }
}

/// 두 번째 응답에서 서버가 대기 중이던 질문 하나를 정리해 뺀다. 앱이 뺀 질문을 띄우거나 보내지 않는지 본다.
class _DroppingReviewClient extends FakeReviewClient {
  final requests = <Map<String, dynamic>>[];

  Map<String, dynamic> _q(String id, String topic, String text, int stage) => {
    'question_id': id,
    'field_path': 'coreCompetencies.text',
    'topic': topic,
    'question': text,
    'reason': 'r',
    'priority': 1,
    'stage': stage,
  };

  @override
  Future<Map<String, dynamic>> review(Map<String, dynamic> body) async {
    requests.add(body);
    reviews++;
    final round = requests.length;
    return {
      'review_id': 'review-$round',
      'input_hash': 'version',
      'summary': '검토',
      'job_source': {
        'company': '루멘커머스',
        'title': '백엔드',
        'snapshot_hash': 'job-version',
      },
      'sentence_reviews': const [],
      'requirement_map': const [],
      'questions': [
        if (round == 1) _q('a1', 'scope', '첫 질문?', 2),
        if (round == 1) _q('b1', 'action', '비슷해서 곧 빠질 질문?', 3),
        _q('c$round', 'result', '남는 질문?', 3),
      ],
    };
  }
}

/// 질문도 수정안도 없는 첨삭. 완료 안내 카드의 초록 "첨삭 완료"가 저장을 기다린 뒤 편집기로 옮기는지 본다.
class _CompletedReviewClient extends FakeReviewClient {
  final events = <String>[];

  @override
  Future<Map<String, dynamic>> review(Map<String, dynamic> body) async {
    reviews++;
    return {
      'review_id': 'review-$reviews',
      'input_hash': 'version',
      'summary': '보완할 곳이 없습니다.',
      'job_source': {
        'company': '식신(주)',
        'title': 'AI/데이터 엔지니어',
        'snapshot_hash': 'job-version',
      },
      'sentence_reviews': const [],
      'requirement_map': const [],
      'questions': const [],
    };
  }

  @override
  Future<void> saveTailoredSession(
    String cohortId,
    String resumeId,
    String tailoredResumeId,
    Map<String, dynamic> state,
  ) async {
    // 실제 서버처럼 저장에 시간이 걸린다. 기다리지 않고 닫으면 목록이 옛 상태를 읽는다.
    await Future<void>.delayed(const Duration(milliseconds: 300));
    events.add('save completed=${state['completed']}');
    await super.saveTailoredSession(
      cohortId,
      resumeId,
      tailoredResumeId,
      state,
    );
  }

  @override
  Future<String> promoteTailoredResume(
    String cohortId,
    String resumeId,
    String tailoredResumeId,
  ) async {
    events.add('promote');
    return 'workspace-1';
  }
}

/// 질문 하나에 답하면 남은 질문이 없다. 세션 저장과 누락 점검이 느린 서버를 흉내 낸다.
class _LastQuestionClient extends FakeReviewClient {
  final phases = <String>[];

  @override
  Future<Map<String, dynamic>> review(Map<String, dynamic> body) async {
    reviews++;
    final answered = (body['answers'] as List?)?.isNotEmpty == true;
    final gapAudit = body['review_phase'] == 'gap_audit';
    phases.add(gapAudit ? 'gap_audit' : (answered ? 'answer' : 'first'));
    if (gapAudit) await Future<void>.delayed(const Duration(milliseconds: 600));
    return {
      'review_id': 'review-$reviews',
      'input_hash': 'version',
      'summary': '검토',
      'job_source': {
        'company': '식신(주)',
        'title': 'AI/데이터 엔지니어',
        'snapshot_hash': 'job-version',
      },
      'sentence_reviews': const [],
      'requirement_map': const [],
      'questions': [
        if (!answered && !gapAudit)
          {
            'question_id': 'q-last',
            'field_path': 'coreCompetencies.text',
            'topic': 'result',
            'question': '마지막 질문?',
            'reason': 'r',
            'priority': 1,
            'stage': 3,
          },
      ],
    };
  }

  @override
  Future<void> saveTailoredSession(
    String cohortId,
    String resumeId,
    String tailoredResumeId,
    Map<String, dynamic> state,
  ) async {
    await Future<void>.delayed(const Duration(milliseconds: 200));
    await super.saveTailoredSession(
      cohortId,
      resumeId,
      tailoredResumeId,
      state,
    );
  }
}

void main() {
  testWidgets('공고 요건 표와 단계를 보여주고, 없음 카드는 답을 입력하지 않고 넘어간다', (tester) async {
    await tester.binding.setSurfaceSize(const Size(1400, 1200));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    final client = _RequirementReviewClient();
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: JobResumeReviewDialog(
            client: client,
            cohortId: 'c',
            resumeId: 'r',
            jobId: 'job',
            jobCompany: '루멘커머스',
            jobTitle: '백엔드 개발자',
            draft: ResumeContent.fromMap({
              'coreCompetencies': {'text': client.text},
            }),
            onChanged: (_) {},
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.text('첨삭 시작'));
    await tester.pumpAndSettle();

    expect(find.text('공고 요건 대조'), findsOneWidget);
    expect(find.text('Java·Spring Boot'), findsOneWidget);
    expect(find.text('Git 협업'), findsOneWidget);
    expect(find.text('공고 요건 확인'), findsOneWidget, reason: '단계 줄');
    expect(find.text('필수 · Git 협업'), findsOneWidget, reason: '질문에 연결된 요건 표시');

    final requestsBefore = client.requests.length;
    await tester.tap(find.byKey(const ValueKey('review-none-answer')));
    await tester.pump();
    expect(
      find.text('이 경험에서 직접 한 일은 무엇인가요?'),
      findsOneWidget,
      reason: '없음은 서버 응답을 기다리지 않고 바로 다음 질문을 띄운다',
    );
    expect(find.text('답변을 검토하고 다음 보완 항목을 준비하고 있어요'), findsNothing);
    await tester.pumpAndSettle();
    expect(
      client.requests.length,
      requestsBefore + 1,
      reason: '기록은 뒤에서 한 번 보낸다',
    );

    final answer = (client.requests.last['answers'] as List).single as Map;
    expect(answer['answer'], '없음');
    expect(find.text('알겠어요. 이력서에는 넣지 않을게요.'), findsOneWidget);
    expect(find.text('경험 보완'), findsWidgets, reason: '다음 질문은 경험 보완 단계');
    final savedRows = client.savedSession!['requirement_map'] as List;
    expect(
      (savedRows[1] as Map)['status'],
      'absent',
      reason: '없음으로 답한 요건은 세션에도 남는다',
    );

    client.close();
  });
  testWidgets('문장 다듬기는 한 카드에서 고른 것만 한 번에 적용하고 그다음 질문으로 넘어간다', (tester) async {
    await tester.binding.setSurfaceSize(const Size(1400, 1400));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    final client = _PolishReviewClient();
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: JobResumeReviewDialog(
            client: client,
            cohortId: 'c',
            resumeId: 'r',
            jobId: 'job',
            draft: ResumeContent.fromMap({
              'coreCompetencies': {'text': client.text},
            }),
            onChanged: (_) {},
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.text('첨삭 시작'));
    await tester.pumpAndSettle();

    expect(find.text('문장 다듬기 3개'), findsOneWidget);
    expect(
      find.text('이 경험에서 직접 한 일은 무엇인가요?'),
      findsNothing,
      reason: '묶음 카드를 처리하기 전에는 질문을 띄우지 않는다',
    );

    await tester.tap(find.text('API를 설계할 수 있습니다.'));
    await tester.pump();
    expect(find.text('선택한 2개 적용'), findsOneWidget);
    await tester.tap(find.byKey(const ValueKey('polish-bundle-apply')));
    await tester.pumpAndSettle();

    expect(client.applied!['selected_indices'], [0, 2]);
    expect(find.text('✓ 문장 다듬기 2개를 이력서에 반영했습니다.'), findsOneWidget);
    expect(
      find.text('이 경험에서 직접 한 일은 무엇인가요?'),
      findsOneWidget,
      reason: '적용한 뒤 질문으로 넘어간다',
    );
    client.close();
  });
  testWidgets('없음을 누르고 곧바로 다음 질문에 답해도 기록이 끝난 뒤 새 질문 번호로 보낸다', (tester) async {
    await tester.binding.setSurfaceSize(const Size(1400, 1200));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    final client = _RequirementReviewClient();
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: JobResumeReviewDialog(
            client: client,
            cohortId: 'c',
            resumeId: 'r',
            jobId: 'job',
            draft: ResumeContent.fromMap({
              'coreCompetencies': {'text': client.text},
            }),
            onChanged: (_) {},
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.text('첨삭 시작'));
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const ValueKey('review-none-answer')));
    await tester.pump();
    await tester.enterText(find.byType(TextField), 'Git Flow로 PR 리뷰 후 병합했어요');
    await tester.tap(find.byTooltip('답변 보내기'));
    await tester.pumpAndSettle();

    expect(
      client.requests.length,
      greaterThanOrEqualTo(3),
      reason: '첫 첨삭, 없음 기록, 다음 답변(그 뒤 누락 점검)',
    );
    final none = (client.requests[1]['answers'] as List).single as Map;
    final next = client.requests[2];
    expect(none['answer'], '없음');
    expect(next['previous_review_id'], 'review-2', reason: '없음 기록 결과를 이어받는다');
    expect(
      ((next['answers'] as List).single as Map)['question_id'],
      'q-exp-r2',
      reason: '화면에 이미 떠 있던 질문도 서버가 새로 매긴 번호로 답한다',
    );
    client.close();
  });
  testWidgets('서버가 정리해 뺀 질문은 띄우지 않고, 남은 질문만 새 번호로 묻는다', (tester) async {
    await tester.binding.setSurfaceSize(const Size(1400, 1200));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    final client = _DroppingReviewClient();
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: JobResumeReviewDialog(
            client: client,
            cohortId: 'c',
            resumeId: 'r',
            jobId: 'job',
            draft: ResumeContent.fromMap({
              'coreCompetencies': {'text': client.text},
            }),
            onChanged: (_) {},
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.text('첨삭 시작'));
    await tester.pumpAndSettle();
    expect(find.text('첫 질문?'), findsOneWidget);

    await tester.tap(find.byKey(const ValueKey('review-none-answer')));
    await tester.pumpAndSettle();

    expect(find.text('비슷해서 곧 빠질 질문?'), findsNothing, reason: '서버가 뺀 질문은 닫는다');
    expect(find.text('남는 질문?'), findsOneWidget);
    await tester.tap(find.byKey(const ValueKey('review-none-answer')));
    await tester.pumpAndSettle();
    final last = client.requests
        .where((request) => (request['answers'] as List?)?.isNotEmpty == true)
        .last;
    expect(
      ((last['answers'] as List).single as Map)['question_id'],
      'c2',
      reason: '서버가 새로 매긴 번호',
    );
    expect(find.textContaining('저장하지 못했습니다'), findsNothing);
    client.close();
  });

  testWidgets('없음을 누르면 대화가 맨 아래로 내려가 다음 질문이 보인다', (tester) async {
    // 창 높이를 줄여 대화가 한 화면을 넘치게 만든다.
    await tester.binding.setSurfaceSize(const Size(1400, 640));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    final client = _RequirementReviewClient();
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: JobResumeReviewDialog(
            client: client,
            cohortId: 'c',
            resumeId: 'r',
            jobId: 'job',
            jobCompany: '루멘커머스',
            jobTitle: '백엔드 개발자',
            draft: ResumeContent.fromMap({
              'coreCompetencies': {'text': client.text},
            }),
            onChanged: (_) {},
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.text('첨삭 시작'));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('review-none-answer')));
    await tester.pumpAndSettle();

    final chat = tester.state<ScrollableState>(
      find
          .ancestor(
            of: find.text('알겠어요. 이력서에는 넣지 않을게요.'),
            matching: find.byType(Scrollable),
          )
          .first,
    );
    expect(
      chat.position.maxScrollExtent,
      greaterThan(0),
      reason: '대화가 화면을 넘친다',
    );
    expect(
      chat.position.pixels,
      chat.position.maxScrollExtent,
      reason: '새 말풍선이 붙으면 맨 아래로 내려간다',
    );
    client.close();
  });

  testWidgets('완료 안내의 초록 첨삭 완료는 위쪽 첨삭 완료처럼 완료 상태를 저장한 뒤 편집기로 옮긴다', (
    tester,
  ) async {
    await tester.binding.setSurfaceSize(const Size(1400, 1200));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    final client = _CompletedReviewClient();
    Object? closedWith = 'not-closed';
    await tester.pumpWidget(
      MaterialApp(
        home: Builder(
          builder: (context) => Scaffold(
            body: TextButton(
              onPressed: () async {
                closedWith = await Navigator.of(context).push<Object?>(
                  MaterialPageRoute(
                    builder: (_) => Scaffold(
                      body: JobResumeReviewDialog(
                        client: client,
                        cohortId: 'c',
                        resumeId: 'r',
                        jobId: 'job',
                        tailoredResumeId: 't1',
                        jobCompany: '식신(주)',
                        jobTitle: 'AI/데이터 엔지니어',
                        draft: ResumeContent.fromMap({
                          'coreCompetencies': {'text': client.text},
                        }),
                        onChanged: (_) {},
                      ),
                    ),
                  ),
                );
                // 목록은 창이 닫힌 뒤 다시 불러온다. 그때 저장이 끝나 있어야 한다.
                client.events.add('closed');
              },
              child: const Text('열기'),
            ),
          ),
        ),
      ),
    );
    await tester.tap(find.text('열기'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('첨삭 시작'));
    await tester.pumpAndSettle();
    await tester.pump(const Duration(seconds: 5));
    await tester.pumpAndSettle();

    final green = find.descendant(
      of: find.byType(FilledButton),
      matching: find.text('첨삭 완료'),
    );
    expect(green, findsOneWidget, reason: '완료 안내 카드의 초록 버튼');
    await tester.tap(green);
    await tester.pump();
    expect(
      find.text('첨삭을 완료할까요?'),
      findsNothing,
      reason: '남은 질문·수정안이 없으면 다시 묻지 않는다',
    );
    await tester.pump(const Duration(seconds: 1));
    await tester.pumpAndSettle();

    expect(closedWith, 'workspace-1', reason: '위쪽 첨삭 완료처럼 편집기로 옮길 이력서를 돌려준다');
    expect(client.events.last, 'closed');
    final lastSave = client.events.lastIndexWhere(
      (event) => event.startsWith('save'),
    );
    expect(client.events[lastSave], 'save completed=true');
    expect(
      lastSave,
      lessThan(client.events.indexOf('closed')),
      reason: '저장이 끝난 뒤 닫는다',
    );
    client.close();
  });

  testWidgets('마지막 질문에 답한 뒤 누락 점검이 끝나기 전에는 첨삭 완료 카드를 띄우지 않는다', (tester) async {
    await tester.binding.setSurfaceSize(const Size(1400, 1200));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    final client = _LastQuestionClient();
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: JobResumeReviewDialog(
            client: client,
            cohortId: 'c',
            resumeId: 'r',
            jobId: 'job',
            tailoredResumeId: 't1',
            draft: ResumeContent.fromMap({
              'coreCompetencies': {'text': client.text},
            }),
            onChanged: (_) {},
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.text('첨삭 시작'));
    await tester.pumpAndSettle();
    expect(find.text('마지막 질문?'), findsOneWidget);

    await tester.enterText(find.byType(TextField), '지연 시간을 30% 줄였어요');
    await tester.tap(find.byTooltip('답변 보내기'));
    final notice = find.textContaining('첨삭을 마칠 수 있습니다');
    // 누락 점검 응답이 올 때까지 프레임마다 본다. 한 프레임이라도 뜨면 깜빡임이다.
    for (
      var frame = 0;
      frame < 60 && !client.phases.contains('gap_audit');
      frame++
    ) {
      await tester.pump(const Duration(milliseconds: 20));
      expect(notice, findsNothing, reason: '누락 점검 전 $frame번째 프레임');
    }
    expect(client.phases, contains('gap_audit'), reason: '저장이 늦어도 누락 점검은 시작한다');
    for (var frame = 0; frame < 25; frame++) {
      await tester.pump(const Duration(milliseconds: 20));
      expect(notice, findsNothing, reason: '누락 점검 중 $frame번째 프레임');
    }
    await tester.pumpAndSettle();
    expect(notice, findsOneWidget, reason: '누락 점검이 끝나면 완료 카드');
    expect(
      find.text('확인했어요. 다음으로 넘어갈게요.'),
      findsOneWidget,
      reason: '수정안이 없는 답변도 실패처럼 알리지 않는다',
    );
    expect(find.textContaining('만들지 못했습니다'), findsNothing);
    expect(client.savedSession?['completed'], isTrue);
    client.close();
  });

  testWidgets('지원 자격은 확인만 줄에 따로 두고, 경험 항목 밑에 STAR 네 칸과 빠진 요소를 보여 준다', (
    tester,
  ) async {
    await tester.binding.setSurfaceSize(const Size(1400, 1200));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    final client = _StarReviewClient();
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: JobResumeReviewDialog(
            client: client,
            cohortId: 'c',
            resumeId: 'r',
            jobId: 'job',
            tailoredResumeId: 't1',
            draft: ResumeContent.fromMap({
              'coreCompetencies': {'text': client.text},
              'projects': [_StarReviewClient.project],
            }),
            onChanged: (_) {},
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.text('첨삭 시작'));
    await tester.pumpAndSettle();

    expect(
      find.textContaining('필수 1/2'),
      findsOneWidget,
      reason: '지원 자격은 근거 개수에서 뺀다',
    );
    expect(
      find.byKey(const ValueKey('review-eligibility-line')),
      findsOneWidget,
    );
    expect(
      find.textContaining('신입 또는 경력 2년 이하'),
      findsOneWidget,
      reason: '확인만 줄에만 보인다',
    );
    expect(find.text('행동 ✓'), findsOneWidget);
    expect(find.text('결과 빠짐'), findsOneWidget);
    expect(find.text('상황 빠짐'), findsOneWidget);
    expect(
      find.text('경험 보완 · 결과가 빠짐'),
      findsOneWidget,
      reason: '질문이 묻는 요소가 빠진 요소면 이유를 붙인다',
    );
    expect(client.savedSession?['star_checks'], isNotEmpty, reason: '세션에도 남는다');
    client.close();
  });

  testWidgets('서버가 답을 다른 항목으로 옮겨 만든 수정안도 보여 준다', (tester) async {
    await tester.binding.setSurfaceSize(const Size(1400, 1200));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    final client = _RoutedAnswerClient();
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: JobResumeReviewDialog(
            client: client,
            cohortId: 'c',
            resumeId: 'r',
            jobId: 'job',
            tailoredResumeId: 't1',
            draft: ResumeContent.fromMap({
              'coreCompetencies': {'text': client.text},
              'projects': _RoutedAnswerClient.projects,
            }),
            onChanged: (_) {},
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.text('첨삭 시작'));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField), '오프라인 다운로드에서 AVPlayer로 재생');
    await tester.tap(find.byTooltip('답변 보내기'));
    await tester.pumpAndSettle();

    expect(
      find.textContaining('AVPlayer로 재생했습니다'),
      findsOneWidget,
      reason: '질문은 프로젝트 1에 붙었지만 답은 프로젝트 2로 옮겨졌다',
    );
    expect(
      find.textContaining("원문의 '끊기지 않게' 표현이 수정안에서 빠졌어요"),
      findsOneWidget,
      reason: '부정 표현이 빠진 수정안은 막지 않고 안내를 붙인다',
    );
    expect(
      find.textContaining('목적 표현으로 바뀌었어요'),
      findsOneWidget,
      reason: '사실이 약해진 수정안도 막지 않고 안내를 붙인다',
    );
    expect(find.textContaining('확인했어요. 다음으로'), findsNothing);
    // 답에 이름이 나온 다른 항목(프로젝트 1)의 수정안은 대기열에 들어가고, 무관한 항목 수정안은 들어가지 않는다.
    await tester.tap(find.text('이 문장으로 바꾸기'));
    await tester.pumpAndSettle();
    expect(find.textContaining('재생 상태를 한곳에 모았습니다'), findsOneWidget);
    expect(find.textContaining('답과 무관한 항목의 수정안'), findsNothing);
    client.close();
  });

  testWidgets('답이 이력서에 없는 별도 경험이면 새 프로젝트로 추가하는 카드를 보여 주고 고르면 적용한다', (
    tester,
  ) async {
    await tester.binding.setSurfaceSize(const Size(1400, 1200));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    final client = _NewProjectClient();
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: JobResumeReviewDialog(
            client: client,
            cohortId: 'c',
            resumeId: 'r',
            jobId: 'job',
            tailoredResumeId: 't1',
            draft: ResumeContent.fromMap({
              'coreCompetencies': {'text': client.text},
              'projects': _NewProjectClient.projects,
            }),
            onChanged: (_) {},
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.text('첨삭 시작'));
    await tester.pumpAndSettle();
    await tester.enterText(
      find.byType(TextField),
      '부트캠프 개인 과제로 카카오맵 API 마커 화면을 만들었어요. 매물 검색 서비스에서는 안 썼어요.',
    );
    await tester.tap(find.byTooltip('답변 보내기'));
    await tester.pumpAndSettle();

    expect(find.byKey(const ValueKey('review-new-project-card')), findsOneWidget);
    expect(find.text('새 프로젝트로 추가'), findsOneWidget);
    expect(find.text('카카오맵 매물 지도'), findsOneWidget);
    expect(find.text('비워 둠 · 직접 채워 주세요'), findsOneWidget, reason: '기간은 답에 없어 비워 둔다');
    expect(find.textContaining('확인했어요. 다음으로'), findsNothing);

    await tester.tap(find.text('프로젝트로 추가'));
    await tester.pumpAndSettle();
    expect(client.applied?['selected_indices'], [0]);
    expect(find.textContaining('새 프로젝트를 이력서에 추가했습니다'), findsOneWidget);
    client.close();
  });

  testWidgets('첨삭을 마친 뒤 이력서를 고치고 재첨삭하면 지난 대화를 정리하고 처음부터 첨삭한다', (
    tester,
  ) async {
    await tester.binding.setSurfaceSize(const Size(1400, 1200));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    final client = _RestartClient();
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: JobResumeReviewDialog(
            client: client,
            cohortId: 'c',
            resumeId: 'r',
            jobId: 'job',
            draft: ResumeContent.fromMap({
              'coreCompetencies': {'text': client.text},
            }),
            onChanged: (_) {},
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    // 추천 패널의 재첨삭 버튼 경로: 창을 열면 첨삭 시작부터다.
    await tester.tap(find.text('첨삭 시작'));
    await tester.pumpAndSettle();

    expect(find.textContaining(_RestartClient.oldMessage), findsNothing, reason: '지난 대화는 정리한다');
    expect(find.textContaining('처음부터 다시 첨삭했어요'), findsOneWidget);
    expect(find.textContaining('새 검토 요약'), findsOneWidget);
    expect(find.textContaining('추가한 프로젝트에서'), findsOneWidget, reason: '새 첨삭의 질문이 보인다');
    // 입력칸은 쓸 수 있어야 한다. enabled를 껐다 켜면 웹에서 입력 연결이 끊기므로 readOnly로 막는다.
    expect(tester.widget<TextField>(find.byType(TextField)).readOnly, isFalse);
    expect(client.reviews, 1);
    client.close();
  });

  testWidgets('목록에서 마친 대화를 열면 완료 안내에 다시 첨삭 버튼이 있고, 누르면 새 첨삭을 시작한다', (
    tester,
  ) async {
    await tester.binding.setSurfaceSize(const Size(1400, 1200));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    final client = _RestartClient();
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: JobResumeReviewDialog(
            client: client,
            cohortId: 'c',
            resumeId: 'r',
            jobId: 'job',
            tailoredResumeId: 't1',
            initialReviewSession: _RestartClient.completedSession,
            draft: ResumeContent.fromMap({
              'coreCompetencies': {'text': client.text},
            }),
            onChanged: (_) {},
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.textContaining(_RestartClient.oldMessage), findsOneWidget);
    final restart = find.text('이력서를 고쳤다면 다시 첨삭');
    expect(restart, findsOneWidget);
    await tester.tap(restart);
    await tester.pumpAndSettle();

    expect(find.textContaining(_RestartClient.oldMessage), findsNothing);
    expect(find.textContaining('새 검토 요약'), findsOneWidget);
    expect(find.textContaining('추가한 프로젝트에서'), findsOneWidget);
    expect(client.reviews, 1);
    client.close();
  });

  testWidgets('이력서가 그대로면 마친 대화를 모델 없이 그대로 복원하고, 다시 첨삭은 버튼으로만 한다', (
    tester,
  ) async {
    await tester.binding.setSurfaceSize(const Size(1400, 1200));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    final client = _RestartClient(savedHash: 'version');
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: JobResumeReviewDialog(
            client: client,
            cohortId: 'c',
            resumeId: 'r',
            jobId: 'job',
            draft: ResumeContent.fromMap({
              'coreCompetencies': {'text': client.text},
            }),
            onChanged: (_) {},
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.text('첨삭 시작'));
    await tester.pumpAndSettle();

    expect(find.textContaining(_RestartClient.oldMessage), findsOneWidget, reason: '지난 대화가 그대로');
    expect(client.reviews, 0, reason: '모델을 부르지 않는다');
    expect(find.text('이력서를 고쳤다면 다시 첨삭'), findsOneWidget);
    client.close();
  });
}

/// 마친 첨삭이 저장된 공고별 사본. 그 뒤 이력서를 고쳐 저장된 판(input_hash)이 달라졌다.
class _RestartClient extends FakeReviewClient {
  _RestartClient({this.savedHash = 'old-version'});

  /// 저장된 대화가 본 이력서 판. 지금 판('version')과 다르면 그 뒤 이력서를 고친 것이다.
  final String savedHash;
  static const oldMessage = '지난 첨삭에서 남긴 대화입니다';
  static final completedSession = _sessionWith('old-version');

  static Map<String, dynamic> _sessionWith(String hash) => {
    'version': 1,
    'resume_id': 'r',
    'job_id': 'job',
    'tailored_resume_id': 't1',
    'result': {
      'review_id': 'old-review',
      'input_hash': hash,
      'job_source': {'job_id': 'job', 'company': '회사', 'title': '개발자'},
      'summary': '지난 요약',
    },
    'messages': [
      {'type': 'assistant', 'text': oldMessage},
    ],
    'question_queue': [],
    'suggestion_queue': [],
    'answered_question_ids': [],
    'applied_indices': [],
    'gap_audit_started': true,
    'gap_audit_finished': true,
    'manually_completed': true,
    'changed': true,
    'requirement_map': [],
    'star_checks': [],
    'completed': true,
  };

  @override
  Future<Map<String, dynamic>> createTailoredResume(
    Map<String, dynamic> body,
  ) async => {
    'tailored_resume_id': 't1',
    'content': {
      'coreCompetencies': {'text': text},
    },
    'review_session': _sessionWith(savedHash),
  };

  @override
  Future<Map<String, dynamic>> review(Map<String, dynamic> body) async {
    reviews++;
    return {
      'review_id': 'review-$reviews',
      'input_hash': 'version',
      'summary': '새 검토 요약입니다.',
      'job_source': {'job_id': 'job', 'company': '회사', 'title': '개발자'},
      'sentence_reviews': const [],
      'requirement_map': const [],
      'questions': [
        {
          'question_id': 'q-new',
          'field_path': 'coreCompetencies.text',
          'topic': 'action',
          'question': '추가한 프로젝트에서 직접 한 일을 알려 주세요.',
          'reason': 'r',
          'priority': 1,
          'stage': 3,
        },
      ],
    };
  }
}

/// 지원 자격 요건과 STAR 판정이 붙은 첫 첨삭. 프로젝트 하나에 행동만 적혀 있다.
class _StarReviewClient extends FakeReviewClient {
  static const project = {
    'id': 'p1',
    'name': '온도 센서 모니터링 장치',
    'description': 'I2C 센서 드라이버 작성, 수집값을 MQTT로 서버에 전송.',
  };

  Map<String, dynamic> get _content => {
    'coreCompetencies': {'text': text},
    'projects': [project],
  };

  @override
  Future<Map<String, dynamic>> context(
    String cohort,
    String resume, {
    String? job,
    String? tailoredResumeId,
  }) async => {
    'content': _content,
    'input_hash': 'version',
    'job_source': {'snapshot_hash': 'job-version'},
  };

  @override
  Future<Map<String, dynamic>> review(Map<String, dynamic> body) async {
    reviews++;
    return {
      'review_id': 'review-$reviews',
      'input_hash': 'version',
      'summary': '검토',
      'job_source': {
        'company': '(주)엣지센서웍스',
        'title': '임베디드 소프트웨어 개발자',
        'snapshot_hash': 'job-version',
      },
      'sentence_reviews': const [],
      'requirement_map': [
        {
          'id': 'req-1',
          'group': 'must',
          'label': '신입 또는 경력 2년 이하',
          'status': 'unconfirmed',
          'kind': 'eligibility',
          'kind_basis': '공고 조건: 신입',
        },
        {
          'id': 'req-2',
          'group': 'must',
          'label': 'C/C++ 개발',
          'status': 'met',
          'kind': 'skill',
        },
        {
          'id': 'req-3',
          'group': 'must',
          'label': '데이터시트 기반 개발',
          'status': 'unconfirmed',
          'kind': 'skill',
        },
      ],
      'star_checks': [
        {
          'field_path': 'projects[0].description',
          'present': ['action'],
          'missing': ['situation', 'task', 'result'],
          'reason': '해결하려던 문제와 결과가 없어요.',
        },
      ],
      'questions': [
        {
          'question_id': 'q-result',
          'field_path': 'projects[0].description',
          'topic': 'result',
          'question': "'온도 센서 모니터링 장치' 프로젝트에서 확인한 결과는 무엇인가요?",
          'reason': 'r',
          'priority': 1,
          'stage': 3,
        },
      ],
    };
  }
}

/// "어느 항목에서 했나요?" 질문의 답을 서버가 다른 프로젝트로 옮겨 수정안을 만든 경우.
class _RoutedAnswerClient extends FakeReviewClient {
  static const projects = [
    {'id': 'p1', 'name': '재생 화면 전환', 'description': '재생 화면을 SwiftUI로 전환했습니다.'},
    {'id': 'p2', 'name': '오프라인 다운로드', 'description': '오디오 파일을 내려받아 재생합니다.'},
  ];

  @override
  Future<Map<String, dynamic>> context(
    String cohort,
    String resume, {
    String? job,
    String? tailoredResumeId,
  }) async => {
    'content': {
      'coreCompetencies': {'text': text},
      'projects': projects,
    },
    'input_hash': 'version',
    'job_source': {'snapshot_hash': 'job-version'},
  };

  @override
  Future<Map<String, dynamic>> review(Map<String, dynamic> body) async {
    reviews++;
    final answered = (body['answers'] as List?)?.isNotEmpty == true;
    return {
      'review_id': 'review-$reviews',
      'input_hash': 'version',
      'summary': '검토',
      'job_source': {
        'company': '(주)예시오디오',
        'title': 'iOS 개발자',
        'snapshot_hash': 'job-version',
      },
      'requirement_map': const [],
      'confirmed_answers': [
        if (answered)
          {
            'question_id': 'q-av',
            'field_path': 'projects[1].description',
            'question': 'AVFoundation?',
            'answer': '오프라인 다운로드에서 AVPlayer로 재생',
          },
      ],
      'answer_scope_paths': [if (answered) 'projects[0].description'],
      'sentence_reviews': [
        if (answered)
          {
            'field_path': 'projects[0].description',
            'original_quote': '재생 화면을 SwiftUI로 전환했습니다.',
            'suggested_revision': '재생 화면을 SwiftUI로 전환하고 재생 상태를 한곳에 모았습니다.',
            'reason': '답변에 적은 재생 화면 전환 내용 반영',
            'edit_type': 'content',
            'status': 'improved',
          },
        if (answered)
          {
            'field_path': 'projects[2].description',
            'original_quote': '다른 항목',
            'suggested_revision': '답과 무관한 항목의 수정안',
            'reason': '보이면 안 됨',
            'edit_type': 'content',
            'status': 'improved',
          },
        if (answered)
          {
            'field_path': 'projects[1].description',
            'original_quote': '오디오 파일을 내려받아 재생합니다.',
            'suggested_revision': '오디오 파일을 내려받아 AVPlayer로 재생했습니다.',
            'reason': '답변 반영',
            'meaning_notice': "원문의 '끊기지 않게' 표현이 수정안에서 빠졌어요. 뜻이 달라지지 않았는지 확인해 주세요.",
            'fact_notice': "원문의 '오디오 파일을 내려받아 재생합니다'이(가) 수정안에서 목적 표현으로 바뀌었어요. 한 일이 그대로 드러나는지 확인해 주세요.",
            'edit_type': 'content',
            'status': 'improved',
          },
      ],
      'questions': [
        if (!answered)
          {
            'question_id': 'q-av',
            'field_path': 'projects[0].description',
            'topic': 'scope',
            'question': "'AVFoundation'을 어느 항목에서 써 봤나요?",
            'reason': 'r',
            'priority': 1,
            'stage': 2,
          },
      ],
    };
  }
}

/// 지도 API 질문에 "기존 프로젝트에서는 안 했고 개인 과제로 했다"고 답하면 서버가 새 프로젝트 추가 수정안을 만든다.
class _NewProjectClient extends FakeReviewClient {
  static const projects = [
    {'id': 'p1', 'name': '매물 검색 서비스', 'description': '검색 필터와 매물 목록 화면을 맡았습니다.'},
  ];

  @override
  Future<Map<String, dynamic>> context(
    String cohort,
    String resume, {
    String? job,
    String? tailoredResumeId,
  }) async => {
    'content': {
      'coreCompetencies': {'text': text},
      'projects': projects,
    },
    'input_hash': 'version',
    'job_source': {'snapshot_hash': 'job-version'},
  };

  @override
  Future<Map<String, dynamic>> review(Map<String, dynamic> body) async {
    reviews++;
    final answered = (body['answers'] as List?)?.isNotEmpty == true;
    return {
      'review_id': 'review-$reviews',
      'input_hash': 'version',
      'summary': '검토',
      'job_source': {
        'company': '(주)예시하우스',
        'title': '프론트엔드 개발자',
        'snapshot_hash': 'job-version',
      },
      'requirement_map': const [],
      'confirmed_answers': [
        if (answered)
          {
            'question_id': 'q-map',
            'field_path': 'projects[0].description',
            'question': '지도 API?',
            'answer': '부트캠프 개인 과제로 카카오맵 API 마커 화면을 만들었어요.',
          },
      ],
      'sentence_reviews': [
        if (answered)
          {
            'field_path': 'projects[1].description',
            'original_quote': '',
            'suggested_revision': '카카오맵 API로 매물 위치 마커 화면을 만들었습니다.',
            'reason': "답변에 적은 경험은 이력서에 있는 프로젝트와 다른 경험이라 '카카오맵 매물 지도' 프로젝트로 새로 추가해요.",
            'edit_type': 'content',
            'status': 'improved',
            'new_item': {
              'section': 'projects',
              'question_id': 'q-map',
              'name': '카카오맵 매물 지도',
              'role': '개인 과제',
              'tech_stack': '카카오맵 API',
              'description': '카카오맵 API로 매물 위치 마커 화면을 만들었습니다.',
            },
          },
      ],
      'questions': [
        if (!answered)
          {
            'question_id': 'q-map',
            'field_path': 'projects[0].description',
            'topic': 'scope',
            'question': "'매물 검색 서비스'에서 지도 API를 써 봤나요?",
            'reason': 'r',
            'priority': 1,
            'stage': 2,
          },
      ],
    };
  }
}
