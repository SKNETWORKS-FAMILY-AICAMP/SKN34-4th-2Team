import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../../core/constants/skill_catalog.dart';
import '../../../../core/theme/app_colors.dart';
import '../../../../shared/models/youtube_recommendation_model.dart';
import '../../../../shared/providers/cohort_providers.dart';
import '../../../../shared/providers/lms_providers.dart';
import '../../../../core/theme/app_space.dart';

/// 관리자 — YouTube 추천 영상 목록 + 등록/수정
class AdminYoutubeRecommendationPanel extends ConsumerWidget {
  const AdminYoutubeRecommendationPanel({super.key});

  Future<void> _openEditor(
    BuildContext context,
    WidgetRef ref, {
    YoutubeRecommendationModel? existing,
  }) async {
    await showDialog<void>(
      context: context,
      builder: (ctx) => _YoutubeRecommendationEditorDialog(existing: existing),
    );
  }

  Future<void> _confirmDelete(
    BuildContext context,
    WidgetRef ref,
    YoutubeRecommendationModel video,
  ) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('추천 영상 삭제'),
        content: Text('「${video.title}」을(를) 삭제할까요?'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('취소'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(ctx, true),
            style: FilledButton.styleFrom(backgroundColor: AppColors.error),
            child: const Text('삭제'),
          ),
        ],
      ),
    );
    if (ok != true || !context.mounted) return;

    final cohortId = ref.read(effectiveCohortIdProvider);
    if (cohortId == null) return;

    try {
      await ref
          .read(lmsRepositoryProvider)
          .deleteYoutubeRecommendation(
            cohortId: cohortId,
            videoId: video.id,
          );
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('삭제되었습니다.')),
        );
      }
    } catch (e) {
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('삭제 실패: $e')),
        );
      }
    }
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final videos = ref.watch(youtubeRecommendationsProvider);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Row(
          children: [
            const Expanded(
              child: Text(
                '관심사 YouTube 추천',
                style: TextStyle(
                  fontSize: 16,
                  fontWeight: FontWeight.w700,
                ),
              ),
            ),
            FilledButton.icon(
              onPressed: () => _openEditor(context, ref),
              icon: const Icon(Icons.add, size: 18),
              label: const Text('영상 등록'),
            ),
          ],
        ),
        SizedBox(height: AppSpace.s(8)),
        Text(
          '선택적 수동 큐레이션입니다. 학생 학습실 추천은 커리큘럼 주차 + YouTube API로 자동 표시됩니다.',
          style: TextStyle(fontSize: 12, color: AppColors.textSecondary),
        ),
        SizedBox(height: AppSpace.s(12)),
        videos.when(
          loading: () => Padding(
            padding: EdgeInsets.all(AppSpace.s(24)),
            child: Center(child: CircularProgressIndicator(strokeWidth: 2)),
          ),
          error: (e, _) => Text('오류: $e'),
          data: (list) {
            if (list.isEmpty) {
              return Container(
                padding: EdgeInsets.all(AppSpace.s(20)),
                decoration: BoxDecoration(
                  color: AppColors.surface,
                  borderRadius: BorderRadius.circular(14),
                  border: Border.all(color: AppColors.border),
                ),
                child: Text(
                  '등록된 추천 영상이 없습니다. 「영상 등록」으로 추가하세요.',
                  style: TextStyle(color: AppColors.textSecondary),
                ),
              );
            }
            return Column(
              children: [
                for (final v in list) ...[
                  _AdminVideoTile(
                    video: v,
                    onEdit: () => _openEditor(context, ref, existing: v),
                    onDelete: () => _confirmDelete(context, ref, v),
                    onTogglePublish: () async {
                      final cohortId = ref.read(effectiveCohortIdProvider);
                      if (cohortId == null) return;
                      await ref
                          .read(lmsRepositoryProvider)
                          .updateYoutubeRecommendation(
                            cohortId: cohortId,
                            videoId: v.id,
                            updates: {'isPublished': !v.isPublished},
                          );
                    },
                  ),
                  SizedBox(height: AppSpace.s(8)),
                ],
              ],
            );
          },
        ),
      ],
    );
  }
}

class _AdminVideoTile extends StatelessWidget {
  const _AdminVideoTile({
    required this.video,
    required this.onEdit,
    required this.onDelete,
    required this.onTogglePublish,
  });

  final YoutubeRecommendationModel video;
  final VoidCallback onEdit;
  final VoidCallback onDelete;
  final VoidCallback onTogglePublish;

  @override
  Widget build(BuildContext context) {
    final thumb = video.effectiveThumbnailUrl;
    return Container(
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: AppColors.border),
      ),
      child: ListTile(
        contentPadding: EdgeInsets.symmetric(horizontal: AppSpace.s(12), vertical: AppSpace.s(6)),
        leading: ClipRRect(
          borderRadius: BorderRadius.circular(8),
          child: thumb.isEmpty
              ? Container(
                  width: 64,
                  height: AppSpace.row(40),
                  color: AppColors.primaryLight,
                  child: Icon(Icons.videocam, color: AppColors.primary),
                )
              : Image.network(
                  thumb,
                  width: 64,
                  height: AppSpace.row(40),
                  fit: BoxFit.cover,
                  errorBuilder: (_, _, _) => Container(
                    width: 64,
                    height: AppSpace.row(40),
                    color: AppColors.primaryLight,
                    child: Icon(Icons.videocam, color: AppColors.primary),
                  ),
                ),
        ),
        title: Text(
          video.title,
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
          style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 14),
        ),
        subtitle: Text(
          [
            video.isPublished ? '공개' : '비공개',
            if (video.tags.isNotEmpty) video.tags.take(4).join(', '),
          ].join(' · '),
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
          style: const TextStyle(fontSize: 12),
        ),
        trailing: Wrap(
          spacing: 0,
          children: [
            IconButton(
              tooltip: video.isPublished ? '비공개로' : '공개로',
              onPressed: onTogglePublish,
              icon: Icon(
                video.isPublished
                    ? Icons.visibility_outlined
                    : Icons.visibility_off_outlined,
                size: 20,
                color: video.isPublished
                    ? AppColors.primary
                    : AppColors.textHint,
              ),
            ),
            IconButton(
              tooltip: '수정',
              onPressed: onEdit,
              icon: const Icon(Icons.edit_outlined, size: 20),
            ),
            IconButton(
              tooltip: '삭제',
              onPressed: onDelete,
              icon: Icon(
                Icons.delete_outline,
                size: 20,
                color: AppColors.error,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _YoutubeRecommendationEditorDialog extends ConsumerStatefulWidget {
  const _YoutubeRecommendationEditorDialog({this.existing});

  final YoutubeRecommendationModel? existing;

  @override
  ConsumerState<_YoutubeRecommendationEditorDialog> createState() =>
      _YoutubeRecommendationEditorDialogState();
}

class _YoutubeRecommendationEditorDialogState
    extends ConsumerState<_YoutubeRecommendationEditorDialog> {
  final _formKey = GlobalKey<FormState>();
  late final TextEditingController _title;
  late final TextEditingController _url;
  late final TextEditingController _description;
  late final TextEditingController _sortOrder;
  late final TextEditingController _tagSearch;
  late Set<String> _tags;
  late bool _isPublished;
  bool _saving = false;

  @override
  void initState() {
    super.initState();
    final e = widget.existing;
    _title = TextEditingController(text: e?.title ?? '');
    _url = TextEditingController(text: e?.youtubeUrl ?? '');
    _description = TextEditingController(text: e?.description ?? '');
    _sortOrder = TextEditingController(text: '${e?.sortOrder ?? 0}');
    _tagSearch = TextEditingController();
    _tags = {...?e?.tags};
    _isPublished = e?.isPublished ?? true;
  }

  @override
  void dispose() {
    _title.dispose();
    _url.dispose();
    _description.dispose();
    _sortOrder.dispose();
    _tagSearch.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    if (!_formKey.currentState!.validate()) return;
    final videoId = extractYoutubeVideoId(_url.text);
    if (videoId == null) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('올바른 YouTube URL을 입력하세요.')),
      );
      return;
    }
    if (_tags.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('태그를 1개 이상 선택하세요.')),
      );
      return;
    }

    final cohortId = ref.read(effectiveCohortIdProvider);
    if (cohortId == null) return;

    setState(() => _saving = true);
    try {
      final model = YoutubeRecommendationModel(
        id: widget.existing?.id ?? '',
        title: _title.text.trim(),
        youtubeUrl: _url.text.trim(),
        videoId: videoId,
        description: _description.text.trim(),
        tags: _tags.toList()..sort(),
        isPublished: _isPublished,
        sortOrder: int.tryParse(_sortOrder.text.trim()) ?? 0,
      );

      if (widget.existing == null) {
        await ref
            .read(lmsRepositoryProvider)
            .createYoutubeRecommendation(
              cohortId: cohortId,
              video: model,
            );
      } else {
        await ref
            .read(lmsRepositoryProvider)
            .updateYoutubeRecommendation(
              cohortId: cohortId,
              videoId: widget.existing!.id,
              updates: model.toFirestore(),
            );
      }
      if (mounted) Navigator.pop(context);
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('저장 실패: $e')),
        );
      }
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final query = _tagSearch.text.trim().toLowerCase();
    final suggestions = SkillCatalog.all
        .where((s) => !_tags.contains(s))
        .where((s) => query.isEmpty || s.toLowerCase().contains(query))
        .take(12)
        .toList();

    return AlertDialog(
      title: Text(widget.existing == null ? 'YouTube 영상 등록' : 'YouTube 영상 수정'),
      content: SizedBox(
        width: 480,
        child: Form(
          key: _formKey,
          child: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                TextFormField(
                  controller: _title,
                  decoration: const InputDecoration(labelText: '제목'),
                  validator: (v) =>
                      (v == null || v.trim().isEmpty) ? '제목을 입력하세요' : null,
                ),
                SizedBox(height: AppSpace.s(12)),
                TextFormField(
                  controller: _url,
                  decoration: const InputDecoration(
                    labelText: 'YouTube URL',
                    hintText: 'https://www.youtube.com/watch?v=...',
                  ),
                  validator: (v) =>
                      (v == null || v.trim().isEmpty) ? 'URL을 입력하세요' : null,
                ),
                SizedBox(height: AppSpace.s(12)),
                TextFormField(
                  controller: _description,
                  decoration: const InputDecoration(labelText: '설명 (선택)'),
                  maxLines: 2,
                ),
                SizedBox(height: AppSpace.s(12)),
                TextFormField(
                  controller: _sortOrder,
                  decoration: const InputDecoration(labelText: '정렬 순서'),
                  keyboardType: TextInputType.number,
                ),
                SizedBox(height: AppSpace.s(8)),
                SwitchListTile(
                  contentPadding: EdgeInsets.zero,
                  title: const Text('공개'),
                  value: _isPublished,
                  onChanged: (v) => setState(() => _isPublished = v),
                ),
                SizedBox(height: AppSpace.s(8)),
                const Text(
                  '태그 (학생 관심사와 매칭)',
                  style: TextStyle(fontWeight: FontWeight.w600, fontSize: 13),
                ),
                SizedBox(height: AppSpace.s(8)),
                if (_tags.isNotEmpty)
                  Wrap(
                    spacing: 6,
                    runSpacing: 6,
                    children: _tags
                        .map(
                          (t) => InputChip(
                            label: Text(t),
                            onDeleted: () => setState(() => _tags.remove(t)),
                          ),
                        )
                        .toList(),
                  ),
                SizedBox(height: AppSpace.s(8)),
                TextField(
                  controller: _tagSearch,
                  decoration: const InputDecoration(
                    hintText: '스킬 검색 후 추가',
                    prefixIcon: Icon(Icons.search, size: 20),
                    isDense: true,
                  ),
                  onChanged: (_) => setState(() {}),
                ),
                SizedBox(height: AppSpace.s(8)),
                Wrap(
                  spacing: 6,
                  runSpacing: 6,
                  children: suggestions
                      .map(
                        (s) => ActionChip(
                          label: Text(s, style: const TextStyle(fontSize: 12)),
                          onPressed: () => setState(() => _tags.add(s)),
                        ),
                      )
                      .toList(),
                ),
              ],
            ),
          ),
        ),
      ),
      actions: [
        TextButton(
          onPressed: _saving ? null : () => Navigator.pop(context),
          child: const Text('취소'),
        ),
        FilledButton(
          onPressed: _saving ? null : _save,
          child: _saving
              ? const SizedBox(
                  width: 18,
                  height: 18,
                  child: CircularProgressIndicator(strokeWidth: 2),
                )
              : const Text('저장'),
        ),
      ],
    );
  }
}
