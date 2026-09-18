import 'dart:async';
import 'dart:convert';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:http/http.dart' as http;

import '../../../shared/models/study_source_model.dart';
import '../../../shared/providers/firebase_providers.dart';
import '../../resume/ai_coach/data/job_recommend_api_client.dart';

/// 공부방 노트 API 접속 설정.
///
/// 노트 생성은 취업 코치 통합 서버(`app.integrated`, 기본 `127.0.0.1:8000`)가
/// `git clone`으로 강사 저장소를 읽고 LangGraph로 정리한다. GitHub REST API는
/// 쓰지 않는다. 기본 주소를 추천 API와 공유한다.
abstract final class StudyNotesApiConfig {
  static const baseUrl = String.fromEnvironment(
    'STUDY_NOTES_API_URL',
    defaultValue: JobRecommendApiConfig.baseUrl,
  );
}

class StudyNotesApiException implements Exception {
  const StudyNotesApiException(this.message, {this.statusCode});

  final String message;
  final int? statusCode;

  @override
  String toString() => message;
}

final studyNoteServiceProvider = Provider<StudyNoteService>((ref) {
  final auth = ref.watch(firebaseAuthProvider);
  return StudyNoteService(
    token: () async => await auth.currentUser?.getIdToken(),
  );
});

class StudyNoteService {
  StudyNoteService({
    required this.token,
    String? baseUrl,
    http.Client? client,
  }) : _baseUrl = (baseUrl ?? StudyNotesApiConfig.baseUrl).replaceAll(
         RegExp(r'/+$'),
         '',
       ),
       _client = client ?? http.Client();

  final Future<String?> Function() token;
  final String _baseUrl;
  final http.Client _client;

  Future<StudySourceTree> listTree({
    required String cohortId,
    required String sourceId,
  }) async {
    final data = await _post(
      '/api/v1/study-notes/tree',
      {'cohortId': cohortId, 'sourceId': sourceId},
      timeout: const Duration(seconds: 120),
    );
    return StudySourceTree.fromMap(data);
  }

  Future<StudyNoteModel> generate({
    required String cohortId,
    required String sourceId,
    required String scopeType,
    required Object scopeValue,
  }) async {
    final data = await _post(
      '/api/v1/study-notes/generate',
      {
        'cohortId': cohortId,
        'sourceId': sourceId,
        'scopeType': scopeType,
        'scopeValue': scopeValue,
      },
      timeout: const Duration(seconds: 540),
    );
    return StudyNoteModel.fromCallable(data);
  }

  Future<StudyNoteModel> getNote({
    required String cohortId,
    String? noteId,
    String? sourceId,
    String? scopeType,
    Object? scopeValue,
  }) async {
    final data = await _post(
      '/api/v1/study-notes/get',
      {
        'cohortId': cohortId,
        'noteId': ?noteId,
        'sourceId': ?sourceId,
        'scopeType': ?scopeType,
        'scopeValue': ?scopeValue,
      },
      timeout: const Duration(seconds: 60),
    );
    return StudyNoteModel.fromCallable(data);
  }

  Future<Map<String, dynamic>> _post(
    String path,
    Map<String, Object?> body, {
    required Duration timeout,
  }) async {
    if (_baseUrl.isEmpty) {
      throw const StudyNotesApiException(
        '공부방 서버 주소가 없습니다. 통합 서버(8000)를 띄워 주세요.',
      );
    }
    final credential = await token();
    if (credential == null || credential.isEmpty) {
      throw const StudyNotesApiException('실제 Firebase 로그인이 필요합니다.');
    }

    http.Response response;
    try {
      response = await _client
          .post(
            Uri.parse('$_baseUrl$path'),
            headers: {
              'Content-Type': 'application/json',
              'Authorization': 'Bearer $credential',
            },
            body: jsonEncode(body),
          )
          .timeout(timeout);
    } on TimeoutException {
      throw const StudyNotesApiException('공부방 서버 응답이 지연되고 있습니다. 잠시 후 다시 시도해 주세요.');
    } on http.ClientException {
      throw const StudyNotesApiException(
        '공부방 서버에 연결하지 못했습니다. 통합 서버(8000)가 켜져 있는지 확인하세요.',
      );
    } catch (error) {
      if (error is StudyNotesApiException) rethrow;
      throw const StudyNotesApiException(
        '공부방 서버에 연결하지 못했습니다. 통합 서버(8000)가 켜져 있는지 확인하세요.',
      );
    }

    if (response.statusCode == 200) {
      final decoded = jsonDecode(response.body);
      if (decoded is Map<String, dynamic>) return decoded;
      if (decoded is Map) return Map<String, dynamic>.from(decoded);
      throw const StudyNotesApiException('공부방 서버 응답 형식이 올바르지 않습니다.');
    }
    throw StudyNotesApiException(
      _errorMessage(response.statusCode, response.body),
      statusCode: response.statusCode,
    );
  }

  String _errorMessage(int statusCode, String body) {
    try {
      final decoded = jsonDecode(body);
      if (decoded is Map && decoded['detail'] is String) {
        return decoded['detail'] as String;
      }
    } catch (_) {}
    return switch (statusCode) {
      401 => '로그인이 만료됐습니다. 다시 로그인해 주세요.',
      403 => '이 기수의 공부방에 접근할 수 없습니다.',
      404 => '수업 저장소 또는 노트를 찾지 못했습니다.',
      409 => '비활성 수업 저장소입니다.',
      422 => '범위 또는 저장소 정보를 확인해 주세요.',
      502 => '수업 저장소를 읽지 못했습니다. 주소·브랜치·공개 여부를 확인하세요.',
      _ => '공부방 요청에 실패했습니다. (HTTP $statusCode)',
    };
  }
}

class StudySourceTree {
  const StudySourceTree({
    required this.dates,
    required this.entries,
    required this.truncated,
  });

  final List<String> dates;
  final List<String> entries;
  final bool truncated;

  factory StudySourceTree.fromMap(Map<String, dynamic> data) {
    final rawDates = data['dates'] as List? ?? [];
    final rawEntries = data['entries'] as List? ?? [];
    return StudySourceTree(
      dates: rawDates.map((e) => e.toString()).toList(),
      entries: rawEntries
          .whereType<Map>()
          .map((e) => Map<String, dynamic>.from(e)['path']?.toString() ?? '')
          .where((path) => path.isNotEmpty)
          .toList(),
      truncated: data['truncated'] == true,
    );
  }

  List<String> folders() {
    final folders = <String>{};
    for (final path in entries) {
      final slash = path.lastIndexOf('/');
      if (slash > 0) folders.add(path.substring(0, slash));
    }
    return folders.toList()..sort();
  }

  List<String> filesUnder(String prefix) {
    final base = prefix.replaceAll(RegExp(r'/+$'), '');
    return entries
        .where((path) => path == base || path.startsWith('$base/'))
        .toList();
  }
}
