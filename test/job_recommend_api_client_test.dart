import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:playdata_lms/features/resume/ai_coach/data/ai_job_coach_repository.dart';
import 'package:playdata_lms/features/resume/ai_coach/data/job_recommend_api_client.dart';
import 'package:playdata_lms/shared/models/job_preferences.dart';
import 'package:playdata_lms/shared/models/resume_content.dart';

/// 추천 조건을 갖춘 이력서. 경력 1년, 전공·자격증 있음.
ResumeContent _resume() => const ResumeContent(
  basicInfo: ResumeBasicInfo(name: '홍길동', email: 'hong@example.com'),
  coreCompetencies: ResumeCoreCompetencies(text: 'Python 백엔드 개발자입니다.'),
  education: [ResumeEducationItem(id: 'e1', school: '한국대학교', major: '컴퓨터공학')],
  experience: [
    ResumeExperienceItem(
      id: 'x1',
      company: '테스트컴퍼니',
      role: '백엔드 개발',
      startDate: '2024-01',
      endDate: '2025-01',
      description: 'FastAPI 서비스를 운영했습니다.',
    ),
  ],
  techStack: [ResumeTechStackItem(id: 't1', name: 'Python')],
  certifications: [ResumeCertificationItem(id: 'c1', name: '정보처리기사')],
  projects: [
    ResumeProjectItem(
      id: 'p1',
      name: '추천 서비스',
      role: '백엔드 개발',
      techStack: 'Python, FastAPI',
      description: 'FastAPI로 추천 API를 개발하고 응답 속도를 개선했습니다.',
    ),
  ],
  selfIntroduction: ResumeSelfIntroduction(
    growth: ResumeIntroSection(subtitle: '성장 과정', body: '꾸준히 학습했습니다.'),
  ),
);

Map<String, dynamic> _serverResponse() => {
  'recommendations': [
    {
      'job_id': 'SARAMIN-1',
      'company': '테스트',
      'title': '백엔드 개발자',
      'source_url': 'https://example.com/jobs/1',
      'fit': '높음',
      'reasons': [
        {
          'claim': 'FastAPI로 API를 만든 경험이 있습니다',
          'resume_quote': 'FastAPI로 추천 API를 개발하고',
          'job_quote': 'FastAPI 기반 API 개발',
        },
      ],
      'concerns': ['Kafka 기반 이벤트 처리 경험이 이력서에서 확인되지 않는다'],
      'conditions': {
        'region': '서울 강남구',
        'employment_type': '정규직',
        'career': '경력무관',
        'education': '학력무관',
        'deadline': '2026-12-31',
      },
      'filter_status': 'PASS',
      'unknown_conditions': [],
      'passed_conditions': ['경력 조건 충족', '학력 조건 충족'],
      'search_rank': 3,
      'body_is_image': false,
    },
  ],
  'search_query': 'Python 백엔드 개발 경험, FastAPI',
  'profile_summary': 'FastAPI 경험이 있는 주니어 백엔드',
  'reranked': true,
  'warnings': [],
  'notice': '추천 순서는 이력서와 공고의 관련도이며 합격 가능성이 아닙니다.',
};

http.Response _json(Map<String, dynamic> body, {int status = 200}) => http.Response(
  jsonEncode(body),
  status,
  headers: {'content-type': 'application/json; charset=utf-8'},
);

void main() {
  group('추천 API 요청', () {
    test('이력서와 희망 조건을 서버 필드 이름으로 보낸다', () async {
      Map<String, dynamic>? sent;
      Uri? url;
      final client = MockClient((request) async {
        sent = jsonDecode(request.body) as Map<String, dynamic>;
        url = request.url;
        return _json(_serverResponse());
      });
      final api = JobRecommendApiClient(baseUrl: 'http://127.0.0.1:8000/', client: client);

      final response = await api.recommend(
        JobRecommendRequest.fromResume(
          _resume(),
          preferences: const JobPreferences(regions: ['서울'], employmentTypes: ['정규직']),
        ),
      );

      expect(url.toString(), 'http://127.0.0.1:8000/api/v1/jobs/recommend');
      expect(sent!['preferred_regions'], ['서울']);
      expect(sent!['preferred_employment_types'], ['정규직']);
      expect(sent!['education_level'], '대졸');
      expect(sent!['career_years'], 1.0);
      expect(sent!['majors'], ['컴퓨터공학']);
      expect(sent!['certifications'], ['정보처리기사']);
      // 화면에 보여줄 건수. 사람이 매긴 43건으로 자를 자리를 재서 정한 값이라
      // 무심코 바꾸면 안 된다. 6건이 오추천 10%, 7건이면 17%로 뛴다.
      expect(sent!['top_k'], 6);
      // 서버는 이 평문 안의 문장을 그대로 인용하므로 사용자가 쓴 문장이 변형 없이 들어가야 한다.
      expect(sent!['resume_text'], contains('FastAPI로 추천 API를 개발하고 응답 속도를 개선했습니다.'));

      final item = response.recommendations.single;
      expect(item.jobId, 'SARAMIN-1');
      expect(item.grade, '높음');
      expect(item.isFromServer, isTrue);
      expect(item.reasons.single.resumeQuote, 'FastAPI로 추천 API를 개발하고');
      expect(item.concerns, hasLength(1));
      expect(item.careerLabel, '경력무관');
      expect(item.region, '서울 강남구');
      expect(item.employmentType, '정규직');
      expect(item.deadline, '2026-12-31');
      expect(item.hardFilterStatus, 'PASS');
      expect(item.passedConditions, contains('경력 조건 충족'));
      expect(response.searchQuery, contains('FastAPI'));
      expect(response.reranked, isTrue);
    });

    test('503은 서버 오류 예외, 연결 실패는 연결 오류 예외', () async {
      final unavailable = JobRecommendApiClient(
        baseUrl: 'http://127.0.0.1:8000',
        client: MockClient((_) async => _json({'detail': '검색 실패'}, status: 503)),
      );
      await expectLater(
        unavailable.recommend(JobRecommendRequest.fromResume(_resume())),
        throwsA(
          isA<JobRecommendApiException>()
              .having((e) => e.statusCode, 'statusCode', 503)
              .having((e) => e.isConnectionError, 'isConnectionError', isFalse)
              .having((e) => e.message, 'message', contains('검색 실패')),
        ),
      );

      final unreachable = JobRecommendApiClient(
        baseUrl: 'http://127.0.0.1:1',
        client: MockClient((_) async => throw http.ClientException('Connection refused')),
      );
      await expectLater(
        unreachable.recommend(JobRecommendRequest.fromResume(_resume())),
        throwsA(
          isA<JobRecommendApiException>().having((e) => e.isConnectionError, 'isConnectionError', isTrue),
        ),
      );
    });
  });

  group('저장소', () {
    test('서버 응답을 그대로 추천 결과로 쓴다', () async {
      final repository = AiJobCoachRepository(
        apiClient: JobRecommendApiClient(
          baseUrl: 'http://127.0.0.1:8000',
          client: MockClient((_) async => _json(_serverResponse())),
        ),
      );
      final result = await repository.analyzeAndMatch(draftContent: _resume());
      expect(result.fromServer, isTrue);
      expect(result.testMode, isFalse);
      expect(result.recommendations.single.title, '백엔드 개발자');
      expect(result.searchQuery, isNotEmpty);
    });

    test('서버에 닿지 못하면 추천하지 않고 연결 오류를 그대로 올린다', () async {
      final repository = AiJobCoachRepository(
        apiClient: JobRecommendApiClient(
          baseUrl: 'http://127.0.0.1:1',
          client: MockClient((_) async => throw http.ClientException('Connection refused')),
        ),
      );
      await expectLater(
        repository.analyzeAndMatch(draftContent: _resume()),
        throwsA(
          isA<JobRecommendApiException>().having((e) => e.isConnectionError, 'isConnectionError', isTrue),
        ),
      );
    });

    test('서버 주소가 비어 있으면 안내 오류를 낸다', () async {
      final repository = AiJobCoachRepository(apiClient: null);
      await expectLater(
        repository.analyzeAndMatch(draftContent: _resume()),
        throwsA(isA<JobRecommendApiException>().having((e) => e.message, 'message', contains('JOB_RECOMMEND_API_URL'))),
      );
    });
  });

  group('이력서의 일부만 보고 추천', () {
    /// "프로젝트 경험만 보고 추천해줘" 같은 요청. 서버가 읽을 글만 프로젝트로 좁힌다.
    ResumeContent projectsOnly() => _resume().copyWith(
      experience: const [],
      techStack: const [],
      coreCompetencies: const ResumeCoreCompetencies(),
      selfIntroduction: const ResumeSelfIntroduction(),
    );

    test('읽을 글만 좁히고 조건은 이력서 원본에서 뽑는다', () {
      final request = JobRecommendRequest.fromResume(
        _resume(),
        focus: projectsOnly(),
      );

      expect(request.resumeText, contains('추천 API를 개발'), reason: '프로젝트는 남는다');
      expect(
        request.resumeText,
        isNot(contains('FastAPI 서비스를 운영')),
        reason: '경력 기술까지 섞으면 "프로젝트 경험만"이 아니다',
      );

      // 조건은 좁힌 쪽이 아니라 원본에서 온다. 좁힌 것으로 뽑으면 연차가 0이 되어
      // 하드 필터가 달라지고, 사용자가 원한 것은 "경력을 없던 셈 치자"가 아니다.
      expect(request.careerYears, greaterThan(0));
      expect(request.certifications, contains('정보처리기사'));
      expect(request.majors, contains('컴퓨터공학'));
    });

    test('좁히지 않으면 지금까지와 똑같다', () {
      final plain = JobRecommendRequest.fromResume(_resume());
      final explicit = JobRecommendRequest.fromResume(_resume(), focus: null);
      expect(explicit.resumeText, plain.resumeText);
    });

    test('좁힌 이력서로 필수 항목 검증을 하지 않는다', () async {
      /// 좁힌 것을 원본 대신 넘겼더니 이력서가 멀쩡한데도 막혔다.
      /// "맞춤 공고를 추천하려면 다음 항목을 먼저 작성해주세요: 핵심역량/강점, ..."
      Map<String, dynamic>? sent;
      final repository = AiJobCoachRepository(
        apiClient: JobRecommendApiClient(
          baseUrl: 'http://127.0.0.1:8000',
          client: MockClient((request) async {
            sent = jsonDecode(request.body) as Map<String, dynamic>;
            return http.Response(
              jsonEncode(_serverResponse()),
              200,
              headers: {'content-type': 'application/json; charset=utf-8'},
            );
          }),
        ),
      );

      final result = await repository.analyzeAndMatch(
        draftContent: _resume(),
        focus: projectsOnly(),
      );

      expect(result.recommendations, isNotEmpty);
      expect(sent!['resume_text'] as String, contains('추천 API를 개발'));
      expect(sent!['resume_text'] as String, isNot(contains('FastAPI 서비스를 운영')));
      expect(sent!['career_years'], greaterThan(0));
    });
  });
}
