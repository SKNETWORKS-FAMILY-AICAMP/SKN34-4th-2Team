import 'package:flutter_test/flutter_test.dart';
import 'package:playdata_lms/shared/models/resume_model.dart';

/// 항목 아래 댓글을 실 모양으로 묶는 규칙.
///
/// 강사가 남긴 피드백에 학생이 그 밑으로 답글을 단다. 답글이 첫 글과 나란히 서면
/// 무엇에 대한 답인지 알 수 없다.
ResumeFeedbackModel _item(String id, {String parent = '', String who = '강사'}) =>
    ResumeFeedbackModel(
      id: id,
      sectionKey: 'coreCompetencies',
      content: '$id 내용',
      authorName: who,
      authorId: who,
      parentId: parent,
    );

void main() {
  test('답글은 첫 글 목록에 끼지 않는다', () {
    final items = [
      _item('f1'),
      _item('r1', parent: 'f1', who: '학생'),
      _item('f2'),
    ];

    expect(threadRoots(items).map((f) => f.id), ['f1', 'f2']);
    expect(threadRepliesTo(items, 'f1').map((f) => f.id), ['r1']);
    expect(threadRepliesTo(items, 'f2'), isEmpty);
  });

  test('부모가 사라진 답글은 첫 글로 올린다', () {
    // 강사가 자기 피드백을 지우면 학생 답글만 남는다. 그대로 두면 화면 어디에도
    // 안 나와서 쓴 사람은 글이 증발한 것으로 본다.
    final items = [_item('r1', parent: '사라진글', who: '학생')];

    expect(threadRoots(items).map((f) => f.id), ['r1']);
  });

  test('예전 기록은 부모가 없어 전부 첫 글이다', () {
    // 답글 기능 전에 쌓인 글에는 parentId가 없다. 옮길 것이 없어야 한다.
    final items = [_item('f1'), _item('f2'), _item('f3')];

    expect(threadRoots(items).length, 3);
    expect(items.every((f) => !f.isThreadReply), isTrue);
  });

  test('답글에 달린 답글은 그 답글 밑으로 간다', () {
    // 화면은 한 단계만 들여쓰지만, 묶는 규칙 자체는 부모를 그대로 따른다.
    final items = [
      _item('f1'),
      _item('r1', parent: 'f1', who: '학생'),
      _item('r2', parent: 'r1'),
    ];

    expect(threadRoots(items).map((f) => f.id), ['f1']);
    expect(threadRepliesTo(items, 'r1').map((f) => f.id), ['r2']);
  });
}
