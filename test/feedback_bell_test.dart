/// 피드백 종 — 읽음이 언제 넘어가는지.
///
/// 이 규칙 하나가 기능 전체의 값어치를 정한다. 목록을 훑기만 해도 읽음이 되면,
/// 배지가 사라진 뒤에야 무슨 말이 있었는지 찾게 된다. 예전 화면이 그랬다 —
/// 이력서를 열기만 해도 전부 읽음으로 넘어갔다.
library;

import 'package:flutter_test/flutter_test.dart';
import 'package:playdata_lms/core/routing/route_paths.dart';
import 'package:playdata_lms/features/resume/presentation/widgets/feedback_bell.dart';
import 'package:playdata_lms/shared/models/resume_model.dart';

ResumeModel _resume({
  int feedbackCount = 0,
  int lastSeen = 0,
  List<String> read = const [],
}) {
  return ResumeModel(
    id: 'r1',
    userId: 'u1',
    title: '이력서',
    status: 'submitted',
    sections: const {},
    feedbackCount: feedbackCount,
    lastSeenFeedbackCount: lastSeen,
    readFeedbackIds: read,
  );
}

void main() {
  group('안 읽은 건수', () {
    test('아무것도 안 읽었으면 전부 안 읽음', () {
      expect(_resume(feedbackCount: 3).unreadFeedbackCount, 3);
      expect(_resume(feedbackCount: 3).hasUnreadFeedback, isTrue);
    });

    test('전문을 연 것만 줄어든다', () {
      expect(_resume(feedbackCount: 3, read: ['a']).unreadFeedbackCount, 2);
      expect(_resume(feedbackCount: 3, read: ['a', 'b']).unreadFeedbackCount, 1);
      expect(_resume(feedbackCount: 3, read: ['a', 'b', 'c']).unreadFeedbackCount, 0);
    });

    test('다 읽으면 종이 조용해진다', () {
      final r = _resume(feedbackCount: 2, read: ['a', 'b']);
      expect(r.hasUnreadFeedback, isFalse);
    });

    test('피드백이 없으면 0. 음수로 내려가지 않는다', () {
      expect(_resume().unreadFeedbackCount, 0);
      expect(_resume(feedbackCount: 1, read: ['a', 'b']).unreadFeedbackCount, 0);
    });

    test('예전 방식으로 읽음 처리된 이력서가 안 읽음으로 되돌아가지 않는다', () {
      // 화면을 열기만 해도 lastSeenFeedbackCount 를 채우던 시절의 기록.
      // readFeedbackIds 는 비어 있지만 이미 본 것으로 두어야 한다.
      final old = _resume(feedbackCount: 4, lastSeen: 4);
      expect(old.unreadFeedbackCount, 0);
    });

    test('예전 기록 뒤에 새로 온 것만 안 읽음', () {
      final r = _resume(feedbackCount: 6, lastSeen: 4);
      expect(r.unreadFeedbackCount, 2);
    });

    test('둘 중 많이 읽은 쪽을 따른다', () {
      final r = _resume(feedbackCount: 5, lastSeen: 1, read: ['a', 'b', 'c']);
      expect(r.unreadFeedbackCount, 2);
    });
  });

  group('저장·복원', () {
    test('읽은 목록이 저장 형식에 실린다', () {
      final map = _resume(feedbackCount: 2, read: ['a']).toFirestore();
      expect(map['readFeedbackIds'], ['a']);
    });

    test('copyWith 로 읽은 목록을 늘릴 수 있다', () {
      final before = _resume(feedbackCount: 2, read: ['a']);
      final after = before.copyWith(readFeedbackIds: [...before.readFeedbackIds, 'b']);
      expect(after.unreadFeedbackCount, 0);
      expect(before.unreadFeedbackCount, 1, reason: '원본은 그대로여야 한다');
    });
  });

  group('말풍선 위치', () {
    // 꼬리 좌표와 말풍선 좌표를 따로 적었다가 꼬리가 156px 왼쪽으로 어긋난 적이 있다.
    // 눈으로만 보면 또 놓친다.
    test('꼬리 한가운데가 종 한가운데에 온다', () {
      for (final bellX in [120.0, 640.0, 1180.0, 1920.0]) {
        expect(tailCenterFor(bellX), closeTo(bellX, 0.01), reason: '종 X=$bellX');
      }
    });

    test('말풍선은 종에서 왼쪽으로 눕는다', () {
      const bellX = 1180.0;
      expect(popoverLeftFor(bellX), lessThan(bellX), reason: '왼쪽으로 펼쳐져야 한다');
      expect(popoverLeftFor(bellX) + 314, greaterThan(bellX),
          reason: '오른쪽 끝은 종보다 조금 더 나가야 꼬리가 모서리에 붙지 않는다');
    });
  });

  group('목록 카드에서 보낼 주소', () {
    test('읽으러 가기는 종을 펼치라는 표를 달고 간다', () {
      final path = RoutePaths.resumeEditPath('r1', openFeedback: true);
      expect(path, contains('/resume/r1/edit'));
      expect(path, contains('feedback=1'));
    });

    test('평소 카드 누름에는 그 표가 없다', () {
      expect(RoutePaths.resumeEditPath('r1'), isNot(contains('feedback')));
      expect(RoutePaths.resumeEditPath('r1'), '/resume/r1/edit');
    });

    test('기수·섹션과 같이 실을 수 있다', () {
      final path = RoutePaths.resumeEditPath(
        'r1',
        section: 'projects',
        cohortId: 'c1',
        openFeedback: true,
      );
      for (final part in ['section=projects', 'cohortId=c1', 'feedback=1']) {
        expect(path, contains(part));
      }
    });
  });
}
