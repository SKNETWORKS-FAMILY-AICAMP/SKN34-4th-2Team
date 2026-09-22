import 'dart:async';
import 'dart:convert';

import 'package:http/http.dart' as http;

/// Django LMS API. Firestore를 보지 않는다.
class LmsApiClient {
  LmsApiClient({this.baseUrl = 'http://127.0.0.1:8000/api'});

  final String baseUrl;
  String firebaseUid = '';
  Map<String, dynamic> snapshot = {};
  final _refresh = StreamController<void>.broadcast();

  Stream<void> get changes => _refresh.stream;

  Map<String, String> get _headers => {
        'Content-Type': 'application/json',
        if (firebaseUid.isNotEmpty) 'X-Firebase-Uid': firebaseUid,
      };

  void bump() {
    if (!_refresh.isClosed) _refresh.add(null);
  }

  Future<Map<String, dynamic>> bootstrap() async {
    final response = await http.get(
      Uri.parse('$baseUrl/bootstrap'),
      headers: _headers,
    );
    if (response.statusCode >= 400) {
      throw StateError('bootstrap ${response.statusCode}');
    }
    snapshot = jsonDecode(utf8.decode(response.bodyBytes)) as Map<String, dynamic>;
    bump();
    return snapshot;
  }

  Future<Map<String, dynamic>> command(String op, [Map<String, dynamic>? payload]) async {
    final response = await http.post(
      Uri.parse('$baseUrl/command'),
      headers: _headers,
      body: jsonEncode({'op': op, 'payload': payload ?? {}}),
    );
    if (response.statusCode >= 400) {
      throw StateError('command $op ${response.statusCode}');
    }
    await bootstrap();
    if (response.body.isEmpty) return {'ok': true};
    return jsonDecode(utf8.decode(response.bodyBytes)) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> getJson(String path) async {
    final response = await http.get(Uri.parse('$baseUrl$path'), headers: _headers);
    if (response.statusCode >= 400) {
      throw StateError('GET $path ${response.statusCode}');
    }
    return jsonDecode(utf8.decode(response.bodyBytes)) as Map<String, dynamic>;
  }

  List<Map<String, dynamic>> list(String key) {
    final raw = snapshot[key];
    if (raw is! List) return const [];
    return raw.map((e) => Map<String, dynamic>.from(e as Map)).toList();
  }
}

final lmsApiClient = LmsApiClient();
