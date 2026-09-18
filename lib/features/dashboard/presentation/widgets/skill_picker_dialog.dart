import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../../core/constants/skill_catalog.dart';
import '../../../../core/theme/app_colors.dart';
import '../../../../shared/providers/lms_providers.dart';
import '../../../../core/theme/app_space.dart';

/// 스킬 선택 모달 — 검색 · 페이지 · 저장
Future<void> showSkillPickerDialog(
  BuildContext context,
  WidgetRef ref, {
  required String uid,
  required List<String> initialSkills,
}) async {
  await showDialog<void>(
    context: context,
    barrierDismissible: true,
    builder: (ctx) => _SkillPickerDialog(
      uid: uid,
      initialSkills: initialSkills,
      onSaved: () {
        if (ctx.mounted) Navigator.pop(ctx);
      },
    ),
  );
}

class _SkillPickerDialog extends ConsumerStatefulWidget {
  const _SkillPickerDialog({
    required this.uid,
    required this.initialSkills,
    required this.onSaved,
  });

  final String uid;
  final List<String> initialSkills;
  final VoidCallback onSaved;

  @override
  ConsumerState<_SkillPickerDialog> createState() => _SkillPickerDialogState();
}

class _SkillPickerDialogState extends ConsumerState<_SkillPickerDialog> {
  late Set<String> _selected;
  final _searchController = TextEditingController();
  String _query = '';
  int _page = 0;
  bool _saving = false;

  @override
  void initState() {
    super.initState();
    _selected = Set.from(widget.initialSkills);
    _searchController.addListener(() {
      setState(() {
        _query = _searchController.text;
        _page = 0;
      });
    });
  }

  @override
  void dispose() {
    _searchController.dispose();
    super.dispose();
  }

  List<String> get _filtered => SkillCatalog.search(_query);
  int get _totalPages => SkillCatalog.totalPages(_filtered);

  Future<void> _save() async {
    setState(() => _saving = true);
    try {
      await ref
          .read(lmsRepositoryProvider)
          .updateProfile(
            uid: widget.uid,
            skills: _selected.toList()..sort(),
          );
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('스킬이 저장되었습니다.')),
        );
        widget.onSaved();
      }
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
    final pageItems = SkillCatalog.pageItems(_filtered, _page);

    return Dialog(
      insetPadding: EdgeInsets.symmetric(horizontal: AppSpace.s(24), vertical: AppSpace.s(32)),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 560, maxHeight: 620),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Padding(
              padding: EdgeInsets.fromLTRB(AppSpace.s(20), AppSpace.s(16), AppSpace.s(8), AppSpace.s(0)),
              child: Row(
                children: [
                  const Text(
                    '스킬 선택',
                    style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
                  ),
                  const Spacer(),
                  IconButton(
                    onPressed: () => Navigator.pop(context),
                    icon: const Icon(Icons.close, size: 20),
                  ),
                ],
              ),
            ),
            Padding(
              padding: EdgeInsets.symmetric(horizontal: AppSpace.s(20)),
              child: Text(
                '사용할 수 있는 스킬을 선택해 주세요.',
                style: TextStyle(color: AppColors.textSecondary, fontSize: 13),
              ),
            ),
            Padding(
              padding: EdgeInsets.fromLTRB(AppSpace.s(20), AppSpace.s(16), AppSpace.s(20), AppSpace.s(8)),
              child: TextField(
                controller: _searchController,
                decoration: InputDecoration(
                  hintText: '스킬 검색',
                  prefixIcon: const Icon(Icons.search, size: 20),
                  isDense: true,
                  filled: true,
                  fillColor: AppColors.surfaceVariant,
                  border: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(10),
                    borderSide: BorderSide.none,
                  ),
                ),
              ),
            ),
            Padding(
              padding: EdgeInsets.symmetric(horizontal: AppSpace.s(20), vertical: AppSpace.s(4)),
              child: Row(
                children: [
                  Text(
                    '총 ${_filtered.length}개',
                    style: TextStyle(
                      fontSize: 12,
                      color: AppColors.textSecondary,
                    ),
                  ),
                  const Spacer(),
                  IconButton(
                    icon: const Icon(Icons.chevron_left, size: 20),
                    onPressed: _page > 0 ? () => setState(() => _page--) : null,
                  ),
                  Text(
                    '${_page + 1} / $_totalPages',
                    style: const TextStyle(fontSize: 12),
                  ),
                  IconButton(
                    icon: const Icon(Icons.chevron_right, size: 20),
                    onPressed: _page < _totalPages - 1
                        ? () => setState(() => _page++)
                        : null,
                  ),
                ],
              ),
            ),
            Expanded(
              child: pageItems.isEmpty
                  ? Center(
                      child: Text(
                        '검색 결과가 없습니다.',
                        style: TextStyle(color: AppColors.textHint),
                      ),
                    )
                  : SingleChildScrollView(
                      padding: EdgeInsets.symmetric(horizontal: AppSpace.s(20)),
                      child: Wrap(
                        spacing: 8,
                        runSpacing: 8,
                        children: pageItems.map((skill) {
                          final selected = _selected.contains(skill);
                          return FilterChip(
                            label: Text(skill),
                            selected: selected,
                            showCheckmark: false,
                            labelStyle: TextStyle(
                              fontSize: 13,
                              color: selected
                                  ? AppColors.textPrimary
                                  : AppColors.textSecondary,
                              fontWeight: selected
                                  ? FontWeight.w600
                                  : FontWeight.normal,
                            ),
                            selectedColor: AppColors.primaryLight,
                            backgroundColor: AppColors.surface,
                            side: BorderSide(
                              color: selected
                                  ? AppColors.textPrimary
                                  : AppColors.border,
                            ),
                            onSelected: (v) {
                              setState(() {
                                if (v) {
                                  _selected.add(skill);
                                } else {
                                  _selected.remove(skill);
                                }
                              });
                            },
                          );
                        }).toList(),
                      ),
                    ),
            ),
            if (_selected.isNotEmpty)
              Container(
                padding: EdgeInsets.symmetric(
                  horizontal: AppSpace.s(20),
                  vertical: AppSpace.s(8),
                ),
                decoration: BoxDecoration(
                  border: Border(top: BorderSide(color: AppColors.border)),
                ),
                child: Text(
                  '${_selected.length}개 선택됨',
                  style: TextStyle(
                    fontSize: 12,
                    color: AppColors.textSecondary,
                  ),
                ),
              ),
            Padding(
              padding: EdgeInsets.all(AppSpace.s(16)),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.end,
                children: [
                  OutlinedButton(
                    onPressed: _saving ? null : () => Navigator.pop(context),
                    child: const Text('취소'),
                  ),
                  SizedBox(width: AppSpace.s(8)),
                  FilledButton(
                    onPressed: _saving ? null : _save,
                    child: _saving
                        ? SizedBox(
                            width: 18,
                            height: 18,
                            child: CircularProgressIndicator(
                              strokeWidth: 2,
                              color: Colors.white,
                            ),
                          )
                        : const Text('완료'),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}
