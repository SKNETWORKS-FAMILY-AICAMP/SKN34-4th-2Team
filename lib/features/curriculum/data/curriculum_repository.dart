import 'dart:typed_data';

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/utils/date_utils.dart';
import '../../../shared/data/lms_api_client.dart';
import '../../../shared/services/storage_service.dart'
    show StorageService, storageServiceProvider;
import '../models/curriculum_meta_model.dart';

const int kCurriculumPdfMaxBytes = 20 * 1024 * 1024;

class CurriculumRepository {
  CurriculumRepository(this._api, this._storage);

  final LmsApiClient _api;
  final StorageService _storage;

  Stream<CurriculumMetaModel?> watchMeta(String cohortId) async* {
    if (_api.snapshot.isEmpty) {
      try {
        await _api.bootstrap();
      } catch (_) {}
    }
    CurriculumMetaModel? pick() {
      final row = _api
          .list('curriculumPdfs')
          .where((item) => '${item['cohortId']}' == cohortId)
          .firstOrNull;
      if (row == null) return null;
      return CurriculumMetaModel(
        published: row['published'] == true,
        fullPdfUrl: row['fullPdfUrl'] as String?,
        fullPdfFileName: row['fullPdfFileName'] as String?,
        updatedAt: AppDateUtils.timestampToDateTime(row['updatedAt']),
        updatedBy: row['updatedBy']?.toString(),
      );
    }

    yield pick();
    await for (final _ in _api.changes) {
      yield pick();
    }
  }

  Future<String> uploadPdf({
    required String cohortId,
    required String fileName,
    required Uint8List bytes,
  }) async {
    if (bytes.length > kCurriculumPdfMaxBytes) {
      throw StateError('PDF는 20MB 이하만 업로드할 수 있습니다.');
    }
    final safeName = fileName.replaceAll(RegExp(r'[^\w.\-가-힣]'), '_');
    final path = 'cohorts/$cohortId/curriculum/full/$safeName';
    return _storage.uploadAndGetUrl(
      storagePath: path,
      bytes: bytes,
      contentType: 'application/pdf',
    );
  }

  Future<void> saveFullPdf({
    required String cohortId,
    required String pdfUrl,
    required String fileName,
    required String updatedBy,
  }) =>
      _api.command('saveCurriculumPdf', {
        'cohortId': cohortId,
        'pdfUrl': pdfUrl,
        'fileName': fileName,
      });

  Future<void> clearFullPdf({
    required String cohortId,
    required String updatedBy,
  }) =>
      _api.command('clearCurriculumPdf', {'cohortId': cohortId});
}

final curriculumRepositoryProvider = Provider<CurriculumRepository>((ref) {
  return CurriculumRepository(
    lmsApiClient,
    ref.watch(storageServiceProvider),
  );
});
