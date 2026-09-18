import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:playdata_lms/features/resume/ai_coach/data/job_recommend_api_client.dart';

/// 공고 찾기 챗봇의 앱↔서버 계약.
///
/// 검색 자체는 서버가 한다(`job_matching_bot/tests/test_job_chat.py`). 여기서 지키는 것은
/// **대화가 이어지는 방식**이다. 서버가 대화를 저장하지 않으므로, 앱이 직전 조건을
/// 돌려보내지 않으면 "서울만" 같은 말이 앞말을 잃는다.

Map<String, dynamic> _response({
  String reply = '서울 백엔드 신입 12건이에요.',
  Map<String, dynamic>? filters,
  List<Map<String, dynamic>>? jobs,
  int total = 12,
  List<String> suggestions = const ['마감 임박한 것만'],
}) => {
  'reply': reply,
  'filters': filters ??
      {
        'roles': ['백엔드'],
        'skills': <String>[],
        'regions': ['서울'],
        'career': '신입',
        'employment_types': <String>[],
        'deadline_within_days': null,
        'keywords': <String>[],
      },
  'jobs': jobs ??
      [
        {
          'job_id': 'SARAMIN-1',
          'company': '테스트컴퍼니',
          'title': '백엔드 개발자',
          'source_url': 'https://example.com/jobs/1',
          'region': '서울 강남구',
          'career': '신입',
          'employment_type': '정규직',
          'deadline': '2026-09-30',
          'tech_stack': ['Python', 'FastAPI'],
        },
      ],
  'total': total,
  'suggestions': suggestions,
};

http.Response _json(Map<String, dynamic> body, {int status = 200}) => http.Response(
  jsonEncode(body),
  status,
  headers: {'content-type': 'application/json; charset=utf-8'},
);

/// 공고 카드 여러 장. `job_id`만 다르고 나머지는 같다 — 여기서 보는 것은 **순서**다.
List<Map<String, dynamic>> _jobsInOrder(List<String> jobIds) => [
  for (final id in jobIds)
    {
      'job_id': id,
      'company': '$id회사',
      'title': '백엔드 개발자',
      'source_url': 'https://example.com/jobs/$id',
      'region': '서울 강남구',
      'career': '신입',
      'employment_type': '정규직',
      'deadline': null,
      'tech_stack': <String>[],
    },
];

void main() {
  group('공고 찾기 챗봇', () {
    test('첫 질문은 조건 없이 보내고, 응답의 조건을 읽어 둔다', () async {
      Map<String, dynamic>? sent;
      Uri? url;
      final api = JobRecommendApiClient(
        baseUrl: 'http://127.0.0.1:8000',
        client: MockClient((request) async {
          sent = jsonDecode(request.body) as Map<String, dynamic>;
          url = request.url;
          return _json(_response());
        }),
      );

      final result = await api.chat(message: '서울 백엔드 신입 있어?');

      expect(url.toString(), 'http://127.0.0.1:8000/api/v1/jobs/chat');
      expect(sent!['message'], '서울 백엔드 신입 있어?');
      expect(sent!['filters'], isNull, reason: '첫 질문에는 직전 조건이 없다');
      expect(result.total, 12);
      expect(result.jobs.single.company, '테스트컴퍼니');
      expect(result.jobs.single.techStack, ['Python', 'FastAPI']);
      expect(result.filters.regions, ['서울']);
      expect(result.suggestions, ['마감 임박한 것만']);
      expect(sent!['job_id'], isNull, reason: '공고를 고르지 않았으면 비운다');
    });

    test('공고를 고르고 물으면 그 job_id를 함께 보낸다', () async {
      Map<String, dynamic>? sent;
      final api = JobRecommendApiClient(
        baseUrl: 'http://127.0.0.1:8000',
        client: MockClient((request) async {
          sent = jsonDecode(request.body) as Map<String, dynamic>;
          return _json({
            'mode': '공고',
            'reply': '자격요건은 이렇습니다.',
            'filters': <String, dynamic>{},
            'jobs': <dynamic>[],
            'total': 0,
            'suggestions': <dynamic>[],
          });
        }),
      );

      final result = await api.chat(message: '신입도 돼?', jobId: 'JOB-1');

      expect(sent!['job_id'], 'JOB-1');
      expect(result.mode, '공고', reason: '앱이 답을 어떻게 보여줄지 정한다');
      expect(result.reply, '자격요건은 이렇습니다.');
    });

    test('이어지는 질문은 직전 조건을 그대로 실어 보낸다', () async {
      Map<String, dynamic>? sent;
      final api = JobRecommendApiClient(
        baseUrl: 'http://127.0.0.1:8000',
        client: MockClient((request) async {
          sent = jsonDecode(request.body) as Map<String, dynamic>;
          return _json(_response());
        }),
      );

      const previous = JobChatFilters(
        roles: ['백엔드'],
        regions: ['서울'],
        career: '신입',
      );
      await api.chat(message: '마감 임박한 것만', filters: previous);

      final filters = sent!['filters'] as Map<String, dynamic>;
      expect(filters['roles'], ['백엔드']);
      expect(filters['regions'], ['서울']);
      expect(filters['career'], '신입');
    });

    test('서버가 준 조건을 빠짐없이 되돌려 보낸다 — 연차·빼는 조건·올라온 날', () async {
      Map<String, dynamic>? sent;
      final api = JobRecommendApiClient(
        baseUrl: 'http://127.0.0.1:8000',
        client: MockClient((request) async {
          sent = jsonDecode(request.body) as Map<String, dynamic>;
          return _json(_response(filters: {
            'roles': ['백엔드'],
            'career': '경력',
            'career_years': 3,
            'exclude_keywords': ['스타트업'],
            'posted_within_days': 0,
          }));
        }),
      );

      final first = await api.chat(message: '스타트업 빼고 오늘 올라온 3년차 백엔드');
      await api.chat(message: '서울만', filters: first.filters);

      final filters = sent!['filters'] as Map<String, dynamic>;
      expect(filters['career_years'], 3, reason: '"3년차" 다음 말에서 연차가 풀리면 안 된다');
      expect(filters['exclude_keywords'], ['스타트업']);
      expect(filters['posted_within_days'], 0, reason: '0(새로 올라온)과 null(조건 없음)은 다르다');
      expect(first.filters.summary, '백엔드 · 3년차 · 새로 올라온 · 스타트업 제외');
    });

    test('조건 요약은 무엇으로 걸렀는지 그대로 보여준다', () {
      const filters = JobChatFilters(
        roles: ['백엔드'],
        regions: ['서울'],
        career: '신입',
        deadlineWithinDays: 7,
      );
      expect(filters.summary, '백엔드 · 서울 · 신입 · 7일 내 마감');
      expect(const JobChatFilters().summary, '조건 없음');
      expect(const JobChatFilters().isEmpty, isTrue);
    });

    test('결과가 없어도 조건은 살아 있어 다음 질문에 이어진다', () async {
      final api = JobRecommendApiClient(
        baseUrl: 'http://127.0.0.1:8000',
        client: MockClient(
          (_) async => _json(
            _response(
              reply: '조건에 맞는 공고를 찾지 못했어요.',
              jobs: const [],
              total: 0,
              suggestions: const ['지역 상관없이'],
            ),
          ),
        ),
      );

      final result = await api.chat(message: '제주 용접');
      expect(result.jobs, isEmpty);
      expect(result.total, 0);
      expect(result.filters.regions, ['서울'], reason: '조건은 응답에 실려 돌아온다');
      expect(result.suggestions, ['지역 상관없이']);
    });

    test('저장소가 없으면 안내 가능한 예외가 된다', () async {
      final api = JobRecommendApiClient(
        baseUrl: 'http://127.0.0.1:8000',
        client: MockClient(
          (_) async => _json({'detail': '공고 저장소가 없습니다.'}, status: 503),
        ),
      );
      await expectLater(
        api.chat(message: '백엔드'),
        throwsA(
          isA<JobRecommendApiException>()
              .having((e) => e.statusCode, 'statusCode', 503)
              .having((e) => e.message, 'message', contains('저장소')),
        ),
      );
    });

    test('마감일이 없는 공고도 읽을 수 있다', () async {
      final api = JobRecommendApiClient(
        baseUrl: 'http://127.0.0.1:8000',
        client: MockClient(
          (_) async => _json(
            _response(
              jobs: [
                {
                  'job_id': 'SARAMIN-2',
                  'company': '상시채용사',
                  'title': '데이터 분석가',
                  'source_url': 'https://example.com/jobs/2',
                  'region': '경기 성남시',
                  'career': '경력무관',
                  'employment_type': '정규직',
                  'deadline': null,
                  'tech_stack': <String>[],
                },
              ],
            ),
          ),
        ),
      );

      final job = (await api.chat(message: '데이터 분석')).jobs.single;
      expect(job.deadline, isNull);
      expect(job.techStack, isEmpty);
      expect(job.career, '경력무관');
    });
  });

  /// "2번 자세히 봐줘" 가 걸리는 자리.
  ///
  /// 서버는 대화를 저장하지 않으므로 직전에 무엇을 보여 줬는지 모른다. 앱이
  /// `last_job_ids`로 되돌려 준다. **순서가 곧 번호다.** 여기서 한 칸 어긋나면
  /// 사용자가 가리킨 것과 다른 공고를 놓고 답하는데, 답 자체는 그럴듯해서
  /// 틀린 줄도 모른다.
  group('직전에 보여 준 목록', () {
    test('첫 질문에는 되돌려 줄 목록이 없다', () async {
      Map<String, dynamic>? sent;
      final api = JobRecommendApiClient(
        baseUrl: 'http://127.0.0.1:8000',
        client: MockClient((request) async {
          sent = jsonDecode(request.body) as Map<String, dynamic>;
          return _json(_response());
        }),
      );

      await api.chat(message: '백엔드 찾아줘');

      expect(sent!['last_job_ids'], isEmpty, reason: '앞에 보여 준 것이 없다');
    });

    test('보여 준 순서 그대로 실어 보낸다', () async {
      Map<String, dynamic>? sent;
      final api = JobRecommendApiClient(
        baseUrl: 'http://127.0.0.1:8000',
        client: MockClient((request) async {
          sent = jsonDecode(request.body) as Map<String, dynamic>;
          return _json(_response());
        }),
      );

      // 검색 결과가 id 순으로 오지 않는다. 정렬해 보내면 번호가 어긋난다.
      await api.chat(message: '2번 자세히 봐줘', lastJobIds: const ['J7', 'J3', 'J1']);

      expect(sent!['last_job_ids'], ['J7', 'J3', 'J1']);
    });

    test('답에 나온 공고 순서가 다음 턴의 번호가 된다', () async {
      Map<String, dynamic>? sent;
      final api = JobRecommendApiClient(
        baseUrl: 'http://127.0.0.1:8000',
        client: MockClient((request) async {
          sent = jsonDecode(request.body) as Map<String, dynamic>;
          return _json(_response(jobs: _jobsInOrder(['J7', 'J3', 'J1'])));
        }),
      );

      final shown = await api.chat(message: '백엔드 찾아줘');
      expect([for (final job in shown.jobs) job.jobId], ['J7', 'J3', 'J1'],
          reason: '화면에 그려지는 순서가 곧 1·2·3번이다');

      await api.chat(
        message: '2번 자세히 봐줘',
        lastJobIds: [for (final job in shown.jobs) job.jobId],
      );

      // 서버는 이 목록의 두 번째, 즉 J3을 놓고 답한다.
      expect(sent!['last_job_ids'], ['J7', 'J3', 'J1']);
      expect((sent!['last_job_ids'] as List)[1], 'J3');
    });

    test('직전 답이 다룬 공고는 따로 보낸다', () async {
      // "두 공고의 자격요건만"에는 번호가 없다. 번호가 가리킬 목록과 방금 이야기한
      // 대상은 다르다. 비교하고 나서도 목록은 찾아 준 다섯 건 그대로여야 한다.
      Map<String, dynamic>? sent;
      final api = JobRecommendApiClient(
        baseUrl: 'http://127.0.0.1:8000',
        client: MockClient((request) async {
          sent = jsonDecode(request.body) as Map<String, dynamic>;
          return _json(_response());
        }),
      );

      await api.chat(
        message: '두 공고의 자격요건만 간단히 비교해줘',
        lastJobIds: const ['J1', 'J2', 'J3', 'J4', 'J5'],
        lastAnswerJobIds: const ['J2', 'J5'],
      );

      expect(sent!['last_job_ids'], ['J1', 'J2', 'J3', 'J4', 'J5']);
      expect(sent!['last_answer_job_ids'], ['J2', 'J5']);
    });

    test('첫 질문에는 다룬 공고도 없다', () async {
      Map<String, dynamic>? sent;
      final api = JobRecommendApiClient(
        baseUrl: 'http://127.0.0.1:8000',
        client: MockClient((request) async {
          sent = jsonDecode(request.body) as Map<String, dynamic>;
          return _json(_response());
        }),
      );

      await api.chat(message: '백엔드 찾아줘');

      expect(sent!['last_answer_job_ids'], isEmpty);
    });

    test('공고를 골라 물을 때도 목록은 함께 간다', () async {
      Map<String, dynamic>? sent;
      final api = JobRecommendApiClient(
        baseUrl: 'http://127.0.0.1:8000',
        client: MockClient((request) async {
          sent = jsonDecode(request.body) as Map<String, dynamic>;
          return _json(_response(jobs: const []));
        }),
      );

      // 카드를 눌러 물은 뒤에도 "3번은?"으로 돌아갈 수 있어야 한다.
      await api.chat(
        message: '신입도 돼?',
        jobId: 'J3',
        lastJobIds: const ['J7', 'J3', 'J1'],
      );

      expect(sent!['job_id'], 'J3');
      expect(sent!['last_job_ids'], ['J7', 'J3', 'J1']);
    });
  });
}
