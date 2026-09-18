import 'package:cloud_functions/cloud_functions.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/theme/app_colors.dart';
import '../../../core/theme/app_layout.dart';
import '../../../core/widgets/loading_widgets.dart';
import '../../../shared/demo/demo_accounts.dart';
import '../../../shared/demo/demo_lms_repository.dart';
import '../../../shared/models/assessment_model.dart';
import '../../../shared/providers/cohort_providers.dart';
import '../../../shared/providers/lms_providers.dart';
import '../../assessments/data/assessment_functions_service.dart';
import '../../assessments/presentation/widgets/assessment_question_view.dart';
import '../../../core/theme/app_space.dart';

/// 강사 — 제출 상세 + 문항별 점수 수정
class InstructorAssessmentSubmissionScreen extends ConsumerStatefulWidget {
  const InstructorAssessmentSubmissionScreen({
    super.key,
    required this.assessmentId,
    required this.submissionId,
    this.canEditScores = true,
  });

  final String assessmentId;
  final String submissionId;
  final bool canEditScores;

  @override
  ConsumerState<InstructorAssessmentSubmissionScreen> createState() =>
      _InstructorAssessmentSubmissionScreenState();
}

class _InstructorAssessmentSubmissionScreenState
    extends ConsumerState<InstructorAssessmentSubmissionScreen> {
  final Map<String, TextEditingController> _scoreCtrls = {};
  final _note = TextEditingController();
  var _saving = false;

  @override
  void dispose() {
    for (final c in _scoreCtrls.values) {
      c.dispose();
    }
    _note.dispose();
    super.dispose();
  }

  TextEditingController _ctrlFor(String qid, int score) {
    return _scoreCtrls.putIfAbsent(
      qid,
      () => TextEditingController(text: '$score'),
    );
  }

  Future<void> _save(
    AssessmentSubmissionModel submission,
    List<AssessmentQuestionModel> questions,
  ) async {
    final adjustments = <Map<String, dynamic>>[];
    for (final q in questions) {
      final entry = submission.answers[q.id];
      if (entry == null) continue;
      final next =
          int.tryParse(_scoreCtrls[q.id]?.text.trim() ?? '') ??
          entry.finalScore;
      if (next != entry.finalScore) {
        adjustments.add({'questionId': q.id, 'finalScore': next});
      }
    }
    if (adjustments.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('변경된 점수가 없습니다.')),
      );
      return;
    }

    final cohortId = ref.read(effectiveCohortIdProvider);
    final user = ref.read(currentUserSyncProvider);
    if (cohortId == null || user == null) return;

    setState(() => _saving = true);
    try {
      final repo = ref.read(lmsRepositoryProvider);
      if (DemoConfig.enabled && repo is DemoLmsRepository) {
        await repo.demoAdjustScores(
          submissionId: widget.submissionId,
          adjustments: adjustments,
          by: user.uid,
          byName: user.displayName,
          note: _note.text.trim().isEmpty ? null : _note.text.trim(),
        );
      } else {
        await ref
            .read(assessmentFunctionsServiceProvider)
            .adjustAssessmentScores(
              cohortId: cohortId,
              submissionId: widget.submissionId,
              adjustments: adjustments,
              note: _note.text.trim().isEmpty ? null : _note.text.trim(),
            );
      }
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('점수가 반영되었습니다.')),
      );
    } on FirebaseFunctionsException catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(e.message ?? e.code)),
      );
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('저장 실패: $e')),
      );
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final submissionAsync = ref.watch(
      assessmentSubmissionProvider(widget.submissionId),
    );
    final questionsAsync = ref.watch(
      assessmentQuestionsProvider(widget.assessmentId),
    );

    return Scaffold(
      backgroundColor: AppColors.surfaceVariant,
      appBar: AppBar(title: const Text('시험 결과')),
      body: submissionAsync.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => ErrorView(
          message: e.toString(),
          onRetry: () =>
              ref.invalidate(assessmentSubmissionProvider(widget.submissionId)),
        ),
        data: (submission) {
          if (submission == null) {
            return const EmptyView(
              message: '제출을 찾을 수 없습니다.',
              icon: Icons.search_off_rounded,
            );
          }
          return questionsAsync.when(
            loading: () => const Center(child: CircularProgressIndicator()),
            error: (e, _) => ErrorView(
              message: e.toString(),
              onRetry: () => ref.invalidate(
                assessmentQuestionsProvider(widget.assessmentId),
              ),
            ),
            data: (questions) {
              return Align(
                alignment: Alignment.topCenter,
                child: ConstrainedBox(
                  constraints: AppLayout.readingConstraints(),
                  child: ListView(
                    padding: EdgeInsets.fromLTRB(AppSpace.s(16), AppSpace.s(16), AppSpace.s(16), AppSpace.s(32)),
                    children: [
                      Card(
                        elevation: 0,
                        color: AppColors.surface,
                        shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(12),
                          side: BorderSide(color: AppColors.border),
                        ),
                        child: ListTile(
                          title: Text(
                            submission.userDisplayName,
                            style: const TextStyle(fontWeight: FontWeight.w700),
                          ),
                          subtitle: Text(
                            '총점 ${submission.totalScore}점 (자동 ${submission.autoTotalScore})',
                          ),
                        ),
                      ),
                      SizedBox(height: AppSpace.s(16)),
                      ...questions.asMap().entries.map((e) {
                        final q = e.value;
                        final ans = submission.answers[q.id];
                        final ctrl = _ctrlFor(q.id, ans?.finalScore ?? 0);
                        final selected = ans?.value is int
                            ? ans!.value as int
                            : int.tryParse('${ans?.value ?? ''}');
                        return Padding(
                          padding: EdgeInsets.only(bottom: AppSpace.s(20)),
                          child: AssessmentQuestionView(
                            number: e.key + 1,
                            prompt: q.prompt,
                            points: q.points,
                            type: q.type.value,
                            choices: q.choices,
                            correctIndex: q.correctIndex,
                            acceptedAnswers: q.acceptedAnswers,
                            explanation: q.explanation,
                            selectedIndex: selected,
                            shortAnswer:
                                q.type == AssessmentQuestionType.shortAnswer
                                ? '${ans?.value ?? ''}'
                                : null,
                            mode: AssessmentQuestionViewMode.review,
                            earnedScore: ans?.finalScore,
                            isCorrect: ans?.isCorrect,
                            footer: widget.canEditScores
                                ? Row(
                                    children: [
                                      Text(
                                        '자동 ${ans?.autoScore ?? 0} / 배점 ${q.points}',
                                        style: TextStyle(
                                          fontSize: 12,
                                          color: AppColors.textSecondary,
                                        ),
                                      ),
                                      const Spacer(),
                                      SizedBox(
                                        width: 88,
                                        child: TextField(
                                          controller: ctrl,
                                          keyboardType: TextInputType.number,
                                          decoration: const InputDecoration(
                                            isDense: true,
                                            labelText: '점수',
                                            border: OutlineInputBorder(),
                                          ),
                                        ),
                                      ),
                                    ],
                                  )
                                : null,
                          ),
                        );
                      }),
                      if (widget.canEditScores) ...[
                        TextField(
                          controller: _note,
                          decoration: InputDecoration(
                            labelText: '수정 사유 (선택)',
                            border: OutlineInputBorder(),
                            filled: true,
                            fillColor: AppColors.surface,
                          ),
                        ),
                        SizedBox(height: AppSpace.s(12)),
                        SizedBox(
                          width: double.infinity,
                          height: AppSpace.row(48),
                          child: FilledButton(
                            onPressed: _saving
                                ? null
                                : () => _save(submission, questions),
                            child: _saving
                                ? SizedBox(
                                    width: 18,
                                    height: 18,
                                    child: CircularProgressIndicator(
                                      strokeWidth: 2,
                                      color: Colors.white,
                                    ),
                                  )
                                : const Text('점수 저장'),
                          ),
                        ),
                      ],
                      if (submission.scoreAdjustments.isNotEmpty) ...[
                        SizedBox(height: AppSpace.s(24)),
                        const Text(
                          '수정 이력',
                          style: TextStyle(fontWeight: FontWeight.w700),
                        ),
                        ...submission.scoreAdjustments.reversed.map(
                          (h) => ListTile(
                            dense: true,
                            title: Text(
                              '${h.questionId}: ${h.previous} → ${h.next}',
                            ),
                            subtitle: Text(
                              '${h.byName ?? h.by}${h.note != null ? ' · ${h.note}' : ''}',
                            ),
                          ),
                        ),
                      ],
                    ],
                  ),
                ),
              );
            },
          );
        },
      ),
    );
  }
}
