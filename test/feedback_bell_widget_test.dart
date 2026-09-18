/// 종을 실제로 눌러 본다. 말풍선이 뜨고 닫히는지, 화면이 잠기지 않는지.
///
/// 처음에는 화면 전체를 덮는 투명한 막을 깔고 바깥을 누르면 닫게 했다. 그러면 열려 있는
/// 동안 다른 곳이 안 눌리고, 막이 남으면 화면은 그려지는데 아무것도 안 되는 상태가 된다.
/// 지금은 막 없이 TapRegion 으로 바깥 누름만 듣는다. 그 약속을 여기서 지킨다.
library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:playdata_lms/features/resume/presentation/widgets/feedback_bell.dart';
import 'package:playdata_lms/shared/models/resume_model.dart';
import 'package:playdata_lms/shared/providers/cohort_providers.dart';
import 'package:playdata_lms/shared/providers/lms_providers.dart';

ResumeModel _resume({int count = 2, List<String> read = const []}) => ResumeModel(
      id: 'r1',
      userId: 'u1',
      title: '이력서',
      status: 'submitted',
      sections: const {},
      feedbackCount: count,
      readFeedbackIds: read,
    );

/// 항목이 많을 때 말풍선이 넘치는지 보려고 수를 늘릴 수 있게 해 둔다.
List<ResumeFeedbackModel> _many(int n) => [
      for (var i = 0; i < n; i++)
        ResumeFeedbackModel(
          id: 'f$i',
          sectionKey: i.isEven ? 'projects' : 'experience',
          content: '내용 $i',
          authorName: 'PLAYDATA 강사',
          authorId: 'teacher-1',
          createdAt: DateTime(2026, 9, 9, 15, i % 60),
        ),
    ];

List<ResumeFeedbackModel> _items() => [
      ResumeFeedbackModel(
        id: 'f1',
        sectionKey: 'projects',
        content: '성과를 숫자로 적어 주세요.',
        authorName: '강사 김대호',
        authorId: 'teacher-1',
        createdAt: DateTime(2026, 9, 9, 15, 42),
      ),
      ResumeFeedbackModel(
        id: 'f2',
        sectionKey: 'selfIntroduction',
        content: '지원동기를 본인 경험으로 이어 주세요.',
        authorName: '강사 김대호',
        authorId: 'teacher-1',
        createdAt: DateTime(2026, 9, 9, 15, 30),
      ),
    ];

Widget _app({
  required ResumeModel resume,
  List<String>? tapped,
  bool openOnStart = false,
  bool asReviewer = false,
  List<ResumeFeedbackModel>? items,
}) {
  return ProviderScope(
    overrides: [
      resumeFeedbackProvider('r1')
          .overrideWith((ref) => Stream.value(items ?? _items())),
      isAdminProvider.overrideWithValue(asReviewer),
      // 종은 '관리자인가'가 아니라 '검토할 수 있는가'를 본다. 강사는 관리자가 아니다.
      canReviewResumesProvider.overrideWithValue(asReviewer),
      effectiveCohortIdProvider.overrideWithValue(null),
    ],
    child: MaterialApp(
      home: Scaffold(
        appBar: AppBar(
          actions: [
            FeedbackBell(
              resume: resume,
              onGoToSection: (key) => tapped?.add(key),
              openOnStart: openOnStart,
            ),
          ],
        ),
        body: const Center(child: Text('이력서 본문')),
      ),
    ),
  );
}

void main() {
  testWidgets('종을 누르면 목록이 뜨고, 제목 줄만 보인다', (tester) async {
    await tester.pumpWidget(_app(resume: _resume()));
    await tester.pumpAndSettle();

    expect(find.byIcon(Icons.notifications), findsOneWidget, reason: '안 읽은 것이 있으면 채워진 종');
    expect(find.text('2'), findsOneWidget, reason: '배지');

    await tester.tap(find.byType(FeedbackBell));
    await tester.pumpAndSettle();

    expect(find.text('피드백'), findsOneWidget);
    expect(find.textContaining('프로젝트 경험'), findsOneWidget);
    expect(find.textContaining('자기소개서'), findsOneWidget);
    expect(find.textContaining('성과를 숫자로'), findsNothing,
        reason: '내용은 말풍선에 보이지 않는다');
  });

  testWidgets('바깥을 누르면 닫히고 화면이 다시 눌린다', (tester) async {
    await tester.pumpWidget(_app(resume: _resume()));
    await tester.pumpAndSettle();
    await tester.tap(find.byType(FeedbackBell));
    await tester.pumpAndSettle();
    expect(find.text('피드백'), findsOneWidget);

    await tester.tapAt(const Offset(60, 500));
    await tester.pumpAndSettle();

    expect(find.text('피드백'), findsNothing, reason: '말풍선이 닫혀야 한다');
    // 막이 남아 있으면 아래 글자를 못 찾거나 눌러도 반응이 없다.
    expect(find.text('이력서 본문'), findsOneWidget);
    await tester.tap(find.text('이력서 본문'));
    await tester.pumpAndSettle();
  });

  testWidgets('항목을 누르면 그 항목으로 보내고 말풍선은 닫힌다', (tester) async {
    // 종은 길잡이다. 읽는 곳은 항목 아래 댓글 한 곳이다.
    final tapped = <String>[];
    await tester.pumpWidget(_app(resume: _resume(), tapped: tapped));
    await tester.pumpAndSettle();
    await tester.tap(find.byType(FeedbackBell));
    await tester.pumpAndSettle();

    await tester.tap(find.textContaining('프로젝트 경험'));
    await tester.pumpAndSettle();

    expect(tapped, ['projects'], reason: '그 항목으로 보내야 한다');
    expect(find.text('피드백'), findsNothing, reason: '보냈으면 말풍선은 닫는다');
  });

  testWidgets('종을 다시 누르면 닫힌다', (tester) async {
    await tester.pumpWidget(_app(resume: _resume()));
    await tester.pumpAndSettle();
    await tester.tap(find.byType(FeedbackBell));
    await tester.pumpAndSettle();
    expect(find.text('피드백'), findsOneWidget);
    await tester.tap(find.byType(FeedbackBell));
    await tester.pumpAndSettle();
    expect(find.text('피드백'), findsNothing);
  });

  testWidgets('말풍선이 열려 있어도 다른 곳이 눌린다', (tester) async {
    await tester.pumpWidget(_app(resume: _resume()));
    await tester.pumpAndSettle();
    await tester.tap(find.byType(FeedbackBell));
    await tester.pumpAndSettle();

    // 화면을 덮는 막이 있으면 여기서 "hit test 가 안 된다"는 경고와 함께 실패한다.
    expect(
      find.text('이력서 본문').hitTestable(),
      findsOneWidget,
      reason: '열려 있는 동안에도 본문이 눌려야 한다',
    );
    expect(
      find.byType(FeedbackBell).hitTestable(),
      findsOneWidget,
      reason: '종 자신도 가려지면 안 된다 — 다시 눌러 닫을 길이 사라진다',
    );
  });

  testWidgets('화면을 떠나도 막이 남지 않는다', (tester) async {
    await tester.pumpWidget(_app(resume: _resume()));
    await tester.pumpAndSettle();
    await tester.tap(find.byType(FeedbackBell));
    await tester.pumpAndSettle();

    // 종이 사라지는 상황(다른 화면으로 이동)을 흉내 낸다.
    // 덮개(ProviderScope)는 그대로 두어야 한다 — 재정의 개수가 바뀌면 Riverpod 이 막는다.
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          resumeFeedbackProvider('r1').overrideWith((ref) => Stream.value(_items())),
          isAdminProvider.overrideWithValue(false),
          canReviewResumesProvider.overrideWithValue(false),
          effectiveCohortIdProvider.overrideWithValue(null),
        ],
        child: const MaterialApp(
          home: Scaffold(body: Center(child: Text('다른 화면'))),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('다른 화면'), findsOneWidget);
    expect(find.text('피드백'), findsNothing, reason: '말풍선도 함께 걷힌다');
    // 막이 남았다면 아래 글자를 눌러도 반응이 없다.
    await tester.tap(find.text('다른 화면'));
    await tester.pumpAndSettle();
  });

  group('목록에서 들어왔을 때', () {
    testWidgets('신규가 있으면 펼쳐진 채로 열린다', (tester) async {
      await tester.pumpWidget(_app(resume: _resume(), openOnStart: true));
      await tester.pumpAndSettle();
      expect(find.text('피드백'), findsOneWidget);
    });

    testWidgets('다 읽었어도 펼쳐진다', (tester) async {
      // 「다시 보기」로 들어오는 길. 안 읽은 것만 따지면 눌러도 아무 일이 없어 보인다.
      await tester.pumpWidget(
        _app(resume: _resume(read: const ['f1', 'f2']), openOnStart: true),
      );
      await tester.pumpAndSettle();
      expect(find.text('피드백'), findsOneWidget);
      expect(find.textContaining('프로젝트 경험'), findsOneWidget);
    });

    testWidgets('받은 것이 없으면 펼치지 않는다', (tester) async {
      await tester.pumpWidget(_app(resume: _resume(count: 0), openOnStart: true));
      await tester.pumpAndSettle();
      expect(find.text('피드백'), findsNothing, reason: '빈 목록을 펼칠 이유가 없다');
    });

    testWidgets('그냥 들어오면 닫힌 채다', (tester) async {
      await tester.pumpWidget(_app(resume: _resume()));
      await tester.pumpAndSettle();
      expect(find.text('피드백'), findsNothing);
    });
  });

  group('넘침과 강사 화면', () {
    testWidgets('항목이 많아도 말풍선이 넘치지 않는다', (tester) async {
      await tester.pumpWidget(
        _app(resume: _resume(count: 12), items: _many(12), openOnStart: true),
      );
      await tester.pumpAndSettle();
      expect(find.text('피드백'), findsOneWidget);
      // 넘치면 RenderFlex overflow 예외가 잡힌다.
      expect(tester.takeException(), isNull);
    });

    testWidgets('강사에게는 자기가 남긴 피드백이 안 읽음으로 잡히지 않는다', (tester) async {
      // 목록의 두 건은 모두 강사가 남긴 것이다. 이것이 강사에게 안 읽음으로 잡히면
      // 아무리 읽어도 줄지 않는, 지워지지 않는 표시가 된다.
      await tester.pumpWidget(_app(resume: _resume(), asReviewer: true));
      await tester.pumpAndSettle();
      expect(find.text('2'), findsNothing);
      expect(find.byIcon(Icons.notifications_none), findsOneWidget,
          reason: '읽을 것이 없으면 빈 종');
    });

    testWidgets('강사에게는 학생 답글이 안 읽음으로 잡힌다', (tester) async {
      final withReply = [
        ..._items(),
        ResumeFeedbackModel(
          id: 'reply-1',
          sectionKey: 'projects',
          content: '고쳤습니다.',
          authorName: '홍길동',
          authorId: 'u1',
          createdAt: DateTime(2026, 9, 9, 21),
        ),
      ];
      await tester.pumpWidget(
        _app(resume: _resume(count: 3), items: withReply, asReviewer: true),
      );
      await tester.pumpAndSettle();
      expect(find.text('1'), findsOneWidget, reason: '답글 한 건');
    });

    testWidgets('학생에게는 배지가 있다', (tester) async {
      await tester.pumpWidget(_app(resume: _resume()));
      await tester.pumpAndSettle();
      expect(find.text('2'), findsOneWidget);
    });
  });
}
