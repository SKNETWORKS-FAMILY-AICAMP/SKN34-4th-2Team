import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../../core/theme/app_colors.dart';
import '../../../../core/widgets/loading_widgets.dart';
import '../../../../shared/models/study_source_model.dart';
import '../../../../shared/providers/cohort_providers.dart';
import '../../../../shared/providers/lms_providers.dart';
import '../../../../core/theme/app_space.dart';

class AdminStudySourcePanel extends ConsumerWidget {
  const AdminStudySourcePanel({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final sources = ref.watch(studySourcesProvider);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Row(
          children: [
            const Expanded(
              child: Text(
                '공부 소스',
                style: TextStyle(fontSize: 16, fontWeight: FontWeight.w700),
              ),
            ),
            FilledButton.icon(
              onPressed: () => _openForm(context, ref),
              icon: const Icon(Icons.add, size: 18),
              label: const Text('소스 추가'),
            ),
          ],
        ),
        SizedBox(height: AppSpace.s(8)),
        Text(
          '기수별 수업 저장소를 등록합니다. 공개 GitHub 저장소면 토큰 없이 됩니다. 학생은 활성 소스만 보고, 고른 범위만 정리합니다.',
          style: TextStyle(fontSize: 12, color: AppColors.textSecondary),
        ),
        SizedBox(height: AppSpace.s(12)),
        sources.when(
          loading: () => Padding(
            padding: EdgeInsets.all(AppSpace.s(24)),
            child: Center(child: CircularProgressIndicator()),
          ),
          error: (e, _) => ErrorView(message: e.toString()),
          data: (list) {
            if (list.isEmpty) {
              return Padding(
                padding: EdgeInsets.symmetric(vertical: AppSpace.s(12)),
                child: Text(
                  '등록된 수업 저장소가 없습니다',
                  style: TextStyle(color: AppColors.textSecondary),
                ),
              );
            }
            return Column(
              children: [
                for (final source in list) ...[
                  _SourceTile(
                    source: source,
                    onEdit: () => _openForm(context, ref, source: source),
                    onToggle: () => _toggle(context, ref, source),
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

  Future<void> _toggle(
    BuildContext context,
    WidgetRef ref,
    StudySourceModel source,
  ) async {
    final cohortId = ref.read(effectiveCohortIdProvider);
    if (cohortId == null) return;
    try {
      await ref
          .read(lmsRepositoryProvider)
          .updateStudySource(
            cohortId: cohortId,
            sourceId: source.id,
            updates: {'isActive': !source.isActive},
          );
    } catch (e) {
      if (!context.mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('변경 실패: $e')),
      );
    }
  }

  Future<void> _openForm(
    BuildContext context,
    WidgetRef ref, {
    StudySourceModel? source,
  }) async {
    final cohortId = ref.read(effectiveCohortIdProvider);
    if (cohortId == null) return;
    final saved = await showDialog<bool>(
      context: context,
      builder: (ctx) => _StudySourceFormDialog(
        source: source,
        onSubmit: (draft) async {
          final repo = ref.read(lmsRepositoryProvider);
          if (source == null) {
            final count =
                ref.read(studySourcesProvider).asData?.value.length ?? 0;
            await repo.createStudySource(
              cohortId: cohortId,
              source: StudySourceModel(
                id: '',
                title: draft.title,
                repoUrl: draft.repoUrl,
                branch: draft.branch,
                allowedPrefixes: draft.allowedPrefixes,
                isActive: draft.isActive,
                sortOrder: count,
              ),
            );
          } else {
            await repo.updateStudySource(
              cohortId: cohortId,
              sourceId: source.id,
              updates: draft.toFirestore(),
            );
          }
        },
      ),
    );
    if (saved == true && context.mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(source == null ? '소스를 추가했습니다.' : '소스를 수정했습니다.')),
      );
    }
  }
}

class _SourceTile extends StatelessWidget {
  const _SourceTile({
    required this.source,
    required this.onEdit,
    required this.onToggle,
  });

  final StudySourceModel source;
  final VoidCallback onEdit;
  final VoidCallback onToggle;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: EdgeInsets.symmetric(horizontal: AppSpace.s(12), vertical: AppSpace.s(10)),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: AppColors.border),
      ),
      child: Row(
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  source.title,
                  style: const TextStyle(fontWeight: FontWeight.w700),
                ),
                SizedBox(height: AppSpace.s(2)),
                Text(
                  source.repoLabel,
                  style: TextStyle(color: AppColors.textSecondary),
                ),
                Text(
                  '${source.branch} · ${source.prefixSummary}',
                  style: TextStyle(fontSize: 12, color: AppColors.textHint),
                ),
              ],
            ),
          ),
          Text(
            source.isActive ? '공개' : '비활성',
            style: TextStyle(
              color: source.isActive ? AppColors.success : AppColors.textHint,
              fontWeight: FontWeight.w600,
            ),
          ),
          IconButton(onPressed: onEdit, icon: const Icon(Icons.edit_outlined)),
          IconButton(
            onPressed: onToggle,
            tooltip: source.isActive ? '비활성화' : '공개',
            icon: Icon(
              source.isActive
                  ? Icons.visibility_off_outlined
                  : Icons.visibility_outlined,
            ),
          ),
        ],
      ),
    );
  }
}

class _StudySourceDraft {
  const _StudySourceDraft({
    required this.title,
    required this.repoUrl,
    required this.branch,
    required this.allowedPrefixes,
    required this.isActive,
  });

  final String title;
  final String repoUrl;
  final String branch;
  final List<String> allowedPrefixes;
  final bool isActive;

  Map<String, dynamic> toFirestore() {
    return StudySourceModel(
      id: '',
      title: title,
      repoUrl: repoUrl,
      branch: branch,
      allowedPrefixes: allowedPrefixes,
      isActive: isActive,
    ).toFirestore();
  }
}

class _StudySourceFormDialog extends StatefulWidget {
  const _StudySourceFormDialog({required this.onSubmit, this.source});

  final StudySourceModel? source;
  final Future<void> Function(_StudySourceDraft draft) onSubmit;

  @override
  State<_StudySourceFormDialog> createState() => _StudySourceFormDialogState();
}

class _StudySourceFormDialogState extends State<_StudySourceFormDialog> {
  final _formKey = GlobalKey<FormState>();
  late final TextEditingController _title;
  late final TextEditingController _url;
  late final TextEditingController _branch;
  late final TextEditingController _prefixes;
  late bool _active;
  bool _saving = false;

  @override
  void initState() {
    super.initState();
    final source = widget.source;
    _title = TextEditingController(text: source?.title ?? '');
    _url = TextEditingController(text: source?.repoUrl ?? '');
    _branch = TextEditingController(text: source?.branch ?? 'main');
    _prefixes = TextEditingController(
      text: source?.allowedPrefixes.join('\n') ?? '',
    );
    _active = source?.isActive ?? true;
  }

  @override
  void dispose() {
    _title.dispose();
    _url.dispose();
    _branch.dispose();
    _prefixes.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    if (!_formKey.currentState!.validate()) return;
    setState(() => _saving = true);
    try {
      await widget.onSubmit(
        _StudySourceDraft(
          title: _title.text.trim(),
          repoUrl: _url.text.trim(),
          branch: _branch.text.trim().isEmpty ? 'main' : _branch.text.trim(),
          allowedPrefixes: _prefixes.text
              .split('\n')
              .map((line) => line.trim())
              .where((line) => line.isNotEmpty)
              .toList(),
          isActive: _active,
        ),
      );
      if (mounted) Navigator.pop(context, true);
    } catch (e) {
      if (!mounted) return;
      setState(() => _saving = false);
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('저장 실패: $e')),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: Text(widget.source == null ? '공부 소스 추가' : '공부 소스 수정'),
      content: SizedBox(
        width: 480,
        child: Form(
          key: _formKey,
          child: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                TextFormField(
                  controller: _title,
                  decoration: const InputDecoration(labelText: '제목'),
                  validator: (value) => (value == null || value.trim().isEmpty)
                      ? '제목을 입력하세요.'
                      : null,
                ),
                SizedBox(height: AppSpace.s(12)),
                TextFormField(
                  controller: _url,
                  decoration: const InputDecoration(
                    labelText: 'GitHub URL',
                    hintText: 'https://github.com/owner/repo',
                  ),
                  validator: (value) =>
                      StudySourceModel.validateRepoUrl(value ?? ''),
                ),
                SizedBox(height: AppSpace.s(12)),
                TextFormField(
                  controller: _branch,
                  decoration: const InputDecoration(labelText: '브랜치'),
                ),
                SizedBox(height: AppSpace.s(12)),
                TextFormField(
                  controller: _prefixes,
                  minLines: 3,
                  maxLines: 6,
                  decoration: const InputDecoration(
                    labelText: '허용 폴더',
                    hintText: '한 줄에 하나. 비우면 날짜·파일로만 선택합니다.',
                    alignLabelWithHint: true,
                  ),
                ),
                SwitchListTile(
                  contentPadding: EdgeInsets.zero,
                  title: const Text('공개'),
                  value: _active,
                  onChanged: _saving
                      ? null
                      : (value) => setState(() => _active = value),
                ),
              ],
            ),
          ),
        ),
      ),
      actions: [
        TextButton(
          onPressed: _saving ? null : () => Navigator.pop(context, false),
          child: const Text('취소'),
        ),
        FilledButton(
          onPressed: _saving ? null : _save,
          child: Text(_saving ? '저장 중' : '저장'),
        ),
      ],
    );
  }
}
