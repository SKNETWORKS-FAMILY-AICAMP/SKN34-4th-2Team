import 'dart:async';
import 'dart:convert';

import 'package:http/http.dart' as http;

import '../../../../shared/models/job_preferences.dart';
import '../../../../shared/models/resume_content.dart';
import '../models/ai_job_coach_result.dart';
import 'resume_profile.dart';
import 'resume_text_builder.dart';

/// 채용공고 추천 API(`job_matching_bot`, FastAPI) 접속 설정.
///
/// 기본값은 내 컴퓨터에서 띄운 서버(`127.0.0.1:8000`)다. 다른 주소는 빌드 시
/// `--dart-define=JOB_RECOMMEND_API_URL=http://...` 로 넣는다. 빈 문자열을 넣으면
/// 추천 버튼이 안내 오류를 낸다.
///
/// 서버가 없거나 응답하지 못하면 추천하지 않는다. 이유는 예외 메시지로 화면에
/// 그대로 보인다(`AiJobCoachRepository`).
abstract final class JobRecommendApiConfig {
  static const baseUrl = String.fromEnvironment(
    'JOB_RECOMMEND_API_URL',
    defaultValue: 'http://127.0.0.1:8000',
  );

  static bool get isConfigured => baseUrl.trim().isNotEmpty;

  /// LLM 재정렬이 평균 30초라 넉넉히 둔다.
  static const timeout = Duration(seconds: 90);

  /// 화면에 보여줄 건수. 목록은 받은 만큼 다 그리므로 이 값이 곧 사용자가 보는 수다.
  ///
  /// 사람이 매긴 43건(이력서 5개 × 8~9건)으로 자를 자리를 재 봤다. 위에서부터
  /// N건까지 보여줄 때 오추천율이 이렇게 움직인다.
  ///
  ///     5건 8%   6건 10%   7건 17%   8건 20%   9건 21%
  ///
  /// 7위부터 눈에 띄게 나빠진다. 6건까지가 오추천 10%로 완만하고, 그 자리에서
  /// 사람이 좋다고 한 공고를 이력서당 5.4개 본다. 그래서 6으로 둔다.
  ///
  /// 등급·순위를 섞어 자르는 방법도 있었으나 규칙이 단순한 쪽을 택했다.
  static const topK = 6;
}

class JobRecommendApiException implements Exception {
  const JobRecommendApiException(
    this.message, {
    this.statusCode,
    this.isConnectionError = false,
  });

  final String message;
  final int? statusCode;

  /// 서버에 닿지 못했거나 시간 안에 응답이 없었다. 서버 로직 오류가 아니다.
  final bool isConnectionError;

  @override
  String toString() => message;
}

/// `POST /api/v1/jobs/recommend` 요청 본문. 필드 이름은 서버 스키마와 같다.
class JobRecommendRequest {
  const JobRecommendRequest({
    required this.resumeText,
    this.preferredRegions = const [],
    this.preferredEmploymentTypes = const [],
    this.educationLevel = '미기재',
    this.careerYears = 0,
    this.majors = const [],
    this.certifications = const [],
    this.topK = JobRecommendApiConfig.topK,
  });

  /// 이력서 평문. 서버는 여기 있는 문장을 그대로 인용해 근거로 쓰므로 다듬지 않는다.
  final String resumeText;
  final List<String> preferredRegions;
  final List<String> preferredEmploymentTypes;
  final String educationLevel;
  final double careerYears;
  final List<String> majors;
  final List<String> certifications;
  final int topK;

  /// 이력서와 프로필의 희망 조건으로 만든다. 학력·연차·전공·자격증은
  /// `RecommendResumeProfile`이 이력서에서 뽑는다.
  /// [focus]를 주면 **읽을 글만** 그것으로 바꾼다. 학력·연차·전공·자격증은 [content]
  /// 그대로다.
  ///
  /// "프로젝트 경험만 보고 추천해줘" 같은 요청을 위한 것이다. 좁혀야 하는 것은 뜻을
  /// 뽑는 재료이지 조건이 아니다. 조건까지 좁히면 연차가 0이 되어 하드 필터가 달라지고,
  /// 사용자가 원한 것은 "경력을 없던 셈 치자"가 아니라 "이 부분을 기준으로 보자"다.
  factory JobRecommendRequest.fromResume(
    ResumeContent content, {
    JobPreferences preferences = const JobPreferences(),
    int topK = JobRecommendApiConfig.topK,
    ResumeContent? focus,
  }) {
    final profile = RecommendResumeProfile.fromContent(content);
    return JobRecommendRequest(
      resumeText: buildResumeText(focus ?? content),
      preferredRegions: preferences.regions,
      preferredEmploymentTypes: preferences.employmentTypes,
      educationLevel: profile.educationLevel,
      careerYears: profile.careerYears,
      majors: profile.majors,
      certifications: profile.certifications,
      topK: topK,
    );
  }

  Map<String, dynamic> toJson() => {
        'resume_text': resumeText,
        'preferred_regions': preferredRegions,
        'preferred_employment_types': preferredEmploymentTypes,
        'education_level': educationLevel,
        'career_years': careerYears,
        'majors': majors,
        'certifications': certifications,
        'top_k': topK,
      };
}

/// `POST /api/v1/jobs/recommend` 응답.
class JobRecommendResponse {
  const JobRecommendResponse({
    required this.recommendations,
    required this.searchQuery,
    required this.profileSummary,
    required this.reranked,
    required this.warnings,
    required this.notice,
    this.promptVersion = '',
    this.model = '',
    this.reasoningEffort = '',
  });

  final List<JobRecommendation> recommendations;

  /// 서버가 이력서에서 만든 검색 질의문. 왜 이런 공고가 나왔는지 보여 준다.
  final String searchQuery;
  final String profileSummary;

  /// false면 LLM 재정렬 없이 검색 순서 그대로다.
  final bool reranked;

  /// 근거 검증에서 제거된 내용.
  final List<String> warnings;
  final String notice;
  final String promptVersion;
  final String model;
  final String reasoningEffort;

  factory JobRecommendResponse.fromMap(Map<String, dynamic> map) {
    final items = map['recommendations'];
    return JobRecommendResponse(
      recommendations: items is List
          ? items
              .whereType<Map>()
              .map((e) => JobRecommendation.fromRecommendApi(
                    Map<String, dynamic>.from(e),
                  ))
              .toList()
          : const [],
      searchQuery: map['search_query'] as String? ?? '',
      profileSummary: map['profile_summary'] as String? ?? '',
      reranked: map['reranked'] as bool? ?? false,
      warnings: (map['warnings'] as List?)?.whereType<String>().toList() ?? const [],
      notice: map['notice'] as String? ?? '',
      promptVersion: map['prompt_version'] as String? ?? '',
      model: map['model'] as String? ?? '',
      reasoningEffort: map['reasoning_effort'] as String? ?? '',
    );
  }
}

/// 대화에서 뽑아낸 검색 조건.
///
/// 서버가 대화를 저장하지 않는다. 응답으로 받은 조건을 앱이 들고 있다가 다음 질문에
/// 그대로 실어 보내야 "서울만" 같은 말이 앞말을 이어받는다.
///
/// **서버가 주는 칸을 빠짐없이 들고 있어야 한다.** 여기 없는 칸은 되돌려 보낼 때 사라진다.
/// `career_years`가 빠져 있어 "3년차" 다음 "서울만"에서 연차가 풀렸고, 빼는 조건·올라온 날도
/// 칸이 없으면 "스타트업 빼고" 다음 말에서 스타트업이 다시 섞인다.
class JobChatFilters {
  const JobChatFilters({
    this.roles = const [],
    this.skills = const [],
    this.regions = const [],
    this.career = '무관',
    this.careerYears,
    this.employmentTypes = const [],
    this.deadlineWithinDays,
    this.keywords = const [],
    this.excludeKeywords = const [],
    this.postedWithinDays,
  });

  final List<String> roles;
  final List<String> skills;
  final List<String> regions;
  final String career;
  final int? careerYears;
  final List<String> employmentTypes;
  final int? deadlineWithinDays;
  final List<String> keywords;

  /// 빼 달라는 말. "스타트업은 빼고" → 스타트업.
  final List<String> excludeKeywords;

  /// 최근 올라온 공고만. 0이면 마지막 수집에서 처음 본 공고.
  final int? postedWithinDays;

  bool get isEmpty =>
      roles.isEmpty &&
      skills.isEmpty &&
      regions.isEmpty &&
      career == '무관' &&
      careerYears == null &&
      employmentTypes.isEmpty &&
      deadlineWithinDays == null &&
      keywords.isEmpty &&
      excludeKeywords.isEmpty &&
      postedWithinDays == null;

  /// 무엇으로 걸렀는지 사용자에게 그대로 보여주기 위한 요약.
  String get summary {
    final parts = [
      ...roles,
      ...skills,
      ...regions,
      ...employmentTypes,
      if (careerYears != null) '$careerYears년차' else if (career != '무관') career,
      if (deadlineWithinDays != null) '$deadlineWithinDays일 내 마감',
      // "오늘"이라고 쓰지 않는다. 서버는 마지막 수집일에서 센다.
      if (postedWithinDays == 0) '새로 올라온'
      else if (postedWithinDays != null) '최근 $postedWithinDays일 새로 올라온',
      ...keywords,
      for (final word in excludeKeywords) '$word 제외',
    ];
    return parts.isEmpty ? '조건 없음' : parts.join(' · ');
  }

  Map<String, dynamic> toJson() => {
        'roles': roles,
        'skills': skills,
        'regions': regions,
        'career': career,
        'career_years': careerYears,
        'employment_types': employmentTypes,
        'deadline_within_days': deadlineWithinDays,
        'keywords': keywords,
        'exclude_keywords': excludeKeywords,
        'posted_within_days': postedWithinDays,
      };

  static List<String> _strings(dynamic value) =>
      value is List ? value.whereType<String>().toList() : const [];

  factory JobChatFilters.fromMap(Map<String, dynamic> map) => JobChatFilters(
        roles: _strings(map['roles']),
        skills: _strings(map['skills']),
        regions: _strings(map['regions']),
        career: map['career'] as String? ?? '무관',
        careerYears: (map['career_years'] as num?)?.toInt(),
        employmentTypes: _strings(map['employment_types']),
        deadlineWithinDays: (map['deadline_within_days'] as num?)?.toInt(),
        keywords: _strings(map['keywords']),
        excludeKeywords: _strings(map['exclude_keywords']),
        postedWithinDays: (map['posted_within_days'] as num?)?.toInt(),
      );
}

/// 챗봇이 찾아 준 공고 한 건. 저장소에서 온 것이라 앱에 박힌 파일보다 최신이다.
class JobChatJob {
  const JobChatJob({
    required this.jobId,
    required this.company,
    required this.title,
    required this.sourceUrl,
    required this.region,
    required this.career,
    required this.employmentType,
    this.deadline,
    this.techStack = const [],
  });

  final String jobId;
  final String company;
  final String title;
  final String sourceUrl;
  final String region;
  final String career;
  final String employmentType;
  final String? deadline;
  final List<String> techStack;

  factory JobChatJob.fromMap(Map<String, dynamic> map) => JobChatJob(
        jobId: map['job_id'] as String? ?? '',
        company: map['company'] as String? ?? '',
        title: map['title'] as String? ?? '',
        sourceUrl: map['source_url'] as String? ?? '',
        region: map['region'] as String? ?? '미기재',
        career: map['career'] as String? ?? '미기재',
        employmentType: map['employment_type'] as String? ?? '미기재',
        deadline: map['deadline'] as String?,
        techStack: JobChatFilters._strings(map['tech_stack']),
      );
}

class JobChatResponse {
  const JobChatResponse({
    required this.mode,
    required this.resumeScope,
    required this.reply,
    required this.filters,
    required this.jobs,
    required this.total,
    required this.suggestions,
    this.promptVersion = '',
    this.model = '',
    this.reasoningEffort = '',
  });

  /// 서버가 어떤 갈래로 답했는지. 검색 / 질문 / 공고 / 안내.
  ///
  /// 답을 어떻게 보여줄지가 달라진다. 검색은 목록이 본문이고, 질문은 글이 본문이며
  /// 공고 목록은 근거로 붙는 것이다.
  final String mode;

  /// mode가 '추천'일 때 이력서의 어디를 근거로 삼을지. 전체 / 프로젝트 / 기술스택.
  final String resumeScope;

  final String reply;
  final JobChatFilters filters;
  final List<JobChatJob> jobs;

  /// 조건에 맞는 전체 건수. `jobs`는 그중 일부다.
  final int total;

  /// 다음에 좁힐 거리. 사용자가 그대로 눌러 보낼 수 있는 말이다.
  final List<String> suggestions;
  final String promptVersion;
  final String model;
  final String reasoningEffort;

  factory JobChatResponse.fromMap(Map<String, dynamic> map) {
    final items = map['jobs'];
    return JobChatResponse(
      mode: map['mode'] as String? ?? '검색',
      resumeScope: map['resume_scope'] as String? ?? '전체',
      reply: map['reply'] as String? ?? '',
      filters: JobChatFilters.fromMap(
        Map<String, dynamic>.from(map['filters'] as Map? ?? const {}),
      ),
      jobs: items is List
          ? items
              .whereType<Map>()
              .map((e) => JobChatJob.fromMap(Map<String, dynamic>.from(e)))
              .toList()
          : const [],
      total: (map['total'] as num?)?.toInt() ?? 0,
      suggestions: JobChatFilters._strings(map['suggestions']),
      promptVersion: map['prompt_version'] as String? ?? '',
      model: map['model'] as String? ?? '',
      reasoningEffort: map['reasoning_effort'] as String? ?? '',
    );
  }
}

class JobRecommendApiClient {
  JobRecommendApiClient({String? baseUrl, http.Client? client})
      : _baseUrl = (baseUrl ?? JobRecommendApiConfig.baseUrl)
            .trim()
            .replaceAll(RegExp(r'/+$'), ''),
        _client = client ?? http.Client();

  final String _baseUrl;
  final http.Client _client;

  String get baseUrl => _baseUrl;

  Future<JobRecommendResponse> recommend(JobRecommendRequest request) async {
    return JobRecommendResponse.fromMap(
      await _post('/api/v1/jobs/recommend', request.toJson()),
    );
  }

  /// 추천을 받으면서 진행 단계를 [onProgress]로 흘려 준다.
  ///
  /// 추천은 15초쯤 걸린다. 그동안 화면에 막대만 돌리면 무엇이 진행 중인지 알 수 없다.
  /// 서버가 단계마다 한 줄씩 보내 주므로 그대로 넘긴다. [detail]이 null이면 그 단계를
  /// **시작**한 것이고, 문자열이 오면 그 단계를 **끝내며** 남긴 결과다.
  ///
  /// 서버가 이 경로를 모르거나(옛 버전) 스트림이 깨지면 조용히 기존 경로로 물러난다.
  /// 진행 표시가 없어질 뿐 추천은 그대로 나온다.
  Future<JobRecommendResponse> recommendWithProgress(
    JobRecommendRequest request, {
    required void Function(String stage, String? detail) onProgress,
  }) async {
    try {
      return await _stream(request, onProgress);
    } on JobRecommendApiException {
      rethrow; // 서버가 이유를 말해 준 실패는 그대로 올린다.
    } catch (_) {
      // 스트림만 못 쓰는 상황이다. 추천 자체를 포기할 이유는 아니다.
      return recommend(request);
    }
  }

  Future<JobRecommendResponse> _stream(
    JobRecommendRequest request,
    void Function(String stage, String? detail) onProgress,
  ) async {
    final http.Request outgoing =
        http.Request('POST', Uri.parse('$_baseUrl/api/v1/jobs/recommend/stream'))
          ..headers.addAll(const {
            'Content-Type': 'application/json',
            'Accept': 'text/event-stream',
          })
          ..body = jsonEncode(request.toJson());

    final response = await _client
        .send(outgoing)
        .timeout(JobRecommendApiConfig.timeout);
    if (response.statusCode == 404) {
      // 옛 서버다. 예외로 빠져 기존 경로를 타게 한다.
      throw const FormatException('스트림 경로 없음');
    }
    if (response.statusCode != 200) {
      throw JobRecommendApiException(
        '추천 서버 오류(HTTP ${response.statusCode})',
        statusCode: response.statusCode,
      );
    }

    JobRecommendResponse? result;
    final lines = response.stream
        .transform(utf8.decoder)
        .transform(const LineSplitter());
    await for (final line in lines.timeout(JobRecommendApiConfig.timeout)) {
      if (!line.startsWith('data: ')) continue;
      final decoded = jsonDecode(line.substring(6));
      if (decoded is! Map) continue;
      switch (decoded['event']) {
        case 'progress':
          onProgress(
            decoded['stage'] as String? ?? '',
            decoded['detail'] as String?,
          );
        case 'done':
          result = JobRecommendResponse.fromMap(
            Map<String, dynamic>.from(decoded['result'] as Map),
          );
        case 'error':
          throw JobRecommendApiException(
            decoded['detail'] as String? ?? '추천에 실패했습니다.',
          );
      }
    }
    if (result == null) {
      // 결과 없이 끊겼다. 다시 받는 편이 빈손보다 낫다.
      throw const FormatException('결과 없이 끊김');
    }
    return result;
  }

  /// 채용에 대해 묻고 답을 받는다. 서버가 세 갈래로 나눠 처리한다.
  ///
  /// - 직전 조건(`filters`)을 함께 보내야 "서울만" 같은 말이 이어진다.
  /// - [jobId]를 주면 그 공고 하나에 대한 물음이 된다. 서버는 조건 해석을 건너뛰고
  ///   그 공고 원문만 근거로 답한다.
  /// - [lastJobIds]는 **찾아 준 목록**을 보여 준 순서 그대로 보낸다. 이게 있어야
  ///   "2번 자세히 봐줘"에 답할 수 있다. 서버는 대화를 저장하지 않으므로 직전에 무엇을
  ///   보여 줬는지 모른다.
  /// - [lastAnswerJobIds]는 **직전 답이 다룬 공고**다. 위와 다르다. 위는 번호가 가리킬
  ///   목록이고 이쪽은 방금 이야기한 대상이라, 비교 답이면 견준 두 건이 들어간다.
  ///   이게 있어야 "두 공고의 자격요건만 간단히 비교해줘"에 답할 수 있다.
  /// - [seenJobIds]는 **같은 조건으로 지금까지 보여 준 공고 전부**다. "이거 말고"를
  ///   거듭하면 서버가 이것을 빼고 다음 공고를 준다. 직전 목록만 보내면 두 번째에 첫
  ///   목록이 다시 나온다.
  Future<JobChatResponse> chat({
    required String message,
    JobChatFilters? filters,
    int topK = 5,
    String? jobId,
    // 공고 하나를 놓고 물을 때만 쓴다. "나한테 맞아?"는 이력서를 봐야 답이 된다.
    String? resumeText,
    List<String> lastJobIds = const [],
    List<String> lastAnswerJobIds = const [],
    List<String> seenJobIds = const [],
  }) async {
    final decoded = await _post('/api/v1/jobs/chat', {
      'message': message,
      'filters': filters?.toJson(),
      'top_k': topK,
      'job_id': jobId,
      'resume_text': resumeText,
      'last_job_ids': lastJobIds,
      'last_answer_job_ids': lastAnswerJobIds,
      'seen_job_ids': seenJobIds,
    });
    return JobChatResponse.fromMap(decoded);
  }

  Future<Map<String, dynamic>> _post(String path, Map<String, dynamic> body) async {
    final uri = Uri.parse('$_baseUrl$path');
    final http.Response response;
    try {
      response = await _client
          .post(
            uri,
            headers: const {'Content-Type': 'application/json'},
            body: jsonEncode(body),
          )
          .timeout(JobRecommendApiConfig.timeout);
    } on http.ClientException catch (error) {
      throw JobRecommendApiException(
        '추천 서버($_baseUrl)에 연결하지 못했습니다: ${error.message}',
        isConnectionError: true,
      );
    } on TimeoutException {
      throw JobRecommendApiException(
        '추천 서버가 ${JobRecommendApiConfig.timeout.inSeconds}초 안에 응답하지 않았습니다.',
        isConnectionError: true,
      );
    } catch (error) {
      // 플랫폼별 소켓 예외 등. 서버 로직 오류가 아니라 닿지 못한 것으로 본다.
      throw JobRecommendApiException(
        '추천 서버($_baseUrl) 요청에 실패했습니다: $error',
        isConnectionError: true,
      );
    }

    if (response.statusCode != 200) {
      final detail = _detail(response);
      final message = switch (response.statusCode) {
        503 => '추천 서버가 검색을 수행하지 못했습니다: $detail',
        422 => '요청을 처리하지 못했습니다: $detail',
        _ => '추천 서버 오류(HTTP ${response.statusCode}): $detail',
      };
      throw JobRecommendApiException(message, statusCode: response.statusCode);
    }

    final decoded = jsonDecode(utf8.decode(response.bodyBytes));
    if (decoded is! Map) {
      throw const JobRecommendApiException('추천 서버 응답 형식이 올바르지 않습니다.');
    }
    return Map<String, dynamic>.from(decoded);
  }

  static String _detail(http.Response response) {
    try {
      final body = jsonDecode(utf8.decode(response.bodyBytes));
      if (body is Map && body['detail'] != null) return body['detail'].toString();
    } catch (_) {
      // 본문이 JSON이 아니면 그대로 보여 준다.
    }
    final text = response.body.trim();
    return text.isEmpty ? '응답 본문 없음' : text;
  }
}
