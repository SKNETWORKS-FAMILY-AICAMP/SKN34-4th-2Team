import 'dart:async';
import 'dart:convert';

import 'package:http/http.dart' as http;

import '../../resume/ai_coach/data/job_recommend_api_client.dart';

/// 학생 챗봇 API 접속 설정.
///
/// 챗봇은 취업 코치 통합 서버(`app.integrated`, 기본 `127.0.0.1:8000`)에 포함되어
/// 있어 기본 주소를 추천 API와 공유한다. 챗봇만 따로 띄웠다면
/// `--dart-define=STUDENT_CHATBOT_API_URL=http://127.0.0.1:8001` 로 바꾼다.
abstract final class StudentChatbotApiConfig {
  static const baseUrl = String.fromEnvironment(
    'STUDENT_CHATBOT_API_URL',
    defaultValue: JobRecommendApiConfig.baseUrl,
  );
}

class StudentChatbotApiClient {
  StudentChatbotApiClient({
    required this.token,
    String? baseUrl,
    http.Client? client,
  }) : _baseUrl = (baseUrl ?? StudentChatbotApiConfig.baseUrl).replaceAll(
         RegExp(r'/+$'),
         '',
       ),
       _client = client ?? http.Client();

  final Future<String?> Function() token;
  final String _baseUrl;
  final http.Client _client;

  void close() => _client.close();

  StudentChatbotOps? lastOps;

  Future<void> initialize(String threadId) async {
    final http.Response response;
    try {
      response = await _client
          .post(
            Uri.parse('$_baseUrl/api/v1/student-chatbot/init'),
            headers: await _headers(),
            body: jsonEncode({'thread_id': threadId}),
          )
          .timeout(const Duration(seconds: 120));
    } on TimeoutException {
      throw const FormatException('챗봇 서버 응답이 지연되고 있습니다. 잠시 후 다시 시도해 주세요.');
    } on http.ClientException {
      throw const FormatException(
        '챗봇 서버에 연결하지 못했습니다. 통합 서버(8000)가 켜져 있는지 확인하세요.',
      );
    }
    if (response.statusCode != 200) {
      throw FormatException(_errorMessage(response.statusCode, response.body));
    }
  }

  Stream<String> ask({
    required String threadId,
    required String question,
  }) async* {
    lastOps = null;
    final request =
        http.Request(
            'POST',
            Uri.parse('$_baseUrl/api/v1/student-chatbot/stream'),
          )
          ..headers.addAll(await _headers())
          ..body = jsonEncode({'thread_id': threadId, 'question': question});

    final http.StreamedResponse response;
    try {
      response = await _client
          .send(request)
          .timeout(const Duration(seconds: 120));
    } on TimeoutException {
      throw const FormatException('챗봇 서버 응답이 지연되고 있습니다. 잠시 후 다시 시도해 주세요.');
    } on http.ClientException {
      throw const FormatException(
        '챗봇 서버에 연결하지 못했습니다. 통합 서버(8000)가 켜져 있는지 확인하세요.',
      );
    }
    if (response.statusCode != 200) {
      final body = await response.stream.bytesToString();
      throw FormatException(_errorMessage(response.statusCode, body));
    }

    await for (final line
        in response.stream
            .transform(utf8.decoder)
            .transform(const LineSplitter())
            .timeout(const Duration(seconds: 120))) {
      if (line.trim().isEmpty) continue;
      final event = jsonDecode(line);
      if (event is! Map<String, dynamic>) continue;
      if (event['type'] == 'token' && event['content'] is String) {
        yield event['content'] as String;
      } else if (event['type'] == 'error') {
        throw FormatException(event['message'] as String? ?? '답변 생성에 실패했습니다.');
      } else if (event['type'] == 'done') {
        lastOps = StudentChatbotOps.tryParse(event['ops']);
      }
    }
  }

  Future<Map<String, String>> _headers() async {
    final credential = await token();
    if (credential == null || credential.isEmpty) {
      throw const FormatException('실제 Firebase 로그인이 필요합니다.');
    }
    return {
      'Content-Type': 'application/json',
      'Authorization': 'Bearer $credential',
    };
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
      403 => '학생 계정만 챗봇을 사용할 수 있습니다.',
      422 => '학생의 기수 또는 질문 정보를 확인해 주세요.',
      503 => '챗봇 서버를 준비하지 못했습니다.',
      _ => '챗봇 요청에 실패했습니다. (HTTP $statusCode)',
    };
  }
}

class StudentChatbotOps {
  const StudentChatbotOps({
    required this.logId,
    this.promptVersion,
    this.route,
  });

  final String logId;
  final String? promptVersion;
  final String? route;

  static StudentChatbotOps? tryParse(Object? raw) {
    if (raw is! Map) return null;
    final logId = raw['logId']?.toString() ?? '';
    if (logId.isEmpty) return null;
    return StudentChatbotOps(
      logId: logId,
      promptVersion: raw['promptVersion']?.toString(),
      route: raw['route']?.toString(),
    );
  }
}
