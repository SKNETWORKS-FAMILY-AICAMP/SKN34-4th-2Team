import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/theme/app_colors.dart';
import '../../features/auth/providers/auth_providers.dart';
import '../providers/firebase_providers.dart';
import '../services/profile_photo_loader.dart';
import '../../core/theme/app_space.dart';

/// 프로필 사진 아바타 — 빈 상태 / 사진 / 수정 배지
class ProfileAvatar extends StatelessWidget {
  const ProfileAvatar({
    super.key,
    required this.radius,
    this.userId,
    this.photoUrl,
    this.photoStoragePath,
    this.previewBytes,
    this.showEditBadge = false,
    this.isUploading = false,
    this.onTap,
  });

  final double radius;
  final String? userId;
  final String? photoUrl;
  final String? photoStoragePath;
  final Uint8List? previewBytes;
  final bool showEditBadge;
  final bool isUploading;
  final VoidCallback? onTap;

  bool get _hasPhotoUrl => photoUrl != null && photoUrl!.trim().isNotEmpty;
  bool get _hasPreview => previewBytes != null && previewBytes!.isNotEmpty;
  bool get _hasStoragePath =>
      photoStoragePath != null && photoStoragePath!.trim().isNotEmpty;
  bool get _hasPhoto => _hasPreview || _hasPhotoUrl || _hasStoragePath;

  @override
  Widget build(BuildContext context) {
    final diameter = radius * 2;
    final badgeSize = (radius * 0.72).clamp(18.0, 24.0);

    Widget avatar = Container(
      width: diameter,
      height: diameter,
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        color: _hasPhoto
            ? AppColors.surfaceVariant
            : AppColors.surfaceVariant.withValues(alpha: 0.65),
        border: Border.all(
          color: _hasPhoto
              ? AppColors.border
              : AppColors.border.withValues(alpha: 0.9),
        ),
      ),
      clipBehavior: Clip.antiAlias,
      child: _buildInner(diameter),
    );

    if (showEditBadge && !isUploading) {
      avatar = Stack(
        clipBehavior: Clip.none,
        children: [
          avatar,
          Positioned(
            right: -2,
            bottom: -2,
            child: Container(
              width: badgeSize,
              height: badgeSize,
              decoration: BoxDecoration(
                color: AppColors.primary,
                shape: BoxShape.circle,
                border: Border.all(color: AppColors.surface, width: 2),
              ),
              child: Icon(
                _hasPhoto ? Icons.edit_outlined : Icons.add_a_photo_outlined,
                size: badgeSize * 0.55,
                color: Colors.white,
              ),
            ),
          ),
        ],
      );
    }

    if (isUploading) {
      avatar = Stack(
        alignment: Alignment.center,
        children: [
          avatar,
          Container(
            width: diameter,
            height: diameter,
            decoration: BoxDecoration(
              color: Colors.black.withValues(alpha: 0.35),
              shape: BoxShape.circle,
            ),
            child: Padding(
              padding: EdgeInsets.all(AppSpace.s(10)),
              child: CircularProgressIndicator(
                strokeWidth: 2,
                color: Colors.white,
              ),
            ),
          ),
        ],
      );
    }

    if (onTap == null) return avatar;

    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: isUploading ? null : onTap,
        customBorder: const CircleBorder(),
        child: avatar,
      ),
    );
  }

  Widget _buildInner(double diameter) {
    if (_hasPreview) {
      return Image.memory(
        previewBytes!,
        width: diameter,
        height: diameter,
        fit: BoxFit.cover,
        gaplessPlayback: true,
      );
    }
    // download URL이 있으면 브라우저/Image.network가 가장 빠름 (Storage 추측 탐색 X)
    if (_hasPhotoUrl) {
      return _NetworkProfileImage(
        photoUrl: photoUrl!,
        diameter: diameter,
        emptyPlaceholder: _emptyPlaceholder(diameter),
      );
    }
    if (_hasStoragePath && userId != null && userId!.isNotEmpty) {
      return _StorageProfileImage(
        userId: userId!,
        photoUrl: photoUrl,
        photoStoragePath: photoStoragePath,
        diameter: diameter,
        emptyPlaceholder: _emptyPlaceholder(diameter),
      );
    }
    return _emptyPlaceholder(diameter);
  }

  Widget _emptyPlaceholder(double diameter) {
    return Center(
      child: Icon(
        Icons.person_outline,
        size: diameter * 0.42,
        color: AppColors.textHint.withValues(alpha: 0.85),
      ),
    );
  }
}

/// photoStoragePath만 있을 때 Storage SDK로 1회 로드
class _StorageProfileImage extends ConsumerStatefulWidget {
  const _StorageProfileImage({
    required this.userId,
    required this.photoUrl,
    required this.photoStoragePath,
    required this.diameter,
    required this.emptyPlaceholder,
  });

  final String userId;
  final String? photoUrl;
  final String? photoStoragePath;
  final double diameter;
  final Widget emptyPlaceholder;

  @override
  ConsumerState<_StorageProfileImage> createState() =>
      _StorageProfileImageState();
}

class _StorageProfileImageState extends ConsumerState<_StorageProfileImage> {
  Uint8List? _bytes;
  bool _loading = true;
  bool _useNetworkFallback = false;

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void didUpdateWidget(covariant _StorageProfileImage oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.photoStoragePath != widget.photoStoragePath ||
        oldWidget.photoUrl != widget.photoUrl ||
        oldWidget.userId != widget.userId) {
      _bytes = null;
      _loading = true;
      _useNetworkFallback = false;
      _load();
    }
  }

  Future<void> _load() async {
    final path = widget.photoStoragePath?.trim();
    if (path != null && path.isNotEmpty) {
      final cached = ProfilePhotoLoader.getCache(path);
      if (cached != null) {
        if (!mounted) return;
        setState(() {
          _bytes = cached;
          _loading = false;
        });
        return;
      }
    }

    setState(() {
      _loading = true;
      _useNetworkFallback = false;
    });

    final loader = ProfilePhotoLoader(
      ref.read(firebaseStorageProvider),
      ref.read(firebaseAuthProvider),
    );

    final data = await loader.load(
      uid: widget.userId,
      photoStoragePath: widget.photoStoragePath,
      photoUrl: widget.photoUrl,
    );

    if (!mounted) return;

    if (data != null) {
      setState(() {
        _bytes = data;
        _loading = false;
      });
      return;
    }

    final hasUrl =
        widget.photoUrl != null && widget.photoUrl!.trim().isNotEmpty;
    setState(() {
      _bytes = null;
      _loading = false;
      _useNetworkFallback = hasUrl;
    });
  }

  @override
  Widget build(BuildContext context) {
    ref.listen(sessionUidProvider, (previous, next) {
      final nextUid = next.value;
      if (nextUid != null && _bytes == null && !_loading) {
        _load();
      }
    });

    if (_bytes != null) {
      return Image.memory(
        _bytes!,
        width: widget.diameter,
        height: widget.diameter,
        fit: BoxFit.cover,
        gaplessPlayback: true,
      );
    }

    if (_useNetworkFallback && widget.photoUrl != null) {
      return _NetworkProfileImage(
        photoUrl: widget.photoUrl!,
        diameter: widget.diameter,
        emptyPlaceholder: widget.emptyPlaceholder,
      );
    }

    if (_loading) {
      return Center(
        child: SizedBox(
          width: widget.diameter * 0.35,
          height: widget.diameter * 0.35,
          child: const CircularProgressIndicator(strokeWidth: 2),
        ),
      );
    }

    return widget.emptyPlaceholder;
  }
}

/// download URL 직접 표시 (브라우저 캐시 활용)
class _NetworkProfileImage extends StatelessWidget {
  const _NetworkProfileImage({
    required this.photoUrl,
    required this.diameter,
    required this.emptyPlaceholder,
  });

  final String photoUrl;
  final double diameter;
  final Widget emptyPlaceholder;

  @override
  Widget build(BuildContext context) {
    return Image.network(
      photoUrl,
      width: diameter,
      height: diameter,
      fit: BoxFit.cover,
      gaplessPlayback: true,
      webHtmlElementStrategy: kIsWeb
          ? WebHtmlElementStrategy.prefer
          : WebHtmlElementStrategy.never,
      errorBuilder: (context, error, stackTrace) => emptyPlaceholder,
      loadingBuilder: (context, child, progress) {
        if (progress == null) return child;
        return Center(
          child: SizedBox(
            width: diameter * 0.35,
            height: diameter * 0.35,
            child: const CircularProgressIndicator(strokeWidth: 2),
          ),
        );
      },
    );
  }
}
