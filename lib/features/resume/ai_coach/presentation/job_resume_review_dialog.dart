import 'dart:async';
import 'dart:math';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../../../shared/constants/ai_ops_types.dart';
import '../../../../shared/models/resume_content.dart';
import '../../../../shared/services/ai_ops_service.dart';
import '../data/resume_review_api_client.dart';
import '../../../../core/theme/app_colors.dart';
import '../../../../core/theme/app_space.dart';
import 'review_dock.dart';
import 'review_requirements.dart';

enum _ReviewBusyKind { review, answer, apply, undo }

const _generalReviewSteps = [
  '기본 이력서 불러오기',
  '이력서 항목 확인',
  '경험 근거 비교',
  '수정안과 확인 질문 준비',
];

const _jobReviewSteps = [
  '공고 요건 정리',
  '이력서 근거 대조',
  '경험·문장 점검',
  '확인 질문과 수정안 준비',
];

String _busyLabel(_ReviewBusyKind kind) => switch (kind) {
  _ReviewBusyKind.answer => '답변을 검토하고 다음 보완 항목을 준비하고 있어요',
  _ReviewBusyKind.undo => '변경 내용을 되돌리고 있어요',
  _ReviewBusyKind.review => '이력서를 분석하고 있어요',
  _ReviewBusyKind.apply => '수정안을 반영하고 있어요',
};

class JobResumeReviewDialog extends StatefulWidget {
  const JobResumeReviewDialog({
    super.key,
    required this.client,
    required this.cohortId,
    required this.resumeId,
    required this.draft,
    required this.onChanged,
    this.jobId = '',
    this.jobCompany = '',
    this.jobTitle = '',
    this.tailoredResumeId = '',
    this.initialReviewSession = const {},
    this.generalReview = false,
    this.aiOps,
  });
  // 없으면 로그를 남기지 않는다. 첨삭이 로그 때문에 막히면 안 된다.
  final AiOpsService? aiOps;
  final ResumeReviewApiClient client;
  final String cohortId,
      resumeId,
      jobId,
      jobCompany,
      jobTitle,
      tailoredResumeId;
  final ResumeContent draft;
  final ValueChanged<ResumeContent> onChanged;
  final bool generalReview;
  final Map<String, dynamic> initialReviewSession;

  @override
  State<JobResumeReviewDialog> createState() => _JobResumeReviewDialogState();
}

class _JobResumeReviewDialogState extends State<JobResumeReviewDialog> {
  static const int _maxReviewQuestions = 10;
  Map<String, dynamic>? _result, _reviewRequest, _applyRequest;
  final Set<int> _selected = {};
  final Set<int> _appliedSuggestionIndices = {};
  final TextEditingController _answerController = TextEditingController();
  // 답변 입력칸의 포커스를 직접 쥔다. "없음" 칩이 나타났다 사라지면서 입력칸이 새로 만들어져도
  // 이 노드로 다시 포커스를 줄 수 있다.
  final FocusNode _answerFocus = FocusNode();
  final ScrollController _chatScrollController = ScrollController();
  final List<_ReviewChatMessage> _messages = [];
  final Set<String> _answeredQuestionIds = {};
  final List<Map<String, dynamic>> _questionQueue = [];
  final List<_ReviewChatMessage> _suggestionQueue = [];
  final Map<String, GlobalKey> _previewSectionKeys = {};
  bool _busy = false, _changed = false;
  // 이 첨삭을 남긴 로그. 사용자가 무엇을 했는지를 나중에 이 id에 붙인다.
  String? _reviewLogId, _reviewPromptVersion;
  // 적용도 되돌림도 없이 닫았는지 가리는 표시. 창을 닫을 때 한 번 본다.
  bool _hadApply = false, _hadUndo = false;
  _ReviewBusyKind? _busyKind;
  int _busyStage = 0;
  bool _mutationPending = false;
  bool _gapAuditScheduled = false;
  bool _gapAuditStarted = false;
  bool _gapAuditFinished = false;
  bool _manuallyCompleted = false;
  Map<String, dynamic>? _pendingQuestion;
  String? _error;
  String? _focusedFieldPath;
  String? _tailoredResumeId;
  // 지난 대화를 정리하고 처음부터 시작할 때 사용자에게 알리는 한 줄.
  String? _restartNotice;
  bool _restartedFromSaved = false;
  // 공고 요건 대조 표. 첫 첨삭 응답의 requirement_map으로 채우고, 답할 때마다 서버가 갱신한다.
  List<ReviewRequirementRow> _requirementRows = [];
  // 경험 항목별 STAR 판정. 미리보기 네 칸과 질문 표시("경험 보완 · 행동이 빠짐")에 쓴다.
  Map<String, ReviewStarCheck> _starChecks = {};
  // 요건 칩을 눌러 근거 위치를 보고 있을 때만 채운다. 다음 질문·수정안이 오면 비운다.
  String? _requirementFocusPath;
  // 대화 끝에 무엇이 붙었는지 기억해 두고, 바뀌면 맨 아래로 스크롤한다(_followChatBottom).
  String _chatTailSignature = '';
  // "없음" 카드 기록은 화면을 막지 않고 뒤에서 순서대로 보낸다. 다음 답변은 이 줄이 끝난 뒤에 보낸다.
  Future<void> _noneAnswerChain = Future<void>.value();
  int _pendingNoneAnswers = 0;
  Future<void> _sessionSaveChain = Future<void>.value();
  final ValueNotifier<double> _previewFraction = ValueNotifier(0.5);
  late ResumeContent _preview;
  String _id() =>
      '${DateTime.now().microsecondsSinceEpoch}_${Random.secure().nextInt(1 << 30)}';
  Map<String, dynamic> get _identity => {
    'cohort_id': widget.cohortId,
    'resume_id': widget.resumeId,
  };

  @override
  void initState() {
    super.initState();
    _preview = widget.draft;
    _tailoredResumeId = widget.tailoredResumeId.isEmpty
        ? null
        : widget.tailoredResumeId;
    // 새 공고는 창을 열어보는 것만으로 맞춤 이력서를 만들지 않는다.
    // 사용자가 실제로 첨삭을 시작할 때 _reviewOnce에서 분기하고,
    // 기존 맞춤 이력서로 재진입한 경우에만 전달받은 세션을 복원한다.
    if (!widget.generalReview &&
        _tailoredResumeId != null &&
        widget.initialReviewSession.isNotEmpty) {
      _restoreSession(widget.initialReviewSession);
      // 목록에서 이어 열었는데 그 사이 이력서를 고쳤으면 지난 질문은 옛 이력서 기준이다.
      if (_result != null && !_sessionCompleted) {
        WidgetsBinding.instance.addPostFrameCallback(
          (_) => _checkRestoredResumeVersion(),
        );
      }
    }
  }

  /// 저장된 대화를 버리고 첫 첨삭 전 상태로 돌린다.
  ///
  /// 사용자가 첨삭을 마친 뒤 이력서에 내용을 더 넣고 "재첨삭"을 누르는 흐름을 위한 것이다(2026-09-15).
  /// 예전에는 마친 대화가 그대로 복원돼 입력창이 잠기고, 고친 이력서로는 새 첨삭을 시작할 수 없었다.
  void _resetSession() {
    _result = null;
    _reviewRequest = null;
    _applyRequest = null;
    _selected.clear();
    _appliedSuggestionIndices.clear();
    _messages.clear();
    _answeredQuestionIds.clear();
    _questionQueue.clear();
    _suggestionQueue.clear();
    _pendingQuestion = null;
    _gapAuditScheduled = false;
    _gapAuditStarted = false;
    _gapAuditFinished = false;
    _manuallyCompleted = false;
    _changed = false;
    _requirementRows = [];
    _starChecks = {};
    _requirementFocusPath = null;
    _error = null;
  }

  /// 목록에서 이어 연 대화가 지금 저장된 이력서와 같은 판인지 본다. 다르면 대화를 정리하고 처음부터 시작하게 한다.
  Future<void> _checkRestoredResumeVersion() async {
    try {
      final snapshot = await widget.client.context(
        widget.cohortId,
        widget.resumeId,
        job: widget.jobId,
        tailoredResumeId: _tailoredResumeId,
      );
      if (!mounted ||
          _result == null ||
          _result!['input_hash'] == snapshot['input_hash']) {
        return;
      }
      setState(() {
        _resetSession();
        _restartNotice = '이력서가 바뀌어 지난 대화를 정리했어요. 첨삭 시작을 누르면 바뀐 이력서로 다시 첨삭해요.';
        _preview = ResumeContent.fromMap(
          Map<String, dynamic>.from(snapshot['content'] as Map),
        );
      });
    } catch (_) {
      // 확인하지 못하면 그대로 둔다. 답을 보낼 때 서버가 판을 다시 확인한다.
    }
  }

  /// 완료 안내의 "다시 첨삭". 고친 이력서로 처음부터 다시 첨삭한다.
  void _restartReview() {
    if (_busy) return;
    setState(_resetSession);
    _restartedFromSaved = true;
    unawaited(_review());
  }

  void _restoreSession(Map<String, dynamic> state) {
    if (state['version'] != 1 || state['result'] is! Map) return;
    final savedResumeId = state['resume_id'] as String?;
    final savedJobId = state['job_id'] as String?;
    final savedResult = Map<String, dynamic>.from(state['result'] as Map);
    final savedJobSource = Map<String, dynamic>.from(
      savedResult['job_source'] as Map? ?? const {},
    );
    final sourceJobId = savedJobSource['job_id'] as String?;
    final sourceCompany = (savedJobSource['company'] as String? ?? '').trim();
    final sourceTitle = (savedJobSource['title'] as String? ?? '').trim();
    if ((savedResumeId != null && savedResumeId != widget.resumeId) ||
        (savedJobId != null && savedJobId != widget.jobId) ||
        (sourceJobId != null &&
            sourceJobId.isNotEmpty &&
            sourceJobId != widget.jobId) ||
        ((sourceJobId == null || sourceJobId.isEmpty) &&
            sourceCompany.isNotEmpty &&
            widget.jobCompany.isNotEmpty &&
            sourceCompany != widget.jobCompany) ||
        ((sourceJobId == null || sourceJobId.isEmpty) &&
            sourceTitle.isNotEmpty &&
            widget.jobTitle.isNotEmpty &&
            sourceTitle != widget.jobTitle)) {
      return;
    }
    _result = savedResult;
    _messages
      ..clear()
      ..addAll(
        (state['messages'] as List? ?? const []).whereType<Map>().map(
          (item) => _ReviewChatMessage.fromMap(item),
        ),
      );
    _questionQueue
      ..clear()
      ..addAll(
        (state['question_queue'] as List? ?? const []).whereType<Map>().map(
          (item) => Map<String, dynamic>.from(item),
        ),
      );
    _suggestionQueue
      ..clear()
      ..addAll(
        (state['suggestion_queue'] as List? ?? const []).whereType<Map>().map(
          (item) => _ReviewChatMessage.fromMap(item),
        ),
      );
    _pendingQuestion = state['pending_question'] is Map
        ? Map<String, dynamic>.from(state['pending_question'] as Map)
        : null;
    _answeredQuestionIds
      ..clear()
      ..addAll(
        (state['answered_question_ids'] as List? ?? const [])
            .whereType<String>(),
      );
    _appliedSuggestionIndices
      ..clear()
      ..addAll(
        (state['applied_indices'] as List? ?? const []).whereType<int>(),
      );
    _gapAuditStarted = state['gap_audit_started'] == true;
    _gapAuditFinished = state['gap_audit_finished'] == true;
    _manuallyCompleted = state['manually_completed'] == true;
    _changed = state['changed'] == true;
    _requirementRows = (state['requirement_map'] as List? ?? const [])
        .whereType<Map>()
        .map(ReviewRequirementRow.fromMap)
        .toList();
    _starChecks = starChecksByPath(state['star_checks']);
    _trimQuestionBacklog();
  }

  Map<String, dynamic> _sessionState() => {
    'version': 1,
    'resume_id': widget.resumeId,
    'job_id': widget.jobId,
    'tailored_resume_id': _tailoredResumeId,
    // 원문 전체가 든 input_fields와 진단 결과를 다시 복제하지 않는다.
    // 이어하기에는 서버 review ID, 현재 hash, 선택 공고 정보만 필요하다.
    'result': _compactSessionResult(),
    'messages': _messages.map((message) => message.toMap()).toList(),
    'question_queue': _questionQueue,
    'suggestion_queue': _suggestionQueue
        .map((message) => message.toMap())
        .toList(),
    'pending_question': _pendingQuestion,
    'answered_question_ids': _answeredQuestionIds.toList(),
    'applied_indices': _appliedSuggestionIndices.toList(),
    'gap_audit_started': _gapAuditStarted,
    'gap_audit_finished': _gapAuditFinished,
    'manually_completed': _manuallyCompleted,
    'changed': _changed,
    'requirement_map': _requirementRows.map((row) => row.toMap()).toList(),
    'star_checks': _starChecks.values.map((check) => check.toMap()).toList(),
    'completed': _sessionCompleted,
  };

  Map<String, dynamic> _compactSessionResult() {
    final result = _result ?? const <String, dynamic>{};
    return {
      for (final key in [
        'review_id',
        'input_hash',
        'job_source',
        'summary',
        'grounding_warnings',
      ])
        if (result.containsKey(key)) key: result[key],
    };
  }

  /// 적용도 건너뛰기도 하지 않은 수정안이 대화에 남아 있는가.
  bool get _hasActiveSuggestion => _messages.any(
    (message) =>
        (message.suggestion != null &&
            message.suggestion!['_applied'] != true &&
            message.suggestion!['_skipped'] != true) ||
        (message.identitySuggestion != null &&
            message.identitySuggestion!['_applied'] != true &&
            message.identitySuggestion!['_skipped'] != true),
  );

  /// 질문을 다 마쳤지만 마지막 누락 점검이 아직 시작되지 않았다.
  ///
  /// 이때 완료로 보면 점검이 붙기 직전 초록 "첨삭 완료" 카드가 잠깐 떴다가 사라지고, 목록 배지도 먼저 완료로
  /// 저장됐다(2026-09-15 앱). 점검 예약은 대기 중에 부르면 취소되므로, 이 상태면 build에서 다시 예약한다.
  /// 적용하지 않은 수정안이 떠 있으면 사용자가 고른 뒤에 점검하므로 기다리는 상태로 보지 않는다.
  bool get _awaitingGapAudit =>
      _result != null &&
      !_manuallyCompleted &&
      !_gapAuditStarted &&
      !_hasActiveSuggestion;

  bool get _sessionCompleted {
    if (_manuallyCompleted) return _result != null;
    final hasActiveQuestion = _messages.any((message) {
      final id = message.question?['question_id'] as String?;
      return message.question != null &&
          (id == null || !_answeredQuestionIds.contains(id));
    });
    return _result != null &&
        !hasActiveQuestion &&
        !_hasActiveSuggestion &&
        _pendingQuestion == null &&
        _questionQueue.isEmpty &&
        _suggestionQueue.isEmpty &&
        !_gapAuditScheduled &&
        _pendingNoneAnswers == 0 &&
        _gapAuditFinished;
  }

  Future<void> _persistSession() {
    final tailoredId = _tailoredResumeId;
    if (widget.generalReview || tailoredId == null || _result == null) {
      return Future<void>.value();
    }
    final state = _sessionState();
    _sessionSaveChain = _sessionSaveChain.then((_) async {
      try {
        await widget.client.saveTailoredSession(
          widget.cohortId,
          widget.resumeId,
          tailoredId,
          state,
        );
      } catch (_) {
        // 이력서 적용 자체는 이미 원자 저장됐다. 세션 저장 실패로 적용을
        // 실패처럼 보이게 하지 않고 다음 사용자 동작에서 다시 저장한다.
      }
    });
    return _sessionSaveChain;
  }

  @override
  void dispose() {
    // 첨삭을 받아 놓고 아무것도 적용하지 않은 채 창을 닫았다. 이것도 결과다 —
    // 수정안이 쓸모없었다는 뜻이므로 빠지면 품질이 실제보다 좋아 보인다.
    final ops = widget.aiOps;
    final logId = _reviewLogId;
    if (ops != null && logId != null && !_hadApply && !_hadUndo) {
      ops.recordOutcome(
        cohortId: widget.cohortId,
        logId: logId,
        outcome: AiOpsOutcomes.abandoned,
        draftId: 'session',
        promptVersion: _reviewPromptVersion,
        type: AiOpsTypes.resumeReview,
      );
    }
    _answerController.dispose();
    _answerFocus.dispose();
    _chatScrollController.dispose();
    _previewFraction.dispose();
    super.dispose();
  }

  Future<void> _run(
    Future<void> Function() action, {
    _ReviewBusyKind kind = _ReviewBusyKind.review,
  }) async {
    setState(() {
      _busy = true;
      _busyKind = kind;
      _busyStage = 0;
      _error = null;
    });
    _reportDock();
    try {
      await action();
    } catch (error) {
      if (mounted) setState(() => _error = error.toString());
    } finally {
      if (mounted) {
        setState(() {
          _busy = false;
          _busyKind = null;
          _busyStage = 0;
        });
        _reportDock();
      }
    }
  }

  void _setBusyStage(int stage) {
    if (mounted) setState(() => _busyStage = stage);
    _reportDock();
  }

  /// 앱 맨 위 층에 떠 있으면 내려둔 막대가 보여줄 상태를 알린다.
  void _reportDock() {
    if (!mounted) return;
    final dock = ReviewDockScope.read(context);
    if (dock == null) return;
    final kind = _busyKind;
    final staged = kind == _ReviewBusyKind.review && _result == null;
    final steps = widget.generalReview ? _generalReviewSteps : _jobReviewSteps;
    final stage = _busyStage.clamp(0, steps.length - 1);
    dock.report(
      ReviewDockStatus(
        title: widget.generalReview ? '이력서 첨삭' : '공고 맞춤 첨삭',
        subtitle: widget.generalReview
            ? ''
            : '${widget.jobCompany} ${widget.jobTitle}'.trim(),
        busy: _busy,
        stageLabel: kind == null
            ? null
            : staged
            ? steps[stage]
            : _busyLabel(kind),
        stageIndex: staged ? stage : null,
        stageCount: staged ? steps.length : null,
        failed: _error != null,
      ),
    );
  }

  /// 대화 상자면 경로를 닫고, 앱 맨 위 층에 떠 있으면 층에서 내린다.
  void _closeWith([Object? result]) {
    final dock = ReviewDockScope.read(context);
    if (dock != null) {
      dock.close(result);
    } else {
      Navigator.pop(context, result);
    }
  }

  Future<void> _review() => _run(() async {
    final watch = Stopwatch()..start();
    try {
      // 저장된 대화를 그대로 보여 준 경우(모델을 부르지 않음)는 로그를 남기지 않는다.
      if (!await _reviewOnce()) return;
    } catch (error) {
      final ops = widget.aiOps;
      if (ops != null) {
        await ops.recordCoachLog(
          type: AiOpsTypes.resumeReview,
          cohortId: widget.cohortId,
          watch: watch,
          success: false,
          error: error,
          meta: {'reviewMode': widget.generalReview ? 'general' : 'job'},
        );
      }
      rethrow;
    }
    final ops = widget.aiOps;
    if (ops != null) {
      final suggestions = (_result!['suggestions'] as List?)?.length ?? 0;
      _reviewLogId = await ops.recordCoachLog(
        type: AiOpsTypes.resumeReview,
        cohortId: widget.cohortId,
        watch: watch,
        success: true,
        promptVersion: AiOpsPromptVersions.resumeReview,
        generatedCount: suggestions == 0 ? 1 : suggestions,
        meta: {
          'reviewMode': widget.generalReview ? 'general' : 'job',
          'jobCount': widget.generalReview ? 0 : 1,
          'requestIdHash': (_reviewRequest?['request_id'] as String? ?? '')
              .hashCode
              .toRadixString(16),
        },
      );
      _reviewPromptVersion = AiOpsPromptVersions.resumeReview;
    }
  }, kind: _ReviewBusyKind.review);

  /// 첨삭을 한 번 돌린다. 저장된 대화만 보여 주고 모델을 부르지 않았으면 false.
  Future<bool> _reviewOnce() async {
    _setBusyStage(0);
    await _ensureTailoredResume();
    _setBusyStage(1);
    if (_reviewRequest == null) {
      final snapshot = await widget.client.context(
        widget.cohortId,
        widget.resumeId,
        job: widget.generalReview ? null : widget.jobId,
        tailoredResumeId: widget.generalReview ? null : _tailoredResumeId,
      );
      final content = Map<String, dynamic>.from(snapshot['content'] as Map);
      if (!sameResumeContent(_preview, content)) {
        throw const FormatException(
          '화면과 저장된 이력서가 다릅니다. 창을 닫고 저장 또는 새로고침한 뒤 다시 추천해 주세요.',
        );
      }
      // 재첨삭: 저장된 대화가 있으면 이력서가 그대로인지 본다. 고쳤으면 지난 대화를 이어 쓰지 않고 처음부터
      // 첨삭한다. 그대로인데 이미 마친 대화면 모델을 부르지 않고 저장된 대화만 보여 준다(다시 첨삭은 완료 카드 버튼).
      final restored = _result;
      if (restored != null) {
        if (restored['input_hash'] != snapshot['input_hash']) {
          _resetSession();
          _restartedFromSaved = true;
        } else if (_sessionCompleted) {
          _setBusyStage(4);
          return false;
        }
      }
      _reviewRequest = {
        ..._identity,
        'request_id': _id(),
        'expected_input_hash': snapshot['input_hash'],
        'review_mode': widget.generalReview ? 'general' : 'job',
        if (!widget.generalReview && _tailoredResumeId != null)
          'tailored_resume_id': _tailoredResumeId,
        if (!widget.generalReview) ...{
          'selected_job_id': widget.jobId,
          'expected_job_hash': (snapshot['job_source'] as Map)['snapshot_hash'],
        },
      };
    }
    _setBusyStage(2);
    _result = await widget.client.review(_reviewRequest!);
    _setBusyStage(4);
    _appendReview(_result!, isFirstReview: _messages.isEmpty);
    if (_restartedFromSaved) {
      _restartedFromSaved = false;
      _messages.insert(
        0,
        const _ReviewChatMessage.assistant('이력서를 처음부터 다시 첨삭했어요. 지난 대화는 정리했어요.'),
      );
    }
    _restartNotice = null;
    await _persistSession();
    return true;
  }

  Future<void> _ensureTailoredResume() async {
    if (widget.generalReview || _tailoredResumeId != null) return;
    final tailored = await widget.client.createTailoredResume({
      'cohort_id': widget.cohortId,
      'resume_id': widget.resumeId,
      'selected_job_id': widget.jobId,
    });
    final tailoredId = tailored['tailored_resume_id'] as String?;
    final rawContent = tailored['content'] as Map?;
    if (tailoredId == null || tailoredId.isEmpty || rawContent == null) {
      throw const FormatException('공고별 이력서를 준비하지 못했습니다. 다시 시도해 주세요.');
    }
    final tailoredContent = ResumeContent.fromMap(
      Map<String, dynamic>.from(rawContent),
    );
    _tailoredResumeId = tailoredId;
    final session = Map<String, dynamic>.from(
      tailored['review_session'] as Map? ?? const {},
    );
    if (mounted) {
      setState(() {
        _preview = tailoredContent;
        _restoreSession(session);
      });
    } else {
      _preview = tailoredContent;
    }
  }

  Future<void> _reload() async {
    final snapshot = await widget.client.context(
      widget.cohortId,
      widget.resumeId,
      job: widget.generalReview ? null : widget.jobId,
      tailoredResumeId: widget.generalReview ? null : _tailoredResumeId,
    );
    final content = ResumeContent.fromMap(
      Map<String, dynamic>.from(snapshot['content'] as Map),
    );
    // 공고 맞춤본은 기본 이력서와 분리되어 서버에 자동 저장된다.
    if (widget.generalReview) widget.onChanged(content);
    if (mounted) {
      setState(() {
        _preview = content;
        _changed = true;
        _mutationPending = false;
      });
    }
  }

  void _appendReview(
    Map<String, dynamic> review, {
    required bool isFirstReview,
    String? answeredFieldPath,
    String? answeredQuestionId,
    String? answeredRequirementId,
    bool isGapAudit = false,
  }) {
    _pendingQuestion = null;
    _requirementFocusPath = null;
    final requirementMap = review['requirement_map'] as List?;
    if (requirementMap != null && requirementMap.isNotEmpty) {
      _requirementRows = requirementMap
          .whereType<Map>()
          .map(ReviewRequirementRow.fromMap)
          .toList();
    }
    final starChecks = starChecksByPath(review['star_checks']);
    if (starChecks.isNotEmpty) _starChecks = starChecks;
    if (isFirstReview) {
      final summary =
          review['summary'] as String? ??
          (widget.generalReview ? '이력서 문장을 검토했습니다.' : '이력서와 선택 공고를 비교했습니다.');
      _messages.add(
        _ReviewChatMessage.assistant(_formatInitialSummary(summary)),
      );
    }
    final reviews = (review['sentence_reviews'] as List? ?? []).cast<Map>();
    final job = Map<String, dynamic>.from(
      review['job_source'] as Map? ??
          {'company': widget.jobCompany, 'title': widget.jobTitle},
    );
    var displayedSuggestions = 0;
    final identitySuggestions = <Map<String, dynamic>>[];
    final polishSuggestions = <Map<String, dynamic>>[];
    // 서버는 "어느 항목에서 했나요?" 질문의 답을 답에 적힌 항목으로 옮긴다. 수정안은 옮겨진 항목에 생기므로
    // 질문이 붙어 있던 칸이 아니라 서버가 기록한 답의 칸으로 거른다. 예전에는 질문 칸으로만 걸러 사용자에게
    // 수정안이 하나도 안 보였다(2026-09-15 새 케이스: AVFoundation 답이 다른 프로젝트로 옮겨짐).
    final resolvedFieldPath = _resolvedAnswerFieldPath(
      review,
      answeredQuestionId,
      answeredFieldPath,
    );
    // 답에 이름이 나온 다른 항목도 이번 재첨삭에서 함께 고쳤다. 그 항목의 수정안도 보여 준다(2026-09-15).
    final scopePaths = {
      for (final path in review['answer_scope_paths'] as List? ?? const [])
        if (path is String) path,
    };
    // 답한 칸의 수정안을 먼저, 이름이 나온 다른 항목의 수정안을 그 뒤에 보여 준다. 모델이 내는 순서는 매번 다르다.
    final order = [
      for (var i = 0; i < reviews.length; i++)
        if (resolvedFieldPath == null ||
            reviews[i]['field_path'] == resolvedFieldPath)
          i,
      for (var i = 0; i < reviews.length; i++)
        if (resolvedFieldPath != null &&
            reviews[i]['field_path'] != resolvedFieldPath)
          i,
    ];
    for (final index in order) {
      final sentence = Map<String, dynamic>.from(reviews[index]);
      // 새 프로젝트 추가 수정안은 아직 없는 칸(projects[N])이라 답의 칸으로 거르지 않고, 방금 답한 질문에서 나온 것만 보여 준다.
      final newItem = sentence['new_item'];
      final fromThisAnswer =
          (newItem is Map && newItem['question_id'] == answeredQuestionId) ||
          scopePaths.contains(sentence['field_path']);
      if (resolvedFieldPath != null &&
          sentence['field_path'] != resolvedFieldPath &&
          !fromThisAnswer) {
        continue;
      }
      if (sentence['suggested_revision'] is String &&
          (sentence['suggested_revision'] as String).trim().isNotEmpty) {
        sentence['_index'] = index;
        if (!widget.generalReview &&
            _isIdentityPlaceholderSuggestion(sentence)) {
          sentence['_company'] = job['company'] ?? widget.jobCompany;
          sentence['_title'] =
              job['role_title'] ?? job['title'] ?? widget.jobTitle;
          identitySuggestions.add(sentence);
        } else if (isFirstReview &&
            const {
              'spelling',
              'tone',
              'clarity',
            }.contains(sentence['edit_type'])) {
          // 새 사실 없이 표현만 고친 수정안. 하나씩 넘기지 않고 한 카드에서 골라 한 번에 적용한다.
          polishSuggestions.add(sentence);
        } else {
          _suggestionQueue.add(_ReviewChatMessage.suggestion(sentence));
        }
        displayedSuggestions++;
      }
    }
    if (polishSuggestions.length == 1) {
      _suggestionQueue.insert(
        0,
        _ReviewChatMessage.suggestion(polishSuggestions.single),
      );
    } else if (polishSuggestions.length > 1) {
      // 회사명·직무명 카드와 같은 묶음 적용 경로(_indices)를 쓴다. 적용·되돌리기·건너뛰기·세션 저장이
      // 이미 여러 수정안을 한 번에 다룬다. 첫 질문보다 먼저 보여 준다.
      _suggestionQueue.insert(
        0,
        _ReviewChatMessage.identityConfirmation({
          '_kind': 'polish',
          'field_path': polishSuggestions.first['field_path'],
          'stage': 1,
          'items': polishSuggestions,
          '_indices': [for (final item in polishSuggestions) item['_index']],
        }),
      );
    }
    if (identitySuggestions.isNotEmpty) {
      // 회사명·직무명 자리표시자는 같은 선택 공고의 확정값으로 바뀝니다.
      // 항목마다 같은 질문을 반복하지 않고 한 번의 확인으로 묶어 적용합니다.
      final groupedIdentitySuggestion =
          Map<String, dynamic>.from(
              identitySuggestions.first,
            )
            ..['_indices'] = identitySuggestions
                .map((suggestion) => suggestion['_index'] as int)
                .toList();
      _suggestionQueue.add(
        _ReviewChatMessage.identityConfirmation(groupedIdentitySuggestion),
      );
    }
    final queuedSuggestion = _takeNextSuggestion();
    if (queuedSuggestion != null) {
      _messages.add(queuedSuggestion);
      final fieldPath =
          queuedSuggestion.suggestion?['field_path'] as String? ??
          queuedSuggestion.identitySuggestion?['field_path'] as String?;
      _focusPreviewField(fieldPath);
    }
    final answeredNone =
        (review['telemetry'] as Map?)?['model_skipped'] == 'none_answer';
    if (!isFirstReview && !isGapAudit && answeredNone) {
      // "없음" 카드. 수정안을 만들려다 실패한 게 아니라 고칠 사실이 없는 것이다.
      String? label;
      for (final row in _requirementRows) {
        if (row.id == answeredRequirementId) label = row.label;
      }
      _messages.add(
        _ReviewChatMessage.assistant(
          label != null ? '알겠어요. 이력서에는 넣지 않을게요.' : '알겠어요. 다음 질문으로 넘어갈게요.',
        ),
      );
    } else if (!isFirstReview && !isGapAudit && displayedSuggestions == 0) {
      final warnings = (review['grounding_warnings'] as List? ?? const [])
          .whereType<String>();
      final answerAlreadyPresent = warnings.any(
        (warning) => warning.startsWith('answer_already_present:'),
      );
      // 답변으로 공고 요건이 확인됐는지. 수정안은 없어도 요건 표는 바뀐다.
      final requirementConfirmed =
          answeredRequirementId != null &&
          (review['requirement_map'] as List? ?? const []).whereType<Map>().any(
            (row) =>
                row['id'] == answeredRequirementId &&
                (row['status'] == 'met' || row['status'] == 'partial'),
          );
      // 수정안이 없다고 실패가 아니다. 지원 자격처럼 확인만 되고 이력서에 적을 문장이 없는 답이
      // 많은데, 예전 문구("안전한 수정안을 만들지 못했습니다")는 오류처럼 읽혔다(2026-09-15 앱).
      _messages.add(
        _ReviewChatMessage.assistant(
          answerAlreadyPresent
              ? '확인했어요. 이미 이력서에 들어 있는 내용이라 그대로 두고 다음으로 넘어갈게요.'
              : requirementConfirmed
              ? '확인했어요. 공고 요건 표에 반영하고 다음으로 넘어갈게요.'
              : '확인했어요. 다음으로 넘어갈게요.',
        ),
      );
    }
    final questions = (review['questions'] as List? ?? []).cast<Map>();
    _syncQuestionsWithServer(
      questions,
      dropMissing: !isFirstReview && !isGapAudit,
    );
    final nextQuestion = _takeNextQuestion();
    if (nextQuestion != null) {
      if (displayedSuggestions > 0 || _suggestionQueue.isNotEmpty) {
        // The user should decide whether to apply the current revision before
        // moving on. Show the next unanswered question after the revised
        // resume is reloaded.
        _pendingQuestion = nextQuestion;
      } else {
        _messages.add(_ReviewChatMessage.question(nextQuestion));
        _focusPreviewField(nextQuestion['field_path'] as String?);
      }
    } else if (!isFirstReview && displayedSuggestions > 0) {
      _messages.add(
        const _ReviewChatMessage.assistant(
          '방금 답한 항목을 기준으로 수정안을 만들었습니다. 적용 전 내용을 확인해 주세요.',
        ),
      );
    }
    if (isGapAudit && nextQuestion == null) {
      _messages.add(
        const _ReviewChatMessage.assistant(
          '누락 점검까지 완료했습니다. 추가로 확인할 중요한 항목이 없습니다.',
        ),
      );
    } else if (!isFirstReview &&
        displayedSuggestions == 0 &&
        nextQuestion == null) {
      _scheduleGapAudit();
    }
  }

  String _formatInitialSummary(String summary) {
    final sentences = summary
        .split(RegExp(r'(?<=[.!?])\s+'))
        .map((sentence) => sentence.trim())
        .where((sentence) => sentence.isNotEmpty)
        .take(3)
        .toList();
    if (sentences.isEmpty) return '검토 요약\n\n• 이력서와 공고를 비교했습니다.';
    return '검토 요약\n\n${sentences.map((sentence) => '• $sentence').join('\n\n')}';
  }

  String _questionKey(Map<String, dynamic> question) {
    // A follow-up response gets a new question_id.  Deduplicate by the target
    // and intent instead, so wording changes cannot ask the same thing again.
    // 공고 요건 질문은 요건마다 하나다. 같은 프로젝트·같은 topic이라도 요건이 다르면 다른 질문이다.
    final requirementId = question['requirement_id'] as String?;
    if (requirementId != null && requirementId.isNotEmpty) {
      return 'requirement|$requirementId';
    }
    return '${question['field_path']}|${question['topic']}';
  }

  bool _hasQuestionKey(String key) {
    if (_pendingQuestion != null && _questionKey(_pendingQuestion!) == key) {
      return true;
    }
    return _questionQueue.any((question) => _questionKey(question) == key) ||
        _messages.any(
          (message) =>
              message.question != null &&
              _questionKey(message.question!) == key,
        );
  }

  Set<String> _acceptedQuestionKeys() => {
    for (final message in _messages)
      if (message.question != null) _questionKey(message.question!),
    for (final question in _questionQueue) _questionKey(question),
    if (_pendingQuestion != null) _questionKey(_pendingQuestion!),
  };

  void _trimQuestionBacklog() {
    final accepted = <String>{};
    for (final message in _messages) {
      if (message.question != null)
        accepted.add(_questionKey(message.question!));
    }
    if (_pendingQuestion != null) {
      final key = _questionKey(_pendingQuestion!);
      if (accepted.length >= _maxReviewQuestions && !accepted.contains(key)) {
        _pendingQuestion = null;
      } else {
        accepted.add(key);
      }
    }
    _questionQueue.removeWhere((question) {
      final key = _questionKey(question);
      if (accepted.contains(key)) return true;
      if (accepted.length >= _maxReviewQuestions) return true;
      accepted.add(key);
      return false;
    });
  }

  void _enqueueQuestions(List<Map> questions) {
    final acceptedKeys = _acceptedQuestionKeys();
    for (final rawQuestion in questions) {
      final question = Map<String, dynamic>.from(rawQuestion);
      final questionId = question['question_id'] as String?;
      if (questionId != null && _answeredQuestionIds.contains(questionId)) {
        continue;
      }
      if ((question['field_path'] as String? ?? '').isEmpty ||
          (question['question'] as String? ?? '').trim().isEmpty) {
        continue;
      }
      final key = _questionKey(question);
      final queuedIndex = _questionQueue.indexWhere(
        (queuedQuestion) => _questionKey(queuedQuestion) == key,
      );
      if (queuedIndex >= 0) {
        // A follow-up review reissues this queued question with its latest
        // review_id. Keep its position, but submit the current server-owned ID.
        _questionQueue[queuedIndex] = question;
      } else if (_pendingQuestion != null &&
          _questionKey(_pendingQuestion!) == key) {
        _pendingQuestion = question;
      } else if (!_hasQuestionKey(key) &&
          acceptedKeys.length < _maxReviewQuestions) {
        _questionQueue.add(question);
        acceptedKeys.add(key);
      }
    }
  }

  /// 위쪽 "첨삭 완료"와 완료 안내 카드의 초록 "첨삭 완료"가 함께 쓴다.
  ///
  /// 초록 버튼은 예전에 창만 닫았다. 완료 상태 저장이 끝나기 전에 목록이 다시 불러와져 "첨삭 진행 중"으로
  /// 남았고, 새로고침해야 "첨삭 완료"로 바뀌었다(2026-09-15 앱). 이제 둘 다 저장을 기다린 뒤 편집기로 옮긴다.
  /// 확인 창은 버리게 될 질문이나 수정안이 남아 있을 때만 띄운다.
  Future<void> _completeReview({bool alwaysConfirm = true}) async {
    if (_busy || _result == null) return;
    final shouldComplete = !alwaysConfirm && !_hasActiveSuggestion
        ? true
        : await showDialog<bool>(
            context: context,
            builder: (dialogContext) => AlertDialog(
              title: const Text('첨삭을 완료할까요?'),
              content: const Text(
                '현재까지 적용한 내용은 유지됩니다. 남은 질문과 적용하지 않은 수정안은 건너뛰고 첨삭을 완료합니다.',
              ),
              actions: [
                TextButton(
                  onPressed: () => Navigator.pop(dialogContext, false),
                  child: const Text('계속 첨삭'),
                ),
                FilledButton(
                  onPressed: () => Navigator.pop(dialogContext, true),
                  child: const Text('첨삭 완료'),
                ),
              ],
            ),
          );
    if (shouldComplete != true || !mounted) return;
    setState(() {
      _manuallyCompleted = true;
      _questionQueue.clear();
      _pendingQuestion = null;
      _suggestionQueue.clear();
      for (final message in _messages) {
        final questionId = message.question?['question_id'] as String?;
        if (questionId != null) _answeredQuestionIds.add(questionId);
        message.suggestion?['_skipped'] = true;
        message.identitySuggestion?['_skipped'] = true;
      }
    });
    await _run(() async {
      _mutationPending = true;
      try {
        await _persistSession();
        await _sessionSaveChain;
        String? workspaceResumeId;
        if (!widget.generalReview && _tailoredResumeId != null) {
          workspaceResumeId = await widget.client.promoteTailoredResume(
            widget.cohortId,
            widget.resumeId,
            _tailoredResumeId!,
          );
        }
        if (mounted) _closeWith(workspaceResumeId);
      } finally {
        _mutationPending = false;
      }
    }, kind: _ReviewBusyKind.apply);
  }

  Map<String, dynamic>? _takeNextQuestion() {
    while (_questionQueue.isNotEmpty) {
      final question = _questionQueue.removeAt(0);
      final questionId = question['question_id'] as String?;
      if (questionId == null || !_answeredQuestionIds.contains(questionId)) {
        return question;
      }
    }
    return null;
  }

  _ReviewChatMessage? _takeNextSuggestion() {
    if (_suggestionQueue.isEmpty) return null;
    return _suggestionQueue.removeAt(0);
  }

  bool get _hasUnansweredDisplayedQuestion {
    for (final message in _messages) {
      final questionId = message.question?['question_id'] as String?;
      if (message.question != null &&
          (questionId == null || !_answeredQuestionIds.contains(questionId))) {
        return true;
      }
    }
    return false;
  }

  void _scheduleGapAudit() {
    if (_gapAuditScheduled || _gapAuditStarted || _result == null) return;
    _gapAuditScheduled = true;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      _gapAuditScheduled = false;
      if (_gapAuditStarted ||
          _busy ||
          _pendingNoneAnswers > 0 ||
          _result == null ||
          _suggestionQueue.isNotEmpty ||
          _pendingQuestion != null ||
          _questionQueue.isNotEmpty ||
          _hasUnansweredDisplayedQuestion) {
        return;
      }
      final previous = _result!;
      setState(() {
        _gapAuditStarted = true;
        _messages.add(
          const _ReviewChatMessage.assistant(
            '기존 질문이 끝났습니다. 놓친 중요한 보완 항목이 있는지 한 번만 점검합니다.',
          ),
        );
      });
      _run(() async {
        final request = <String, dynamic>{
          ..._identity,
          'request_id': _id(),
          'review_mode': widget.generalReview ? 'general' : 'job',
          'review_phase': 'gap_audit',
          'previous_review_id': previous['review_id'],
          'expected_input_hash': previous['input_hash'],
          if (!widget.generalReview && _tailoredResumeId != null)
            'tailored_resume_id': _tailoredResumeId,
          if (!widget.generalReview) ...{
            'selected_job_id': widget.jobId,
            'expected_job_hash':
                (previous['job_source'] as Map?)?['snapshot_hash'],
          },
        };
        _result = await widget.client.review(request);
        _gapAuditFinished = true;
        _appendReview(_result!, isFirstReview: false, isGapAudit: true);
        await _persistSession();
      }, kind: _ReviewBusyKind.answer);
    });
  }

  void _markAppliedSuggestionMessages(
    Set<int> appliedIndices,
    Map<String, dynamic> application,
  ) {
    for (final message in _messages) {
      message.suggestion?['_undo_available'] = false;
      message.identitySuggestion?['_undo_available'] = false;
    }
    for (final message in _messages) {
      final suggestion = message.suggestion;
      if (suggestion != null && appliedIndices.contains(suggestion['_index'])) {
        suggestion['_applied'] = true;
        suggestion['_undone'] = false;
        suggestion['_operation_id'] = application['operation_id'];
        suggestion['_application_input_hash'] = application['input_hash'];
        suggestion['_undo_available'] = true;
      }
      final identitySuggestion = message.identitySuggestion;
      if (identitySuggestion != null) {
        final indices = (identitySuggestion['_indices'] as List? ?? const [])
            .whereType<int>()
            .toList();
        if (indices.isNotEmpty && indices.every(appliedIndices.contains)) {
          identitySuggestion['_applied'] = true;
          identitySuggestion['_undone'] = false;
          identitySuggestion['_operation_id'] = application['operation_id'];
          identitySuggestion['_application_input_hash'] =
              application['input_hash'];
          identitySuggestion['_undo_available'] = true;
        }
      }
    }
  }

  void _skipSuggestion(List<int> indices) {
    if (_busy || indices.isEmpty) return;
    setState(() {
      for (final message in _messages.reversed) {
        final suggestion = message.suggestion;
        if (suggestion != null &&
            suggestion['_applied'] != true &&
            suggestion['_skipped'] != true &&
            indices.contains(suggestion['_index'])) {
          suggestion['_skipped'] = true;
          break;
        }
        final identitySuggestion = message.identitySuggestion;
        if (identitySuggestion != null &&
            identitySuggestion['_applied'] != true &&
            identitySuggestion['_skipped'] != true) {
          final suggestionIndices =
              (identitySuggestion['_indices'] as List? ?? const [])
                  .whereType<int>()
                  .toList();
          if (suggestionIndices.length == indices.length &&
              suggestionIndices.every(indices.contains)) {
            identitySuggestion['_skipped'] = true;
            break;
          }
        }
      }
    });
    final nextSuggestion = _takeNextSuggestion();
    if (nextSuggestion != null) {
      setState(() => _messages.add(nextSuggestion));
      final fieldPath =
          nextSuggestion.suggestion?['field_path'] as String? ??
          nextSuggestion.identitySuggestion?['field_path'] as String?;
      _focusPreviewField(fieldPath);
      unawaited(_persistSession());
      return;
    }
    if (_pendingQuestion != null) {
      final question = _pendingQuestion!;
      setState(() {
        _pendingQuestion = null;
        _messages.add(_ReviewChatMessage.question(question));
      });
      _focusPreviewField(question['field_path'] as String?);
      unawaited(_persistSession());
      return;
    }
    _scheduleGapAudit();
    unawaited(_persistSession());
  }

  bool _isIdentityPlaceholderSuggestion(Map<String, dynamic> sentence) {
    final original = sentence['original_quote'] as String? ?? '';
    return original.contains('[회사명]') || original.contains('[직무명]');
  }

  String _previewTargetForFieldPath(String fieldPath) {
    final parts = fieldPath.split('.');
    // 자기소개서는 하나의 긴 본문이 아니라 문항별 카드로 표시한다.
    // 따라서 body·subtitle 어느 필드를 질문해도 해당 문항 카드에 맞춘다.
    if (parts.length >= 2 && parts.first == 'selfIntroduction') {
      return '${parts[0]}.${parts[1]}';
    }
    return fieldPath.split(RegExp(r'[.\[]')).first;
  }

  GlobalKey _previewKeyFor(String fieldPath) => _previewSectionKeys.putIfAbsent(
    _previewTargetForFieldPath(fieldPath),
    GlobalKey.new,
  );

  /// 서버가 답을 옮겨 둔 칸. 응답의 `confirmed_answers`에서 이 질문의 답을 찾아 그 `field_path`를 쓴다.
  static String? _resolvedAnswerFieldPath(
    Map<String, dynamic> review,
    String? questionId,
    String? fallback,
  ) {
    if (questionId == null) return fallback;
    for (final raw in (review['confirmed_answers'] as List? ?? const [])) {
      if (raw is Map && raw['question_id'] == questionId) {
        return raw['field_path'] as String? ?? fallback;
      }
    }
    return fallback;
  }

  void _focusPreviewField(String? fieldPath) {
    if (fieldPath == null || fieldPath == _focusedFieldPath) return;
    _focusedFieldPath = fieldPath;
    final key = _previewKeyFor(fieldPath);
    WidgetsBinding.instance.addPostFrameCallback((_) {
      final target = key.currentContext;
      if (target != null) {
        Scrollable.ensureVisible(
          target,
          alignment: 0.18,
          duration: const Duration(milliseconds: 380),
          curve: Curves.easeOutCubic,
        );
      }
    });
  }

  /// "없음" 카드. 고칠 사실이 없으니 서버 응답을 기다리지 않고 바로 다음 질문을 띄운다.
  ///
  /// 서버는 이 답이면 모델을 부르지 않고 기록만 한다(요건이면 absent). 그래도 1~2초 걸리는데, 그동안
  /// 대기 표시를 띄우면 "없음"을 여러 번 누르는 흐름이 느리게 느껴졌다. 기록은 뒤에서 순서대로 보내고,
  /// 서버가 다시 매긴 질문 번호는 화면에 떠 있는 질문에 옮겨 둔다.
  void _submitNoneAnswer(Map<String, dynamic> question) {
    if (_busy || _result == null) return;
    final questionId = question['question_id'] as String?;
    if (questionId != null && _answeredQuestionIds.contains(questionId)) return;
    final requirementId = question['requirement_id'] as String?;
    Map<String, dynamic>? next;
    setState(() {
      if (questionId != null) _answeredQuestionIds.add(questionId);
      _messages.add(const _ReviewChatMessage.user('없음'));
      _messages.add(
        _ReviewChatMessage.assistant(
          requirementId != null
              ? '알겠어요. 이력서에는 넣지 않을게요.'
              : '알겠어요. 다음 질문으로 넘어갈게요.',
        ),
      );
      if (requirementId != null) {
        _requirementRows = [
          for (final row in _requirementRows)
            // 근거를 못 찾은 요건만 해당 없음. 일부 근거가 있는 요건은 좁게 물은 질문에만 없다고 한 것이다.
            row.id == requirementId && row.status == 'unconfirmed'
                ? ReviewRequirementRow.fromMap({
                    ...row.toMap(),
                    'status': 'absent',
                    'source': 'user',
                    'evidence_paths': const [],
                    'evidence_quotes': const [],
                  })
                : row,
        ];
      }
      next = _takeNextQuestion();
      if (next != null) _messages.add(_ReviewChatMessage.question(next!));
    });
    if (next != null) _focusPreviewField(next!['field_path'] as String?);
    // 칩을 누르면 포커스가 칩으로 간다. 다음 질문이 떴으니 입력칸으로 돌려준다.
    _refocusAnswerField();
    _pendingNoneAnswers++;
    _noneAnswerChain = _noneAnswerChain
        .then((_) => _recordNoneAnswer(question))
        .whenComplete(() => _pendingNoneAnswers--);
    unawaited(
      _noneAnswerChain.then((_) async {
        if (!mounted) return;
        await _persistSession();
        if (_pendingNoneAnswers == 0 && !_hasUnansweredDisplayedQuestion) {
          _scheduleGapAudit();
        }
      }),
    );
  }

  Future<void> _recordNoneAnswer(Map<String, dynamic> question) async {
    if (!mounted || _result == null) return;
    // 앞선 기록 사이에 서버가 이 질문을 뺐으면 기록할 것이 없다.
    if (!_isQuestionStillOpen(question)) return;
    final previous = _result!;
    try {
      final response = await widget.client.review({
        ..._identity,
        'request_id': _id(),
        'review_mode': widget.generalReview ? 'general' : 'job',
        if (!widget.generalReview && _tailoredResumeId != null)
          'tailored_resume_id': _tailoredResumeId,
        if (!widget.generalReview) ...{
          'selected_job_id': widget.jobId,
          'expected_job_hash':
              (previous['job_source'] as Map?)?['snapshot_hash'],
        },
        'previous_review_id': previous['review_id'],
        'expected_input_hash': previous['input_hash'],
        'answers': [
          {
            'question_id': question['question_id'],
            'field_path': question['field_path'],
            'question': question['question'],
            'answer': '없음',
          },
        ],
      });
      if (!mounted) return;
      setState(() {
        _result = response;
        final requirementMap = response['requirement_map'] as List?;
        if (requirementMap != null && requirementMap.isNotEmpty) {
          _requirementRows = requirementMap
              .whereType<Map>()
              .map(ReviewRequirementRow.fromMap)
              .toList();
        }
        final starChecks = starChecksByPath(response['star_checks']);
        if (starChecks.isNotEmpty) _starChecks = starChecks;
        final questions = (response['questions'] as List? ?? const [])
            .whereType<Map>()
            .toList();
        _syncQuestionsWithServer(questions, dropMissing: true);
        if (!_hasUnansweredDisplayedQuestion && _suggestionQueue.isEmpty) {
          final next = _takeNextQuestion();
          if (next != null) _messages.add(_ReviewChatMessage.question(next));
        }
      });
    } on ResumeReviewApiException catch (error) {
      // 서버가 이미 뺀 질문이면(422) 기록할 것이 없으니 넘어간다. 나머지 실패만 알린다.
      if (mounted && error.statusCode != 422) {
        setState(() => _error = '없음 답변을 저장하지 못했습니다. 다시 시도해 주세요. ($error)');
      }
    } catch (error) {
      if (mounted) {
        setState(() => _error = '없음 답변을 저장하지 못했습니다. 다시 시도해 주세요. ($error)');
      }
    }
  }

  /// 서버가 돌려준 질문 목록을 기준으로 대기열을 맞춘다.
  ///
  /// 서버는 답할 때마다 남은 질문을 다시 정리한다(답한 질문과 비슷한 질문, 이미 확인된 요건 질문, 요건
  /// 질문 개수 제한을 넘친 질문을 뺀다). 앱이 예전 목록을 그대로 들고 있으면 서버가 이미 뺀 질문을 띄우고,
  /// 그 질문에 답하면 서버가 "모르는 질문"으로 거절한다(2026-09-15 앱에서 "없음" 기록이 실패했다).
  void _syncQuestionsWithServer(
    List<Map> questions, {
    required bool dropMissing,
  }) {
    _adoptReissuedQuestionIds(questions);
    if (dropMissing) {
      final keys = {
        for (final raw in questions)
          _questionKey(Map<String, dynamic>.from(raw)),
      };
      _questionQueue.removeWhere(
        (question) => !keys.contains(_questionKey(question)),
      );
      // 화면에 먼저 띄웠지만(없음 뒤 바로 다음 질문) 서버가 뺀 질문은 답하지 않은 채 대화에서 걷어낸다.
      _messages.removeWhere((message) {
        final shown = message.question;
        final shownId = shown?['question_id'] as String?;
        final stale =
            shown != null &&
            shownId != null &&
            !_answeredQuestionIds.contains(shownId) &&
            !keys.contains(_questionKey(shown));
        if (stale) _answeredQuestionIds.add(shownId);
        return stale;
      });
      if (_pendingQuestion != null &&
          !keys.contains(_questionKey(_pendingQuestion!))) {
        _pendingQuestion = null;
      }
    }
    _enqueueQuestions(questions);
  }

  /// 화면에 띄운 질문이 서버의 최신 질문 목록에 아직 있는가. 없으면 서버가 이미 뺀 질문이다.
  bool _isQuestionStillOpen(Map<String, dynamic> question) {
    final questionId = question['question_id'] as String?;
    final serverQuestions = (_result?['questions'] as List? ?? const [])
        .whereType<Map>();
    return serverQuestions.any((raw) => raw['question_id'] == questionId);
  }

  /// 서버가 이미 뺀 질문에 답하려 할 때. 보내지 않고 다음 질문으로 넘어간다.
  ///
  /// 예전에는 친 답을 입력칸에 그대로 두었는데, 보내지지도 않은 글이 회색으로 남아 사용자는 답이
  /// 전송된 줄 알았다(2026-09-16 앱). 이제 입력칸을 비우고, 무슨 일이 있었는지 대화에 적는다.
  /// 친 글은 안내 안에 그대로 실어 다시 쓸 수 있게 한다.
  void _skipStaleQuestion(Map<String, dynamic> question, {String? typed}) {
    Map<String, dynamic>? next;
    final text = (typed ?? _answerController.text).trim();
    _answerController.clear();
    setState(() {
      final questionId = question['question_id'] as String?;
      if (questionId != null) _answeredQuestionIds.add(questionId);
      // 보내려다 거절당한 경우엔 사용자 말풍선을 이미 붙여 두었다. 답이 두 번 보이지 않게 걷어낸다.
      if (typed != null &&
          _messages.isNotEmpty &&
          _messages.last.isUser &&
          _messages.last.text == text) {
        _messages.removeLast();
      }
      _messages.add(
        _ReviewChatMessage.assistant(
          text.isEmpty
              ? '앞 질문이 정리돼 넘어갈게요.'
              : '앞 질문이 정리돼 이 답은 보내지 못했어요. 필요하면 다시 붙여 넣어 주세요.\n\n$text',
        ),
      );
      next = _takeNextQuestion();
      if (next != null) _messages.add(_ReviewChatMessage.question(next!));
    });
    if (next != null) {
      _focusPreviewField(next!['field_path'] as String?);
      _refocusAnswerField();
    } else {
      _scheduleGapAudit();
    }
  }

  /// 서버는 응답마다 남은 질문에 새 번호를 매긴다. 이미 화면에 띄운 질문도 새 번호로 답해야 받아 준다.
  void _adoptReissuedQuestionIds(List<Map> questions) {
    void adopt(Map<String, dynamic>? target, String key, Object? reissuedId) {
      if (target == null || _questionKey(target) != key) return;
      final currentId = target['question_id'] as String?;
      if (currentId != null && _answeredQuestionIds.contains(currentId)) return;
      target['question_id'] = reissuedId;
    }

    for (final raw in questions) {
      final reissued = Map<String, dynamic>.from(raw);
      final key = _questionKey(reissued);
      final reissuedId = reissued['question_id'];
      for (final message in _messages) {
        adopt(message.question, key, reissuedId);
      }
      // 아직 띄우지 않은 질문도 새 번호를 받아야 한다. 화면에 뜬 질문만 갈아 주던 때는 대기열에서
      // 꺼낸 질문이 죽은 번호를 들고 있어, 답을 보내지 못하고 조용히 건너뛰었다(친 답은 입력칸에
      // 남고 다음 질문만 쌓였다). 서버는 첨삭마다 남은 질문에 새 번호를 매긴다.
      for (final queued in _questionQueue) {
        adopt(queued, key, reissuedId);
      }
      adopt(_pendingQuestion, key, reissuedId);
    }
  }

  void _focusRequirement(ReviewRequirementRow row) {
    final path = row.evidencePaths.isNotEmpty ? row.evidencePaths.first : null;
    setState(() => _requirementFocusPath = path);
    if (path != null) {
      _focusedFieldPath = null;
      _focusPreviewField(path);
    }
  }

  Future<void> _submitAnswer(Map<String, dynamic> question) async {
    final answer = _answerController.text.trim();
    if (answer.isEmpty || _busy || _result == null) return;
    if (_pendingNoneAnswers > 0) {
      // 앞서 누른 "없음" 기록이 서버에 도착해야 이 답변이 최신 첨삭 결과를 이어받는다.
      setState(() => _busy = true);
      await _noneAnswerChain;
      if (!mounted) return;
      setState(() => _busy = false);
    }
    // 보내기 전에 "이 질문은 죽었다"고 앱이 미리 판단하지 않는다. 그 판단이 틀리면 멀쩡한 답이
    // 조용히 버려졌다(2026-09-16 앱: 서버는 질문을 알고 있는데도 답이 전송되지 않았다).
    // 일단 보내고, 서버가 모르는 질문이라고 거절할 때만(422) 안내하고 넘어간다.
    final previous = _result!;
    _answerController.clear();
    setState(() {
      final questionId = question['question_id'] as String?;
      if (questionId != null) _answeredQuestionIds.add(questionId);
      _messages.add(_ReviewChatMessage.user(answer));
    });
    await _run(() async {
      final nextRequest = <String, dynamic>{
        ..._identity,
        'request_id': _id(),
        'review_mode': widget.generalReview ? 'general' : 'job',
        if (!widget.generalReview && _tailoredResumeId != null)
          'tailored_resume_id': _tailoredResumeId,
        if (!widget.generalReview) ...{
          'selected_job_id': widget.jobId,
          'expected_job_hash':
              (previous['job_source'] as Map?)?['snapshot_hash'],
        },
        'previous_review_id': previous['review_id'],
        'expected_input_hash': previous['input_hash'],
        'answers': [
          {
            'question_id': question['question_id'],
            'field_path': question['field_path'],
            'question': question['question'],
            'answer': answer,
          },
        ],
      };
      final Map<String, dynamic> response;
      try {
        response = await widget.client.review(nextRequest);
      } on ResumeReviewApiException catch (error) {
        if (error.statusCode != 422) rethrow;
        // 서버가 이미 정리한 질문이다. 답은 남겨 보여 주고 다음 질문으로 넘어간다.
        _skipStaleQuestion(question, typed: answer);
        return;
      }
      _result = response;
      // The server rebases the previous review after an applied edit.  This
      // new review now owns the latest resume snapshot and can accept another
      // selected revision in the same chat flow.
      if (mounted) {
        setState(() {
          _appliedSuggestionIndices.clear();
          _applyRequest = null;
        });
      }
      _appendReview(
        _result!,
        isFirstReview: false,
        answeredFieldPath: question['field_path'] as String?,
        answeredQuestionId: question['question_id'] as String?,
        answeredRequirementId: question['requirement_id'] as String?,
      );
      await _persistSession();
    }, kind: _ReviewBusyKind.answer);
    // 답을 보내고 나면 다음 질문이 바로 뜬다. 포커스를 입력칸에 돌려줘야 클릭 없이 이어서 칠 수 있다.
    _refocusAnswerField();
  }

  /// 다음 질문에 바로 답할 수 있게 입력칸에 포커스를 돌려준다.
  ///
  /// 입력칸이 꺼져 있으면(처리 중·질문 없음) 아무것도 하지 않는다. 꺼진 칸에 포커스를 주면
  /// 커서만 깜빡이고 글자는 안 들어간다.
  void _refocusAnswerField() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted || _busy || _error != null) return;
      if (_hasUnansweredDisplayedQuestion) _answerFocus.requestFocus();
    });
  }

  Future<void> _applySuggestion(List<int> indices) async {
    if (_busy ||
        indices.isEmpty ||
        indices.every(_appliedSuggestionIndices.contains)) {
      return;
    }
    setState(() {
      _selected
        ..clear()
        ..addAll(indices);
      _applyRequest = null;
    });
    await _apply();
  }

  Future<void> _apply() => _run(() async {
    _setBusyStage(0);
    _mutationPending = true;
    _changed = false;
    _applyRequest ??= {
      ..._identity,
      'request_id': _id(),
      'review_id': _result!['review_id'],
      'expected_input_hash': _result!['input_hash'],
      'selected_indices': _selected.toList()..sort(),
      if (_tailoredResumeId != null) 'tailored_resume_id': _tailoredResumeId,
    };
    final application = await _mutate(
      () => widget.client.apply(_applyRequest!),
    );
    _setBusyStage(1);
    // The server has rebased this review to the persisted content.  Keep the
    // next answer on the current snapshot rather than the pre-apply hash.
    _result!['input_hash'] = application['input_hash'];
    // 수정안을 받아들였다. 고른 것이 전부보다 적으면 부분 적용이다.
    _hadApply = true;
    final applyOps = widget.aiOps;
    final applyLogId = _reviewLogId;
    if (applyOps != null && applyLogId != null) {
      final selected = _selected.length;
      final total = (_result!['suggestions'] as List?)?.length ?? selected;
      await applyOps.recordOutcome(
        cohortId: widget.cohortId,
        logId: applyLogId,
        outcome: selected < total
            ? AiOpsOutcomes.partialApply
            : AiOpsOutcomes.applied,
        draftId: 'apply',
        promptVersion: _reviewPromptVersion,
        type: AiOpsTypes.resumeReview,
      );
    }
    if (mounted) {
      setState(() {
        _appliedSuggestionIndices.addAll(_selected);
        _markAppliedSuggestionMessages(_selected, application);
      });
    }
    await _reload();
    _setBusyStage(2);
    if (!mounted) return;
    final nextSuggestion = _takeNextSuggestion();
    if (nextSuggestion != null) {
      setState(() => _messages.add(nextSuggestion));
      final fieldPath =
          nextSuggestion.suggestion?['field_path'] as String? ??
          nextSuggestion.identitySuggestion?['field_path'] as String?;
      _focusPreviewField(fieldPath);
      await _persistSession();
      return;
    }
    if (_pendingQuestion != null) {
      final question = _pendingQuestion!;
      setState(() {
        _pendingQuestion = null;
        _messages.add(_ReviewChatMessage.question(question));
      });
      _focusPreviewField(question['field_path'] as String?);
      await _persistSession();
      return;
    }
    _scheduleGapAudit();
    await _persistSession();
  }, kind: _ReviewBusyKind.apply);

  Future<void> _undoSuggestion(Map<String, dynamic> item) async {
    if (_busy || item['_undo_available'] != true) return;
    await _run(() async {
      final operationId = item['_operation_id'] as String?;
      final applicationInputHash = item['_application_input_hash'] as String?;
      if (operationId == null || applicationInputHash == null) return;
      final indices = (item['_indices'] as List? ?? [item['_index']])
          .whereType<int>()
          .toSet();
      _mutationPending = true;
      _changed = false;
      final undoRequest = {
        ..._identity,
        'request_id': _id(),
        'application_id': operationId,
        'expected_input_hash': applicationInputHash,
        if (_tailoredResumeId != null) 'tailored_resume_id': _tailoredResumeId,
      };
      final undone = await _mutate(() => widget.client.undo(undoRequest));
      _result!['input_hash'] = undone['input_hash'];
      _applyRequest = null;
      // 받아들였다가 물렸다. **수정안 하나마다 남긴다.**
      //
      // develop은 마지막 적용을 통째로 되돌리는 화면이라 되돌림이 한 번뿐이었다.
      // 여기서는 하나씩 물릴 수 있으므로, 전체를 물렸을 때만 세면 셋 중 둘을
      // 물려도 0으로 잡힌다. 물린 수가 곧 쓸모없었던 수정안의 수다.
      _hadUndo = true;
      final undoOps = widget.aiOps;
      final undoLogId = _reviewLogId;
      if (undoOps != null && undoLogId != null) {
        await undoOps.recordOutcome(
          cohortId: widget.cohortId,
          logId: undoLogId,
          outcome: AiOpsOutcomes.undone,
          draftId: 'undo',
          promptVersion: _reviewPromptVersion,
          type: AiOpsTypes.resumeReview,
        );
      }
      await _reload();
      if (mounted) {
        setState(() {
          _appliedSuggestionIndices.removeAll(indices);
          item['_applied'] = false;
          item['_undone'] = true;
          item['_undo_available'] = false;
        });
      }
      await _persistSession();
    }, kind: _ReviewBusyKind.undo);
  }

  Future<Map<String, dynamic>> _mutate(
    Future<Map<String, dynamic>> Function() action,
  ) async {
    try {
      return await action();
    } on ResumeReviewApiException catch (error) {
      if (error.statusCode < 500) {
        _mutationPending = false;
      }
      rethrow;
    }
  }

  /// 새 말풍선·진행 표시·오류가 붙으면 대화를 맨 아래로 내린다.
  ///
  /// 예전에는 첫 첨삭과 답변 응답을 붙일 때만 내렸다. "없음" 뒤 다음 질문, 수정안 적용 뒤 다음 질문,
  /// 누락 점검 안내처럼 다른 길로 붙은 말풍선은 화면 아래에 가려져 사용자가 직접 내려야 했다.
  /// 말풍선을 붙이는 곳마다 부르는 대신 build에서 대화 끝의 상태가 바뀌었는지만 본다.
  void _followChatBottom() {
    final signature = '${_messages.length}|$_busy|$_busyStage|${_error ?? ''}';
    if (signature == _chatTailSignature) return;
    _chatTailSignature = signature;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted || !_chatScrollController.hasClients) return;
      _chatScrollController.animateTo(
        _chatScrollController.position.maxScrollExtent,
        duration: const Duration(milliseconds: 220),
        curve: Curves.easeOut,
      );
    });
  }

  @override
  Widget build(BuildContext context) {
    _followChatBottom();
    Map<String, dynamic>? activeQuestion;
    for (final message in _messages.reversed) {
      final questionId = message.question?['question_id'] as String?;
      if (message.question != null &&
          (questionId == null || !_answeredQuestionIds.contains(questionId))) {
        activeQuestion = message.question;
        break;
      }
    }
    String? activeSuggestionFieldPath;
    int? activeSuggestionStage;
    for (final message in _messages.reversed) {
      final suggestion = message.suggestion;
      if (suggestion != null &&
          suggestion['_applied'] != true &&
          suggestion['_skipped'] != true) {
        activeSuggestionFieldPath = suggestion['field_path'] as String?;
        activeSuggestionStage = (suggestion['stage'] as num?)?.toInt();
        break;
      }
      final identitySuggestion = message.identitySuggestion;
      if (identitySuggestion != null &&
          identitySuggestion['_applied'] != true &&
          identitySuggestion['_skipped'] != true) {
        activeSuggestionFieldPath = identitySuggestion['field_path'] as String?;
        activeSuggestionStage = identitySuggestion['_kind'] == 'polish' ? 1 : 4;
        break;
      }
    }
    final highlightedFieldPath =
        _requirementFocusPath ??
        activeQuestion?['field_path'] as String? ??
        activeSuggestionFieldPath;
    final remainingQuestionCount =
        _questionQueue.length +
        (_pendingQuestion == null ? 0 : 1) +
        (activeQuestion == null ? 0 : 1);
    final questionsDone =
        _result != null &&
        !_busy &&
        _error == null &&
        activeQuestion == null &&
        _pendingQuestion == null &&
        _questionQueue.isEmpty &&
        _pendingNoneAnswers == 0;
    if (questionsDone && _awaitingGapAudit) _scheduleGapAudit();
    final reviewCompleted =
        questionsDone &&
        !_awaitingGapAudit &&
        !_gapAuditScheduled &&
        (!_gapAuditStarted || _gapAuditFinished);
    final dock = ReviewDockScope.watch(context);
    final activeStage =
        (activeQuestion?['stage'] as num?)?.toInt() ?? activeSuggestionStage;
    final currentStage = reviewCompleted
        ? kReviewStageLabels.length + 1
        : (activeStage != null && activeStage > 0 ? activeStage : 0);
    return PopScope(
      canPop: !_busy && !_mutationPending,
      child: Dialog(
        insetPadding: EdgeInsets.all(AppSpace.s(24)),
        clipBehavior: Clip.antiAlias,
        child: SizedBox(
          width: 1180,
          height: 760,
          child: Column(
            children: [
              _ReviewDialogHeader(
                job: widget.generalReview
                    ? null
                    : _result?['job_source'] as Map? ??
                          {
                            'company': widget.jobCompany,
                            'title': widget.jobTitle,
                          },
                generalReview: widget.generalReview,
                busy: _busy,
                canComplete: _result != null,
                onComplete: _completeReview,
                // 기다리는 동안에만 내려둔다. 앱 맨 위 층에 떠 있을 때만 된다.
                onMinimize: dock != null && _busy ? dock.minimize : null,
                onClose: _closeWith,
              ),
              const Divider(height: 1),
              Expanded(
                child: LayoutBuilder(
                  builder: (context, constraints) {
                    final horizontal = constraints.maxWidth >= 820;
                    final preview = _ResumeDraftPreview(
                      content: _preview,
                      changed: _changed,
                      highlightedFieldPath: highlightedFieldPath,
                      sectionKeys: _previewSectionKeys,
                      starChecks: _starChecks,
                    );
                    final chat = _ReviewChatPane(
                      messages: _messages,
                      busy: _busy,
                      busyKind: _busyKind,
                      busyStage: _busyStage,
                      error: _error,
                      resultAvailable: _result != null,
                      reviewCompleted: reviewCompleted,
                      remainingQuestionCount: remainingQuestionCount,
                      awaitingSuggestionApply: _pendingQuestion != null,
                      generalReview: widget.generalReview,
                      answerController: _answerController,
                      answerFocusNode: _answerFocus,
                      scrollController: _chatScrollController,
                      activeQuestion: activeQuestion,
                      appliedSuggestionIndices: _appliedSuggestionIndices,
                      onStart: _review,
                      onAnswer: activeQuestion == null
                          ? null
                          : () => _submitAnswer(activeQuestion!),
                      onApply: _applySuggestion,
                      onSkip: _skipSuggestion,
                      onUndo: _undoSuggestion,
                      canMinimize: dock != null,
                      requirementRows: widget.generalReview
                          ? const []
                          : _requirementRows,
                      starChecks: _starChecks,
                      currentStage: currentStage,
                      onRequirementTap: _focusRequirement,
                      onNoneAnswer: activeQuestion == null
                          ? null
                          : () => _submitNoneAnswer(activeQuestion!),
                      onClose: () => _completeReview(alwaysConfirm: false),
                      onRestart: _restartReview,
                      restartNotice: _restartNotice,
                    );
                    if (!horizontal) {
                      return Column(
                        children: [
                          Expanded(child: preview),
                          const Divider(height: 1),
                          Expanded(child: chat),
                        ],
                      );
                    }
                    const handleWidth = 14.0;
                    return ValueListenableBuilder<double>(
                      valueListenable: _previewFraction,
                      builder: (_, fraction, _) => Row(
                        children: [
                          SizedBox(
                            width:
                                (constraints.maxWidth - handleWidth) * fraction,
                            child: preview,
                          ),
                          MouseRegion(
                            cursor: SystemMouseCursors.resizeColumn,
                            child: GestureDetector(
                              behavior: HitTestBehavior.opaque,
                              onHorizontalDragUpdate: (details) {
                                final available =
                                    constraints.maxWidth - handleWidth;
                                _previewFraction.value =
                                    (_previewFraction.value +
                                            details.delta.dx / available)
                                        .clamp(0.3, 0.7)
                                        .toDouble();
                              },
                              onDoubleTap: () => _previewFraction.value = 0.5,
                              child: SizedBox(
                                width: handleWidth,
                                child: Center(
                                  child: Container(
                                    width: 2,
                                    height: double.infinity,
                                    color: AppColors.border,
                                  ),
                                ),
                              ),
                            ),
                          ),
                          Expanded(child: chat),
                        ],
                      ),
                    );
                  },
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _ReviewDialogHeader extends StatelessWidget {
  const _ReviewDialogHeader({
    required this.job,
    required this.generalReview,
    required this.busy,
    required this.canComplete,
    required this.onComplete,
    required this.onMinimize,
    required this.onClose,
  });

  final Map? job;
  final bool generalReview;
  final bool busy;
  final bool canComplete;
  final VoidCallback onComplete;
  final VoidCallback? onMinimize;
  final VoidCallback onClose;

  @override
  Widget build(BuildContext context) {
    final jobLabel = '${job?['company'] ?? ''} ${job?['title'] ?? ''}'.trim();
    return Padding(
      padding: EdgeInsets.fromLTRB(
        AppSpace.s(20),
        AppSpace.s(12),
        AppSpace.s(12),
        AppSpace.s(12),
      ),
      child: Row(
        children: [
          const Icon(Icons.auto_awesome, color: Color(0xFF16A34A), size: 20),
          SizedBox(width: AppSpace.s(8)),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  generalReview ? '이력서 첨삭' : '공고 맞춤 이력서 첨삭',
                  style: TextStyle(fontSize: 17, fontWeight: FontWeight.w700),
                ),
                if (generalReview)
                  Text(
                    '문장 표현과 이력서 근거를 검토해 수정안을 제시합니다.',
                    style: TextStyle(
                      fontSize: 11,
                      color: AppColors.textSecondary,
                    ),
                  )
                else if (jobLabel.isNotEmpty)
                  Text(
                    jobLabel,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                      fontSize: 11,
                      color: AppColors.textSecondary,
                    ),
                  ),
              ],
            ),
          ),
          if (canComplete) ...[
            SizedBox(width: AppSpace.s(8)),
            OutlinedButton.icon(
              onPressed: busy ? null : onComplete,
              icon: const Icon(Icons.check, size: 16),
              label: const Text('첨삭 완료'),
            ),
          ],
          if (onMinimize != null) ...[
            SizedBox(width: AppSpace.s(8)),
            OutlinedButton.icon(
              onPressed: onMinimize,
              style: OutlinedButton.styleFrom(
                foregroundColor: AppColors.primary,
                backgroundColor: AppColors.primaryLight,
                side: BorderSide(color: AppColors.primary),
              ),
              icon: const Icon(Icons.keyboard_arrow_down, size: 18),
              label: const Text('내려두기'),
            ),
          ],
          IconButton(
            tooltip: '닫기',
            onPressed: busy ? null : onClose,
            icon: const Icon(Icons.close),
          ),
        ],
      ),
    );
  }
}

class _ResumeDraftPreview extends StatelessWidget {
  const _ResumeDraftPreview({
    required this.content,
    required this.changed,
    required this.highlightedFieldPath,
    required this.sectionKeys,
    this.starChecks = const {},
  });

  final ResumeContent content;
  final bool changed;
  final String? highlightedFieldPath;
  final Map<String, GlobalKey> sectionKeys;
  final Map<String, ReviewStarCheck> starChecks;

  static const _labels = {
    'coreCompetencies': '핵심 역량',
    'experience': '경력',
    'education': '학력',
    'techStack': '기술 스택',
    'certifications': '자격증',
    'awards': '수상 내역',
    'trainingExperience': '교육 경험',
    'otherActivities': '기타 활동',
    'projects': '프로젝트',
    'selfIntroduction': '자기소개서',
  };

  @override
  Widget build(BuildContext context) {
    final map = content.toMap();
    final info = Map<String, dynamic>.from(map['basicInfo'] as Map);
    return ColoredBox(
      color: AppColors.tint(const Color(0xFFF8FAFC)),
      // 이력서 문장을 드래그해 복사할 수 있게 한다. 첨삭 결과를 다른 곳에 옮겨 적는 일이 많다.
      child: SelectionArea(
        child: SingleChildScrollView(
        padding: EdgeInsets.all(AppSpace.s(20)),
        child: Container(
          padding: EdgeInsets.all(AppSpace.s(22)),
          decoration: BoxDecoration(
            color: AppColors.surface,
            border: Border.all(color: AppColors.tint(const Color(0xFFE5E7EB))),
            borderRadius: BorderRadius.circular(12),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Expanded(
                    child: Text(
                      (info['name'] as String? ?? '').trim().isEmpty
                          ? '작성 중인 이력서'
                          : info['name'] as String,
                      style: const TextStyle(
                        fontSize: 20,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                  ),
                  if (changed) const _PreviewUpdatedBadge(),
                ],
              ),
              if ((info['email'] as String? ?? '').isNotEmpty) ...[
                SizedBox(height: AppSpace.s(4)),
                Text(
                  info['email'] as String,
                  style: TextStyle(
                    fontSize: 11,
                    color: AppColors.textSecondary,
                  ),
                ),
              ],
              SizedBox(height: AppSpace.s(18)),
              for (final entry in _labels.entries)
                if (entry.key == 'selfIntroduction')
                  _SelfIntroductionPreview(
                    key: sectionKeys[entry.key],
                    sections: Map<String, dynamic>.from(
                      map[entry.key] as Map? ?? const <String, dynamic>{},
                    ),
                    highlightedFieldPath: highlightedFieldPath,
                    itemKeys: sectionKeys,
                    starChecks: starChecks,
                  )
                else if (entry.key == 'techStack' &&
                    (map[entry.key] as List? ?? const []).isNotEmpty)
                  _TechStackPreview(
                    key: sectionKeys[entry.key],
                    items: (map[entry.key] as List? ?? const [])
                        .whereType<Map>()
                        .map((item) => Map<String, dynamic>.from(item))
                        .toList(),
                    highlighted: _highlighted(entry.key),
                  )
                else if (_compactConfig.containsKey(entry.key) &&
                    (map[entry.key] as List? ?? const []).isNotEmpty)
                  _CompactItemsPreview(
                    key: sectionKeys[entry.key],
                    title: entry.value,
                    items: (map[entry.key] as List? ?? const [])
                        .whereType<Map>()
                        .map((item) => Map<String, dynamic>.from(item))
                        .toList(),
                    config: _compactConfig[entry.key]!,
                    highlighted: _highlighted(entry.key),
                    sectionKey: entry.key,
                    starChecks: starChecks,
                  )
                else if (_render(map[entry.key]).isNotEmpty)
                  _PreviewSection(
                    key: sectionKeys[entry.key],
                    title: entry.value,
                    text: _render(map[entry.key]),
                    highlighted: _highlighted(entry.key),
                  ),
            ],
          ),
        ),
      ),
      ),
    );
  }

  bool _highlighted(String key) =>
      highlightedFieldPath?.startsWith('$key.') == true ||
      highlightedFieldPath?.startsWith('$key[') == true;

  static const _compactConfig = <String, _CompactItemConfig>{
    'experience': _CompactItemConfig(
      primary: 'company',
      secondary: ['role'],
      startDate: 'startDate',
      endDate: 'endDate',
      description: 'description',
    ),
    'education': _CompactItemConfig(
      primary: 'school',
      secondary: ['major', 'status'],
      startDate: 'startDate',
      endDate: 'endDate',
    ),
    'certifications': _CompactItemConfig(
      primary: 'name',
      secondary: ['issuer'],
      singleDate: 'acquiredDate',
    ),
    'awards': _CompactItemConfig(
      primary: 'name',
      secondary: ['organization'],
      singleDate: 'date',
      description: 'description',
    ),
    'trainingExperience': _CompactItemConfig(
      primary: 'course',
      secondary: ['organization'],
      startDate: 'startDate',
      endDate: 'endDate',
      description: 'description',
    ),
    'otherActivities': _CompactItemConfig(
      primary: 'name',
      startDate: 'startDate',
      endDate: 'endDate',
      description: 'description',
    ),
    'projects': _CompactItemConfig(
      primary: 'name',
      secondary: ['role', 'techStack'],
      startDate: 'startDate',
      endDate: 'endDate',
      description: 'description',
    ),
  };

  static String _render(Object? value) {
    if (value is String) return value.trim();
    if (value is List) {
      return value.map(_render).where((text) => text.isNotEmpty).join('\n\n');
    }
    if (value is Map) {
      const ignored = {'id', 'url', 'githubUrl', 'blogUrl', 'isCurrent'};
      return value.entries
          .where((entry) => !ignored.contains(entry.key))
          .map((entry) => _render(entry.value))
          .where((text) => text.isNotEmpty)
          .join('\n');
    }
    return '';
  }
}

class _CompactItemConfig {
  const _CompactItemConfig({
    required this.primary,
    this.secondary = const [],
    this.startDate,
    this.endDate,
    this.singleDate,
    this.description,
  });

  final String primary;
  final List<String> secondary;
  final String? startDate;
  final String? endDate;
  final String? singleDate;
  final String? description;
}

class _CompactItemsPreview extends StatelessWidget {
  const _CompactItemsPreview({
    super.key,
    required this.title,
    required this.items,
    required this.config,
    required this.highlighted,
    this.sectionKey = '',
    this.starChecks = const {},
  });

  final String title;
  final List<Map<String, dynamic>> items;
  final _CompactItemConfig config;
  final bool highlighted;
  final String sectionKey;
  final Map<String, ReviewStarCheck> starChecks;

  String _text(Map<String, dynamic> item, String? key) =>
      key == null ? '' : (item[key] as String? ?? '').trim();

  String _date(Map<String, dynamic> item) {
    final single = _text(item, config.singleDate);
    if (single.isNotEmpty) return single;
    final start = _text(item, config.startDate);
    final end = _text(item, config.endDate);
    if (start.isEmpty) return end;
    if (end.isEmpty) return start;
    return '$start – $end';
  }

  @override
  Widget build(BuildContext context) {
    // 서버의 field_path("projects[2].description")는 원래 목록 번호라, 빈 항목을 거르기 전 번호를 함께 둔다.
    final filledIndices = [
      for (var index = 0; index < items.length; index++)
        if (_text(items[index], config.primary).isNotEmpty) index,
    ];
    final filled = [for (final index in filledIndices) items[index]];
    if (filled.isEmpty) return const SizedBox.shrink();
    return Container(
      margin: EdgeInsets.only(bottom: AppSpace.s(18)),
      padding: highlighted ? EdgeInsets.all(AppSpace.s(10)) : EdgeInsets.zero,
      decoration: highlighted ? _previewHighlightDecoration : null,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _PreviewSectionTitle(title: title, highlighted: highlighted),
          SizedBox(height: AppSpace.s(9)),
          for (var index = 0; index < filled.length; index++) ...[
            _CompactItemRow(
              primary: _text(filled[index], config.primary),
              metadata: [
                ...config.secondary.map((key) => _text(filled[index], key)),
                _date(filled[index]),
              ].where((value) => value.isNotEmpty).toList(),
              description: _text(filled[index], config.description),
              star:
                  starChecks['$sectionKey[${filledIndices[index]}].${config.description}'],
            ),
            if (index != filled.length - 1) SizedBox(height: AppSpace.s(8)),
          ],
        ],
      ),
    );
  }
}

class _CompactItemRow extends StatelessWidget {
  const _CompactItemRow({
    required this.primary,
    required this.metadata,
    required this.description,
    this.star,
  });

  final String primary;
  final List<String> metadata;
  final String description;
  final ReviewStarCheck? star;

  @override
  Widget build(BuildContext context) => Container(
    width: double.infinity,
    padding: EdgeInsets.symmetric(
      horizontal: AppSpace.s(11),
      vertical: AppSpace.s(9),
    ),
    decoration: BoxDecoration(
      color: AppColors.tint(const Color(0xFFF8FAFC)),
      border: Border.all(color: AppColors.tint(const Color(0xFFE5E7EB))),
      borderRadius: BorderRadius.circular(8),
    ),
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Expanded(
              child: Text(
                primary,
                style: const TextStyle(
                  fontSize: 12,
                  fontWeight: FontWeight.w700,
                ),
              ),
            ),
            if (metadata.isNotEmpty) ...[
              SizedBox(width: AppSpace.s(10)),
              Flexible(
                child: Text(
                  metadata.join(' · '),
                  textAlign: TextAlign.right,
                  style: TextStyle(
                    fontSize: 10.5,
                    color: AppColors.textSecondary,
                  ),
                ),
              ),
            ],
          ],
        ),
        if (description.isNotEmpty) ...[
          SizedBox(height: AppSpace.s(5)),
          Text(
            description,
            style: const TextStyle(fontSize: 11, height: 1.45),
          ),
        ],
        if (star != null && description.isNotEmpty)
          ReviewStarCells(check: star!),
      ],
    ),
  );
}

class _TechStackPreview extends StatelessWidget {
  const _TechStackPreview({
    super.key,
    required this.items,
    required this.highlighted,
  });

  final List<Map<String, dynamic>> items;
  final bool highlighted;

  @override
  Widget build(BuildContext context) {
    final filled = items.where((item) {
      return (item['name'] as String? ?? '').trim().isNotEmpty;
    }).toList();
    if (filled.isEmpty) return const SizedBox.shrink();
    return Container(
      margin: EdgeInsets.only(bottom: AppSpace.s(18)),
      padding: highlighted ? EdgeInsets.all(AppSpace.s(10)) : EdgeInsets.zero,
      decoration: highlighted ? _previewHighlightDecoration : null,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _PreviewSectionTitle(title: '기술 스택', highlighted: highlighted),
          SizedBox(height: AppSpace.s(9)),
          Wrap(
            spacing: 7,
            runSpacing: 7,
            children: [
              for (final item in filled)
                Container(
                  padding: EdgeInsets.symmetric(
                    horizontal: AppSpace.s(10),
                    vertical: AppSpace.s(6),
                  ),
                  decoration: BoxDecoration(
                    color: AppColors.primaryLight,
                    border: Border.all(
                      color: AppColors.primary.withValues(alpha: 0.35),
                    ),
                    borderRadius: BorderRadius.circular(99),
                  ),
                  child: Text.rich(
                    TextSpan(
                      children: [
                        TextSpan(
                          text: (item['name'] as String? ?? '').trim(),
                          style: const TextStyle(fontWeight: FontWeight.w700),
                        ),
                        if ((item['level'] as String? ?? '').trim().isNotEmpty)
                          TextSpan(
                            text: '  ${(item['level'] as String).trim()}',
                            style: TextStyle(color: AppColors.textSecondary),
                          ),
                      ],
                    ),
                    style: const TextStyle(fontSize: 11),
                  ),
                ),
            ],
          ),
        ],
      ),
    );
  }
}

BoxDecoration get _previewHighlightDecoration => BoxDecoration(
  color: AppColors.tint(const Color(0xFFFFFBEA)),
  border: Border.fromBorderSide(
    BorderSide(color: Color(0xFFF59E0B), width: 1.5),
  ),
  borderRadius: BorderRadius.all(Radius.circular(8)),
);

class _PreviewSectionTitle extends StatelessWidget {
  const _PreviewSectionTitle({required this.title, required this.highlighted});

  final String title;
  final bool highlighted;

  @override
  Widget build(BuildContext context) => Row(
    children: [
      Text(
        title,
        style: TextStyle(
          fontSize: 13,
          fontWeight: FontWeight.w700,
          color: AppColors.primaryDark,
        ),
      ),
      if (highlighted) ...[
        SizedBox(width: AppSpace.s(7)),
        const Text(
          'AI 질문 대상',
          style: TextStyle(
            fontSize: 10,
            fontWeight: FontWeight.w700,
            color: Color(0xFFB45309),
          ),
        ),
      ],
    ],
  );
}

class _SelfIntroductionPreview extends StatelessWidget {
  const _SelfIntroductionPreview({
    super.key,
    required this.sections,
    required this.highlightedFieldPath,
    required this.itemKeys,
    this.starChecks = const {},
  });

  final Map<String, dynamic> sections;
  final String? highlightedFieldPath;
  final Map<String, GlobalKey> itemKeys;
  final Map<String, ReviewStarCheck> starChecks;

  @override
  Widget build(BuildContext context) {
    final filled = ResumeSelfIntroLabels.keys
        .map((key) {
          final raw = sections[key];
          final section = raw is Map
              ? Map<String, dynamic>.from(raw)
              : const <String, dynamic>{};
          final body = (section['body'] as String? ?? '').trim();
          return (key: key, body: body);
        })
        .where((entry) => entry.body.isNotEmpty)
        .toList();
    if (filled.isEmpty) return const SizedBox.shrink();

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Padding(
          padding: EdgeInsets.only(bottom: AppSpace.s(8)),
          child: Text(
            '자기소개서',
            style: TextStyle(
              fontSize: 13,
              fontWeight: FontWeight.w700,
              color: AppColors.primaryDark,
            ),
          ),
        ),
        for (final entry in filled)
          _PreviewSection(
            key: itemKeys['selfIntroduction.${entry.key}'],
            title: ResumeSelfIntroLabels.labels[entry.key] ?? entry.key,
            text: entry.body,
            highlighted:
                highlightedFieldPath?.startsWith(
                      'selfIntroduction.${entry.key}.',
                    ) ==
                    true ||
                highlightedFieldPath == 'selfIntroduction.${entry.key}',
            star: starChecks['selfIntroduction.${entry.key}.body'],
          ),
      ],
    );
  }
}

class _PreviewUpdatedBadge extends StatelessWidget {
  const _PreviewUpdatedBadge();

  @override
  Widget build(BuildContext context) => Container(
    padding: EdgeInsets.symmetric(
      horizontal: AppSpace.s(7),
      vertical: AppSpace.s(3),
    ),
    decoration: BoxDecoration(
      color: AppColors.tint(const Color(0xFFDCFCE7)),
      borderRadius: BorderRadius.circular(99),
    ),
    child: const Text(
      '수정 반영됨',
      style: TextStyle(fontSize: 10, color: Color(0xFF15803D)),
    ),
  );
}

class _PreviewSection extends StatelessWidget {
  const _PreviewSection({
    super.key,
    required this.title,
    required this.text,
    required this.highlighted,
    this.star,
  });

  final String title;
  final String text;
  final bool highlighted;
  final ReviewStarCheck? star;

  @override
  Widget build(BuildContext context) => Container(
    margin: EdgeInsets.only(bottom: AppSpace.s(18)),
    padding: highlighted ? EdgeInsets.all(AppSpace.s(10)) : EdgeInsets.zero,
    decoration: highlighted
        ? BoxDecoration(
            color: AppColors.tint(const Color(0xFFFFFBEA)),
            border: Border.all(color: const Color(0xFFF59E0B), width: 1.5),
            borderRadius: BorderRadius.circular(8),
          )
        : null,
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Text(
              title,
              style: TextStyle(
                fontSize: 13,
                fontWeight: FontWeight.w700,
                color: AppColors.primaryDark,
              ),
            ),
            if (highlighted) ...[
              SizedBox(width: AppSpace.s(7)),
              const Text(
                'AI 질문 대상',
                style: TextStyle(
                  fontSize: 10,
                  fontWeight: FontWeight.w700,
                  color: Color(0xFFB45309),
                ),
              ),
            ],
          ],
        ),
        SizedBox(height: AppSpace.s(7)),
        Text(text, style: const TextStyle(fontSize: 12, height: 1.55)),
        if (star != null) ReviewStarCells(check: star!),
      ],
    ),
  );
}

class _ReviewChatPane extends StatelessWidget {
  const _ReviewChatPane({
    required this.messages,
    required this.busy,
    required this.busyKind,
    required this.busyStage,
    required this.error,
    required this.resultAvailable,
    required this.reviewCompleted,
    required this.remainingQuestionCount,
    required this.awaitingSuggestionApply,
    required this.generalReview,
    required this.answerController,
    required this.answerFocusNode,
    required this.scrollController,
    required this.activeQuestion,
    required this.appliedSuggestionIndices,
    required this.onStart,
    required this.onAnswer,
    required this.onApply,
    required this.onSkip,
    required this.onUndo,
    required this.canMinimize,
    required this.requirementRows,
    this.starChecks = const {},
    required this.currentStage,
    required this.onRequirementTap,
    required this.onNoneAnswer,
    required this.onClose,
    required this.onRestart,
    this.restartNotice,
  });

  final List<_ReviewChatMessage> messages;
  final bool busy;
  final _ReviewBusyKind? busyKind;
  final int busyStage;
  final String? error;
  final bool resultAvailable;
  final bool reviewCompleted;
  final int remainingQuestionCount;
  final bool awaitingSuggestionApply;
  final bool generalReview;
  final TextEditingController answerController;
  final FocusNode answerFocusNode;
  final ScrollController scrollController;
  final Map<String, dynamic>? activeQuestion;
  final Set<int> appliedSuggestionIndices;
  final Future<void> Function() onStart;
  final VoidCallback? onAnswer;
  final ValueChanged<List<int>> onApply;
  final ValueChanged<List<int>> onSkip;
  final ValueChanged<Map<String, dynamic>> onUndo;
  final bool canMinimize;
  final List<ReviewRequirementRow> requirementRows;
  final Map<String, ReviewStarCheck> starChecks;

  /// 0이면 아직 단계가 없고(첫 첨삭 전), 6이면 모두 끝났다.
  final int currentStage;
  final ValueChanged<ReviewRequirementRow> onRequirementTap;
  final VoidCallback? onNoneAnswer;
  final VoidCallback onClose;
  final VoidCallback onRestart;
  final String? restartNotice;

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        Container(
          width: double.infinity,
          padding: EdgeInsets.symmetric(
            horizontal: AppSpace.s(20),
            vertical: AppSpace.s(14),
          ),
          decoration: BoxDecoration(
            color: AppColors.surface,
            border: Border(
              bottom: BorderSide(
                color: AppColors.tint(const Color(0xFFE5E7EB)),
              ),
            ),
          ),
          child: Row(
            children: [
              const Icon(
                Icons.smart_toy_outlined,
                size: 18,
                color: Color(0xFF16A34A),
              ),
              SizedBox(width: AppSpace.s(7)),
              const Text(
                'AI 첨삭 대화',
                style: TextStyle(fontWeight: FontWeight.w700),
              ),
              SizedBox(width: AppSpace.s(8)),
              Text(
                generalReview
                    ? '문장 표현과 경험 근거를 함께 검토합니다.'
                    : '근거가 부족한 내용은 질문으로 확인합니다.',
                style: TextStyle(
                  fontSize: 11,
                  color: AppColors.textSecondary,
                ),
              ),
              const Spacer(),
              if (resultAvailable && remainingQuestionCount > 0)
                Container(
                  padding: EdgeInsets.symmetric(
                    horizontal: AppSpace.s(9),
                    vertical: AppSpace.s(4),
                  ),
                  decoration: BoxDecoration(
                    color: AppColors.primaryLight,
                    borderRadius: BorderRadius.circular(99),
                  ),
                  child: Text(
                    '남은 질문 약 $remainingQuestionCount개',
                    style: TextStyle(
                      fontSize: 10.5,
                      fontWeight: FontWeight.w600,
                      color: AppColors.primary,
                    ),
                  ),
                ),
            ],
          ),
        ),
        if (requirementRows.isNotEmpty)
          ReviewRequirementStrip(
            rows: requirementRows,
            onTapRow: onRequirementTap,
          ),
        if (resultAvailable && currentStage > 0)
          ReviewStageBar(
            currentStage: currentStage,
            includeRequirementStage: requirementRows.isNotEmpty,
          ),
        Expanded(
          // 대화 글을 드래그해 복사할 수 있게 SelectionArea로 감싼다. 예전에 이걸 빼 둔 것은
          // 타이핑이 안 되는 원인으로 의심했기 때문인데, 실제 원인은 "없음" 칩이 사라질 때
          // 자리가 없어지는 것과 readOnly 토글이었다(2026-09-16 앱). 둘을 고쳤으므로 되돌린다.
          child: SelectionArea(
            child: ListView(
              controller: scrollController,
              padding: EdgeInsets.all(AppSpace.s(18)),
              children: [
                if (!resultAvailable && !busy && error == null) ...[
                  if (restartNotice != null)
                    Padding(
                      padding: EdgeInsets.only(bottom: AppSpace.s(10)),
                      child: _ReviewNoticeLine(text: restartNotice!),
                    ),
                  _ChatIntro(onStart: onStart, generalReview: generalReview),
                ],
                for (final message in messages)
                  _ReviewChatBubble(
                    message: message,
                    requirementRows: requirementRows,
                    starChecks: starChecks,
                    appliedSuggestionIndices: appliedSuggestionIndices,
                    onApply: onApply,
                    onSkip: onSkip,
                    onUndo: onUndo,
                  ),
                if (busy)
                  Padding(
                    padding: EdgeInsets.only(top: AppSpace.s(10)),
                    child: busyKind == _ReviewBusyKind.review
                        ? _InitialReviewProgress(
                            currentStage: busyStage,
                            generalReview: generalReview,
                            canMinimize: canMinimize,
                          )
                        : _ReviewInlineProgress(
                            kind: busyKind ?? _ReviewBusyKind.answer,
                          ),
                  ),
                if (error != null)
                  Container(
                    margin: EdgeInsets.only(top: AppSpace.s(10)),
                    padding: EdgeInsets.all(AppSpace.s(10)),
                    decoration: BoxDecoration(
                      color: AppColors.tint(const Color(0xFFFEF2F2)),
                      borderRadius: BorderRadius.circular(8),
                    ),
                    child: Text(
                      error!,
                      style: const TextStyle(color: Color(0xFFB91C1C)),
                    ),
                  ),
                if (reviewCompleted)
                  _ReviewCompletedNotice(
                    requirementRows: requirementRows,
                    hasSuggestions: messages.any(
                      (message) =>
                          message.suggestion != null ||
                          message.identitySuggestion != null,
                    ),
                    onClose: onClose,
                    onRestart: onRestart,
                  ),
              ],
            ),
          ),
        ),
        if (resultAvailable && !reviewCompleted)
          Container(
            padding: EdgeInsets.all(AppSpace.s(14)),
            decoration: BoxDecoration(
              color: AppColors.surface,
              border: Border(
                top: BorderSide(color: AppColors.tint(const Color(0xFFE5E7EB))),
              ),
            ),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                // 칩을 통째로 빼지 않고 빈 자리로 둔다. 자식 수가 바뀌면 아래 입력칸의 자리 번호가
                // 밀려 위젯이 새로 만들어지고, 웹에서는 그때 브라우저 입력 연결이 끊겨 글자가
                // 들어가지 않았다(2026-09-16 앱: 답변 전송·수정안 반영 직후마다 입력 불가).
                Visibility(
                  visible: onNoneAnswer != null && !busy,
                  // maintainState만으로는 자리가 사라진다. 자리가 사라지면 레이어가 버려지면서
                  // 입력칸이 위치를 엔진에 알리다 터지고(domElement != null), DOM 포커스를 옮기는
                  // 마지막 단계가 실행되지 않아 focus=true인데 글자가 안 들어간다(2026-09-16 앱).
                  maintainState: true,
                  maintainAnimation: true,
                  maintainSize: true,
                  child: Padding(
                    padding: EdgeInsets.only(bottom: AppSpace.s(8)),
                    child: ActionChip(
                      key: const ValueKey('review-none-answer'),
                      onPressed: onNoneAnswer,
                      avatar: Icon(
                        Icons.remove_circle_outline_rounded,
                        size: 16,
                        color: AppColors.textSecondary,
                      ),
                      label: const Text('없음'),
                      tooltip:
                          '해 본 적이 없거나 기억나지 않으면 누르세요. 이력서에 넣지 않고 다음 질문으로 넘어갑니다.',
                    ),
                  ),
                ),
                Focus(
                  // 고정 키가 있어야 한다. 위의 "없음" 칩이 busy에 따라 나타났다 사라지면 이 위젯의
                  // 자리 번호가 밀리는데, 키가 없으면 Flutter가 앞자리의 다른 타입 위젯과 맞추려다
                  // 실패해 입력칸을 통째로 새로 만든다. 그러면 포커스가 날아가, 답변을 보낸 직후마다
                  // 글자가 입력되지 않았다(2026-09-16 앱: 닫았다 열면 잠깐 되던 것도 이 때문이다).
                  key: const ValueKey('review-answer-input'),
                  onKeyEvent: (_, event) {
                    if (event is KeyDownEvent &&
                        event.logicalKey == LogicalKeyboardKey.enter &&
                        !HardwareKeyboard.instance.isShiftPressed) {
                      onAnswer?.call();
                      return KeyEventResult.handled;
                    }
                    return KeyEventResult.ignored;
                  },
                  child: TextField(
                    controller: answerController,
                    focusNode: answerFocusNode,
                    // 입력칸은 항상 편집 가능하게 둔다. enabled는 물론 readOnly도 껐다 켜면 웹에서
                    // 입력 연결이 닫히고, 그 뒤 입력칸이 위치를 엔진에 알리다 터진다
                    // (domElement != null). 그러면 focus=true인데 글자가 안 들어간다
                    // (2026-09-16 앱: 답변 전송·수정안 반영 직후마다 재현).
                    // 처리 중 전송은 _submitAnswer가 _busy로 막으므로 잠글 필요가 없다.
                    // 못 쓰는 상태는 힌트와 바탕색으로만 알린다.
                    readOnly: false,
                    minLines: 1,
                    maxLines: 3,
                    decoration: InputDecoration(
                      // 입력칸이 꺼지는 조건(busy·질문 없음)을 힌트가 그대로 말해야 한다. 예전에는 꺼져
                      // 있어도 "답변을 입력하세요"가 떠서, 쓸 수 있는 줄 알고 치다가 왜 안 되는지
                      // 알 수 없었다(2026-09-16 앱).
                      hintText: busy
                          ? '처리 중입니다. 끝나면 입력할 수 있어요.'
                          : activeQuestion == null
                          ? awaitingSuggestionApply
                                ? '수정안을 반영하면 다음 질문을 이어갑니다.'
                                : '현재 추가 확인 질문이 없습니다.'
                          : '답변을 입력하세요. (Enter 전송 · Shift+Enter 줄바꿈)',
                      isDense: true,
                      // readOnly는 회색으로 흐려지지 않으므로, 못 쓰는 상태는 바탕색으로 알린다.
                      filled: true,
                      fillColor: busy || activeQuestion == null
                          ? AppColors.surfaceVariant
                          : AppColors.surface,
                      border: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(10),
                      ),
                      suffixIcon: IconButton(
                        tooltip: '답변 보내기',
                        onPressed: onAnswer,
                        icon: Icon(Icons.send, color: AppColors.primary),
                      ),
                    ),
                  ),
                ),
              ],
            ),
          ),
      ],
    );
  }
}

class _InitialReviewProgress extends StatelessWidget {
  const _InitialReviewProgress({
    required this.currentStage,
    required this.generalReview,
    this.canMinimize = false,
  });

  final int currentStage;
  final bool generalReview;
  final bool canMinimize;

  @override
  Widget build(BuildContext context) {
    final steps = generalReview ? _generalReviewSteps : _jobReviewSteps;
    return Container(
      padding: EdgeInsets.all(AppSpace.s(16)),
      decoration: BoxDecoration(
        color: AppColors.tint(const Color(0xFFF8FAFC)),
        border: Border.all(color: AppColors.tint(const Color(0xFFE2E8F0))),
        borderRadius: BorderRadius.circular(14),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(
                  generalReview ? '이력서 첨삭 준비 중' : '공고 맞춤 첨삭 준비 중',
                  style: const TextStyle(
                    fontSize: 14,
                    fontWeight: FontWeight.w700,
                  ),
                ),
              ),
              Text(
                '${(currentStage + 1).clamp(1, steps.length)} / ${steps.length} 단계',
                style: TextStyle(
                  fontSize: 11,
                  color: AppColors.textHint,
                ),
              ),
            ],
          ),
          SizedBox(height: AppSpace.s(4)),
          Text(
            generalReview
                ? '이력서의 문장과 경험 근거를 문항별로 확인합니다.'
                : '선택한 공고 기준으로 첨삭 항목을 준비하고 있어요.',
            style: TextStyle(fontSize: 11, color: AppColors.textSecondary),
          ),
          SizedBox(height: AppSpace.s(2)),
          // 2026-09-14 기록으로 첫 첨삭은 33~71초였다. "15초"라고 하면 더 답답하다.
          Text(
            canMinimize
                ? '보통 1분 안팎 걸립니다. 내려두기를 누르고 다른 화면을 봐도 첨삭은 계속됩니다.'
                : '보통 1분 안팎 걸립니다. 창을 닫지 않고 잠시 기다려 주세요.',
            style: TextStyle(
              fontSize: 10.5,
              color: canMinimize ? AppColors.primary : AppColors.textHint,
              fontWeight: canMinimize ? FontWeight.w600 : null,
            ),
          ),
          SizedBox(height: AppSpace.s(14)),
          for (var index = 0; index < steps.length; index++)
            _ReviewProgressRow(
              label: steps[index],
              state: index < currentStage
                  ? _ReviewStepState.done
                  : index == currentStage
                  ? _ReviewStepState.running
                  : _ReviewStepState.waiting,
              last: index == steps.length - 1,
            ),
        ],
      ),
    );
  }
}

class _ReviewInlineProgress extends StatelessWidget {
  const _ReviewInlineProgress({required this.kind});

  final _ReviewBusyKind kind;

  @override
  Widget build(BuildContext context) {
    return _CompactBusyCard(label: _busyLabel(kind));
  }
}

class _CompactBusyCard extends StatefulWidget {
  const _CompactBusyCard({required this.label});
  final String label;

  @override
  State<_CompactBusyCard> createState() => _CompactBusyCardState();
}

class _CompactBusyCardState extends State<_CompactBusyCard>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 900),
    )..repeat();
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final primary = Theme.of(context).colorScheme.primary;
    return Container(
      padding: EdgeInsets.symmetric(
        horizontal: AppSpace.s(14),
        vertical: AppSpace.s(13),
      ),
      decoration: BoxDecoration(
        color: Theme.of(context).colorScheme.primaryContainer,
        borderRadius: BorderRadius.circular(12),
      ),
      child: Row(
        children: [
          Semantics(
            label: '처리 중',
            child: AnimatedBuilder(
              animation: _controller,
              builder: (context, _) => Row(
                mainAxisSize: MainAxisSize.min,
                children: List.generate(3, (index) {
                  final wave = sin(
                    (_controller.value * pi * 2) - (index * 0.8),
                  );
                  return Transform.translate(
                    offset: Offset(0, -3 * wave),
                    child: Container(
                      width: 6,
                      height: 6,
                      margin: EdgeInsets.symmetric(horizontal: AppSpace.s(2)),
                      decoration: BoxDecoration(
                        color: primary,
                        shape: BoxShape.circle,
                      ),
                    ),
                  );
                }),
              ),
            ),
          ),
          SizedBox(width: AppSpace.s(10)),
          Expanded(
            child: Text(
              widget.label,
              style: const TextStyle(
                fontSize: 12,
                fontWeight: FontWeight.w600,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

enum _ReviewStepState { done, running, waiting }

class _ReviewProgressRow extends StatelessWidget {
  const _ReviewProgressRow({
    required this.label,
    required this.state,
    required this.last,
  });

  final String label;
  final _ReviewStepState state;
  final bool last;

  @override
  Widget build(BuildContext context) {
    final color = switch (state) {
      _ReviewStepState.done => const Color(0xFF16A34A),
      _ReviewStepState.running => AppColors.primary,
      _ReviewStepState.waiting => const Color(0xFF94A3B8),
    };
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Column(
          children: [
            SizedBox(
              width: 16,
              height: 16,
              child: switch (state) {
                _ReviewStepState.done => Icon(
                  Icons.check_circle,
                  size: 16,
                  color: color,
                ),
                _ReviewStepState.running => Padding(
                  padding: EdgeInsets.all(AppSpace.s(1.5)),
                  child: CircularProgressIndicator(strokeWidth: 2),
                ),
                _ReviewStepState.waiting => Icon(
                  Icons.circle_outlined,
                  size: 16,
                  color: color,
                ),
              },
            ),
            if (!last)
              Container(
                width: 1.5,
                height: 14,
                margin: EdgeInsets.symmetric(vertical: AppSpace.s(2)),
                color: state == _ReviewStepState.done
                    ? const Color(0xFF86EFAC)
                    : AppColors.tint(const Color(0xFFE2E8F0)),
              ),
          ],
        ),
        SizedBox(width: AppSpace.s(11)),
        Expanded(
          child: Padding(
            padding: EdgeInsets.only(
              bottom: last ? AppSpace.s(0) : AppSpace.s(8),
            ),
            child: Row(
              children: [
                Flexible(
                  child: Text(
                    label,
                    style: TextStyle(
                      fontSize: 12.5,
                      fontWeight: FontWeight.w700,
                      color: state == _ReviewStepState.done
                          ? const Color(0xFF16A34A)
                          : state == _ReviewStepState.waiting
                          ? AppColors.textHint
                          : AppColors.primary,
                    ),
                  ),
                ),
                if (state == _ReviewStepState.running) ...[
                  SizedBox(width: AppSpace.s(8)),
                  Container(
                    padding: EdgeInsets.symmetric(
                      horizontal: AppSpace.s(7),
                      vertical: AppSpace.s(2),
                    ),
                    decoration: BoxDecoration(
                      color: AppColors.primaryLight,
                      borderRadius: BorderRadius.circular(99),
                    ),
                    child: Text(
                      '진행 중',
                      style: TextStyle(
                        fontSize: 9.5,
                        fontWeight: FontWeight.w700,
                        color: AppColors.primary,
                      ),
                    ),
                  ),
                ],
              ],
            ),
          ),
        ),
      ],
    );
  }
}

class _ReviewCompletedNotice extends StatelessWidget {
  const _ReviewCompletedNotice({
    required this.requirementRows,
    required this.hasSuggestions,
    required this.onClose,
    required this.onRestart,
  });

  final List<ReviewRequirementRow> requirementRows;
  final bool hasSuggestions;
  final VoidCallback onClose;
  final VoidCallback onRestart;

  /// "공고 요건: 필수 4/5 · 우대 2/3 근거 확인". 공고 없는 첨삭이면 빈 문자열.
  String get _requirementSummary {
    String part(String group) {
      final rows = requirementRows
          .where((row) => row.group == group && !row.isEligibility)
          .toList();
      if (rows.isEmpty) return '';
      final met = rows.where((row) => row.status == 'met').length;
      return '${requirementGroupLabel(group)} $met/${rows.length}';
    }

    final parts = [
      part('must'),
      part('preferred'),
    ].where((text) => text.isNotEmpty);
    if (parts.isEmpty) return '';
    final missing = requirementRows.any(
      (row) => row.status != 'met' && row.group != 'task' && !row.isEligibility,
    );
    return '공고 요건: ${parts.join(' · ')} 근거 확인'
        '${missing ? '. 확인되지 않은 요건은 이력서에 넣지 않았습니다.' : ''}';
  }

  @override
  Widget build(BuildContext context) => Container(
    margin: EdgeInsets.only(top: AppSpace.s(8)),
    padding: EdgeInsets.all(AppSpace.s(14)),
    decoration: BoxDecoration(
      color: AppColors.tint(const Color(0xFFF0FDF4)),
      border: Border.all(color: const Color(0xFF86EFAC)),
      borderRadius: BorderRadius.circular(10),
    ),
    child: Row(
      children: [
        const Icon(Icons.check_circle, color: Color(0xFF16A34A), size: 22),
        SizedBox(width: AppSpace.s(9)),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text(
                '첨삭 완료',
                style: TextStyle(
                  fontWeight: FontWeight.w700,
                  color: Color(0xFF166534),
                ),
              ),
              SizedBox(height: AppSpace.s(2)),
              if (_requirementSummary.isNotEmpty) ...[
                Text(
                  _requirementSummary,
                  style: const TextStyle(
                    fontSize: 11.5,
                    height: 1.4,
                    fontWeight: FontWeight.w600,
                    color: Color(0xFF166534),
                  ),
                ),
                SizedBox(height: AppSpace.s(2)),
              ],
              Text(
                hasSuggestions
                    ? '추가 확인 질문이 없습니다. 표시된 수정안은 원하는 것만 반영한 뒤 마칠 수 있습니다.'
                    : '추가 확인 질문과 적용할 수정안이 없습니다. 첨삭을 마칠 수 있습니다.',
                style: const TextStyle(
                  fontSize: 11,
                  height: 1.4,
                  color: Color(0xFF166534),
                ),
              ),
              SizedBox(height: AppSpace.s(4)),
              // 이력서에 내용을 더 넣은 뒤 여기서 다시 첨삭한다. 지난 대화는 정리하고 처음부터 본다.
              Align(
                alignment: Alignment.centerLeft,
                child: TextButton.icon(
                  onPressed: onRestart,
                  style: TextButton.styleFrom(
                    foregroundColor: const Color(0xFF166534),
                    visualDensity: VisualDensity.compact,
                    padding: EdgeInsets.zero,
                  ),
                  icon: const Icon(Icons.refresh, size: 15),
                  label: const Text(
                    '이력서를 고쳤다면 다시 첨삭',
                    style: TextStyle(fontSize: 11.5),
                  ),
                ),
              ),
            ],
          ),
        ),
        SizedBox(width: AppSpace.s(8)),
        FilledButton(
          onPressed: onClose,
          style: FilledButton.styleFrom(
            backgroundColor: const Color(0xFF16A34A),
            foregroundColor: Colors.white,
            visualDensity: VisualDensity.compact,
          ),
          child: const Text('첨삭 완료'),
        ),
      ],
    ),
  );
}

class _ChatIntro extends StatelessWidget {
  const _ChatIntro({required this.onStart, required this.generalReview});

  final Future<void> Function() onStart;
  final bool generalReview;

  @override
  Widget build(BuildContext context) => Center(
    child: Padding(
      padding: EdgeInsets.only(top: AppSpace.s(72)),
      child: Column(
        children: [
          Icon(
            Icons.auto_awesome,
            size: 34,
            color: Theme.of(context).colorScheme.primary,
          ),
          SizedBox(height: AppSpace.s(12)),
          Text(
            generalReview ? '이력서 문장과 경험 근거를 확인합니다.' : '선택 공고 기준으로 이력서를 확인합니다.',
            style: TextStyle(fontWeight: FontWeight.w700),
          ),
          SizedBox(height: AppSpace.s(6)),
          Text(
            generalReview
                ? '필요한 사실은 질문으로 확인하고, 맞춤법·문법·표현도 함께 다듬습니다.'
                : '부족한 사실은 AI가 질문하고, 답변을 근거로 수정안을 제시합니다.',
            textAlign: TextAlign.center,
            style: TextStyle(fontSize: 12, color: AppColors.textSecondary),
          ),
          SizedBox(height: AppSpace.s(16)),
          FilledButton.icon(
            onPressed: () => onStart(),
            icon: const Icon(Icons.play_arrow, size: 18),
            label: const Text('첨삭 시작'),
          ),
        ],
      ),
    ),
  );
}

class _ReviewChatBubble extends StatelessWidget {
  const _ReviewChatBubble({
    required this.message,
    required this.requirementRows,
    this.starChecks = const {},
    required this.appliedSuggestionIndices,
    required this.onApply,
    required this.onSkip,
    required this.onUndo,
  });

  final _ReviewChatMessage message;
  final List<ReviewRequirementRow> requirementRows;
  final Map<String, ReviewStarCheck> starChecks;
  final Set<int> appliedSuggestionIndices;

  /// 수정안 카드 밑에 붙일 안내. 칸 사이 중복과 원문 부정 표현이 빠진 것.
  static List<String> _noticesFor(Map<String, dynamic> item) => [
    for (final key in const [
      'overlap_notice',
      'meaning_notice',
      'fact_notice',
      'flow_notice',
    ])
      if ((item[key] as String? ?? '').isNotEmpty) item[key] as String,
  ];

  /// 질문·수정안 위에 붙일 표시. 요건에 연결되면 "필수 · Git 협업", 아니면 단계 이름.
  Widget? _tagFor(Map<String, dynamic> item) {
    final requirementId = item['requirement_id'] as String?;
    if (requirementId != null) {
      for (final row in requirementRows) {
        if (row.id == requirementId) {
          return ReviewItemTag(
            text: '${requirementGroupLabel(row.group)} · ${row.label}',
            requirementGroup: row.group,
          );
        }
      }
    }
    final stage = reviewStageLabel((item['stage'] as num?)?.toInt());
    // 경험 질문이 묻는 요소가 STAR 판정에서 빠진 요소면 이유를 함께 보인다. "경험 보완 · 행동이 빠짐".
    final topic = item['topic'] as String?;
    final check = starChecks[item['field_path']];
    const gaps = {
      'situation': '상황이 빠짐',
      'task': '과제가 빠짐',
      'action': '행동이 빠짐',
      'result': '결과가 빠짐',
    };
    final starText =
        item.containsKey('question') &&
            topic != null &&
            check != null &&
            gaps.containsKey(topic) &&
            !check.has(topic)
        ? gaps[topic]
        : null;
    if (stage.isEmpty) return null;
    return ReviewItemTag(
      text: starText == null ? stage : '$stage · $starText',
      requirementGroup: null,
    );
  }

  final ValueChanged<List<int>> onApply;
  final ValueChanged<List<int>> onSkip;
  final ValueChanged<Map<String, dynamic>> onUndo;

  static TextStyle get _revisionTextStyle => TextStyle(
    fontSize: 12,
    height: 1.5,
    color: AppColors.textPrimary,
  );

  /// 수정안에 실제로 새로 들어간 글자만 굵게 표시한다.
  /// 원문과 수정안을 LCS로 비교하므로 앞·뒤에 여러 수정이 있어도
  /// 변경되지 않은 중간 문장이 함께 굵어지지 않는다.
  static List<InlineSpan> _changedRevisionSpans(
    String original,
    String revision,
  ) {
    if (original == revision) return [TextSpan(text: revision)];
    final before = original.runes.toList();
    final after = revision.runes.toList();
    if (before.isEmpty) {
      return [
        TextSpan(
          text: revision,
          style: const TextStyle(fontWeight: FontWeight.w700),
        ),
      ];
    }
    if (after.isEmpty) return const [];

    // 긴 문장을 여러 장 보여도 화면이 무거워지지 않도록 안전한 상한을 둔다.
    if (before.length * after.length > 300000) {
      return _fallbackChangedRevisionSpans(before, after);
    }

    final table = List<Uint16List>.generate(
      before.length + 1,
      (_) => Uint16List(after.length + 1),
    );
    for (var i = before.length - 1; i >= 0; i--) {
      for (var j = after.length - 1; j >= 0; j--) {
        table[i][j] = before[i] == after[j]
            ? table[i + 1][j + 1] + 1
            : max(table[i + 1][j], table[i][j + 1]);
      }
    }

    final characters = <String>[];
    final changed = <bool>[];
    var i = 0;
    var j = 0;
    while (i < before.length && j < after.length) {
      if (before[i] == after[j]) {
        characters.add(String.fromCharCode(after[j]));
        changed.add(false);
        i++;
        j++;
      } else if (table[i + 1][j] >= table[i][j + 1]) {
        // 원문에서 삭제된 글자는 수정안에 표시하지 않는다.
        i++;
      } else {
        characters.add(String.fromCharCode(after[j]));
        changed.add(true);
        j++;
      }
    }
    while (j < after.length) {
      characters.add(String.fromCharCode(after[j++]));
      changed.add(true);
    }
    return _buildDiffSpans(characters, changed);
  }

  static List<InlineSpan> _fallbackChangedRevisionSpans(
    List<int> before,
    List<int> after,
  ) {
    var prefix = 0;
    while (prefix < before.length &&
        prefix < after.length &&
        before[prefix] == after[prefix]) {
      prefix++;
    }
    var suffix = 0;
    while (suffix < before.length - prefix &&
        suffix < after.length - prefix &&
        before[before.length - 1 - suffix] ==
            after[after.length - 1 - suffix]) {
      suffix++;
    }
    final characters = <String>[];
    final changed = <bool>[];
    for (var index = 0; index < after.length; index++) {
      characters.add(String.fromCharCode(after[index]));
      changed.add(index >= prefix && index < after.length - suffix);
    }
    return _buildDiffSpans(characters, changed);
  }

  static List<InlineSpan> _buildDiffSpans(
    List<String> characters,
    List<bool> changed,
  ) {
    final spans = <InlineSpan>[];
    var start = 0;
    while (start < characters.length) {
      final isChanged = changed[start];
      var end = start + 1;
      while (end < characters.length && changed[end] == isChanged) {
        end++;
      }
      spans.add(
        TextSpan(
          text: characters.sublist(start, end).join(),
          style: isChanged
              ? const TextStyle(fontWeight: FontWeight.w700)
              : null,
        ),
      );
      start = end;
    }
    return spans;
  }

  @override
  Widget build(BuildContext context) {
    if (message.identitySuggestion?['_kind'] == 'polish') {
      final item = message.identitySuggestion!;
      final count = (item['_indices'] as List? ?? const []).length;
      if (item['_undone'] == true) {
        return const _AppliedSuggestionNotice(text: '문장 다듬기 반영을 취소했습니다.');
      }
      if (item['_applied'] == true) {
        return _AppliedSuggestionNotice(
          text: '문장 다듬기 $count개를 이력서에 반영했습니다.',
          onUndo: item['_undo_available'] == true ? () => onUndo(item) : null,
        );
      }
      if (item['_skipped'] == true) {
        return const _AppliedSuggestionNotice(text: '문장 다듬기를 건너뛰었습니다.');
      }
      return _PolishBundleCard(
        item: item,
        onApply: onApply,
        onSkip: onSkip,
        tag: _tagFor(item),
      );
    }
    if (message.identitySuggestion != null) {
      final item = message.identitySuggestion!;
      final indices = (item['_indices'] as List? ?? [item['_index']])
          .whereType<int>()
          .toList();
      final company = item['_company'] as String? ?? '';
      final title = item['_title'] as String? ?? '';
      final applied =
          indices.isNotEmpty &&
          (item['_applied'] == true ||
              indices.every(appliedSuggestionIndices.contains));
      if (item['_undone'] == true) {
        return const _AppliedSuggestionNotice(text: '회사명·직무명 수정안 반영을 취소했습니다.');
      }
      if (applied) {
        return _AppliedSuggestionNotice(
          text: '회사명·직무명 수정안을 반영했습니다.',
          onUndo: item['_undo_available'] == true ? () => onUndo(item) : null,
        );
      }
      if (item['_skipped'] == true) {
        return const _AppliedSuggestionNotice(text: '회사명·직무명 수정안을 건너뛰었습니다.');
      }
      return Align(
        alignment: Alignment.centerLeft,
        child: Container(
          margin: EdgeInsets.only(bottom: AppSpace.s(12)),
          constraints: const BoxConstraints(maxWidth: 410),
          padding: EdgeInsets.all(AppSpace.s(12)),
          decoration: BoxDecoration(
            color: AppColors.surface,
            border: Border.all(color: const Color(0xFFBBF7D0)),
            borderRadius: BorderRadius.circular(12),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                indices.length > 1
                    ? '이력서의 ${indices.length}개 항목에 있는 회사명·직무명 자리표시자를 $company / $title(으)로 한 번에 반영할까요?'
                    : '회사명을 $company, 직무명을 $title(으)로 변경할까요?',
                style: const TextStyle(fontSize: 12.5, height: 1.45),
              ),
              SizedBox(height: AppSpace.s(9)),
              Row(
                children: [
                  OutlinedButton(
                    onPressed: () => onSkip(indices),
                    child: const Text('건너뛰기'),
                  ),
                  SizedBox(width: AppSpace.s(8)),
                  FilledButton.icon(
                    onPressed: () => onApply(indices),
                    style: FilledButton.styleFrom(
                      backgroundColor: const Color(0xFF16A34A),
                      foregroundColor: Colors.white,
                      visualDensity: VisualDensity.compact,
                    ),
                    icon: const Icon(Icons.check, size: 15),
                    label: const Text('네, 변경할게요'),
                  ),
                ],
              ),
            ],
          ),
        ),
      );
    }
    if (message.suggestion != null) {
      final item = message.suggestion!;
      final index = item['_index'] as int;
      final applied =
          item['_applied'] == true || appliedSuggestionIndices.contains(index);
      if (item['_undone'] == true) {
        return const _AppliedSuggestionNotice(text: '수정안 반영을 취소했습니다.');
      }
      final newItem = item['new_item'] is Map
          ? Map<String, dynamic>.from(item['new_item'] as Map)
          : null;
      if (applied) {
        return _AppliedSuggestionNotice(
          text: newItem != null
              ? '새 프로젝트를 이력서에 추가했습니다. 기간은 직접 채워 주세요.'
              : '수정안을 이력서에 반영했습니다.',
          onUndo: item['_undo_available'] == true ? () => onUndo(item) : null,
        );
      }
      if (item['_skipped'] == true) {
        return const _AppliedSuggestionNotice(text: '수정안을 건너뛰었습니다.');
      }
      if (newItem != null) {
        return _NewProjectSuggestionCard(
          item: item,
          newItem: newItem,
          tag: _tagFor(item),
          onSkip: () => onSkip([index]),
          onApply: () => onApply([index]),
        );
      }
      return Card(
        margin: EdgeInsets.only(bottom: AppSpace.s(12)),
        color: AppColors.tint(const Color(0xFFF0FDF4)),
        child: Padding(
          padding: EdgeInsets.all(AppSpace.s(12)),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              ?_tagFor(item),
              const Text(
                'AI 수정안',
                style: TextStyle(
                  fontWeight: FontWeight.w700,
                  color: Color(0xFF166534),
                ),
              ),
              SizedBox(height: AppSpace.s(7)),
              Text(
                '원문',
                style: TextStyle(fontSize: 11, color: AppColors.textSecondary),
              ),
              SizedBox(height: AppSpace.s(3)),
              Text(
                item['original_quote'] as String? ?? '',
                style: _revisionTextStyle,
              ),
              Padding(
                padding: EdgeInsets.symmetric(vertical: AppSpace.s(9)),
                child: Divider(
                  height: 1,
                  thickness: 0.6,
                  color: Color(0x33000000),
                ),
              ),
              const Text(
                '수정안',
                style: TextStyle(fontSize: 11, color: Color(0xFF166534)),
              ),
              SizedBox(height: AppSpace.s(3)),
              Text.rich(
                TextSpan(
                  style: _revisionTextStyle,
                  children: _changedRevisionSpans(
                    item['original_quote'] as String? ?? '',
                    item['suggested_revision'] as String? ?? '',
                  ),
                ),
              ),
              if ((item['reason'] as String? ?? '').isNotEmpty) ...[
                SizedBox(height: AppSpace.s(5)),
                Text(
                  item['reason'] as String,
                  style: TextStyle(
                    fontSize: 11,
                    color: AppColors.textSecondary,
                  ),
                ),
              ],
              // 다른 칸과 겹치거나 원문의 부정 표현이 빠진 수정안은 막지 않고 알린다. 사용자가 보고 고른다(2026-09-15).
              for (final notice in _noticesFor(item)) ...[
                SizedBox(height: AppSpace.s(6)),
                _ReviewNoticeLine(text: notice),
              ],
              SizedBox(height: AppSpace.s(9)),
              Row(
                children: [
                  OutlinedButton(
                    onPressed: () => onSkip([index]),
                    child: const Text('건너뛰기'),
                  ),
                  SizedBox(width: AppSpace.s(8)),
                  FilledButton.icon(
                    onPressed: () => onApply([index]),
                    style: FilledButton.styleFrom(
                      backgroundColor: const Color(0xFF16A34A),
                      foregroundColor: Colors.white,
                      visualDensity: VisualDensity.compact,
                    ),
                    icon: const Icon(Icons.check, size: 15),
                    label: const Text('이 문장으로 바꾸기'),
                  ),
                ],
              ),
            ],
          ),
        ),
      );
    }

    final isUser = message.isUser;
    final text = message.question?['question'] as String? ?? message.text;
    final questionTag = message.question == null
        ? null
        : _tagFor(message.question!);
    return Align(
      alignment: isUser ? Alignment.centerRight : Alignment.centerLeft,
      child: Container(
        margin: EdgeInsets.only(bottom: AppSpace.s(12)),
        constraints: const BoxConstraints(maxWidth: 410),
        padding: EdgeInsets.symmetric(
          horizontal: AppSpace.s(12),
          vertical: AppSpace.s(10),
        ),
        decoration: BoxDecoration(
          color: isUser ? AppColors.primary : AppColors.surface,
          border: isUser
              ? null
              : Border.all(color: AppColors.tint(const Color(0xFFE5E7EB))),
          borderRadius: BorderRadius.circular(12),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisSize: MainAxisSize.min,
          children: [
            ?questionTag,
            // 내 말풍선은 파란 바탕에 흰 글씨라 기본 선택 강조색(파랑)이 묻혀, 드래그해도
            // 선택이 안 된 것처럼 보였다. 이 말풍선 안에서만 흰 강조색을 쓴다.
            DefaultSelectionStyle(
              selectionColor: isUser
                  ? const Color(0x66FFFFFF)
                  : DefaultSelectionStyle.of(context).selectionColor,
              child: Text(
                text,
                style: TextStyle(
                  fontSize: 12.5,
                  height: 1.45,
                  color: isUser ? Colors.white : AppColors.textPrimary,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// 답변이 이력서에 없는 별도 경험일 때의 수정안. 기존 칸을 고치지 않고 프로젝트 목록 끝에 항목을 하나 더한다.
/// 원문이 없으니 바뀐 부분 대신 추가될 이름·형태·기술·설명을 그대로 보여 준다(2026-09-15).
class _NewProjectSuggestionCard extends StatelessWidget {
  const _NewProjectSuggestionCard({
    required this.item,
    required this.newItem,
    required this.tag,
    required this.onSkip,
    required this.onApply,
  });

  final Map<String, dynamic> item;
  final Map<String, dynamic> newItem;
  final Widget? tag;
  final VoidCallback onSkip;
  final VoidCallback onApply;

  Widget _row(String label, String value) => Padding(
    padding: EdgeInsets.only(bottom: AppSpace.s(5)),
    child: Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        SizedBox(
          width: 44,
          child: Text(
            label,
            style: TextStyle(fontSize: 11, color: AppColors.textSecondary),
          ),
        ),
        Expanded(
          child: Text(
            value.isEmpty ? '비워 둠 · 직접 채워 주세요' : value,
            style: TextStyle(
              fontSize: 12,
              height: 1.5,
              color: value.isEmpty
                  ? AppColors.textSecondary
                  : AppColors.textPrimary,
            ),
          ),
        ),
      ],
    ),
  );

  @override
  Widget build(BuildContext context) {
    final notice = item['overlap_notice'] as String? ?? '';
    final reason = item['reason'] as String? ?? '';
    return Card(
      key: const ValueKey('review-new-project-card'),
      margin: EdgeInsets.only(bottom: AppSpace.s(12)),
      color: AppColors.tint(const Color(0xFFF0FDF4)),
      child: Padding(
        padding: EdgeInsets.all(AppSpace.s(12)),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            ?tag,
            const Row(
              children: [
                Icon(Icons.add_box_outlined, size: 16, color: Color(0xFF166534)),
                SizedBox(width: 5),
                Text(
                  '새 프로젝트로 추가',
                  style: TextStyle(
                    fontWeight: FontWeight.w700,
                    color: Color(0xFF166534),
                  ),
                ),
              ],
            ),
            SizedBox(height: AppSpace.s(8)),
            _row('이름', newItem['name'] as String? ?? ''),
            _row('형태', newItem['role'] as String? ?? ''),
            _row('기술', newItem['tech_stack'] as String? ?? ''),
            _row('기간', ''),
            _row('설명', newItem['description'] as String? ?? ''),
            if (reason.isNotEmpty) ...[
              SizedBox(height: AppSpace.s(3)),
              Text(
                reason,
                style: TextStyle(fontSize: 11, color: AppColors.textSecondary),
              ),
            ],
            if (notice.isNotEmpty) ...[
              SizedBox(height: AppSpace.s(6)),
              _ReviewNoticeLine(text: notice),
            ],
            SizedBox(height: AppSpace.s(9)),
            Row(
              children: [
                OutlinedButton(onPressed: onSkip, child: const Text('건너뛰기')),
                SizedBox(width: AppSpace.s(8)),
                FilledButton.icon(
                  onPressed: onApply,
                  style: FilledButton.styleFrom(
                    backgroundColor: const Color(0xFF16A34A),
                    foregroundColor: Colors.white,
                    visualDensity: VisualDensity.compact,
                  ),
                  icon: const Icon(Icons.add, size: 15),
                  label: const Text('프로젝트로 추가'),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

/// 수정안을 막지는 않지만 사용자가 확인해야 할 점을 알리는 한 줄.
class _ReviewNoticeLine extends StatelessWidget {
  const _ReviewNoticeLine({required this.text});

  final String text;

  @override
  Widget build(BuildContext context) {
    final color = AppColors.isDark
        ? AppColors.warning
        : const Color(0xFFB45309);
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Icon(Icons.info_outline, size: 14, color: color),
        SizedBox(width: AppSpace.s(5)),
        Expanded(
          child: Text(
            text,
            style: TextStyle(fontSize: 11, height: 1.4, color: color),
          ),
        ),
      ],
    );
  }
}

class _AppliedSuggestionNotice extends StatelessWidget {
  const _AppliedSuggestionNotice({required this.text, this.onUndo});

  final String text;
  final VoidCallback? onUndo;

  @override
  Widget build(BuildContext context) => Align(
    alignment: Alignment.centerLeft,
    child: Container(
      margin: EdgeInsets.only(bottom: AppSpace.s(12)),
      padding: EdgeInsets.symmetric(
        horizontal: AppSpace.s(11),
        vertical: AppSpace.s(8),
      ),
      decoration: BoxDecoration(
        color: AppColors.tint(const Color(0xFFF0FDF4)),
        borderRadius: BorderRadius.circular(9),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Flexible(
            child: Text(
              '✓ $text',
              style: const TextStyle(
                fontSize: 12,
                fontWeight: FontWeight.w600,
                color: Color(0xFF166534),
              ),
            ),
          ),
          if (onUndo != null) ...[
            SizedBox(width: AppSpace.s(8)),
            TextButton.icon(
              onPressed: onUndo,
              style: TextButton.styleFrom(
                visualDensity: VisualDensity.compact,
                padding: EdgeInsets.symmetric(horizontal: AppSpace.s(6)),
                foregroundColor: const Color(0xFF166534),
              ),
              icon: const Icon(Icons.undo, size: 14),
              label: const Text('되돌리기'),
            ),
          ],
        ],
      ),
    ),
  );
}

class _ReviewChatMessage {
  const _ReviewChatMessage.assistant(this.text)
    : isUser = false,
      question = null,
      suggestion = null,
      identitySuggestion = null;
  const _ReviewChatMessage.user(this.text)
    : isUser = true,
      question = null,
      suggestion = null,
      identitySuggestion = null;
  const _ReviewChatMessage.question(this.question)
    : text = '',
      isUser = false,
      suggestion = null,
      identitySuggestion = null;
  const _ReviewChatMessage.suggestion(this.suggestion)
    : text = '',
      isUser = false,
      question = null,
      identitySuggestion = null;
  const _ReviewChatMessage.identityConfirmation(this.identitySuggestion)
    : text = '',
      isUser = false,
      question = null,
      suggestion = null;

  final String text;
  final bool isUser;
  final Map<String, dynamic>? question;
  final Map<String, dynamic>? suggestion;
  final Map<String, dynamic>? identitySuggestion;

  factory _ReviewChatMessage.fromMap(Map<dynamic, dynamic> raw) {
    final map = Map<String, dynamic>.from(raw);
    final payload = map['payload'] is Map
        ? Map<String, dynamic>.from(map['payload'] as Map)
        : <String, dynamic>{};
    return switch (map['type']) {
      'user' => _ReviewChatMessage.user(map['text'] as String? ?? ''),
      'question' => _ReviewChatMessage.question(payload),
      'suggestion' => _ReviewChatMessage.suggestion(payload),
      'identity' => _ReviewChatMessage.identityConfirmation(payload),
      _ => _ReviewChatMessage.assistant(map['text'] as String? ?? ''),
    };
  }

  Map<String, dynamic> toMap() {
    if (question != null) return {'type': 'question', 'payload': question};
    if (suggestion != null)
      return {'type': 'suggestion', 'payload': suggestion};
    if (identitySuggestion != null) {
      return {'type': 'identity', 'payload': identitySuggestion};
    }
    return {'type': isUser ? 'user' : 'assistant', 'text': text};
  }
}

/// 첫 첨삭의 문장 다듬기 수정안을 한 카드에 모은다. 새 사실이 없는 표현 수정이라 하나씩 넘기지 않고
/// 고른 것만 한 번에 적용한다. 적용·되돌리기는 회사명·직무명 카드와 같은 `_indices` 경로를 쓴다.
class _PolishBundleCard extends StatefulWidget {
  const _PolishBundleCard({
    required this.item,
    required this.onApply,
    required this.onSkip,
    required this.tag,
  });

  final Map<String, dynamic> item;
  final ValueChanged<List<int>> onApply;
  final ValueChanged<List<int>> onSkip;
  final Widget? tag;

  @override
  State<_PolishBundleCard> createState() => _PolishBundleCardState();
}

class _PolishBundleCardState extends State<_PolishBundleCard> {
  late final List<Map<String, dynamic>> _items = [
    for (final raw in widget.item['items'] as List? ?? const [])
      if (raw is Map) Map<String, dynamic>.from(raw),
  ];
  late final Set<int> _chosen = {
    for (final item in _items) item['_index'] as int,
  };

  String _fieldLabel(String path) {
    const sections = {
      'coreCompetencies': '핵심 역량',
      'experience': '경력',
      'projects': '프로젝트',
      'awards': '수상',
      'otherActivities': '기타 활동',
      'trainingExperience': '교육',
      'education': '학력',
      'certifications': '자격증',
    };
    const intro = {
      'intro': '자기소개',
      'motivation': '지원동기',
      'challenge': '어려움 극복 경험',
      'growth': '성장과정',
      'strengthsWeaknesses': '성격의 장단점',
      'aspiration': '입사 후 포부',
    };
    final parts = path.split('.');
    if (parts.first == 'selfIntroduction' && parts.length > 1) {
      return intro[parts[1]] ?? '자기소개서';
    }
    final match = RegExp(r'^(\w+)\[(\d+)\]').firstMatch(path);
    if (match != null) {
      return '${sections[match.group(1)] ?? match.group(1)} ${int.parse(match.group(2)!) + 1}';
    }
    return sections[parts.first] ?? parts.first;
  }

  @override
  Widget build(BuildContext context) {
    final all = [for (final item in _items) item['_index'] as int];
    return Card(
      key: const ValueKey('polish-bundle'),
      margin: EdgeInsets.only(bottom: AppSpace.s(12)),
      color: AppColors.tint(const Color(0xFFF0FDF4)),
      child: Padding(
        padding: EdgeInsets.all(AppSpace.s(12)),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            ?widget.tag,
            Text(
              '문장 다듬기 ${_items.length}개',
              style: const TextStyle(
                fontWeight: FontWeight.w700,
                color: Color(0xFF166534),
              ),
            ),
            SizedBox(height: AppSpace.s(3)),
            Text(
              '새 사실 없이 읽기 좋게 고친 문장이에요. 원하는 것만 골라 한 번에 적용하세요. '
              '적용한 뒤 질문에 답하면 다듬어진 문장을 기준으로 다시 첨삭합니다.',
              style: TextStyle(fontSize: 11, color: AppColors.textSecondary),
            ),
            SizedBox(height: AppSpace.s(8)),
            for (final item in _items)
              _PolishBundleRow(
                label: _fieldLabel(item['field_path'] as String? ?? ''),
                notices: _ReviewChatBubble._noticesFor(item),
                original: item['original_quote'] as String? ?? '',
                revision: item['suggested_revision'] as String? ?? '',
                checked: _chosen.contains(item['_index']),
                onChanged: (value) => setState(() {
                  final index = item['_index'] as int;
                  value ? _chosen.add(index) : _chosen.remove(index);
                }),
              ),
            SizedBox(height: AppSpace.s(6)),
            Row(
              children: [
                TextButton(
                  onPressed: () => setState(() {
                    _chosen.length == all.length
                        ? _chosen.clear()
                        : _chosen.addAll(all);
                  }),
                  child: Text(_chosen.length == all.length ? '모두 해제' : '모두 선택'),
                ),
                const Spacer(),
                OutlinedButton(
                  onPressed: () => widget.onSkip(all),
                  child: const Text('건너뛰기'),
                ),
                SizedBox(width: AppSpace.s(8)),
                FilledButton.icon(
                  key: const ValueKey('polish-bundle-apply'),
                  onPressed: _chosen.isEmpty
                      ? null
                      : () {
                          final selected = [
                            for (final index in all)
                              if (_chosen.contains(index)) index,
                          ];
                          // 고르지 않은 수정안은 이 카드에서 버린다. 적용 표시와 되돌리기가 고른 것만 본다.
                          widget.item['_indices'] = selected;
                          widget.onApply(selected);
                        },
                  style: FilledButton.styleFrom(
                    backgroundColor: const Color(0xFF16A34A),
                    foregroundColor: Colors.white,
                    visualDensity: VisualDensity.compact,
                  ),
                  icon: const Icon(Icons.check, size: 15),
                  label: Text('선택한 ${_chosen.length}개 적용'),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

class _PolishBundleRow extends StatelessWidget {
  const _PolishBundleRow({
    required this.label,
    required this.original,
    required this.revision,
    required this.checked,
    required this.onChanged,
    this.notices = const [],
  });

  final String label;
  final List<String> notices;
  final String original;
  final String revision;
  final bool checked;
  final ValueChanged<bool> onChanged;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.only(bottom: AppSpace.s(6)),
      child: InkWell(
        onTap: () => onChanged(!checked),
        borderRadius: BorderRadius.circular(8),
        child: Container(
          padding: EdgeInsets.fromLTRB(
            AppSpace.s(4),
            AppSpace.s(6),
            AppSpace.s(8),
            AppSpace.s(8),
          ),
          decoration: BoxDecoration(
            color: AppColors.surface,
            borderRadius: BorderRadius.circular(8),
            border: Border.all(color: AppColors.tint(const Color(0xFFBBF7D0))),
          ),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Checkbox(
                value: checked,
                onChanged: (value) => onChanged(value ?? false),
                visualDensity: VisualDensity.compact,
              ),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      label,
                      style: TextStyle(
                        fontSize: 11,
                        fontWeight: FontWeight.w700,
                        color: AppColors.textSecondary,
                      ),
                    ),
                    SizedBox(height: AppSpace.s(2)),
                    Text(
                      original,
                      style: TextStyle(
                        fontSize: 11.5,
                        height: 1.45,
                        color: AppColors.textHint,
                        decoration: TextDecoration.lineThrough,
                      ),
                    ),
                    SizedBox(height: AppSpace.s(3)),
                    Text.rich(
                      TextSpan(
                        style: TextStyle(
                          fontSize: 12,
                          height: 1.5,
                          color: AppColors.textPrimary,
                        ),
                        children: _ReviewChatBubble._changedRevisionSpans(
                          original,
                          revision,
                        ),
                      ),
                    ),
                    for (final notice in notices) ...[
                      SizedBox(height: AppSpace.s(4)),
                      _ReviewNoticeLine(text: notice),
                    ],
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
