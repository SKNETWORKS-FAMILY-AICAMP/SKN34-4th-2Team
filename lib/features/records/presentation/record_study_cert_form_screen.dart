import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/constants/record_types.dart';
import '../../../core/utils/date_utils.dart';
import '../../../shared/models/submission_model.dart';
import '../../../shared/providers/cohort_providers.dart';
import '../../../shared/providers/lms_providers.dart';
import '../data/record_submission_helper.dart';
import 'widgets/record_file_upload.dart';
import 'widgets/record_page_layout.dart';
import '../../../core/theme/app_space.dart';

/// Pre-course study certification (Jesus student challenge)
class RecordStudyCertFormScreen extends ConsumerStatefulWidget {
  const RecordStudyCertFormScreen({super.key});

  @override
  ConsumerState<RecordStudyCertFormScreen> createState() =>
      _RecordStudyCertFormScreenState();
}

class _RecordStudyCertFormScreenState
    extends ConsumerState<RecordStudyCertFormScreen> {
  final _contentCtrl = TextEditingController();
  DateTime? _learningDate;
  List<PlatformFile> _files = [];
  bool _submitting = false;

  @override
  void dispose() {
    _contentCtrl.dispose();
    super.dispose();
  }

  Future<void> _pickDate() async {
    final picked = await showDatePicker(
      context: context,
      initialDate: _learningDate ?? DateTime.now(),
      firstDate: DateTime(2024),
      lastDate: DateTime(2030),
    );
    if (picked == null) return;
    setState(() => _learningDate = picked);
  }

  Future<void> _submit() async {
    final user = ref.read(currentUserSyncProvider);
    final cohortId = ref.read(effectiveCohortIdProvider);
    if (user == null || cohortId == null) return;

    final content = _contentCtrl.text.trim();
    if (_learningDate == null) {
      _snack('학습일자를 선택해 주세요.');
      return;
    }
    if (content.isEmpty) {
      _snack('학습한 내용을 입력해 주세요.');
      return;
    }
    if (_files.isEmpty) {
      _snack('날짜·시간이 보이는 인증 사진을 첨부해 주세요.');
      return;
    }

    setState(() => _submitting = true);
    try {
      final submissionId = newSubmissionId(ref);
      final urls = await uploadRecordFiles(
        ref: ref,
        cohortId: cohortId,
        userId: user.uid,
        submissionId: submissionId,
        files: _files,
      );
      final dateLabel = AppDateUtils.formatDisplay(_learningDate!);

      await submitRecord(
        ref: ref,
        submission: SubmissionModel(
          id: submissionId,
          userId: user.uid,
          userDisplayName: user.displayName,
          title: '학습인증 $dateLabel',
          type: RecordTypes.studyCert,
          status: 'pending',
          learningDate: _learningDate,
          learningContent: content,
          fileUrls: urls,
        ),
      );

      if (mounted) {
        _snack('제출되었습니다. 관리자 승인을 기다려 주세요.');
        context.go('/records');
      }
    } catch (e) {
      if (mounted) _snack('제출 실패: $e');
    } finally {
      if (mounted) setState(() => _submitting = false);
    }
  }

  void _snack(String msg) {
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(msg)));
  }

  @override
  Widget build(BuildContext context) {
    final user = ref.watch(currentUserSyncProvider);
    final cohortName = ref.watch(effectiveCohortNameProvider);
    if (user == null) {
      return const Center(child: Text('로그인이 필요합니다'));
    }

    return RecordPageScaffold(
      user: user,
      cohortName: cohortName,
      body: SingleChildScrollView(
        padding: EdgeInsets.only(bottom: AppSpace.s(24)),
        child: RecordFormPanel(
          title: '학습인증 제출',
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              RecordInfoBanner(
                message: RecordTypes.descriptions[RecordTypes.studyCert]!,
              ),
              SizedBox(height: AppSpace.s(20)),
              const RecordFieldLabel('학습일자'),
              OutlinedButton(
                onPressed: _pickDate,
                child: Text(
                  _learningDate == null
                      ? '날짜 선택'
                      : AppDateUtils.formatDisplay(_learningDate!),
                ),
              ),
              SizedBox(height: AppSpace.s(20)),
              const RecordFieldLabel('학습한 내용'),
              TextField(
                controller: _contentCtrl,
                maxLines: 4,
                decoration: recordInputDecoration(
                  hint: '오늘 학습한 주제 및 키워드',
                ),
              ),
              SizedBox(height: AppSpace.s(20)),
              const RecordFieldLabel('학습 인증 사진'),
              RecordFileUpload(
                files: _files,
                multiple: true,
                hint: '날짜·시간이 보이도록 교재/화면/필기 사진 첨부',
                onPick: () async {
                  final picked = await pickRecordFiles(multiple: true);
                  if (picked.isNotEmpty) {
                    setState(() => _files = [..._files, ...picked]);
                  }
                },
                onRemove: (i) => setState(() => _files.removeAt(i)),
              ),
            ],
          ),
          actions: RecordFormActions(
            onBack: () => context.pop(),
            onSubmit: _submit,
            submitting: _submitting,
          ),
        ),
      ),
    );
  }
}
