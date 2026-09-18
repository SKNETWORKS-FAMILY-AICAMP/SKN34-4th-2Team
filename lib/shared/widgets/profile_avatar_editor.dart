import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../providers/cohort_providers.dart';
import '../providers/profile_photo_providers.dart';
import '../services/profile_photo_service.dart';
import 'profile_avatar.dart';

/// 탭 시 프로필 사진 업로드 — 로딩 상태 포함
class ProfileAvatarEditor extends ConsumerStatefulWidget {
  const ProfileAvatarEditor({
    super.key,
    required this.uid,
    this.photoUrl,
    this.photoStoragePath,
    required this.radius,
  });

  final String uid;
  final String? photoUrl;
  final String? photoStoragePath;
  final double radius;

  @override
  ConsumerState<ProfileAvatarEditor> createState() => _ProfileAvatarEditorState();
}

class _ProfileAvatarEditorState extends ConsumerState<ProfileAvatarEditor> {
  bool _uploading = false;
  Uint8List? _localPreview;

  Future<void> _pickPhoto() async {
    if (_uploading) return;
    if (ref.read(currentUserSyncProvider)?.isStudent != true) return;

    final service = ref.read(profilePhotoServiceProvider);
    try {
      final picked = await service.pickProfilePhotoBytes();
      if (picked == null || !mounted) return;

      setState(() {
        _localPreview = picked.bytes;
        _uploading = true;
      });
      setProfilePhotoPreview(ref, picked.bytes);

      await service.uploadProfilePhoto(
        uid: widget.uid,
        bytes: picked.bytes,
        extension: picked.extension,
      );

      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('프로필 사진이 저장되었습니다.')),
      );
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('업로드 실패: $e')),
        );
      }
    } finally {
      if (mounted) setState(() => _uploading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final canEdit = ref.watch(currentUserSyncProvider)?.isStudent == true;
    final globalPreview = ref.watch(profilePhotoPreviewProvider);
    final preview = _localPreview ?? globalPreview;

    return ProfileAvatar(
      radius: widget.radius,
      userId: widget.uid,
      photoUrl: widget.photoUrl,
      photoStoragePath: widget.photoStoragePath,
      previewBytes: preview,
      showEditBadge: canEdit,
      isUploading: _uploading,
      onTap: canEdit ? _pickPhoto : null,
    );
  }
}
