import 'package:file_picker/file_picker.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../features/auth/providers/auth_providers.dart';
import '../../../shared/demo/demo_accounts.dart';
import '../../../shared/models/submission_model.dart';
import '../../../shared/providers/cohort_providers.dart';
import '../../../shared/providers/firebase_providers.dart';
import '../../../shared/providers/lms_providers.dart';
import '../../../shared/services/storage_service.dart';

String newSubmissionId(WidgetRef ref) {
  final uid = ref.read(sessionUidProvider).value;
  if (DemoConfig.enabled && uid != null && DemoAccounts.isDemoUid(uid)) {
    return 'sub${DateTime.now().millisecondsSinceEpoch}';
  }
  return ref.read(firestoreProvider).collection('_ids').doc().id;
}

Future<List<String>> uploadRecordFiles({
  required WidgetRef ref,
  required String cohortId,
  required String userId,
  required String submissionId,
  required List<PlatformFile> files,
}) async {
  final uid = ref.read(sessionUidProvider).value;
  if (DemoConfig.enabled && uid != null && DemoAccounts.isDemoUid(uid)) {
    return files.map((f) => 'demo://${f.name}').toList();
  }

  final storage = ref.read(storageServiceProvider);
  final urls = <String>[];
  for (final file in files) {
    final bytes = await file.readAsBytes();
    final path = StorageService.recordSubmissionPath(
      cohortId: cohortId,
      userId: userId,
      submissionId: submissionId,
      fileName: file.name,
    );
    final url = await storage.uploadAndGetUrl(
      storagePath: path,
      bytes: bytes,
      contentType: _guessContentType(file.name),
    );
    urls.add(url);
  }
  return urls;
}

String _guessContentType(String name) {
  final lower = name.toLowerCase();
  if (lower.endsWith('.png')) return 'image/png';
  if (lower.endsWith('.jpg') || lower.endsWith('.jpeg')) return 'image/jpeg';
  if (lower.endsWith('.pdf')) return 'application/pdf';
  return 'application/octet-stream';
}

Future<void> submitRecord({
  required WidgetRef ref,
  required SubmissionModel submission,
}) async {
  final cohortId = ref.read(effectiveCohortIdProvider);
  if (cohortId == null) throw StateError('기수가 선택되지 않았습니다.');

  await ref.read(lmsRepositoryProvider).createSubmission(
        cohortId: cohortId,
        submission: submission,
      );
  ref.invalidate(mySubmissionsProvider);
  ref.invalidate(allSubmissionsProvider);
}
