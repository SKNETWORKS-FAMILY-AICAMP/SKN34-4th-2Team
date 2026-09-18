import 'package:cloud_functions/cloud_functions.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/routing/route_paths.dart';
import '../../../core/theme/app_colors.dart';
import '../../../core/theme/app_layout.dart';
import '../../../shared/demo/demo_accounts.dart';
import '../../../shared/demo/demo_lms_repository.dart';
import '../../../shared/providers/cohort_providers.dart';
import '../../../shared/providers/lms_providers.dart';
import '../data/assessment_functions_service.dart';
import 'widgets/assessment_question_view.dart';
import '../../../core/theme/app_space.dart';

/// 학생 응시 화면
class AssessmentTakeScreen extends ConsumerStatefulWidget {
  const AssessmentTakeScreen({super.key, required this.assessmentId});

  final String assessmentId;

  @override
  ConsumerState<AssessmentTakeScreen> createState() =>
      _AssessmentTakeScreenState();
}

class _AssessmentTakeScreenState extends ConsumerState<AssessmentTakeScreen> {
  var _loading = true;
  var _submitting = false;
  String? _error;
  String _title = '';
  final List<_TakeQuestion> _questions = [];
  final Map<String, dynamic> _answers = {};

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _load());
  }

  Map<String, dynamic> _asStringKeyedMap(dynamic raw) {
    if (raw is Map<String, dynamic>) return raw;
    if (raw is Map) {
      return raw.map((k, v) => MapEntry(k.toString(), v));
    }
    return <String, dynamic>{};
  }

  List<_TakeQuestion> _parseQuestions(dynamic raw) {
    if (raw is! List) return [];
    final out = <_TakeQuestion>[];
    for (var i = 0; i < raw.length; i++) {
      final m = _asStringKeyedMap(raw[i]);
      if (m.isEmpty) continue;
      final choicesRaw = m['choices'];
      final choices = choicesRaw is List
          ? choicesRaw.map((e) => '$e').toList()
          : <String>[];
      out.add(
        _TakeQuestion(
          id: m['id']?.toString() ?? 'q_$i',
          order: _asInt(m['order']) ?? i,
          type: m['type']?.toString() ?? 'mc',
          prompt: m['prompt']?.toString() ?? '',
          points: _asInt(m['points']) ?? 0,
          choices: choices,
        ),
      );
    }
    out.sort((a, b) => a.order.compareTo(b.order));
    return out;
  }

  int? _asInt(dynamic v) {
    if (v == null) return null;
    if (v is int) return v;
    if (v is num) return v.toInt();
    return int.tryParse('$v');
  }

  String _functionsErrorMessage(FirebaseFunctionsException e) {
    final msg = e.message?.trim();
    if (msg != null &&
        msg.isNotEmpty &&
        msg.toUpperCase() != 'INTERNAL' &&
        !msg.toUpperCase().startsWith('INTERNAL ')) {
      return msg;
    }
    return switch (e.code) {
      'failed-precondition' => '지금은 응시할 수 없습니다. 공개·기간을 확인해 주세요.',
      'already-exists' => '이미 응시한 평가입니다.',
      'not-found' => '평가를 찾을 수 없습니다.',
      'permission-denied' => '이 평가에 접근할 권한이 없습니다.',
      'unauthenticated' => '로그인이 필요합니다.',
      _ => '평가를 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.',
    };
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
        final questions = await repo
            .watchAssessmentQuestions(cohortId, widget.assessmentId)
            .first;
        final assessment = await repo
            .watchAssessment(cohortId, widget.assessmentId)
            .first;
        setState(() {
          _title = assessment?.title ?? '';
          _questions
            ..clear()
            ..addAll(
              questions.map(
                (q) => _TakeQuestion(
                  id: q.id,
                  order: q.order,
                  type: q.type.value,
                  prompt: q.prompt,
                  points: q.points,
                  choices: q.choices,
                ),
              ),
            );
          _loading = false;
          if (_questions.isEmpty) {
            _error = '등록된 문제가 없습니다. 강사에게 문의하세요.';
          }
        });
        return;
      }

      final data = await ref
          .read(assessmentFunctionsServiceProvider)
          .getAssessmentForTake(
            cohortId: cohortId,
            assessmentId: widget.assessmentId,
          );
      final assessment = _asStringKeyedMap(data['assessment']);
      final parsed = _parseQuestions(data['questions']);
      setState(() {
        _title = assessment['title']?.toString() ?? '';
        _questions
          ..clear()
          ..addAll(parsed);
        _loading = false;
        if (_questions.isEmpty) {
          _error = '등록된 문제가 없습니다. 강사에게 문의하세요.';
        }
      });
    } on FirebaseFunctionsException catch (e) {
      if (e.code == 'already-exists' && mounted) {
        context.go(RoutePaths.assessmentResultPath(widget.assessmentId));
        return;
      }
      setState(() {
        _loading = false;
        _error = _functionsErrorMessage(e);
      });
    } catch (e) {
      setState(() {
        _loading = false;
        _error = '평가를 불러오지 못했습니다.\n$e';
      });
    }
  }

  Future<void> _submit() async {
    final unanswered = _questions.where((q) {
      final v = _answers[q.id];
      if (q.type == 'mc') return v == null;
      return v == null || '$v'.trim().isEmpty;
    }).toList();
    if (unanswered.isNotEmpty) {
      final ok = await showDialog<bool>(
        context: context,
        builder: (ctx) => AlertDialog(
          title: const Text('미응답 문항이 있습니다'),
          content: Text('${unanswered.length}문항이 비어 있습니다. 그대로 제출할까요?'),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(ctx, false),
              child: const Text('취소'),
            ),
            FilledButton(
              onPressed: () => Navigator.pop(ctx, true),
              child: const Text('제출'),
            ),
          ],
        ),
      );
      if (ok != true) return;
    }

    final cohortId = ref.read(effectiveCohortIdProvider);
    final user = ref.read(currentUserSyncProvider);
    if (cohortId == null || user == null) return;

    setState(() => _submitting = true);
    try {
      final repo = ref.read(lmsRepositoryProvider);
      if (DemoConfig.enabled && repo is DemoLmsRepository) {
        await repo.demoSubmitAssessment(
          assessmentId: widget.assessmentId,
          userId: user.uid,
          userDisplayName: user.displayName,
          answers: Map<String, dynamic>.from(_answers),
        );
      } else {
        await ref
            .read(assessmentFunctionsServiceProvider)
            .submitAssessment(
              cohortId: cohortId,
              assessmentId: widget.assessmentId,
              answers: Map<String, dynamic>.from(_answers),
            );
      }
      if (!mounted) return;
      context.go(RoutePaths.assessmentResultPath(widget.assessmentId));
    } on FirebaseFunctionsException catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(_functionsErrorMessage(e))),
      );
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('제출 실패: $e')),
      );
    } finally {
      if (mounted) setState(() => _submitting = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.surfaceVariant,
      appBar: AppBar(
        title: Text(_title.isEmpty ? '성취도평가' : _title),
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : _error != null
          ? Center(
              child: Padding(
                padding: EdgeInsets.all(AppSpace.s(24)),
                child: Text(_error!, textAlign: TextAlign.center),
              ),
            )
          : Column(
              children: [
                Expanded(
                  child: ListView.separated(
                    padding: EdgeInsets.fromLTRB(AppSpace.s(16), AppSpace.s(16), AppSpace.s(16), AppSpace.s(24)),
                    itemCount: _questions.length,
                    separatorBuilder: (_, __) => SizedBox(height: AppSpace.s(20)),
                    itemBuilder: (context, i) {
                      final q = _questions[i];
                      return Align(
                        alignment: Alignment.topCenter,
                        heightFactor: 1,
                        child: ConstrainedBox(
                          constraints: const BoxConstraints(
                            maxWidth: AppLayout.reading,
                          ),
                          child: AssessmentQuestionView(
                            number: i + 1,
                            prompt: q.prompt,
                            points: q.points,
                            type: q.type,
                            choices: q.choices,
                            selectedIndex: q.type == 'mc'
                                ? _asInt(_answers[q.id])
                                : null,
                            shortAnswer: q.type != 'mc'
                                ? '${_answers[q.id] ?? ''}'
                                : null,
                            mode: AssessmentQuestionViewMode.take,
                            onSelectChoice: (ci) =>
                                setState(() => _answers[q.id] = ci),
                            onShortAnswerChanged: (v) => _answers[q.id] = v,
                          ),
                        ),
                      );
                    },
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
                              onPressed: _submitting ? null : _submit,
                              child: _submitting
                                  ? SizedBox(
                                      width: 20,
                                      height: 20,
                                      child: CircularProgressIndicator(
                                        strokeWidth: 2,
                                        color: Colors.white,
                                      ),
                                    )
                                  : const Text('제출하기'),
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

class _TakeQuestion {
  _TakeQuestion({
    required this.id,
    required this.order,
    required this.type,
    required this.prompt,
    required this.points,
    required this.choices,
  });

  final String id;
  final int order;
  final String type;
  final String prompt;
  final int points;
  final List<String> choices;
}
