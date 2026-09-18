import 'dart:typed_data';

import 'package:firebase_auth/firebase_auth.dart';
import 'package:firebase_storage/firebase_storage.dart';

const _kMaxProfilePhotoBytes = 5 * 1024 * 1024;

/// 메모리 캐시 — AppBar/Drawer 중복 로드 방지
final Map<String, Uint8List> _profilePhotoBytesCache = {};

/// Firebase Storage에서 프로필 사진 bytes 로드 (정확한 path만, 1회)
class ProfilePhotoLoader {
  ProfilePhotoLoader(this._storage, this._auth);

  final FirebaseStorage _storage;
  final FirebaseAuth _auth;

  static void putCache(String key, Uint8List bytes) {
    if (bytes.isEmpty) return;
    _profilePhotoBytesCache[key] = bytes;
  }

  static Uint8List? getCache(String key) => _profilePhotoBytesCache[key];

  static void invalidate(String key) => _profilePhotoBytesCache.remove(key);

  Future<Uint8List?> load({
    required String uid,
    String? photoStoragePath,
    String? photoUrl,
  }) async {
    final path = photoStoragePath?.trim();
    final url = photoUrl?.trim();
    final cacheKey = (path != null && path.isNotEmpty)
        ? path
        : (url != null && url.isNotEmpty ? url : 'users/$uid/profile');

    final cached = _profilePhotoBytesCache[cacheKey];
    if (cached != null && cached.isNotEmpty) return cached;

    // 저장된 path/url이 없으면 추측 탐색하지 않음 (404 연쇄 = 수 초 지연)
    if ((path == null || path.isEmpty) && (url == null || url.isEmpty)) {
      return null;
    }

    await _waitForAuth();

    if (path != null && path.isNotEmpty) {
      try {
        final data = await _storage.ref(path).getData(_kMaxProfilePhotoBytes);
        if (data != null && data.isNotEmpty) {
          _profilePhotoBytesCache[cacheKey] = data;
          return data;
        }
      } catch (_) {
        // path 실패 시 URL fallback
      }
    }

    if (url != null && url.isNotEmpty) {
      try {
        final data =
            await _storage.refFromURL(url).getData(_kMaxProfilePhotoBytes);
        if (data != null && data.isNotEmpty) {
          _profilePhotoBytesCache[cacheKey] = data;
          return data;
        }
      } catch (_) {
        // 호출측에서 Image.network fallback
      }
    }

    return null;
  }

  Future<void> _waitForAuth() async {
    if (_auth.currentUser != null) return;

    try {
      await _auth
          .authStateChanges()
          .firstWhere((user) => user != null)
          .timeout(const Duration(seconds: 3));
    } catch (_) {
      // auth 대기 실패 — 호출측 fallback
    }
  }
}
