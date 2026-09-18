import 'dart:typed_data';

import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/routing/route_paths.dart';
import '../../../core/theme/app_colors.dart';
import '../../../core/widgets/app_dropdown.dart';
import '../../../shared/demo/demo_accounts.dart';
import '../../../shared/models/assessment_model.dart';
import '../../../shared/providers/cohort_providers.dart';
import '../../../shared/providers/lms_providers.dart';
import '../../../shared/services/storage_service.dart';
import '../../assessments/data/assessment_functions_service.dart';
import '../../assessments/presentation/widgets/assessment_question_view.dart';
import '../../assessments/presentation/widgets/assessment_thumbnail.dart';
import 'widgets/assessment_ai_flow_dialogs.dart';
import '../../../core/theme/app_space.dart';

/// 강사 — 평가 생성/수정 + 문제 편집 + 문제 생성 AI
class InstructorAssessmentFormScreen extends ConsumerStatefulWidget {
  const InstructorAssessmentFormScreen({super.key, this.assessmentId});

  final String? assessmentId;

  @override
  ConsumerState<InstructorAssessmentFormScreen> createState() =>
      _InstructorAssessmentFormScreenState();
}

class _InstructorAssessmentFormScreenState
    extends ConsumerState<InstructorAssessmentFormScreen> {
  final _title = TextEditingController();
  final _tags = TextEditingController();
  DateTime _startAt = DateTime.now();
  DateTime _endAt = DateTime.now().add(const Duration(days: 7));
  String? _thumbnailUrl;
  String? _thumbnailPath;
  Uint8List? _pendingThumbBytes;
  String? _pendingThumbName;
  var _published = false;
  var _loading = false;
  var _initialized = false;
  final List<AssessmentQuestionModel> _questions = [];

  bool get _isEdit => widget.assessmentId != null;

  @override
  void dispose() {
    _title.dispose();
    _tags.dispose();
    super.dispose();
  }

  void _hydrate(AssessmentModel a, List<AssessmentQuestionModel> qs) {
    if (_initialized) return;
    _title.text = a.title;
    _tags.text = a.tags.join(', ');
    _startAt = a.startAt;
    _endAt = a.endAt;
    _thumbnailUrl = a.thumbnailUrl;
    _thumbnailPath = a.thumbnailPath;
    _published = a.published;
    _questions
      ..clear()
      ..addAll(qs);
    _initialized = true;
  }

  Future<void> _pickThumbnail() async {
    final picked = await FilePicker.pickFiles(type: FileType.image);
    if (picked.isEmpty) return;
    final f = picked.first;
    final bytes = await f.readAsBytes();
    if (!mounted) return;
    setState(() {
      _pendingThumbBytes = bytes;
      _pendingThumbName = f.name;
    });
  }

  Future<void> _pickDate({required bool isStart}) async {
    final initial = isStart ? _startAt : _endAt;
    final date = await showDatePicker(
      context: context,
      initialDate: initial,
      firstDate: DateTime(2024),
      lastDate: DateTime(2035),
    );
    if (date == null) return;
    final time = await showTimePicker(
      context: context,
      initialTime: TimeOfDay.fromDateTime(initial),
    );
    if (time == null) return;
    final dt = DateTime(
      date.year,
      date.month,
      date.day,
      time.hour,
      time.minute,
    );
    setState(() {
      if (isStart) {
        _startAt = dt;
      } else {
        _endAt = dt;
      }
    });
  }

  Future<String> _ensureAssessmentId() async {
    if (widget.assessmentId != null) return widget.assessmentId!;
    final cohortId = ref.read(effectiveCohortIdProvider)!;
    final user = ref.read(currentUserSyncProvider)!;
    final tags = _tags.text
        .split(',')
        .map((e) => e.trim())
        .where((e) => e.isNotEmpty)
        .toList();
    return ref
        .read(lmsRepositoryProvider)
        .createAssessment(
          cohortId: cohortId,
          assessment: AssessmentModel(
            id: '',
            title: _title.text.trim().isEmpty ? '새 성취도평가' : _title.text.trim(),
            tags: tags,
            questionCount: 0,
            maxScore: 0,
            startAt: _startAt,
            endAt: _endAt,
            published: false,
            createdBy: user.uid,
          ),
        );
  }

  Future<void> _save({bool publish = false}) async {
    final title = _title.text.trim();
    if (title.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('제목을 입력해 주세요.')),
      );
      return;
    }
    if (_questions.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('문제를 1개 이상 추가해 주세요.')),
      );
      return;
    }

    final cohortId = ref.read(effectiveCohortIdProvider);
    final user = ref.read(currentUserSyncProvider);
    if (cohortId == null || user == null) return;

    setState(() => _loading = true);
    try {
      final id = await _ensureAssessmentId();
      var thumbUrl = _thumbnailUrl;
      var thumbPath = _thumbnailPath;

      if (_pendingThumbBytes != null) {
        if (DemoConfig.enabled) {
          thumbUrl = 'demo://thumb/${_pendingThumbName ?? 'thumb.png'}';
          thumbPath = thumbUrl;
        } else {
          final name = _pendingThumbName ?? 'thumb.jpg';
          final path = StorageService.assessmentThumbnailPath(
            cohortId: cohortId,
            assessmentId: id,
            fileName: name,
          );
          final contentType = name.toLowerCase().endsWith('.png')
              ? 'image/png'
              : name.toLowerCase().endsWith('.webp')
              ? 'image/webp'
              : 'image/jpeg';
          thumbUrl = await ref
              .read(storageServiceProvider)
              .uploadAndGetUrl(
                storagePath: path,
                bytes: _pendingThumbBytes!,
                contentType: contentType,
              );
          thumbPath = path;
          AssessmentThumbnail.putCache(path, _pendingThumbBytes!);
          AssessmentThumbnail.putCache(thumbUrl, _pendingThumbBytes!);
        }
      }

      final tags = _tags.text
          .split(',')
          .map((e) => e.trim())
          .where((e) => e.isNotEmpty)
          .toList();

      await ref
          .read(lmsRepositoryProvider)
          .updateAssessment(
            cohortId: cohortId,
            assessmentId: id,
            updates: {
              'title': title,
              'tags': tags,
              'startAt': _startAt,
              'endAt': _endAt,
              if (thumbUrl != null) 'thumbnailUrl': thumbUrl,
              if (thumbPath != null) 'thumbnailPath': thumbPath,
              'published': publish || _published,
            },
          );

      await ref
          .read(lmsRepositoryProvider)
          .replaceAssessmentQuestions(
            cohortId: cohortId,
            assessmentId: id,
            questions: _questions,
          );

      if (publish) {
        await ref
            .read(lmsRepositoryProvider)
            .publishAssessment(
              cohortId: cohortId,
              assessmentId: id,
            );
      }

      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(publish ? '발행되었습니다.' : '저장되었습니다.'),
        ),
      );
      if (!_isEdit) {
        context.go(RoutePaths.instructorAssessmentDetailPath(id));
      } else {
        context.pop();
      }
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('저장 실패: $e')),
      );
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _editQuestion([
    AssessmentQuestionModel? existing,
    int? index,
  ]) async {
    final result = await showDialog<AssessmentQuestionModel>(
      context: context,
      builder: (ctx) => _QuestionEditorDialog(initial: existing),
    );
    if (result == null) return;
    setState(() {
      if (index != null) {
        _questions[index] = result.copyWith(order: index);
      } else {
        _questions.add(result.copyWith(order: _questions.length));
      }
    });

    final edited = index != null ? _questions[index] : _questions.last;
    if (edited.origin == 'ai' &&
        edited.aiLogId != null &&
        edited.aiDraftId != null) {
      final cohortId = ref.read(effectiveCohortIdProvider);
      if (cohortId != null) {
        try {
          await ref
              .read(assessmentFunctionsServiceProvider)
              .recordAiQuestionFeedback(
                cohortId: cohortId,
                logId: edited.aiLogId!,
                promptVersion: edited.promptVersion,
                assessmentId: widget.assessmentId,
                items: [
                  {
                    'draftId': edited.aiDraftId!,
                    'outcome': 'edited',
                    if (edited.sourceDay != null) 'sourceDay': edited.sourceDay,
                    if (edited.sourceTopic != null)
                      'sourceTopic': edited.sourceTopic,
                    'questionId': edited.id,
                  },
                ],
              );
        } catch (_) {
          if (mounted) {
            ScaffoldMessenger.of(context).showSnackBar(
              const SnackBar(content: Text('수정 피드백 저장에 실패했습니다. (출제는 유지됩니다)')),
            );
          }
        }
      }
    }
  }

  Future<void> _openCurriculumAi() async {
    final generated = await showDialog<GenerateAssessmentResult>(
      context: context,
      barrierDismissible: false,
      builder: (ctx) => const CurriculumAiGenerateDialog(),
    );
    if (generated == null || generated.questions.isEmpty || !mounted) return;

    final selected = await showDialog<List<AssessmentQuestionModel>>(
      context: context,
      barrierDismissible: false,
      builder: (ctx) => AssessmentAiReviewDialog(initial: generated),
    );
    if (selected == null || selected.isEmpty) return;
    setState(() {
      for (final q in selected) {
        _questions.add(q.copyWith(order: _questions.length));
      }
    });
  }

  @override
  void initState() {
    super.initState();
    if (_isEdit) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        ref.listenManual(
          assessmentProvider(widget.assessmentId!),
          (prev, next) {
            next.whenData((a) {
              if (a == null || _initialized) return;
              final qs =
                  ref
                      .read(assessmentQuestionsProvider(widget.assessmentId!))
                      .asData
                      ?.value ??
                  [];
              setState(() => _hydrate(a, qs));
            });
          },
          fireImmediately: true,
        );
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.surfaceVariant,
      appBar: AppBar(
        title: Text(_isEdit ? '평가 수정' : '평가 만들기'),
        actions: [
          TextButton(
            onPressed: _loading ? null : () => _save(publish: false),
            child: const Text('저장'),
          ),
          Padding(
            padding: EdgeInsets.only(right: AppSpace.s(12)),
            child: FilledButton(
              onPressed: _loading ? null : () => _save(publish: true),
              child: const Text('발행'),
            ),
          ),
        ],
      ),
      body: Align(
        alignment: Alignment.topCenter,
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 860),
          child: ListView(
            padding: EdgeInsets.fromLTRB(AppSpace.s(16), AppSpace.s(16), AppSpace.s(16), AppSpace.s(40)),
            children: [
              Container(
                padding: EdgeInsets.all(AppSpace.s(16)),
                decoration: BoxDecoration(
                  color: AppColors.surface,
                  borderRadius: BorderRadius.circular(12),
                  border: Border.all(color: AppColors.border),
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    TextField(
                      controller: _title,
                      decoration: const InputDecoration(
                        labelText: '제목',
                        border: OutlineInputBorder(),
                      ),
                    ),
                    SizedBox(height: AppSpace.s(12)),
                    TextField(
                      controller: _tags,
                      decoration: const InputDecoration(
                        labelText: '태그 (쉼표 구분)',
                        border: OutlineInputBorder(),
                      ),
                    ),
                    SizedBox(height: AppSpace.s(12)),
                    Row(
                      children: [
                        Expanded(
                          child: OutlinedButton(
                            onPressed: () => _pickDate(isStart: true),
                            child: Text(
                              '시작: ${_startAt.toString().substring(0, 16)}',
                              overflow: TextOverflow.ellipsis,
                            ),
                          ),
                        ),
                        SizedBox(width: AppSpace.s(8)),
                        Expanded(
                          child: OutlinedButton(
                            onPressed: () => _pickDate(isStart: false),
                            child: Text(
                              '종료: ${_endAt.toString().substring(0, 16)}',
                              overflow: TextOverflow.ellipsis,
                            ),
                          ),
                        ),
                      ],
                    ),
                    SizedBox(height: AppSpace.s(12)),
                    Row(
                      children: [
                        AssessmentThumbnail(
                          url: _thumbnailUrl,
                          storagePath: _thumbnailPath,
                          bytes: _pendingThumbBytes,
                          title: _title.text.trim().isEmpty
                              ? null
                              : _title.text.trim(),
                          width: 96,
                          height: AppSpace.row(54),
                          placeholderIcon: Icons.image_outlined,
                          placeholderIconSize: 22,
                        ),
                        SizedBox(width: AppSpace.s(12)),
                        OutlinedButton.icon(
                          onPressed: _pickThumbnail,
                          icon: const Icon(Icons.upload),
                          label: const Text('썸네일'),
                        ),
                      ],
                    ),
                  ],
                ),
              ),
              SizedBox(height: AppSpace.s(20)),
              const Text(
                '문제',
                style: TextStyle(fontSize: 16, fontWeight: FontWeight.w700),
              ),
              SizedBox(height: AppSpace.s(10)),
              Row(
                children: [
                  Expanded(
                    flex: 3,
                    child: SizedBox(
                      height: AppSpace.row(48),
                      child: FilledButton.icon(
                        onPressed: _openCurriculumAi,
                        style: FilledButton.styleFrom(
                          backgroundColor: AppColors.primary,
                          foregroundColor: Colors.white,
                        ),
                        icon: const Icon(Icons.auto_awesome, size: 20),
                        label: const Text(
                          '문제 생성 AI',
                          style: TextStyle(fontWeight: FontWeight.w700),
                        ),
                      ),
                    ),
                  ),
                  SizedBox(width: AppSpace.s(10)),
                  Expanded(
                    flex: 2,
                    child: SizedBox(
                      height: AppSpace.row(48),
                      child: OutlinedButton.icon(
                        onPressed: () => _editQuestion(),
                        icon: const Icon(Icons.add, size: 20),
                        label: const Text('수동 추가'),
                      ),
                    ),
                  ),
                ],
              ),
              SizedBox(height: AppSpace.s(16)),
              if (_questions.isEmpty)
                Container(
                  width: double.infinity,
                  padding: EdgeInsets.symmetric(
                    horizontal: AppSpace.s(20),
                    vertical: AppSpace.s(36),
                  ),
                  decoration: BoxDecoration(
                    color: AppColors.surface,
                    borderRadius: BorderRadius.circular(12),
                    border: Border.all(color: AppColors.border),
                  ),
                  child: Column(
                    children: [
                      Icon(
                        Icons.quiz_outlined,
                        size: 40,
                        color: Colors.grey.shade400,
                      ),
                      SizedBox(height: AppSpace.s(12)),
                      const Text(
                        '아직 문제가 없습니다',
                        style: TextStyle(
                          fontWeight: FontWeight.w700,
                          fontSize: 15,
                        ),
                      ),
                      SizedBox(height: AppSpace.s(6)),
                      Text(
                        '문제 생성 AI로 초안을 만들거나\n수동으로 추가해 보세요.',
                        textAlign: TextAlign.center,
                        style: TextStyle(
                          color: AppColors.textSecondary,
                          height: 1.4,
                        ),
                      ),
                    ],
                  ),
                )
              else
                ..._questions.asMap().entries.map((e) {
                  final q = e.value;
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
                      mode: AssessmentQuestionViewMode.preview,
                      footer: Row(
                        children: [
                          TextButton.icon(
                            onPressed: () => _editQuestion(q, e.key),
                            icon: const Icon(Icons.edit_outlined, size: 18),
                            label: const Text('수정'),
                          ),
                          TextButton.icon(
                            onPressed: () =>
                                setState(() => _questions.removeAt(e.key)),
                            style: TextButton.styleFrom(
                              foregroundColor: AppColors.error,
                            ),
                            icon: const Icon(Icons.delete_outline, size: 18),
                            label: const Text('삭제'),
                          ),
                        ],
                      ),
                    ),
                  );
                }),
              if (_loading)
                Padding(
                  padding: EdgeInsets.all(AppSpace.s(24)),
                  child: Center(child: CircularProgressIndicator()),
                ),
            ],
          ),
        ),
      ),
    );
  }
}

class _QuestionEditorDialog extends StatefulWidget {
  const _QuestionEditorDialog({this.initial});

  final AssessmentQuestionModel? initial;

  @override
  State<_QuestionEditorDialog> createState() => _QuestionEditorDialogState();
}

class _QuestionEditorDialogState extends State<_QuestionEditorDialog> {
  late AssessmentQuestionType _type;
  late final TextEditingController _prompt;
  late final TextEditingController _points;
  late final TextEditingController _choices;
  late final TextEditingController _accepted;
  late final TextEditingController _explanation;
  int _correctIndex = 0;

  @override
  void initState() {
    super.initState();
    final i = widget.initial;
    _type = i?.type ?? AssessmentQuestionType.multipleChoice;
    _prompt = TextEditingController(text: i?.prompt ?? '');
    _points = TextEditingController(text: '${i?.points ?? 4}');
    _choices = TextEditingController(text: (i?.choices ?? const []).join('\n'));
    _accepted = TextEditingController(
      text: (i?.acceptedAnswers ?? const []).join('\n'),
    );
    _explanation = TextEditingController(text: i?.explanation ?? '');
    _correctIndex = i?.correctIndex ?? 0;
  }

  @override
  void dispose() {
    _prompt.dispose();
    _points.dispose();
    _choices.dispose();
    _accepted.dispose();
    _explanation.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: Text(widget.initial == null ? '문제 추가' : '문제 수정'),
      content: SizedBox(
        width: 480,
        child: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              AppDropdownField<AssessmentQuestionType>(
                value: _type,
                items: const [
                  AppDropdownItem(
                    value: AssessmentQuestionType.multipleChoice,
                    label: '객관식',
                  ),
                  AppDropdownItem(
                    value: AssessmentQuestionType.shortAnswer,
                    label: '단답',
                  ),
                ],
                onChanged: (v) {
                  if (v != null) setState(() => _type = v);
                },
                decoration: const InputDecoration(labelText: '유형'),
              ),
              TextField(
                controller: _prompt,
                maxLines: 3,
                decoration: const InputDecoration(labelText: '문제'),
              ),
              TextField(
                controller: _points,
                keyboardType: TextInputType.number,
                decoration: const InputDecoration(labelText: '배점'),
              ),
              if (_type == AssessmentQuestionType.multipleChoice) ...[
                TextField(
                  controller: _choices,
                  maxLines: 4,
                  decoration: const InputDecoration(
                    labelText: '선택지 (줄바꿈 구분)',
                  ),
                ),
                TextField(
                  decoration: const InputDecoration(
                    labelText: '정답 인덱스 (0부터)',
                  ),
                  keyboardType: TextInputType.number,
                  controller: TextEditingController(text: '$_correctIndex'),
                  onChanged: (v) =>
                      _correctIndex = int.tryParse(v) ?? _correctIndex,
                ),
              ] else
                TextField(
                  controller: _accepted,
                  maxLines: 3,
                  decoration: const InputDecoration(
                    labelText: '정답 후보 (줄바꿈 구분)',
                  ),
                ),
              TextField(
                controller: _explanation,
                decoration: const InputDecoration(labelText: '해설 (선택)'),
              ),
            ],
          ),
        ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.pop(context),
          child: const Text('취소'),
        ),
        FilledButton(
          onPressed: () {
            final choices = _choices.text
                .split('\n')
                .map((e) => e.trim())
                .where((e) => e.isNotEmpty)
                .toList();
            final accepted = _accepted.text
                .split('\n')
                .map((e) => e.trim())
                .where((e) => e.isNotEmpty)
                .toList();
            final initial = widget.initial;
            Navigator.pop(
              context,
              AssessmentQuestionModel(
                id:
                    initial?.id ??
                    'draft_${DateTime.now().millisecondsSinceEpoch}',
                order: initial?.order ?? 0,
                type: _type,
                prompt: _prompt.text.trim(),
                points: int.tryParse(_points.text.trim()) ?? 4,
                choices: choices,
                correctIndex: _type == AssessmentQuestionType.multipleChoice
                    ? _correctIndex
                    : null,
                acceptedAnswers: accepted,
                explanation: _explanation.text.trim().isEmpty
                    ? null
                    : _explanation.text.trim(),
                origin: initial?.origin ?? 'manual',
                aiLogId: initial?.aiLogId,
                promptVersion: initial?.promptVersion,
                sourceDay: initial?.sourceDay,
                sourceTopic: initial?.sourceTopic,
                aiDraftId: initial?.aiDraftId,
              ),
            );
          },
          child: const Text('확인'),
        ),
      ],
    );
  }
}
