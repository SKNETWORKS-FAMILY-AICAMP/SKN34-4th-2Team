import 'package:cloud_functions/cloud_functions.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/routing/route_paths.dart';
import '../../../core/theme/app_colors.dart';
import '../../../core/theme/app_layout.dart';
import '../../../shared/demo/demo_accounts.dart';
import '../../../shared/demo/demo_lms_repository.dart';
import '../../../shared/models/assessment_model.dart';
import '../../../shared/providers/cohort_providers.dart';
import '../../../shared/providers/lms_providers.dart';
import '../data/assessment_functions_service.dart';
import 'widgets/assessment_question_view.dart';
import '../../../core/theme/app_space.dart';

/// 학생 — 결과 화면 (문항별 정답 리뷰)
class AssessmentResultScreen extends ConsumerStatefulWidget {
  const AssessmentResultScreen({super.key, required this.assessmentId});

  final String assessmentId;

  @override
  ConsumerState<AssessmentResultScreen> createState() =>
      _AssessmentResultScreenState();
}

class _AssessmentResultScreenState
    extends ConsumerState<AssessmentResultScreen> {
  var _loading = true;
  String? _error;
  List<AssessmentQuestionModel> _questions = [];
  Map<String, AssessmentAnswerEntry> _answers = {};
  int _totalScore = 0;
  int _autoTotal = 0;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _load());
  }

  int? _asInt(dynamic v) {
    if (v == null) return null;
    if (v is int) return v;
    if (v is num) return v.toInt();
    return int.tryParse('$v');
  }

  Map<String, dynamic> _asStringKeyedMap(dynamic raw) {
    if (raw is Map<String, dynamic>) return raw;
    if (raw is Map) {
      return raw.map((k, v) => MapEntry(k.toString(), v));
    }
    return <String, dynamic>{};
  }

  Future<void> _load() async {
    final cohortId = ref.read(effectiveCohortIdProvider);
    if (cohortId == null) {
      setState(() {
        _loading = false;
        _error = '기수 정보가 없습니다.';
      });
      return;
    }

    try {
      final repo = ref.read(lmsRepositoryProvider);
      if (DemoConfig.enabled && repo is DemoLmsRepository) {
        final qs = await repo
            .watchAssessmentQuestions(cohortId, widget.assessmentId)
            .first;
        final user = ref.read(currentUserSyncProvider);
        final subs = await repo
            .watchMyAssessmentSubmissions(cohortId, user!.uid)
            .first;
        final sub = subs
            .where((s) => s.assessmentId == widget.assessmentId)
            .firstOrNull;
        if (sub == null) {
          setState(() {
            _loading = false;
            _error = '제출 기록이 없습니다.';
          });
          return;
        }
        setState(() {
          _questions = qs;
          _answers = sub.answers;
          _totalScore = sub.totalScore;
          _autoTotal = sub.autoTotalScore;
          _loading = false;
        });
        return;
      }

      final data = await ref
          .read(assessmentFunctionsServiceProvider)
          .getAssessmentReview(
            cohortId: cohortId,
            assessmentId: widget.assessmentId,
          );
      final rawQs = data['questions'] as List? ?? [];
      final sub = _asStringKeyedMap(data['submission']);
      final rawAnswers = sub['answers'] as Map? ?? {};
      final answers = <String, AssessmentAnswerEntry>{};
      rawAnswers.forEach((k, v) {
        answers[k.toString()] = AssessmentAnswerEntry.fromMap(
          _asStringKeyedMap(v),
        );
      });

      setState(() {
        _questions = rawQs.asMap().entries.map((e) {
          final m = _asStringKeyedMap(e.value);
          return AssessmentQuestionModel.fromMap(
            m['id']?.toString() ?? 'q_${e.key}',
            m,
          );
        }).toList();
        _answers = answers;
        _totalScore = _asInt(sub['totalScore']) ?? 0;
        _autoTotal = _asInt(sub['autoTotalScore']) ?? 0;
        _loading = false;
      });
    } catch (e) {
      setState(() {
        _loading = false;
        if (e is FirebaseFunctionsException) {
          final msg = e.message?.trim();
          _error =
              (msg != null &&
                  msg.isNotEmpty &&
                  msg.toUpperCase() != 'INTERNAL' &&
                  !msg.toUpperCase().startsWith('INTERNAL '))
              ? msg
              : '결과를 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.';
        } else {
          _error = '결과를 불러오지 못했습니다.';
        }
      });
    }
  }

  void _leave() {
    if (context.canPop()) {
      context.pop();
    } else {
      context.go(RoutePaths.assessments);
    }
  }

  @override
  Widget build(BuildContext context) {
    final user = ref.watch(currentUserSyncProvider);
    final assessment = ref.watch(assessmentProvider(widget.assessmentId));

    return Scaffold(
      backgroundColor: AppColors.surfaceVariant,
      appBar: AppBar(title: const Text('평가 결과')),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : _error != null
          ? Center(child: Text(_error!))
          : Column(
              children: [
                Expanded(
                  child: ListView(
                    padding: EdgeInsets.fromLTRB(AppSpace.s(16), AppSpace.s(16), AppSpace.s(16), AppSpace.s(24)),
                    children: [
                      Align(
                        alignment: Alignment.topCenter,
                        heightFactor: 1,
                        child: ConstrainedBox(
                          constraints: const BoxConstraints(
                            maxWidth: AppLayout.reading,
                          ),
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.stretch,
                            children: [
                              Card(
                                elevation: 0,
                                color: AppColors.surface,
                                shape: RoundedRectangleBorder(
                                  borderRadius: BorderRadius.circular(12),
                                  side: BorderSide(
                                    color: AppColors.border,
                                  ),
                                ),
                                child: Padding(
                                  padding: EdgeInsets.all(AppSpace.s(20)),
                                  child: Column(
                                    children: [
                                      Text(
                                        assessment.asData?.value?.title ??
                                            '성취도평가',
                                        textAlign: TextAlign.center,
                                        style: const TextStyle(
                                          fontSize: 18,
                                          fontWeight: FontWeight.w700,
                                        ),
                                      ),
                                      SizedBox(height: AppSpace.s(8)),
                                      Text(
                                        user?.displayName ?? '',
                                        style: TextStyle(
                                          color: AppColors.textSecondary,
                                        ),
                                      ),
                                      SizedBox(height: AppSpace.s(16)),
                                      Text(
                                        '$_totalScore / ${assessment.asData?.value?.maxScore ?? '-'}',
                                        style: const TextStyle(
                                          fontSize: 36,
                                          fontWeight: FontWeight.w800,
                                        ),
                                      ),
                                      SizedBox(height: AppSpace.s(4)),
                                      Text(
                                        '자동채점 $_autoTotal점'
                                        '${_totalScore != _autoTotal ? ' · 조정 반영' : ''}',
                                        style: TextStyle(
                                          color: AppColors.textSecondary,
                                          fontSize: 13,
                                        ),
                                      ),
                                    ],
                                  ),
                                ),
                              ),
                              SizedBox(height: AppSpace.s(20)),
                              const Text(
                                '문항별 결과',
                                style: TextStyle(
                                  fontWeight: FontWeight.w700,
                                  fontSize: 16,
                                ),
                              ),
                              SizedBox(height: AppSpace.s(12)),
                              ..._questions.asMap().entries.map((e) {
                                final q = e.value;
                                final ans = _answers[q.id];
                                final selected = _asInt(ans?.value);
                                return Padding(
                                  padding: EdgeInsets.only(
                                    bottom: AppSpace.s(20),
                                  ),
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
                                        q.type ==
                                            AssessmentQuestionType.shortAnswer
                                        ? '${ans?.value ?? ''}'
                                        : null,
                                    mode: AssessmentQuestionViewMode.review,
                                    earnedScore: ans?.finalScore,
                                    isCorrect: ans?.isCorrect,
                                  ),
                                );
                              }),
                            ],
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
                Material(
                  color: AppColors.surface,
                  elevation: 6,
                  child: SafeArea(
                    top: false,
                    child: Padding(
                      padding: EdgeInsets.fromLTRB(AppSpace.s(16), AppSpace.s(10), AppSpace.s(16), AppSpace.s(12)),
                      child: Align(
                        alignment: Alignment.center,
                        heightFactor: 1,
                        child: ConstrainedBox(
                          constraints: const BoxConstraints(
                            maxWidth: AppLayout.reading,
                          ),
                          child: SizedBox(
                            width: double.infinity,
                            height: AppSpace.row(48),
                            child: FilledButton(
                              onPressed: _leave,
                              child: const Text('확인 · 나가기'),
                            ),
                          ),
                        ),
                      ),
                    ),
                  ),
                ),
              ],
            ),
    );
  }
}
