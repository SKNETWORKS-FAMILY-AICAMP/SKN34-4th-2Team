import 'dart:typed_data';

import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/theme/app_colors.dart';
import '../../../shared/models/notice_model.dart';
import '../../../shared/providers/cohort_providers.dart';
import '../../../shared/providers/lms_providers.dart';
import '../../../shared/services/storage_service.dart';
import '../../hub/presentation/widgets/board_ui.dart';
import '../../../core/theme/app_space.dart';

/// 관리자 — 공지 작성/수정
class AdminNoticeFormScreen extends ConsumerStatefulWidget {
  const AdminNoticeFormScreen({super.key, this.noticeId});

  final String? noticeId;

  @override
  ConsumerState<AdminNoticeFormScreen> createState() =>
      _AdminNoticeFormScreenState();
}

class _AdminNoticeFormScreenState extends ConsumerState<AdminNoticeFormScreen> {
  final _titleController = TextEditingController();
  final _contentController = TextEditingController();
  var _isFavorite = false;
  var _loading = false;
  var _initialized = false;
  Uint8List? _imageBytes;
  String? _imageFileName;
  String? _imageUrl;

  bool get _isEdit => widget.noticeId != null;

  static const _borderless = InputDecoration(
    border: InputBorder.none,
    enabledBorder: InputBorder.none,
    focusedBorder: InputBorder.none,
    contentPadding: EdgeInsets.zero,
    isDense: true,
  );

  @override
  void dispose() {
    _titleController.dispose();
    _contentController.dispose();
    super.dispose();
  }

  void _loadNotice(List<NoticeModel> notices) {
    if (_initialized || widget.noticeId == null) return;
    final notice = notices.where((n) => n.id == widget.noticeId).firstOrNull;
    if (notice == null) return;
    _titleController.text = notice.title;
    _contentController.text = notice.content;
    _isFavorite = notice.isFavorite;
    _imageUrl = notice.imageUrl;
    _initialized = true;
  }

  Future<void> _pickImage() async {
    final picked = await FilePicker.pickFiles(
      type: FileType.image,
    );
    if (picked.isEmpty || !mounted) return;
    final file = picked.first;
    final bytes = await file.readAsBytes();
    if (!mounted) return;
    if (bytes.length > 5 * 1024 * 1024) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('이미지는 5MB 이하만 등록할 수 있습니다.')),
      );
      return;
    }
    setState(() {
      _imageBytes = bytes;
      _imageFileName = file.name;
    });
  }

  String _imageContentType(String fileName) {
    final extension = fileName.split('.').last.toLowerCase();
    return switch (extension) {
      'png' => 'image/png',
      'gif' => 'image/gif',
      'webp' => 'image/webp',
      _ => 'image/jpeg',
    };
  }

  Future<void> _save() async {
    final title = _titleController.text.trim();
    final content = _contentController.text.trim();
    if (title.isEmpty || content.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('제목과 내용을 입력해 주세요.')),
      );
      return;
    }

    final user = ref.read(currentUserSyncProvider);
    final cohortId = ref.read(effectiveCohortIdProvider);
    if (user == null || cohortId == null) return;

    setState(() => _loading = true);
    try {
      final repo = ref.read(lmsRepositoryProvider);
      var imageUrl = _imageUrl;
      if (_imageBytes != null && _imageFileName != null) {
        final storagePath = StorageService.noticeImagePath(
          cohortId: cohortId,
          userId: user.uid,
          fileName: _imageFileName!,
        );
        imageUrl = await ref.read(storageServiceProvider).uploadAndGetUrl(
          storagePath: storagePath,
          bytes: _imageBytes!,
          contentType: _imageContentType(_imageFileName!),
        );
      }
      final notice = NoticeModel(
        id: widget.noticeId ?? '',
        title: title,
        content: content,
        authorName: user.displayName,
        isFavorite: _isFavorite,
        imageUrl: imageUrl,
      );

      if (_isEdit) {
        await repo.updateNotice(
          cohortId: cohortId,
          notice: notice,
          authorId: user.uid,
          authorName: user.displayName,
        );
      } else {
        await repo.createNotice(
          cohortId: cohortId,
          notice: notice,
          authorId: user.uid,
          authorName: user.displayName,
        );
      }

      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(_isEdit ? '공지가 수정되었습니다.' : '공지가 등록되었습니다.')),
        );
        context.pop();
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('저장 실패: $e')),
        );
      }
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final notices = ref.watch(noticesStreamProvider);
    notices.whenData(_loadNotice);

    return Scaffold(
      backgroundColor: AppColors.surface,
      appBar: AppBar(
        elevation: 0,
        scrolledUnderElevation: 0,
        backgroundColor: AppColors.surface,
        foregroundColor: AppColors.textPrimary,
        title: Text(
          _isEdit ? '공지 수정' : '공지 작성',
          style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 16),
        ),
        bottom: PreferredSize(
          preferredSize: Size.fromHeight(1),
          child: Divider(height: 1, color: AppColors.border),
        ),
        actions: [
          IconButton(
            tooltip: _isFavorite ? '즐겨찾기 해제' : '즐겨찾기 (상단 고정)',
            onPressed: () => setState(() => _isFavorite = !_isFavorite),
            icon: Icon(
              _isFavorite ? Icons.star_rounded : Icons.star_outline_rounded,
              color: _isFavorite ? BoardUi.favorite : AppColors.textHint,
            ),
          ),
          Padding(
            padding: EdgeInsets.only(right: AppSpace.s(16)),
            child: FilledButton(
              onPressed: _loading ? null : _save,
              style: BoardUi.primaryButtonStyle(),
              child: _loading
                  ? SizedBox(
                      width: 18,
                      height: 18,
                      child: CircularProgressIndicator(
                        strokeWidth: 2,
                        color: Colors.white,
                      ),
                    )
                  : Text(_isEdit ? '수정 완료' : '공지 등록'),
            ),
          ),
        ],
      ),
      body: Align(
        alignment: Alignment.topCenter,
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: BoardUi.contentMaxWidth),
          child: Padding(
            padding: EdgeInsets.fromLTRB(AppSpace.s(32), AppSpace.s(24), AppSpace.s(32), AppSpace.s(32)),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                TextField(
                  controller: _titleController,
                  decoration: _borderless.copyWith(
                    hintText: '공지 제목을 입력하세요',
                    hintStyle: TextStyle(
                      fontSize: 22,
                      fontWeight: FontWeight.w700,
                      color: AppColors.textHint.withValues(alpha: 0.7),
                    ),
                  ),
                  style: TextStyle(
                    fontSize: 22,
                    fontWeight: FontWeight.w700,
                    color: AppColors.textPrimary,
                  ),
                ),
                SizedBox(height: AppSpace.s(16)),
                Divider(height: 1, color: AppColors.border),
                SizedBox(height: AppSpace.s(20)),
                Row(
                  children: [
                    OutlinedButton.icon(
                      onPressed: _loading ? null : _pickImage,
                      icon: const Icon(Icons.add_photo_alternate_outlined),
                      label: Text(
                        _imageBytes != null || _imageUrl != null
                            ? '사진 변경'
                            : '사진 추가',
                      ),
                    ),
                    if (_imageBytes != null || _imageUrl != null) ...[
                      SizedBox(width: AppSpace.s(8)),
                      TextButton.icon(
                        onPressed: _loading
                            ? null
                            : () => setState(() {
                                  _imageBytes = null;
                                  _imageFileName = null;
                                  _imageUrl = null;
                                }),
                        icon: const Icon(Icons.delete_outline),
                        label: const Text('사진 제거'),
                      ),
                    ],
                  ],
                ),
                Expanded(
                  child: SingleChildScrollView(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        TextField(
                          controller: _contentController,
                          decoration: _borderless.copyWith(
                            hintText: '학생에게 전달할 공지 내용을 작성하세요.',
                            hintStyle: TextStyle(
                              fontSize: 15,
                              color: AppColors.textHint,
                              height: 1.7,
                            ),
                            alignLabelWithHint: true,
                          ),
                          style: TextStyle(
                            fontSize: 15,
                            height: 1.7,
                            color: AppColors.textPrimary,
                          ),
                          minLines: 12,
                          maxLines: null,
                          textAlignVertical: TextAlignVertical.top,
                        ),
                        if (_imageBytes != null || _imageUrl != null) ...[
                          SizedBox(height: AppSpace.s(20)),
                          ClipRRect(
                            borderRadius: BorderRadius.circular(12),
                            child: _imageBytes != null
                                ? Image.memory(
                                    _imageBytes!,
                                    width: double.infinity,
                                    fit: BoxFit.contain,
                                  )
                                : Image.network(
                                    _imageUrl!,
                                    width: double.infinity,
                                    fit: BoxFit.contain,
                                    errorBuilder: (_, _, _) => Container(
                                      height: 120,
                                      alignment: Alignment.center,
                                      color: AppColors.surfaceVariant,
                                      child: const Text(
                                        '이미지를 불러오지 못했습니다.',
                                      ),
                                    ),
                                  ),
                          ),
                          SizedBox(height: AppSpace.s(16)),
                        ],
                      ],
                    ),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
