import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/constants/record_types.dart';
import '../../../core/widgets/app_dropdown.dart';
import '../../../shared/models/submission_model.dart';
import '../../../shared/providers/cohort_providers.dart';
import '../../../shared/providers/lms_providers.dart';
import '../data/record_submission_helper.dart';
import 'widgets/record_file_upload.dart';
import 'widgets/record_page_layout.dart';
import '../../../core/theme/app_space.dart';

class RecordCertFormScreen extends ConsumerStatefulWidget {
  const RecordCertFormScreen({super.key});

  @override
  ConsumerState<RecordCertFormScreen> createState() =>
      _RecordCertFormScreenState();
}

class _RecordCertFormScreenState extends ConsumerState<RecordCertFormScreen> {
  final _titleCtrl = TextEditingController();
  String _certType = RecordTypes.certKinds.first;
  List<PlatformFile> _files = [];
  bool _submitting = false;

  @override
  void dispose() {
    _titleCtrl.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    final user = ref.read(currentUserSyncProvider);
    final cohortId = ref.read(effectiveCohortIdProvider);
    if (user == null || cohortId == null) return;

    final title = _titleCtrl.text.trim();
    if (title.isEmpty) {
      _snack('자격증 제목을 입력해 주세요.');
      return;
    }
    if (_files.isEmpty) {
      _snack('증빙 이미지를 첨부해 주세요.');
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

      await submitRecord(
        ref: ref,
        submission: SubmissionModel(
          id: submissionId,
          userId: user.uid,
          userDisplayName: user.displayName,
          title: title,
          type: RecordTypes.certification,
          status: 'pending',
          certType: _certType,
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
          title: '자격증 제출',
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              RecordInfoBanner(
                message: RecordTypes.descriptions[RecordTypes.certification]!,
              ),
              SizedBox(height: AppSpace.s(20)),
              const RecordFieldLabel('자격증 종류'),
              AppDropdownField<String>(
                value: _certType,
                decoration: recordInputDecoration(),
                items: [
                  for (final c in RecordTypes.certKinds)
                    AppDropdownItem(value: c, label: c),
                ],
                onChanged: (v) => setState(() => _certType = v ?? _certType),
              ),
              SizedBox(height: AppSpace.s(20)),
              const RecordFieldLabel('제목'),
              TextField(
                controller: _titleCtrl,
                decoration: recordInputDecoration(
                  hint: '예: Python Certified Entry Programmer',
                ),
              ),
              SizedBox(height: AppSpace.s(20)),
              const RecordFieldLabel('증빙 이미지'),
              RecordFileUpload(
                files: _files,
                onPick: () async {
                  final picked = await pickRecordFiles(multiple: false);
                  if (picked.isNotEmpty) setState(() => _files = picked);
                },
                onRemove: (_) => setState(() => _files = []),
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
