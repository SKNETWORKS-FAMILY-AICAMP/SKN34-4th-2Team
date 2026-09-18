import 'dart:async';
import 'dart:convert';

import 'package:http/http.dart' as http;

import '../../../../shared/models/resume_content.dart';
import 'job_recommend_api_client.dart';

Object? _sorted(Object? value) {
  if (value is Map) {
    final keys = value.keys.cast<String>().toList()..sort();
    return {for (final key in keys) key: _sorted(value[key])};
  }
  if (value is List) return value.map(_sorted).toList();
  return value;
}

bool sameResumeContent(ResumeContent draft, Map<String, dynamic> stored) =>
    jsonEncode(_sorted(draft.toMap())) ==
    jsonEncode(_sorted(ResumeContent.fromMap(stored).toMap()));

class ResumeReviewApiException extends FormatException {
  const ResumeReviewApiException(super.message, this.statusCode);
  final int statusCode;
}

class ResumeReviewApiClient {
  ResumeReviewApiClient({
    required this.token,
    String? baseUrl,
    http.Client? client,
  }) : _baseUrl =
           (baseUrl ??
                   const String.fromEnvironment(
                     'RESUME_REVIEW_API_URL',
                     defaultValue:
                         '${JobRecommendApiConfig.baseUrl}/resume-review',
                   ))
               .replaceAll(RegExp(r'/+$'), ''),
       _client = client ?? http.Client();

  final Future<String?> Function() token;
  final String _baseUrl;
  final http.Client _client;

  void close() => _client.close();

  Future<Map<String, dynamic>> context(
    String cohort,
    String resume, {
    String? job,
    String? tailoredResumeId,
  }) => _request(
    'GET',
    '/api/v1/resumes/review-context',
    query: {
      'cohort_id': cohort,
      'resume_id': resume,
      'job_id': ?job,
      'tailored_resume_id': ?tailoredResumeId,
    },
  );

  Future<Map<String, dynamic>> createTailoredResume(
    Map<String, dynamic> body,
  ) => _request('POST', '/api/v1/resumes/tailored', body: body);
  Future<List<Map<String, dynamic>>> listTailoredResumes(
    String cohortId,
    String resumeId,
  ) async {
    final response = await _requestJson(
      'GET',
      '/api/v1/resumes/$resumeId/tailored',
      query: {'cohort_id': cohortId},
    );
    return (response as List? ?? const [])
        .whereType<Map>()
        .map((item) => Map<String, dynamic>.from(item))
        .toList();
  }

  Future<Map<String, dynamic>> tailoredResume(
    String cohortId,
    String resumeId,
    String tailoredResumeId,
  ) => _request(
    'GET',
    '/api/v1/resumes/$resumeId/tailored/$tailoredResumeId',
    query: {'cohort_id': cohortId},
  );

  Future<void> saveTailoredSession(
    String cohortId,
    String resumeId,
    String tailoredResumeId,
    Map<String, dynamic> state,
  ) async {
    await _request(
      'PUT',
      '/api/v1/resumes/$resumeId/tailored/$tailoredResumeId/session',
      body: {'cohort_id': cohortId, 'state': state},
    );
  }

  Future<void> deleteTailoredResume(
    String cohortId,
    String resumeId,
    String tailoredResumeId,
  ) async {
    await _request(
      'DELETE',
      '/api/v1/resumes/$resumeId/tailored/$tailoredResumeId',
      query: {'cohort_id': cohortId},
    );
  }

  Future<String> promoteTailoredResume(
    String cohortId,
    String resumeId,
    String tailoredResumeId,
  ) async {
    final response = await _request(
      'POST',
      '/api/v1/resumes/$resumeId/tailored/$tailoredResumeId/promote',
      body: {'cohort_id': cohortId},
    );
    final workspaceId = response['workspace_resume_id'] as String?;
    if (workspaceId == null || workspaceId.isEmpty) {
      throw const FormatException('완료한 맞춤 이력서를 편집 화면으로 연결하지 못했습니다.');
    }
    return workspaceId;
  }

  Future<Map<String, dynamic>> review(Map<String, dynamic> body) =>
      _request('POST', '/api/v1/resumes/reviews', body: body);
  Future<Map<String, dynamic>> apply(Map<String, dynamic> body) =>
      _request('POST', '/api/v1/resumes/reviews/apply', body: body);
  Future<Map<String, dynamic>> undo(Map<String, dynamic> body) =>
      _request('POST', '/api/v1/resumes/reviews/undo', body: body);

  String _failureMessage(http.Response response) {
    String? detail;
    try {
      final payload = jsonDecode(utf8.decode(response.bodyBytes));
      if (payload is Map && payload['detail'] is String) {
        detail = payload['detail'] as String;
      }
    } on FormatException {
      // A non-JSON proxy error still receives a safe, generic message.
    }
    return switch ((response.statusCode, detail)) {
      (409, 'selected_job_closed') || (409, 'selected_job_expired') =>
        '선택한 공고가 마감되어 맞춤 첨삭을 할 수 없습니다. 다른 공고를 선택해 주세요.',
      (422, 'selected_job_full_text_unavailable') =>
        '이 공고는 상세 내용이 이미지뿐이라 원문 근거 첨삭을 할 수 없습니다. 텍스트 공고를 선택해 주세요.',
      (422, 'selected_job_deadline_unverified') =>
        '선택한 공고의 마감일 형식을 확인할 수 없습니다. 공고 원문을 확인하거나 다른 공고를 선택해 주세요.',
      (422, 'selected_job_not_found') =>
        '선택한 공고 원문을 찾을 수 없습니다. 추천 목록을 새로고침한 뒤 다시 선택해 주세요.',
      (422, 'invalid_selection') || (422, 'selection_not_applicable') =>
        '선택한 수정안이 현재 이력서 원문에 적용될 수 없습니다. 첨삭을 다시 실행해 주세요.',
      (422, 'unknown, duplicate or mismatched question') =>
        '이전 단계의 질문 상태를 확인하지 못했습니다. 창을 닫고 최신 이력서로 첨삭을 다시 시작해 주세요.',
      (409, 'resume_version_changed') ||
      (409, 'resume_version_changed: reload the resume and review') =>
        '수정안 적용으로 이력서가 갱신되었습니다. 기존 결과는 적용 전 내용 기준이므로 최신 이력서로 첨삭을 다시 시작해 주세요.',
      (409, 'resume_changed_after_application') =>
        '이력서가 적용 후 변경되어 되돌릴 수 없습니다. 최신 내용을 확인해 주세요.',
      // 앞서 적용한 수정안이 이 수정안의 원문을 바꿨다. 오류가 아니라 이미 다른 수정안으로 고친 문장이다.
      (409, 'ambiguous_or_masked_quote') || (409, 'overlapping_edits') =>
        '이 문장은 앞서 적용한 수정안으로 이미 바뀌어 이 수정안은 적용할 수 없어요. 건너뛰고 다음으로 넘어가 주세요.',
      (409, 'resume_item_changed') =>
        '이력서 항목 구성이 바뀌어 새 프로젝트를 추가할 수 없어요. 최신 이력서로 첨삭을 다시 시작해 주세요.',
      (401, _) => '로그인이 만료됐습니다. 다시 로그인해 주세요.',
      (403, _) => '본인 소유 이력서만 첨삭할 수 있습니다.',
      (404, _) => '이력서를 찾을 수 없습니다.',
      (409, _) => '이력서 또는 공고가 변경됐거나 요청이 처리 중입니다. 결과를 확인하고 다시 시도해 주세요.',
      (422, _) => '첨삭에 필요한 공고 원문 또는 선택한 수정안을 확인할 수 없습니다.',
      (503, _) => '첨삭 서버 설정 또는 공고 원문 DB를 사용할 수 없습니다. 서버 로그의 오류 유형을 확인해 주세요.',
      _ => '첨삭 요청에 실패했습니다 (HTTP ${response.statusCode}).',
    };
  }

  Future<Map<String, dynamic>> _request(
    String method,
    String path, {
    Map<String, dynamic>? body,
    Map<String, String>? query,
  }) async {
    final decoded = await _requestJson(method, path, body: body, query: query);
    if (decoded is! Map<String, dynamic>) {
      throw const FormatException('첨삭 응답 형식 오류');
    }
    return decoded;
  }

  Future<Object?> _requestJson(
    String method,
    String path, {
    Map<String, dynamic>? body,
    Map<String, String>? query,
  }) async {
    final credential = await token();
    if (credential == null || credential.isEmpty) {
      throw const FormatException('실제 Firebase 로그인이 필요합니다. 데모 계정은 사용할 수 없습니다.');
    }
    final uri = Uri.parse('$_baseUrl$path').replace(queryParameters: query);
    final headers = {
      'Content-Type': 'application/json',
      'Authorization': 'Bearer $credential',
    };
    final http.Response response;
    try {
      final encodedBody = body == null ? null : jsonEncode(body);
      response = await switch (method) {
        'GET' => _client.get(uri, headers: headers),
        'PUT' => _client.put(uri, headers: headers, body: encodedBody),
        'DELETE' => _client.delete(uri, headers: headers, body: encodedBody),
        _ => _client.post(uri, headers: headers, body: encodedBody),
      }.timeout(const Duration(seconds: 120));
    } on TimeoutException {
      throw const FormatException('응답 시간이 초과됐습니다. 재시도는 같은 요청 ID로 처리됩니다.');
    } on http.ClientException {
      throw const FormatException('첨삭 서버에 연결하지 못했습니다. 서버 주소와 실행 상태를 확인해 주세요.');
    }
    if (response.statusCode != 200) {
      throw ResumeReviewApiException(
        _failureMessage(response),
        response.statusCode,
      );
    }
    return jsonDecode(utf8.decode(response.bodyBytes));
  }
}
