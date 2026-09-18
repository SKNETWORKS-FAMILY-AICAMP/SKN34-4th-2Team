import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/constants/mission_rules.dart';
import '../../../core/constants/record_types.dart';
import '../../../shared/models/submission_model.dart';
import '../../../shared/providers/cohort_providers.dart';
import '../../../shared/providers/lms_providers.dart';
import '../data/record_submission_helper.dart';
import 'widgets/record_file_upload.dart';
import 'widgets/record_page_layout.dart';
import '../../../core/theme/app_space.dart';

/// Precourse quiz result submission
class RecordPrecourseQuizFormScreen extends ConsumerStatefulWidget {
  const RecordPrecourseQuizFormScreen({super.key});

  @override
  ConsumerState<RecordPrecourseQuizFormScreen> createState() =>
      _RecordPrecourseQuizFormScreenState();
}

class _RecordPrecourseQuizFormScreenState
    extends ConsumerState<RecordPrecourseQuizFormScreen> {
  final _titleCtrl = TextEditingController();
  final _scoreCtrl = TextEditingController();
  List<PlatformFile> _files = [];
  bool _submitting = false;

  @override
  void dispose() {
    _titleCtrl.dispose();
    _scoreCtrl.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    final user = ref.read(currentUserSyncProvider);
    final cohortId = ref.read(effectiveCohortIdProvider);
    if (user == null || cohortId == null) return;

    final title = _titleCtrl.text.trim();
    final score = int.tryParse(_scoreCtrl.text.trim());
    if (title.isEmpty) {
      _snack('회차/제목을 입력해 주세요. (예: 프리코스 1차)');
      return;
    }
    if (score == null || score < 0 || score > 100) {
      _snack('점수를 0~100 사이로 입력해 주세요.');
      return;
    }
    if (_files.isEmpty) {
      _snack('점수 확인용 증빙(캡처 등)을 첨부해 주세요.');
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
          type: RecordTypes.precourseQuiz,
          status: 'pending',
          quizScore: score,
          fileUrls: urls,
        ),
      );

      if (mounted) {
        final tip = score >= MissionRules.quizPassScore
            ? '제출되었습니다. 승인 시 60점↑ 통과 횟수에 반영됩니다.'
            : '제출되었습니다. ${MissionRules.quizPassScore}점 미만은 통과 횟수에 반영되지 않습니다.';
        _snack(tip);
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
          title: '프리코스 퀴즈 제출',
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              RecordInfoBanner(
                message: RecordTypes.descriptions[RecordTypes.precourseQuiz]!,
              ),
              SizedBox(height: AppSpace.s(20)),
              const RecordFieldLabel('회차 / 제목'),
              TextField(
                controller: _titleCtrl,
                decoration: recordInputDecoration(hint: '예: 프리코스 1차 쪽지시험'),
              ),
              SizedBox(height: AppSpace.s(20)),
              const RecordFieldLabel('점수 (0~100)'),
              TextField(
                controller: _scoreCtrl,
                keyboardType: TextInputType.number,
                decoration: recordInputDecoration(hint: '예: 80'),
              ),
              SizedBox(height: AppSpace.s(20)),
              const RecordFieldLabel('증빙'),
              RecordFileUpload(
                files: _files,
                multiple: true,
                hint: '점수 화면 캡처 등을 첨부해 주세요',
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
