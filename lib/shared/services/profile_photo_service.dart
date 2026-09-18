import 'dart:typed_data';

import 'package:cloud_firestore/cloud_firestore.dart';
import 'package:file_picker/file_picker.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/constants/firestore_paths.dart';
import '../demo/demo_accounts.dart';
import '../demo/demo_session.dart';
import '../providers/firebase_providers.dart';
import '../providers/lms_providers.dart';
import 'profile_photo_loader.dart';
import 'storage_service.dart';

const _kMaxProfilePhotoBytes = 5 * 1024 * 1024;

class ProfilePhotoUploadResult {
  const ProfilePhotoUploadResult({
    required this.url,
    required this.storagePath,
    required this.bytes,
  });

  final String url;
  final String storagePath;
  final Uint8List bytes;
}

/// 프로필 사진 선택 · Storage 업로드 · Firestore URL 저장
class ProfilePhotoService {
  ProfilePhotoService(this._storage, this._lmsRepo, this._firestore);

  final StorageService _storage;
  final dynamic _lmsRepo;
  final FirebaseFirestore _firestore;

  /// 파일 선택만 (미리보기용 bytes 반환)
  Future<({Uint8List bytes, String extension})?> pickProfilePhotoBytes() async {
    final picked = await FilePicker.pickFiles(type: FileType.image);
    if (picked.isEmpty) return null;

    final file = picked.first;
    final bytes = await file.readAsBytes();
    if (bytes.isEmpty) {
      throw StateError('이미지 데이터를 읽을 수 없습니다.');
    }
    if (bytes.length > _kMaxProfilePhotoBytes) {
      throw StateError('프로필 사진은 5MB 이하만 업로드할 수 있습니다.');
    }

    return (bytes: bytes, extension: _normalizeExtension(file.extension));
  }

  /// Storage 업로드 + Firestore photoUrl / photoStoragePath 저장
  Future<ProfilePhotoUploadResult> uploadProfilePhoto({
    required String uid,
    required Uint8List bytes,
    required String extension,
  }) async {
    final ext = _normalizeExtension(extension);
    final contentType = _contentTypeForExtension(ext);
    final fileName = 'avatar.$ext';
    final storagePath = StorageService.profilePhotoPath(
      userId: uid,
      fileName: fileName,
    );

    final url = await _storage.uploadAndGetUrl(
      storagePath: storagePath,
      bytes: bytes,
      contentType: contentType,
    );

    ProfilePhotoLoader.putCache(storagePath, bytes);
    ProfilePhotoLoader.putCache(url, bytes);

    await _lmsRepo.updateProfile(
      uid: uid,
      photoUrl: url,
      photoStoragePath: storagePath,
    );

    await _verifyFirestoreSaved(uid: uid, url: url, storagePath: storagePath);

    if (DemoConfig.enabled) {
      final sessionUser = DemoSession.instance.currentUser;
      if (sessionUser != null && sessionUser.uid == uid) {
        DemoSession.instance.updateCurrentUser(
          sessionUser.copyWith(
            photoUrl: url,
            photoStoragePath: storagePath,
          ),
        );
      }
    }

    return ProfilePhotoUploadResult(
      url: url,
      storagePath: storagePath,
      bytes: bytes,
    );
  }

  Future<void> _verifyFirestoreSaved({
    required String uid,
    required String url,
    required String storagePath,
  }) async {
    final snap =
        await _firestore.collection(FirestorePaths.users).doc(uid).get();
    final data = snap.data();
    if (data == null) {
      throw StateError('사용자 프로필을 찾을 수 없습니다.');
    }
    final savedUrl = data['photoUrl'] as String?;
    final savedPath = data['photoStoragePath'] as String?;
    if (savedUrl != url || savedPath != storagePath) {
      throw StateError(
        '프로필 사진 정보가 Firestore에 저장되지 않았습니다. '
        '권한 설정을 확인해 주세요.',
      );
    }
  }

  static String _normalizeExtension(String? ext) {
    final normalized = (ext ?? 'jpg').toLowerCase();
    return switch (normalized) {
      'jpeg' => 'jpg',
      'jpg' || 'png' || 'webp' => normalized,
      _ => 'jpg',
    };
  }

  static String _contentTypeForExtension(String ext) {
    return switch (ext) {
      'png' => 'image/png',
      'webp' => 'image/webp',
      _ => 'image/jpeg',
    };
  }
}

final profilePhotoServiceProvider = Provider<ProfilePhotoService>((ref) {
  return ProfilePhotoService(
    ref.watch(storageServiceProvider),
    ref.watch(lmsRepositoryProvider),
    ref.watch(firestoreProvider),
  );
});
