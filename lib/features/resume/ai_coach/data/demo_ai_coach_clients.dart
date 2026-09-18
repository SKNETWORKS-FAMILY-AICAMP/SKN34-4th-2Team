import 'dart:async';
import 'dart:convert';

import '../../../../shared/models/resume_content.dart';
import 'job_recommend_api_client.dart';
import 'resume_review_api_client.dart';

// 데모 모드용 AI 코치.
//
// 맞춤 공고 추천(job_matching_bot)과 이력서 첨삭은 실제로는 통합 서버·공고 DB·
// Firebase 로그인이 있어야 한다. 데모 모드에서는 연결 오류만 보이므로, 온보딩
// 캡처·녹화에서 흐름을 보여 줄 수 있게 예시 결과를 돌려준다.
// 공고는 모두 예시이고, 첨삭 수정안은 이력서에 이미 있는 사실만으로 문장을 다듬는다.

const _demoNotice = '데모 화면 · 예시 공고로 보여 주는 결과입니다.';

Map<String, dynamic> _job({
  required String id,
  required String company,
  required String title,
  required String fit,
  required String region,
  required String career,
  required String deadline,
  required List<Map<String, String>> reasons,
  List<String> concerns = const [],
  required int rank,
}) => {
  'job_id': id,
  'source_url': '',
  'company': company,
  'title': title,
  'fit': fit,
  'filter_status': 'PASS',
  'passed_conditions': ['학력 조건 충족', '경력 조건 충족', '희망 지역 일치'],
  'unknown_conditions': <String>[],
  'conditions': {
    'region': region,
    'employment_type': '정규직',
    'education': '전문학사 이상',
    'career': career,
    'deadline': deadline,
  },
  'reasons': reasons,
  'concerns': concerns,
  'search_rank': rank,
};

final _demoJobs = <Map<String, dynamic>>[
  _job(
    id: 'demo-job-1',
    company: '데이터온 (예시)',
    title: '데이터 엔지니어 신입',
    fit: '높음',
    region: '서울 강남구',
    career: '신입',
    deadline: '2026-10-15',
    rank: 1,
    reasons: [
      {
        'claim': 'Airflow 배치 파이프라인 운영 경험이 공고의 필수 요건과 맞습니다.',
        'resume_quote': '공고 크롤 결과를 정규화·중복 제거해 일 단위로 적재. Airflow DAG 5개 운영.',
        'job_quote': 'Airflow 등 워크플로 도구로 배치 파이프라인을 운영해 본 분',
      },
      {
        'claim': 'SQL 집계 자동화 경험이 데이터 마트 구축 업무와 이어집니다.',
        'resume_quote': '매장별 매출 데이터를 SQL로 집계해 주간 리포트를 자동화했습니다.',
        'job_quote': 'SQL로 분석용 데이터 마트를 설계·구축합니다',
      },
    ],
    concerns: ['Spark 실무 경험은 이력서에서 확인되지 않습니다.'],
  ),
  _job(
    id: 'demo-job-2',
    company: '리테일인사이트 (예시)',
    title: '데이터 분석가 (Junior)',
    fit: '높음',
    region: '서울 마포구',
    career: '신입·경력 2년 이하',
    deadline: '2026-10-08',
    rank: 2,
    reasons: [
      {
        'claim': '매출 리포트 자동화 성과가 공고의 리포팅 업무와 직접 맞닿아 있습니다.',
        'resume_quote': '손으로 만들던 4시간짜리 작업을 20분으로 줄였습니다.',
        'job_quote': '반복되는 매출·재고 리포트를 자동화하고 개선합니다',
      },
    ],
    concerns: ['Tableau 등 BI 도구 사용 경험은 확인되지 않습니다.'],
  ),
  _job(
    id: 'demo-job-3',
    company: '모빌리티랩 (예시)',
    title: '데이터 파이프라인 엔지니어',
    fit: '보통',
    region: '경기 성남시',
    career: '신입',
    deadline: '2026-10-31',
    rank: 3,
    reasons: [
      {
        'claim': '공공 교통 데이터 수집·시각화 경험이 서비스 도메인과 가깝습니다.',
        'resume_quote': '지역별 대중교통 이용 데이터로 배차 개선안을 제안. 데이터 수집과 시각화를 맡았습니다.',
        'job_quote': '이동 데이터를 수집·정제해 서비스 지표를 만듭니다',
      },
    ],
    concerns: ['Kafka 등 스트리밍 처리 경험은 확인되지 않습니다.'],
  ),
];

/// 데모 모드용 맞춤 공고 추천 클라이언트.
class DemoJobRecommendApiClient extends JobRecommendApiClient {
  DemoJobRecommendApiClient() : super(baseUrl: 'demo');

  JobRecommendResponse get _response => JobRecommendResponse.fromMap({
    'recommendations': _demoJobs,
    'search_query': '데이터 엔지니어 · 데이터 분석 신입, Python · SQL · Airflow',
    'profile_summary': '데이터 정제·집계 파이프라인과 리포트 자동화 경험이 있는 데이터 직무 신입',
    'reranked': true,
    'warnings': <String>[],
    'notice': _demoNotice,
  });

  @override
  Future<JobRecommendResponse> recommend(JobRecommendRequest request) async {
    await Future<void>.delayed(const Duration(seconds: 2));
    return _response;
  }

  @override
  Future<JobRecommendResponse> recommendWithProgress(
    JobRecommendRequest request, {
    required void Function(String stage, String? detail) onProgress,
  }) async {
    // 실제 서버와 같은 단계 이름을 쓴다(job_matching_bot/api/service.py).
    const steps = [
      ('resume', '기술 6개 · 직무 2개를 뽑았어요'),
      ('search', '열린 공고에서 40건을 추렸어요'),
      ('filter', '조건을 통과한 12건이 남았어요'),
      ('judge', '3건의 근거를 맞대어 봤어요'),
    ];
    for (final (stage, detail) in steps) {
      onProgress(stage, null);
      await Future<void>.delayed(const Duration(milliseconds: 900));
      onProgress(stage, detail);
    }
    return _response;
  }

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
  }) async {
    await Future<void>.delayed(const Duration(milliseconds: 1200));
    return JobChatResponse.fromMap({
      'mode': '검색',
      'reply': '데모 화면에서는 예시 공고로 보여 드려요. 실제 서비스에서는 지금 열려 있는 공고에서 찾아 드립니다.',
      'filters': {
        'roles': ['데이터'],
        'career': '신입',
      },
      'jobs': [
        for (final job in _demoJobs)
          {
            'job_id': job['job_id'],
            'company': job['company'],
            'title': job['title'],
            'source_url': '',
            'region': (job['conditions'] as Map)['region'],
            'career': (job['conditions'] as Map)['career'],
            'employment_type': '정규직',
            'deadline': (job['conditions'] as Map)['deadline'],
          },
      ],
      'total': _demoJobs.length,
      'suggestions': ['서울만 보여줘', '신입 데이터 분석가는 뭘 준비해야 해?'],
    });
  }
}

/// 데모 모드용 이력서 첨삭 클라이언트.
///
/// 이력서 본문을 들고 있다가, 수정안을 적용하면 본문의 해당 문장을 바꾸고
/// 되돌리면 이전 본문으로 돌린다.
class DemoResumeReviewApiClient extends ResumeReviewApiClient {
  DemoResumeReviewApiClient({
    required ResumeContent draft,
    this.jobCompany,
    this.jobTitle,
  }) : _content = _copy(draft.toMap()),
       super(token: _noToken, baseUrl: 'demo');

  static Future<String?> _noToken() async => null;

  final String? jobCompany;
  final String? jobTitle;
  Map<String, dynamic> _content;
  int _version = 1;
  int _reviewCount = 0;
  final Map<String, Map<String, dynamic>> _undo = {};
  List<Map<String, dynamic>> _lastSuggestions = const [];

  static Map<String, dynamic> _copy(Map<String, dynamic> map) =>
      Map<String, dynamic>.from(jsonDecode(jsonEncode(map)) as Map);

  String get _hash => 'demo-$_version';

  Map<String, dynamic> get _jobSource => {
    'snapshot_hash': 'demo-job',
    'company': jobCompany ?? '',
    'title': jobTitle ?? '',
  };

  // 이력서에 이미 있는 사실만으로 다듬은 수정안. 원문이 본문에 있을 때만 제안한다.
  static const _candidates = [
    (
      'coreCompetencies.text',
      'Spark 기초와 Tensorflow 모델 학습 실습 경험.',
      'Spark 기초를 익혔고, Tensorflow로 모델을 학습해 보는 실습을 진행했습니다.',
      '명사로 끊긴 문장을 완결된 문장으로 바꿔 읽기 쉽게 했습니다.',
    ),
    (
      'projects[0].description',
      'Airflow DAG 5개 운영.',
      'Airflow DAG 5개를 운영하며 일 단위 적재를 자동화했습니다.',
      '앞 문장의 일 단위 적재와 이어 붙여 무엇을 운영했는지 드러나게 했습니다.',
    ),
    (
      'selfIntroduction.intro.body',
      '화려한 모델보다 데이터가 매일 깨지지 않고 들어오게 만드는 일에 흥미를 느낍니다.',
      '화려한 모델보다 데이터가 매일 깨지지 않고 들어오게 만드는 일에 흥미를 느끼며, 인턴 때 주간 리포트 작업을 4시간에서 20분으로 줄였습니다.',
      '이력서의 인턴 성과를 자기소개 첫 문단에 연결해 강점이 바로 보이게 했습니다.',
    ),
  ];

  @override
  void close() {}

  @override
  Future<Map<String, dynamic>> context(
    String cohort,
    String resume, {
    String? job,
    String? tailoredResumeId,
  }) async {
    await Future<void>.delayed(const Duration(milliseconds: 500));
    return {
      'content': _copy(_content),
      'input_hash': _hash,
      'job_source': _jobSource,
    };
  }

  @override
  Future<Map<String, dynamic>> createTailoredResume(
    Map<String, dynamic> body,
  ) async {
    await Future<void>.delayed(const Duration(milliseconds: 700));
    return {'tailored_resume_id': 'demo-tailored', 'content': _copy(_content)};
  }

  @override
  Future<Map<String, dynamic>> review(Map<String, dynamic> body) async {
    await Future<void>.delayed(const Duration(milliseconds: 1800));
    _reviewCount++;
    final followUp = body['previous_review_id'] != null;
    final general = body['review_mode'] == 'general';
    final suggestions = followUp
        ? <Map<String, dynamic>>[]
        : [
            for (final (path, original, revision, reason) in _candidates)
              // 공고 맞춤 첨삭은 서버처럼 단계 순서를 지킨다. 자기소개서(5단계) 수정안이 요건 질문(2단계)보다
              // 먼저 뜨지 않도록 첫 첨삭에서는 문장 다듬기만 준다.
              if ((_read(_content, path) ?? '').contains(original) &&
                  (general || !path.startsWith('selfIntroduction')))
                {
                  'field_path': path,
                  'original_quote': original,
                  'suggested_revision': revision,
                  'reason': reason,
                  'edit_type': path.startsWith('selfIntroduction')
                      ? 'content'
                      : 'clarity',
                  'stage': path.startsWith('selfIntroduction') ? 5 : 1,
                },
          ];
    _lastSuggestions = suggestions;
    final company = jobCompany ?? '선택한 공고';
    // 공고 맞춤 첫 첨삭에는 서버 v3 응답처럼 요건 표·STAR 판정·단계가 붙은 질문을 함께 준다.
    // 근거 인용은 데모 이력서(resume_mocks의 데이터 엔지니어 신입)에 실제로 있는 문장만 쓴다.
    final jobFirst = !general && !followUp;
    return {
      'review_id': 'demo-review-$_reviewCount',
      'input_hash': _hash,
      'summary': general
          ? '명사로 끊긴 문장과 성과가 흐릿한 문장을 찾았습니다. 이력서에 이미 있는 내용만으로 다듬었습니다. 수정안을 하나씩 확인해 적용해 보세요.'
          : '$company 공고의 요건 4개를 이력서와 대조했습니다. 배치 파이프라인 경험은 근거가 있고, SQL 데이터 마트는 일부만 확인됩니다. 먼저 문장을 다듬고, 확인이 필요한 요건을 여쭤볼게요.',
      'sentence_reviews': suggestions,
      'suggestions': suggestions,
      'questions': jobFirst ? _demoQuestions : <Map<String, dynamic>>[],
      'requirement_map': jobFirst
          ? _demoRequirements
          : <Map<String, dynamic>>[],
      'star_checks': jobFirst ? _demoStarChecks : <Map<String, dynamic>>[],
      'grounding_warnings': <String>[],
      'job_source': _jobSource,
    };
  }

  static const _demoRequirements = <Map<String, dynamic>>[
    {
      'id': 'req-1',
      'group': 'must',
      'label': 'Airflow 배치 파이프라인',
      'posting_quote': 'Airflow 등 워크플로 도구로 배치 파이프라인을 운영해 본 분',
      'status': 'met',
      'evidence_paths': ['projects[0].description'],
      'evidence_quotes': ['Airflow DAG 5개 운영'],
      'source': 'resume',
    },
    {
      'id': 'req-2',
      'group': 'must',
      'label': 'SQL 데이터 마트 구축',
      'posting_quote': 'SQL로 분석용 데이터 마트를 설계·구축합니다',
      'status': 'partial',
      'evidence_paths': ['otherActivities[0].description'],
      'evidence_quotes': ['매장별 매출 데이터를 SQL로 집계해 주간 리포트를 자동화했습니다.'],
      'source': 'resume',
    },
    {
      'id': 'req-3',
      'group': 'preferred',
      'label': 'Spark 대용량 처리',
      'posting_quote': 'Spark 등 대용량 처리 경험 우대',
      'status': 'unconfirmed',
      'source': 'none',
    },
    {
      'id': 'req-4',
      'group': 'must',
      'label': '전문학사 이상',
      'posting_quote': '전문학사 이상',
      'status': 'unconfirmed',
      'source': 'none',
      'kind': 'eligibility',
      'kind_basis': '공고 조건: 전문학사 이상',
    },
  ];

  static const _demoStarChecks = <Map<String, dynamic>>[
    {
      'field_path': 'projects[0].description',
      'present': ['task', 'action'],
      'reason': '해결하려던 문제와 확인한 결과가 빠져 있습니다.',
    },
    {
      'field_path': 'otherActivities[0].description',
      'present': ['situation', 'action', 'result'],
      'reason': '',
    },
  ];

  static const _demoQuestions = <Map<String, dynamic>>[
    {
      'question_id': 'demo-q-1',
      'field_path': 'projects[0].description',
      'topic': 'scope',
      'question':
          '공고 우대사항의 Spark 같은 대용량 처리 도구를 써 본 적이 있나요? 있다면 이력서의 어느 항목에서 무엇을 했는지 항목 이름과 함께 알려 주세요. 없다면 없다고 답해 주세요.',
      'reason': '공고 우대사항이 이력서에서 확인되지 않습니다.',
      'priority': 2,
      'requirement_id': 'req-3',
      'stage': 2,
    },
    {
      'question_id': 'demo-q-2',
      'field_path': 'projects[0].description',
      'topic': 'result',
      'question':
          "'채용공고 수집 파이프라인' 프로젝트에서 적재를 자동화한 뒤 무엇이 달라졌나요? 처리 시간이나 누락 건수처럼 확인한 결과를 알려 주세요.",
      'reason': '행동은 적혀 있지만 결과가 빠져 있습니다.',
      'priority': 1,
      'stage': 3,
    },
  ];

  @override
  Future<Map<String, dynamic>> apply(Map<String, dynamic> body) async {
    await Future<void>.delayed(const Duration(milliseconds: 900));
    final before = _copy(_content);
    final indices = (body['selected_indices'] as List? ?? const [])
        .whereType<int>();
    for (final index in indices) {
      if (index < 0 || index >= _lastSuggestions.length) continue;
      final s = _lastSuggestions[index];
      final path = s['field_path'] as String;
      final current = _read(_content, path);
      if (current == null) continue;
      _write(
        _content,
        path,
        current.replaceFirst(
          s['original_quote'] as String,
          s['suggested_revision'] as String,
        ),
      );
    }
    _version++;
    final operationId = 'demo-op-$_version';
    _undo[operationId] = before;
    return {'operation_id': operationId, 'input_hash': _hash};
  }

  @override
  Future<Map<String, dynamic>> undo(Map<String, dynamic> body) async {
    await Future<void>.delayed(const Duration(milliseconds: 700));
    final snapshot = _undo.remove(body['application_id']);
    if (snapshot != null) _content = snapshot;
    _version++;
    return {'input_hash': _hash};
  }

  /// `a.b[0].c` 모양의 경로를 따라 문자열을 읽는다.
  static String? _read(Map<String, dynamic> root, String path) {
    Object? node = root;
    for (final key in _keys(path)) {
      if (key is int && node is List && key < node.length) {
        node = node[key];
      } else if (key is String && node is Map) {
        node = node[key];
      } else {
        return null;
      }
    }
    return node is String ? node : null;
  }

  static void _write(Map<String, dynamic> root, String path, String value) {
    final keys = _keys(path);
    Object? node = root;
    for (final key in keys.take(keys.length - 1)) {
      node = key is int ? (node as List)[key] : (node as Map)[key];
    }
    final last = keys.last;
    if (last is int) {
      (node as List)[last] = value;
    } else {
      (node as Map)[last] = value;
    }
  }

  static List<Object> _keys(String path) => [
    for (final match in RegExp(r'([^.\[\]]+)|\[(\d+)\]').allMatches(path))
      if (match.group(2) != null)
        int.parse(match.group(2)!)
      else
        match.group(1)!,
  ];
}
