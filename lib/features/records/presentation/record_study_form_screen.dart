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

class RecordStudyFormScreen extends ConsumerStatefulWidget {
  const RecordStudyFormScreen({super.key});

  @override
  ConsumerState<RecordStudyFormScreen> createState() =>
      _RecordStudyFormScreenState();
}

class _RecordStudyFormScreenState extends ConsumerState<RecordStudyFormScreen> {
  final _titleCtrl = TextEditingController();
  DateTime? _start;
  DateTime? _end;
  List<PlatformFile> _files = [];
  bool _submitting = false;
  bool _isTeamStudy = true;

  @override
  void dispose() {
    _titleCtrl.dispose();
    super.dispose();
  }

  Future<void> _pickDate({required bool isStart}) async {
    final initial =
        isStart ? (_start ?? DateTime.now()) : (_end ?? _start ?? DateTime.now());
    final picked = await showDatePicker(
      context: context,
      initialDate: initial,
      firstDate: DateTime(2024),
      lastDate: DateTime(2030),
    );
    if (picked == null) return;
    setState(() {
      if (isStart) {
        _start = picked;
        if (_end != null && _end!.isBefore(_start!)) _end = _start;
      } else {
        _end = picked;
      }
    });
  }

  Future<void> _submit() async {
    final user = ref.read(currentUserSyncProvider);
    final cohortId = ref.read(effectiveCohortIdProvider);
    if (user == null || cohortId == null) return;

    final title = _titleCtrl.text.trim();
    if (title.isEmpty) {
      _snack('스터디 제목을 입력해 주세요.');
      return;
    }
    if (_start == null || _end == null) {
      _snack('시작일과 종료일을 선택해 주세요.');
      return;
    }
    if (_files.isEmpty) {
      _snack('증빙 이미지를 1개 이상 첨부해 주세요.');
      return;
    }
    if (!_isTeamStudy) {
      _snack('개인 스터디는 마일리지 미션 대상이 아닙니다. 팀 스터디만 인정됩니다.');
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
          type: RecordTypes.study,
          status: 'pending',
          startAt: _start,
          endAt: _end,
          fileUrls: urls,
          isTeamStudy: true,
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
          title: '스터디 제출',
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              RecordInfoBanner(
                message: RecordTypes.descriptions[RecordTypes.study]!,
              ),
              SizedBox(height: AppSpace.s(12)),
              SwitchListTile(
                contentPadding: EdgeInsets.zero,
                title: const Text('팀 스터디입니다'),
                subtitle: const Text('개인 스터디는 미션 적립 대상이 아닙니다'),
                value: _isTeamStudy,
                onChanged: (v) => setState(() => _isTeamStudy = v),
              ),
              SizedBox(height: AppSpace.s(8)),
              const RecordFieldLabel('스터디 제목'),
              TextField(
                controller: _titleCtrl,
                decoration: recordInputDecoration(hint: '예: 알고리즘 스터디'),
              ),
              SizedBox(height: AppSpace.s(20)),
              const RecordFieldLabel('기간'),
              Row(
                children: [
                  Expanded(
                    child: OutlinedButton(
                      onPressed: () => _pickDate(isStart: true),
                      child: Text(
                        _start == null
                            ? '시작일'
                            : AppDateUtils.formatDisplay(_start!),
                      ),
                    ),
                  ),
                  Padding(
                    padding: EdgeInsets.symmetric(horizontal: AppSpace.s(8)),
                    child: Text('~'),
                  ),
                  Expanded(
                    child: OutlinedButton(
                      onPressed: () => _pickDate(isStart: false),
                      child: Text(
                        _end == null
                            ? '종료일'
                            : AppDateUtils.formatDisplay(_end!),
                      ),
                    ),
                  ),
                ],
              ),
              SizedBox(height: AppSpace.s(20)),
              const RecordFieldLabel('증빙 이미지'),
              RecordFileUpload(
                files: _files,
                multiple: true,
                hint: '오프라인 스터디 사진(날짜·시간 확인 가능)을 첨부해 주세요',
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
