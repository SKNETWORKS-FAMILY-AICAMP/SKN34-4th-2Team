import 'dart:convert';

import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/theme/app_colors.dart';
import '../../../core/theme/app_layout.dart';
import '../../../core/widgets/loading_widgets.dart';
import '../../../shared/demo/demo_accounts.dart';
import '../../../shared/models/curriculum_sheet_model.dart';
import '../../../shared/providers/cohort_providers.dart';
import '../../../shared/providers/lms_providers.dart';
import '../../../shared/services/storage_service.dart';
import '../../../shared/utils/curriculum_csv_parser.dart';
import '../../onboarding/domain/onboarding_target_registry.dart';
import '../../onboarding/instructor/instructor_onboarding_keys.dart';
import '../../../core/theme/app_space.dart';

/// 강사 — 커리큘럼 CSV 업로드 + 표 조회
class InstructorCurriculumScreen extends ConsumerStatefulWidget {
  const InstructorCurriculumScreen({super.key});

  @override
  ConsumerState<InstructorCurriculumScreen> createState() =>
      _InstructorCurriculumScreenState();
}

class _InstructorCurriculumScreenState
    extends ConsumerState<InstructorCurriculumScreen> {
  var _uploading = false;
  String _query = '';

  Future<void> _uploadCsv({String? replaceSheetId}) async {
    final cohortId = ref.read(effectiveCohortIdProvider);
    final user = ref.read(currentUserSyncProvider);
    if (cohortId == null || user == null) return;

    final picked = await FilePicker.pickFiles(
      type: FileType.custom,
      allowedExtensions: const ['csv'],
    );
    if (picked.isEmpty) return;
    final file = picked.first;
    final bytes = await file.readAsBytes();
    if (!mounted) return;

    String text;
    try {
      text = utf8.decode(bytes);
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('UTF-8로 읽을 수 없습니다. CSV를 UTF-8로 저장해 주세요. ($e)')),
      );
      return;
    }

    List<Map<String, dynamic>> parsed;
    try {
      parsed = CurriculumCsvParser.parse(text);
    } on FormatException catch (e) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(e.message)),
      );
      return;
    }

    final preview = parsed.take(10).toList();
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('CSV 미리보기'),
        content: SizedBox(
          width: 520,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text('${parsed.length}행 파싱됨. 상위 ${preview.length}행:'),
              SizedBox(height: AppSpace.s(8)),
              SizedBox(
                height: 220,
                child: ListView.builder(
                  itemCount: preview.length,
                  itemBuilder: (_, i) {
                    final r = preview[i];
                    return ListTile(
                      dense: true,
                      title: Text(
                        '${r['dayIndex']}. [${r['subject']}] ${r['topic']}',
                      ),
                      subtitle: Text('${r['dateLabel']}'),
                    );
                  },
                ),
              ),
            ],
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('취소'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('저장'),
          ),
        ],
      ),
    );
    if (confirmed != true || !mounted) return;

    setState(() => _uploading = true);
    try {
      final rows = parsed.map((m) => CurriculumRowModel.fromMap(m)).toList();
      var storagePath = '';
      if (!DemoConfig.enabled) {
        final tempId =
            replaceSheetId ?? DateTime.now().millisecondsSinceEpoch.toString();
        storagePath = StorageService.curriculumSheetCsvPath(
          cohortId: cohortId,
          sheetId: tempId,
          fileName: file.name,
        );
        await ref
            .read(storageServiceProvider)
            .uploadAndGetUrl(
              storagePath: storagePath,
              bytes: bytes,
              contentType: 'text/csv',
            );
      }

      final sheet = CurriculumSheetModel(
        id: '',
        title: file.name.replaceAll(
          RegExp(r'\.csv$', caseSensitive: false),
          '',
        ),
        fileName: file.name,
        rows: rows,
        uploadedBy: user.uid,
        uploadedByName: user.displayName,
        storagePath: storagePath.isEmpty ? null : storagePath,
      );

      await ref
          .read(lmsRepositoryProvider)
          .saveCurriculumSheet(
            cohortId: cohortId,
            sheet: sheet,
            replaceSheetId: replaceSheetId,
          );

      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('커리큘럼 ${rows.length}행이 저장되었습니다.')),
      );
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('업로드 실패: $e')),
      );
    } finally {
      if (mounted) setState(() => _uploading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final sheetAsync = ref.watch(latestCurriculumSheetProvider);

    return Scaffold(
      floatingActionButton: KeyedSubtree(
        key: OnboardingTargetRegistry.keyOf(
          InstructorOnboardingTargets.curriculumUpload,
        ),
        child: FloatingActionButton.extended(
          onPressed: _uploading
              ? null
              : () => _uploadCsv(
                  replaceSheetId: sheetAsync.asData?.value?.id,
                ),
          icon: _uploading
              ? const SizedBox(
                  width: 18,
                  height: 18,
                  child: CircularProgressIndicator(strokeWidth: 2),
                )
              : const Icon(Icons.upload_file),
          label: Text(
            sheetAsync.asData?.value == null ? 'CSV 등록' : 'CSV 교체',
          ),
        ),
      ),
      body: sheetAsync.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => ErrorView(
          message: e.toString(),
          onRetry: () => ref.invalidate(latestCurriculumSheetProvider),
        ),
        data: (sheet) {
          if (sheet == null) {
            return const EmptyView(
              message: '등록된 커리큘럼이 없습니다.\n구글시트에서 CSV로 내려받은 파일을 업로드하세요.',
              icon: Icons.table_chart_outlined,
            );
          }

          final q = _query.trim().toLowerCase();
          final rows = sheet.rows.where((r) {
            if (q.isEmpty) return true;
            return r.subject.toLowerCase().contains(q) ||
                r.topic.toLowerCase().contains(q) ||
                r.detail.toLowerCase().contains(q) ||
                r.dateLabel.toLowerCase().contains(q) ||
                '${r.dayIndex}'.contains(q);
          }).toList();

          return Align(
            alignment: Alignment.topCenter,
            child: ConstrainedBox(
              constraints: AppLayout.listConstraints(),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Padding(
                    padding: EdgeInsets.fromLTRB(AppSpace.s(16), AppSpace.s(12), AppSpace.s(16), AppSpace.s(8)),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          sheet.title,
                          style: const TextStyle(
                            fontSize: 16,
                            fontWeight: FontWeight.w700,
                          ),
                        ),
                        SizedBox(height: AppSpace.s(2)),
                        Text(
                          '${sheet.fileName} · ${sheet.rowCount}행'
                          '${sheet.uploadedAt != null ? ' · ${sheet.uploadedAt}' : ''}',
                          style: TextStyle(
                            color: AppColors.textSecondary,
                            fontSize: 12,
                          ),
                        ),
                        SizedBox(height: AppSpace.s(10)),
                        TextField(
                          onChanged: (v) => setState(() => _query = v),
                          decoration: InputDecoration(
                            hintText: '검색 (일수·교과목·내용)',
                            prefixIcon: const Icon(Icons.search, size: 20),
                            isDense: true,
                            filled: true,
                            fillColor: AppColors.surface,
                            contentPadding: EdgeInsets.symmetric(
                              vertical: AppSpace.s(10),
                            ),
                            border: OutlineInputBorder(
                              borderRadius: BorderRadius.circular(10),
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),
                  Expanded(
                    child: ListView.separated(
                      padding: EdgeInsets.fromLTRB(AppSpace.s(16), AppSpace.s(4), AppSpace.s(16), AppSpace.s(88)),
                      itemCount: rows.length,
                      separatorBuilder: (_, __) => SizedBox(height: AppSpace.s(6)),
                      itemBuilder: (context, i) {
                        final r = rows[i];
                        return Card(
                          elevation: 0,
                          margin: EdgeInsets.zero,
                          shape: RoundedRectangleBorder(
                            borderRadius: BorderRadius.circular(8),
                            side: BorderSide(color: AppColors.border),
                          ),
                          child: Theme(
                            data: Theme.of(context).copyWith(
                              dividerColor: Colors.transparent,
                            ),
                            child: ExpansionTile(
                              dense: true,
                              visualDensity: VisualDensity.compact,
                              tilePadding: EdgeInsets.symmetric(
                                horizontal: AppSpace.s(12),
                                vertical: AppSpace.s(0),
                              ),
                              childrenPadding: EdgeInsets.fromLTRB(
                                AppSpace.s(12),
                                AppSpace.s(0),
                                AppSpace.s(12),
                                AppSpace.s(12),
                              ),
                              title: Text(
                                '${r.dayIndex}. ${r.topic}',
                                style: const TextStyle(
                                  fontSize: 14,
                                  fontWeight: FontWeight.w600,
                                ),
                              ),
                              subtitle: Text(
                                '${r.dateLabel.isEmpty ? '' : '${r.dateLabel} · '}${r.subject}',
                                style: const TextStyle(fontSize: 11),
                              ),
                              children: [
                                Align(
                                  alignment: Alignment.centerLeft,
                                  child: Text(
                                    r.detailOrTopic,
                                    style: TextStyle(
                                      fontSize: 13,
                                      color: AppColors.textSecondary,
                                    ),
                                  ),
                                ),
                              ],
                            ),
                          ),
                        );
                      },
                    ),
                  ),
                ],
              ),
            ),
          );
        },
      ),
    );
  }
}
