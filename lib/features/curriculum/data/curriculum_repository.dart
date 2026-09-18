import 'dart:typed_data';

import 'package:cloud_firestore/cloud_firestore.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../shared/providers/firebase_providers.dart';
import '../../../shared/services/storage_service.dart'
    show StorageService, storageServiceProvider;
import '../models/curriculum_meta_model.dart';

const int kCurriculumPdfMaxBytes = 20 * 1024 * 1024;

class CurriculumRepository {
  CurriculumRepository(this._firestore, this._storage);

  final FirebaseFirestore _firestore;
  final StorageService _storage;

  DocumentReference<Map<String, dynamic>> _metaRef(String cohortId) =>
      _firestore
          .collection('cohorts')
          .doc(cohortId)
          .collection('curriculum')
          .doc('meta');

  Stream<CurriculumMetaModel?> watchMeta(String cohortId) {
    return _metaRef(cohortId).snapshots().map((doc) {
      if (!doc.exists) return null;
      return CurriculumMetaModel.fromFirestore(doc);
    });
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
  }) async {
    await _metaRef(cohortId).set(
      {
        'fullPdfUrl': pdfUrl,
        'fullPdfFileName': fileName,
        'published': true,
        'updatedAt': FieldValue.serverTimestamp(),
        'updatedBy': updatedBy,
      },
      SetOptions(merge: true),
    );
  }

  Future<void> clearFullPdf({
    required String cohortId,
    required String updatedBy,
  }) async {
    await _metaRef(cohortId).set(
      {
        'fullPdfUrl': FieldValue.delete(),
        'fullPdfFileName': FieldValue.delete(),
        'published': false,
        'updatedAt': FieldValue.serverTimestamp(),
        'updatedBy': updatedBy,
      },
      SetOptions(merge: true),
    );
  }
}

final curriculumRepositoryProvider = Provider<CurriculumRepository>((ref) {
  return CurriculumRepository(
    ref.watch(firestoreProvider),
    ref.watch(storageServiceProvider),
  );
});
