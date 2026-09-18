import 'dart:async';

import 'student_chatbot_api_client.dart';

/// 데모 모드용 학생 챗봇.
///
/// 실제 챗봇은 통합 서버(OpenAI·Pinecone)와 Firebase 로그인 토큰이 있어야 해서
/// 데모 모드에서는 연결 오류만 보인다. 온보딩 캡처·녹화에서 챗봇 사용 흐름을
/// 보여 줄 수 있도록, 질문 키워드에 맞춘 안내 문구를 조금씩 흘려보낸다.
/// 문구는 챗봇 화면의 자주 묻는 질문 답변과 뜻을 맞춘다.
class DemoStudentChatbotApiClient extends StudentChatbotApiClient {
  DemoStudentChatbotApiClient() : super(token: _noToken);

  static Future<String?> _noToken() async => null;

  static const _answers = <(List<String>, String)>[
    (
      ['훈련장려금', '장려금'],
      '''훈련장려금은 해당 **단위기간 출석률 80% 이상**이면 지급 기준을 충족해요.

- 출석률 85%라면 출석 기준은 충족한 상태예요.
- 다만 실업급여 등 다른 지원금 수급 여부나 취업 상태에 따라 지급 대상에서 제외될 수 있어요.
- 공가 증빙이 모두 반영된 뒤의 최종 출석률로 판단하니, 확정 여부는 담당 매니저에게 확인해 주세요.''',
    ),
    (
      ['공가'],
      '''공가는 이렇게 사용해요.

1. 공가 당일 출결이슈 구글폼으로 일정을 공유해 주세요.
2. 다음 출석일 16:50에 라운지에서 증빙서류를 제출해 주세요.
3. 출석입력대장에 서명하면 끝이에요.''',
    ),
    (
      ['지각', '조퇴', '외출', '출결', '출석'],
      '''정규수업 8시간 중 **4시간 이상 8시간 미만**을 수강하면 지각·조퇴·외출로 처리돼요.

단위기간 안에서 지각·조퇴·외출을 합쳐 **3회가 되면 결석 1일**로 환산되니 주의해 주세요.''',
    ),
    (
      ['프로젝트'],
      '''이전 기수 프로젝트 레퍼런스에서 주제와 활용 기술, GitHub 주소를 찾아 드릴 수 있어요.

기수·차수·원하는 개수를 함께 적어 주세요. 예: “25기 3차 프로젝트 주제 5개와 핵심 기술을 알려줘”''',
    ),
    (
      ['운영 시간', '몇 시', '캠퍼스'],
      '캠퍼스 운영 시간은 **오전 8:30부터 오후 9:50까지**예요.',
    ),
  ];

  static const _fallback =
      '''LMS 정책·공지, 출결과 공가, 훈련장려금, 이전 기수 프로젝트에 대해 물어봐 주세요.

기수·단위기간·날짜 같은 조건을 함께 적으면 더 정확하게 안내할 수 있어요.''';

  @override
  Future<void> initialize(String threadId) async {
    await Future<void>.delayed(const Duration(milliseconds: 700));
  }

  @override
  Stream<String> ask({
    required String threadId,
    required String question,
  }) async* {
    lastOps = null;
    final answer = _answers
        .firstWhere(
          (entry) => entry.$1.any(question.contains),
          orElse: () => (const [], _fallback),
        )
        .$2;
    // 검색 중 표시가 잠깐 보이도록 기다렸다가 몇 글자씩 보낸다.
    await Future<void>.delayed(const Duration(milliseconds: 1400));
    for (var i = 0; i < answer.length; i += 4) {
      yield answer.substring(i, i + 4 > answer.length ? answer.length : i + 4);
      await Future<void>.delayed(const Duration(milliseconds: 22));
    }
  }

  @override
  void close() {}
}
