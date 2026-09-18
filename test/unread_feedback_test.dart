/// 안 읽은 피드백을 누구 기준으로 세나.
///
/// 답글이 생기면서 한 목록을 두 사람이 다른 눈으로 보게 됐다. 학생은 강사의 말을,
/// 강사는 학생의 답글을 읽어야 한다. 내가 쓴 글이 나에게 안 읽음으로 잡히면
/// 숫자가 영영 줄지 않는다.
library;

import 'package:flutter_test/flutter_test.dart';
import 'package:playdata_lms/shared/models/resume_model.dart';

const _student = 'student-1';
const _teacher = 'teacher-1';

ResumeModel _resume({
  List<String> read = const [],
  List<String> reviewerRead = const [],
  int lastSeen = 0,
}) =>
    ResumeModel(
      id: 'r1',
      userId: _student,
      title: '이력서',
      status: 'submitted',
      sections: const {},
      readFeedbackIds: read,
      reviewerReadFeedbackIds: reviewerRead,
      lastSeenFeedbackCount: lastSeen,
    );

ResumeFeedbackModel _item(String id, String authorId) => ResumeFeedbackModel(
      id: id,
      sectionKey: 'experience',
      content: '내용 $id',
      authorName: authorId == _student ? '홍길동' : 'PLAYDATA 강사',
      authorId: authorId,
    );

/// 강사 글 둘, 학생 답글 하나.
List<ResumeFeedbackModel> _thread() => [
      _item('a', _teacher),
      _item('b', _teacher),
      _item('c', _student),
    ];

List<String> _ids(List<ResumeFeedbackModel> items) => [for (final i in items) i.id];

void main() {
  group('학생이 볼 때', () {
    test('강사 글만 안 읽음으로 센다', () {
      final unread = unreadFeedback(_thread(), _resume(), asReviewer: false);
      expect(_ids(unread), ['a', 'b'], reason: '자기 답글은 안 읽음이 아니다');
    });

    test('읽은 것은 빠진다', () {
      final unread =
          unreadFeedback(_thread(), _resume(read: ['a']), asReviewer: false);
      expect(_ids(unread), ['b']);
    });

    test('다 읽으면 비어 있다', () {
      final unread = unreadFeedback(
        _thread(),
        _resume(read: ['a', 'b']),
        asReviewer: false,
      );
      expect(unread, isEmpty);
    });
  });

  group('검토자가 볼 때', () {
    test('학생 답글만 안 읽음으로 센다', () {
      final unread = unreadFeedback(_thread(), _resume(), asReviewer: true);
      expect(_ids(unread), ['c'], reason: '자기가 남긴 피드백은 안 읽음이 아니다');
    });

    test('강사가 읽어도 관리자에게는 여전히 안 읽음이다', () {
      final resume = _resume(reviewerRead: [reviewerReadKey(_teacher, 'c')]);
      expect(
        unreadFeedback(_thread(), resume, asReviewer: true, viewerId: _teacher),
        isEmpty,
        reason: '읽은 사람에게서만 사라진다',
      );
      expect(
        _ids(
          unreadFeedback(
            _thread(),
            resume,
            asReviewer: true,
            viewerId: 'admin-1',
          ),
        ),
        ['c'],
        reason: '다른 검토자의 알림은 그대로 남는다',
      );
    });

    test('누가 읽었는지 모르는 예전 기록은 검토자 각자에게 다시 보인다', () {
      final resume = _resume(reviewerRead: ['c']);
      expect(
        _ids(
          unreadFeedback(
            _thread(),
            resume,
            asReviewer: true,
            viewerId: _teacher,
          ),
        ),
        ['c'],
      );
    });

    test('학생이 읽은 것과 서로 섞이지 않는다', () {
      final resume = _resume(read: ['a', 'b'], reviewerRead: const []);
      expect(_ids(unreadFeedback(_thread(), resume, asReviewer: true)), ['c']);
      expect(unreadFeedback(_thread(), resume, asReviewer: false), isEmpty);
    });
  });

  group('예전 기록', () {
    test('열기만 해도 읽음 처리되던 이력서가 되돌아가지 않는다', () {
      final old = _resume(lastSeen: 3);
      expect(unreadFeedback(_thread(), old, asReviewer: false), isEmpty);
    });

    test('그 뒤에 새로 온 것은 안 읽음이다', () {
      final items = [..._thread(), _item('d', _teacher)];
      final old = _resume(lastSeen: 3);
      expect(_ids(unreadFeedback(items, old, asReviewer: false)), ['a', 'b', 'd'],
          reason: '어느 것이 새것인지 모르니 안전하게 다시 보여 준다');
    });

    test('글쓴이를 모르는 옛 글은 검토자가 남긴 것으로 본다', () {
      final legacy = [ResumeFeedbackModel(
        id: 'x',
        sectionKey: 'experience',
        content: '옛 기록',
        authorName: '관리자',
      )];
      expect(_ids(unreadFeedback(legacy, _resume(), asReviewer: false)), ['x']);
      expect(unreadFeedback(legacy, _resume(), asReviewer: true), isEmpty);
    });
  });

  group('내가 쓴 글', () {
    test('강사가 자기 이력서를 볼 때 자기 글이 안 읽음으로 잡히지 않는다', () {
      // 강사도 자기 이력서를 쓴다. 그때는 검토자이면서 주인이라, 역할만 보면
      // 자기 글이 '답글'로 잡혀 아무리 읽어도 숫자가 줄지 않는다.
      final own = ResumeModel(
        id: 'r2',
        userId: _teacher,
        title: '강사 본인 이력서',
        status: 'submitted',
        sections: const {},
      );
      final items = [_item('a', _teacher), _item('b', _teacher)];
      expect(
        unreadFeedback(items, own, asReviewer: true, viewerId: _teacher),
        isEmpty,
      );
    });

    test('같은 상황에서 남이 남긴 글은 여전히 잡힌다', () {
      final own = ResumeModel(
        id: 'r2',
        userId: _teacher,
        title: '강사 본인 이력서',
        status: 'submitted',
        sections: const {},
      );
      final items = [_item('a', _teacher), _item('b', 'admin-1')];
      // 남이 남긴 것은 이 이력서 주인이 쓴 것이 아니므로 '검토자가 읽을 것'은 아니다.
      // 주인(=강사)으로서 읽어야 할 글이다.
      expect(
        _ids(unreadFeedback(items, own, asReviewer: false, viewerId: _teacher)),
        ['b'],
      );
    });

    test('viewerId 를 모르면 예전처럼 역할로만 가른다', () {
      expect(_ids(unreadFeedback(_thread(), _resume(), asReviewer: true)), ['c']);
    });
  });
}
