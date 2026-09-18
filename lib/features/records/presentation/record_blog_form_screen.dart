import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/constants/record_types.dart';
import '../../../core/theme/app_colors.dart';
import '../../../shared/models/submission_model.dart';
import '../../../shared/providers/cohort_providers.dart';
import '../../../shared/providers/lms_providers.dart';
import '../data/record_submission_helper.dart';
import 'widgets/record_page_layout.dart';
import 'widgets/record_week_picker.dart';
import '../../../core/theme/app_space.dart';

class RecordBlogFormScreen extends ConsumerStatefulWidget {
  const RecordBlogFormScreen({super.key});

  @override
  ConsumerState<RecordBlogFormScreen> createState() =>
      _RecordBlogFormScreenState();
}

class _RecordBlogFormScreenState extends ConsumerState<RecordBlogFormScreen> {
  final _urlCtrl = TextEditingController();
  int? _selectedWeek;
  bool _submitting = false;

  @override
  void dispose() {
    _urlCtrl.dispose();
    super.dispose();
  }

  Set<int> _approvedWeeks(List<SubmissionModel> mine) {
    return mine
        .where((s) =>
            s.type == RecordTypes.blog &&
            s.isApproved &&
            s.weekNumber != null)
        .map((s) => s.weekNumber!)
        .toSet();
  }

  Future<void> _submit() async {
    final weeks = generateBlogWeeks();
    if (_selectedWeek == null) return;

    final week = weeks.firstWhere((w) => w.weekNumber == _selectedWeek);
    final user = ref.read(currentUserSyncProvider);
    final cohortId = ref.read(effectiveCohortIdProvider);
    if (user == null || cohortId == null) return;

    final url = _urlCtrl.text.trim();
    if (url.isEmpty) {
      _snack('블로그 URL을 입력해 주세요.');
      return;
    }
    if (!url.startsWith('http://') && !url.startsWith('https://')) {
      _snack('http:// 또는 https:// 로 시작하는 URL을 입력해 주세요.');
      return;
    }

    setState(() => _submitting = true);
    try {
      final submissionId = newSubmissionId(ref);
      await submitRecord(
        ref: ref,
        submission: SubmissionModel(
          id: submissionId,
          userId: user.uid,
          userDisplayName: user.displayName,
          title: '${week.label} 블로그',
          type: RecordTypes.blog,
          status: 'pending',
          weekNumber: week.weekNumber,
          weekLabel: week.label,
          link: url,
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
    final weeks = generateBlogWeeks();
    final mine = ref.watch(mySubmissionsProvider).value ?? [];
    final approved = _approvedWeeks(mine);

    if (user == null) {
      return const Center(child: Text('로그인이 필요합니다'));
    }

    return RecordPageScaffold(
      user: user,
      cohortName: cohortName,
      body: SingleChildScrollView(
        padding: EdgeInsets.only(bottom: AppSpace.s(24)),
        child: RecordFormPanel(
          title: '블로그 제출',
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              RecordInfoBanner(
                message: RecordTypes.descriptions[RecordTypes.blog]!,
              ),
              SizedBox(height: AppSpace.s(20)),
              const RecordFieldLabel('주차 선택'),
              RecordWeekPicker(
                weeks: weeks,
                approvedWeekNumbers: approved,
                selectedWeek: _selectedWeek,
                onSelected: (n) => setState(() => _selectedWeek = n),
              ),
              SizedBox(height: AppSpace.s(8)),
              Text(
                '승인된 주차는 다시 작성할 수 없습니다.',
                style: TextStyle(fontSize: 12, color: AppColors.textSecondary),
              ),
              SizedBox(height: AppSpace.s(20)),
              const RecordFieldLabel('링크'),
              TextField(
                controller: _urlCtrl,
                decoration: recordInputDecoration(hint: 'URL'),
                keyboardType: TextInputType.url,
              ),
            ],
          ),
          actions: RecordFormActions(
            onBack: () => context.pop(),
            onSubmit: _submit,
            submitting: _submitting,
            submitEnabled: _selectedWeek != null,
          ),
        ),
      ),
    );
  }
}
