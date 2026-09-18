import 'dart:typed_data';

import 'package:firebase_storage/firebase_storage.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../providers/firebase_providers.dart';

/// Firebase Storage 업로드 서비스 — 진행률 콜백 지원
class StorageService {
  StorageService(this._storage);

  final FirebaseStorage _storage;

  Stream<double> uploadFile({
    required String storagePath,
    required Uint8List bytes,
    required String contentType,
  }) async* {
    final ref = _storage.ref(storagePath);
    final uploadTask = ref.putData(
      bytes,
      SettableMetadata(contentType: contentType),
    );

    await for (final snapshot in uploadTask.snapshotEvents) {
      if (snapshot.totalBytes == 0) continue;
      yield snapshot.bytesTransferred / snapshot.totalBytes;
    }
  }

  Future<String> getDownloadUrl(String storagePath) async {
    return _storage.ref(storagePath).getDownloadURL();
  }

  Future<String> uploadAndGetUrl({
    required String storagePath,
    required Uint8List bytes,
    required String contentType,
  }) async {
    final ref = _storage.ref(storagePath);
    await ref.putData(bytes, SettableMetadata(contentType: contentType));
    return ref.getDownloadURL();
  }

  static String recordSubmissionPath({
    required String cohortId,
    required String userId,
    required String submissionId,
    required String fileName,
  }) =>
      'cohorts/$cohortId/records/$userId/$submissionId/$fileName';

  static String assignmentPath({
    required String cohortId,
    required String assignmentId,
    required String userId,
    required String fileName,
  }) =>
      'cohorts/$cohortId/assignments/$assignmentId/submissions/$userId/$fileName';

  static String assessmentThumbnailPath({
    required String cohortId,
    required String assessmentId,
    required String fileName,
  }) =>
      'cohorts/$cohortId/assessments/$assessmentId/thumbnails/$fileName';

  static String noticeImagePath({
    required String cohortId,
    required String userId,
    required String fileName,
  }) =>
      'cohorts/$cohortId/notices/$userId/${DateTime.now().millisecondsSinceEpoch}_$fileName';

  static String curriculumSheetCsvPath({
    required String cohortId,
    required String sheetId,
    required String fileName,
  }) =>
      'cohorts/$cohortId/curriculumSheets/$sheetId/$fileName';

  static String profilePhotoPath({
    required String userId,
    required String fileName,
  }) =>
      'users/$userId/profile/$fileName';
}

final storageServiceProvider = Provider<StorageService>((ref) {
  return StorageService(ref.watch(firebaseStorageProvider));
});
