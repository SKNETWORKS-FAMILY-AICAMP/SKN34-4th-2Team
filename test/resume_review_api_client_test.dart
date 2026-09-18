import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:playdata_lms/features/resume/ai_coach/data/resume_review_api_client.dart';
import 'package:playdata_lms/shared/models/resume_content.dart';

void main() {
  test(
    'uses bearer token and sends job ID, not a client job excerpt',
    () async {
      final client = ResumeReviewApiClient(
        baseUrl: 'http://localhost/resume-review',
        token: () async => 'test-token',
        client: MockClient((request) async {
          expect(request.url.path, '/resume-review/api/v1/resumes/reviews');
          expect(request.headers['Authorization'], 'Bearer test-token');
          final body = jsonDecode(request.body) as Map;
          expect(body['selected_job_id'], 'saramin:1');
          expect(body.containsKey('job_posting_text'), false);
          return http.Response('{"review_id":"r"}', 200);
        }),
      );
      expect(
        (await client.review({'selected_job_id': 'saramin:1'}))['review_id'],
        'r',
      );
      client.close();
    },
  );

  test('no login prevents network requests', () async {
    final client = ResumeReviewApiClient(
      token: () async => null,
      client: MockClient((_) async => throw StateError('must not call')),
    );
    await expectLater(client.context('c', 'r'), throwsFormatException);
    client.close();
  });

  test('draft comparison ignores map order but detects edits', () {
    final draft = ResumeContent.fromMap({
      'coreCompetencies': {'text': 'Python'},
      'projects': [],
    });
    expect(
      sameResumeContent(draft, {
        'projects': [],
        'coreCompetencies': {'text': 'Python'},
      }),
      true,
    );
    expect(
      sameResumeContent(draft, {
        'coreCompetencies': {'text': 'Java'},
      }),
      false,
    );
  });

  test('conflicts are errors, never a successful empty response', () async {
    final client = ResumeReviewApiClient(
      token: () async => 'test',
      client: MockClient(
        (_) async => http.Response('{"detail":"resume_version_changed"}', 409),
      ),
    );
    await expectLater(client.apply({}), throwsFormatException);
    client.close();
  });
}
