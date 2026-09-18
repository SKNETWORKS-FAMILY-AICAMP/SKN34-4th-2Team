import 'dart:typed_data';

import 'package:flutter_riverpod/flutter_riverpod.dart';

class ProfilePhotoPreviewNotifier extends Notifier<Uint8List?> {
  @override
  Uint8List? build() => null;

  void setPreview(Uint8List bytes) => state = bytes;

  void clearPreview() => state = null;
}

/// 업로드 직후 · 네트워크 로드 전 로컬 미리보기 (Web CORS 대응)
final profilePhotoPreviewProvider =
    NotifierProvider<ProfilePhotoPreviewNotifier, Uint8List?>(
  ProfilePhotoPreviewNotifier.new,
);

void clearProfilePhotoPreview(WidgetRef ref) {
  ref.read(profilePhotoPreviewProvider.notifier).clearPreview();
}

void setProfilePhotoPreview(WidgetRef ref, Uint8List bytes) {
  ref.read(profilePhotoPreviewProvider.notifier).setPreview(bytes);
}
