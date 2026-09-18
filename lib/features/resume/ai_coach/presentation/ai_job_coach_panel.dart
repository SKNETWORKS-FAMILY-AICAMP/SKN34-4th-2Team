import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../../../core/theme/app_colors.dart';
import '../../../../core/routing/route_paths.dart';
import '../../../../shared/demo/demo_accounts.dart';
import '../../../chatbot/presentation/robot_head_icon.dart';
import '../../../../shared/models/job_preferences.dart';
import '../../../../shared/models/resume_content.dart';
import '../../../../shared/providers/firebase_providers.dart';
import '../../../../shared/providers/cohort_providers.dart';
import '../../../../shared/services/ai_ops_service.dart';
import '../../../../shared/constants/ai_ops_types.dart';
import '../data/demo_ai_coach_clients.dart';
import '../data/resume_review_api_client.dart';
import 'job_resume_review_dialog.dart';
import 'job_recommendation_loading.dart';
import 'review_dock.dart';
import '../../../auth/providers/auth_providers.dart';
import '../data/ai_job_coach_repository.dart';
import '../data/job_recommend_api_client.dart';
import '../data/chat_job_refs.dart';
import '../data/chat_text.dart';
import '../data/resume_text_builder.dart';
import '../models/ai_job_coach_result.dart';
import '../models/resume_readiness.dart';
import '../../../../core/theme/app_space.dart';

class AiJobCoachPanel extends ConsumerStatefulWidget {
  const AiJobCoachPanel({
    super.key,
    required this.resumeId,
    this.resumeTitle = '',
    required this.draftContent,
    required this.isSidebar,
    required this.onClose,
    this.hasUnsavedChanges = false,
    this.onResumeChanged,
    this.onSaveRequested,
    this.baseResumeId = '',
    this.sourceTailoredResumeId = '',
    this.linkedJobId = '',
  });

  final String resumeId;
  final String resumeTitle;
  final String baseResumeId;
  final String sourceTailoredResumeId;
  final String linkedJobId;
  final ResumeContent draftContent;
  final bool isSidebar;
  final VoidCallback onClose;
  final bool hasUnsavedChanges;
  final ValueChanged<ResumeContent>? onResumeChanged;

  /// 이력서를 저장한다. 저장에 성공하면 true.
  ///
  /// 첨삭은 서버가 Firestore의 저장본을 읽고 그 자리에 고쳐 쓰므로, 저장 안 된 초안으로는
  /// 시작할 수 없다. 사용자가 저장 버튼을 따로 누르게 하는 대신 여기서 대신 저장한다.
  final Future<bool> Function()? onSaveRequested;

  @override
  ConsumerState<AiJobCoachPanel> createState() => _AiJobCoachPanelState();
}

/// 챗봇 대화 한 줄.
class _ChatMessage {
  const _ChatMessage.user(this.text)
    : isUser = true,
      jobs = const [],
      suggestions = const [],
      recommendations = const [],
      mode = '검색';
  const _ChatMessage.bot(
    this.text, {
    this.jobs = const [],
    this.suggestions = const [],
    this.mode = '검색',
    this.recommendations = const [],
  }) : isUser = false;

  final String text;
  final bool isUser;

  /// 서버가 어떤 갈래로 답했는지. 답이 목록인지 글인지가 달라진다.
  final String mode;

  /// 질문에 답한 경우 이 목록은 **답의 근거**다. 찾아 준 결과가 아니다.
  final List<JobChatJob> jobs;

  /// 이력서를 읽고 고른 공고. 조건 검색 결과와 달리 적합도와 근거가 붙는다.
  final List<JobRecommendation> recommendations;

  /// 다음에 좁힐 거리. 누르면 그대로 질문이 된다.
  final List<String> suggestions;
}

class _AiJobCoachPanelState extends ConsumerState<AiJobCoachPanel> {
  String _resolvedLinkedJobId = '';

  bool get _hasLinkedJob =>
      _resolvedLinkedJobId.isNotEmpty ||
      widget.linkedJobId.isNotEmpty ||
      (widget.baseResumeId.isNotEmpty &&
          widget.sourceTailoredResumeId.isNotEmpty);

  @override
  void initState() {
    super.initState();
    _resolvedLinkedJobId = widget.linkedJobId;
    if (_resolvedLinkedJobId.isEmpty) {
      unawaited(_restoreLinkedJobId());
    }
  }

  Future<void> _restoreLinkedJobId() async {
    if (widget.baseResumeId.isEmpty || widget.sourceTailoredResumeId.isEmpty) {
      return;
    }
    final cohort = ref.read(effectiveCohortIdProvider);
    if (cohort == null) return;
    try {
      final snapshot = await ref
          .read(firestoreProvider)
          .collection('cohorts')
          .doc(cohort)
          .collection('resumes')
          .doc(widget.baseResumeId)
          .collection('tailoredResumes')
          .doc(widget.sourceTailoredResumeId)
          .get();
      final jobId = snapshot.data()?['jobId'] as String? ?? '';
      if (mounted && jobId.isNotEmpty) {
        setState(() => _resolvedLinkedJobId = jobId);
      }
    } catch (_) {
      // 이전 저장본의 연결 정보를 읽지 못하면 버튼을 눌렀을 때 안내한다.
    }
  }

  Future<void> _showLinkedJob() async {
    if (_loading || _linkedJobLoading) return;
    var jobId = _resolvedLinkedJobId;
    if (jobId.isEmpty) {
      await _restoreLinkedJobId();
      jobId = _resolvedLinkedJobId;
    }
    final api = ref.read(jobRecommendApiClientProvider);
    if (jobId.isEmpty || api == null) {
      if (mounted) setState(() => _error = '연결된 맞춤 공고를 불러올 수 없습니다.');
      return;
    }
    // 새로 추천하는 게 아니라 연결된 공고 하나를 읽어 온다. 추천용 로봇 로딩(4단계가 계속 "대기")과 "분석 중"
    // 배지를 띄우면 추천을 다시 도는 것처럼 보였다(2026-09-15 앱). 짧은 안내 줄만 보인다.
    setState(() {
      _linkedJobLoading = true;
      _error = null;
      _recommendationError = null;
    });
    try {
      final response = await api.chat(message: '이 공고 정보', jobId: jobId);
      final job = response.jobs
          .where((item) => item.jobId == jobId)
          .firstOrNull;
      if (job == null) {
        throw const JobRecommendApiException('연결된 공고가 현재 공고 저장소에 없습니다.');
      }
      final recommendation = JobRecommendation(
        jobId: job.jobId,
        source: '',
        sourceUrl: job.sourceUrl,
        company: job.company,
        title: job.title,
        score: 0,
        grade: '맞춤',
        hardFilterStatus: 'PASS',
        unknownConditions: const [],
        evidence: job.techStack,
        matchedSkills: job.techStack,
        region: job.region,
        employmentType: job.employmentType,
        careerText: job.career,
        deadline: job.deadline,
        // 연결 공고는 새로 점수를 계산한 추천 결과가 아니다. 서버 공고 카드로
        // 표시해야 0.0점 같은 가짜 점수를 숨기고 재첨삭 버튼도 노출된다.
        searchRank: 1,
      );
      if (!mounted) return;
      setState(() {
        _result = AiJobCoachResult(
          testMode: false,
          notice: '이 맞춤 이력서와 연결된 공고입니다.',
          recommendations: [recommendation],
          selectedJob: null,
          skillJudgements: const [],
          resumeFeedback: const [],
          learningRecommendations: const [],
          analysisId: '',
          fromServer: true,
        );
      });
    } on JobRecommendApiException catch (error) {
      if (mounted) setState(() => _error = error.message);
    } finally {
      if (mounted) setState(() => _linkedJobLoading = false);
    }
  }

  /// 저장 안 된 변경이 있으면 사용자에게 묻고 대신 저장한다. 이어가도 되면 true.
  Future<bool> _saveBeforeReview() async {
    final save = widget.onSaveRequested;
    if (save == null) {
      setState(() => _error = '이력서를 먼저 저장한 뒤 다시 추천하고 첨삭해 주세요.');
      return false;
    }
    final ok = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: const Text('이력서 저장'),
        content: const Text(
          '첨삭은 저장된 이력서를 기준으로 합니다. 지금 저장하고 첨삭을 시작할까요?',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(dialogContext, false),
            child: const Text('취소'),
          ),
          ElevatedButton(
            onPressed: () => Navigator.pop(dialogContext, true),
            child: const Text('저장하고 첨삭'),
          ),
        ],
      ),
    );
    if (ok != true) return false;
    if (!await save()) {
      if (mounted) setState(() => _error = '이력서 저장에 실패해 첨삭을 시작하지 못했습니다.');
      return false;
    }
    return true;
  }

  Future<void> _reviewJob(JobRecommendation job) async {
    if (job.bodyIsImage) {
      setState(
        () =>
            _error = '이 공고는 상세 내용이 이미지뿐이라 원문 근거 첨삭을 할 수 없습니다. 텍스트 공고를 선택해 주세요.',
      );
      return;
    }
    // 저장하는 동안 사용자가 패널을 닫을 수 있다. 그러면 대화창을 띄우지 않는다.
    if (widget.hasUnsavedChanges && !await _saveBeforeReview()) return;
    if (!mounted) return;
    final cohort = ref.read(effectiveCohortIdProvider);
    final user = ref.read(firebaseAuthProvider).currentUser;
    if (cohort == null || (user == null && !DemoConfig.enabled)) {
      setState(() => _error = '첨삭에는 실제 Firebase 로그인이 필요합니다.');
      return;
    }
    // 데모 모드에는 첨삭 서버가 없다. 온보딩 캡처용 예시 수정안을 돌려준다.
    final ResumeReviewApiClient client = DemoConfig.enabled
        ? DemoResumeReviewApiClient(
            draft: widget.draftContent,
            jobCompany: job.company,
            jobTitle: job.title,
          )
        : ResumeReviewApiClient(token: () => user!.getIdToken());
    // 이 추천을 받아 첨삭까지 갔다는 표시. 추천이 실제로 쓰였는지를 이걸로 센다.
    // 기다리지 않는다 — 로그 때문에 대화창이 늦게 뜨면 안 된다.
    final recommendLogId = _recommendLogId;
    if (recommendLogId != null) {
      unawaited(
        ref
            .read(aiOpsServiceProvider)
            .recordOutcome(
              cohortId: cohort,
              logId: recommendLogId,
              outcome: AiOpsOutcomes.selectedForReview,
              draftId: job.jobId,
              promptVersion: _recommendPromptVersion,
              type: AiOpsTypes.jobRecommend,
            ),
      );
    }
    // 창을 내려두고 다른 화면으로 가면 이 패널은 사라진다. 끝난 뒤 이동은 라우터로 한다.
    final router = GoRouter.of(context);
    final reviewKey = ValueKey('job-review-${widget.resumeId}-${job.jobId}');
    try {
      final workspaceResumeId = await ReviewDock.show<String>(
        context,
        key: reviewKey,
        child: JobResumeReviewDialog(
          key: reviewKey,
          client: client,
          cohortId: cohort,
          aiOps: DemoConfig.enabled ? null : ref.read(aiOpsServiceProvider),
          resumeId: widget.resumeId,
          jobId: job.jobId,
          jobCompany: job.company,
          jobTitle: job.title,
          draft: widget.draftContent,
          onChanged: (_) {
            // 공고별 사본은 서버에서 자동 저장한다. 기본 이력서 편집 상태에는
            // 전달하지 않아 다른 공고용 자리표시자가 바뀌지 않게 한다.
            if (mounted)
              setState(() {
                _result = null;
              });
          },
        ),
      );
      if (workspaceResumeId != null) {
        router.push(RoutePaths.resumeEditPath(workspaceResumeId));
      }
    } finally {
      client.close();
    }
  }

  @override
  void didUpdateWidget(covariant AiJobCoachPanel oldWidget) {
    super.didUpdateWidget(oldWidget);
    // 이력서가 그대로면 견줄 것도 없다. 아래 비교는 이력서 전체를 JSON으로 두 번
    // 직렬화하는데, 편집 화면은 키 입력마다 다시 만들어지므로 그때마다 치르면 안 된다.
    // 글자를 고치면 `copyWith`가 새 객체를 만들므로 이 지름길로는 안 빠진다.
    if (identical(widget.draftContent, oldWidget.draftContent)) return;
    if (!sameResumeContent(
      widget.draftContent,
      oldWidget.draftContent.toMap(),
    )) {
      _result = null;
    }
  }

  final TextEditingController _chatController = TextEditingController();
  final List<_ChatMessage> _messages = [
    const _ChatMessage.bot(
      '채용에 대해 물어보세요. 공고를 찾아드리고, 궁금한 것에도 답해드려요.\n'
      '답은 지금 열려 있는 공고를 직접 세어 드립니다.',
      suggestions: [
        '서울 백엔드 신입',
        '백엔드 신입은 뭘 준비해야 해?',
        '요즘 많이 요구하는 기술이 뭐야?',
      ],
    ),
  ];

  /// 직전 검색 조건. 서버가 대화를 저장하지 않으므로 앱이 들고 이어 보낸다.
  JobChatFilters? _chatFilters;

  /// 공고 하나를 놓고 묻는 중이면 그 공고. 비어 있으면 평소 대화다.
  ///
  /// 이걸 들고 있는 동안의 말은 전부 이 공고에 대한 물음으로 간다. 그래야 "신입도
  /// 돼?"처럼 짧은 말이 어느 공고 이야기인지 흐려지지 않는다.
  JobChatJob? _askingAbout;

  /// **찾아 준 목록.** 화면에 나온 순서 그대로. "2번"을 가리킬 때 서버가 쓴다.
  List<String> _lastShownJobIds = const [];

  /// **직전 답이 다룬 공고.** 위와 다르다. 위는 번호가 가리킬 목록이고, 이쪽은 방금
  /// 이야기한 대상이다. 비교 답이면 견준 두 건이 들어간다.
  ///
  /// "두 공고의 자격요건만 간단히 비교해줘"에는 번호가 없다. 이게 없으면 챗봇이
  /// 스스로 권한 말을 눌렀는데 "공고가 보이지 않아 비교할 수 없다"고 답한다.
  List<String> _lastAnswerJobIds = const [];

  /// **같은 조건으로 지금까지 보여 준 공고 전부.** "이거 말고"를 거듭할 때 서버가 빼고
  /// 다음 공고를 준다. 조건이 바뀌면 새로 센다(`nextSeenJobIds`).
  List<String> _seenJobIds = const [];
  bool _chatBusy = false;

  /// 기다리는 동안 보여줄 말. 추천은 11초쯤 걸리므로 무엇을 하는 중인지 밝힌다.
  /// 차례대로 넘어가고 마지막 말에서 멈춘다.
  List<String> _chatBusyLabels = const [];
  AiJobCoachResult? _result;
  bool _chatMode = false;
  bool _loading = false;
  // 맞춤 이력서에 연결된 공고를 읽어 오는 중. 추천(_loading)과 달리 로봇 로딩을 띄우지 않는다.
  bool _linkedJobLoading = false;
  bool _recommendationCompleted = false;
  // 직전 추천을 남긴 로그의 id. 그 추천으로 무엇을 했는지(첨삭으로 넘어갔는지)를
  // 나중에 이 id에 붙인다. 추천을 다시 돌리면 새 id로 덮인다.
  String? _recommendLogId;
  String? _recommendPromptVersion;
  String? _recommendationError;
  String? _error;

  /// 지금 진행 중인 추천 단계의 이름. 서버가 알려 준다. 아직 안 왔으면 null이다.
  String? _stage;

  /// 끝난 단계가 남긴 결과 한 줄. {단계 이름: "열린 공고에서 40건을 추렸어요"}
  final Map<String, String> _stageResults = {};

  ResumeReadiness get _readiness => ResumeReadiness.of(widget.draftContent);

  /// 취업 희망 조건은 이력서가 아니라 프로필(`users/{uid}.jobPreferences`)에 있다.
  JobPreferences get _preferences =>
      ref.read(currentUserProvider).value?.jobPreferences ??
      const JobPreferences();

  @override
  void dispose() {
    _chatController.dispose();
    super.dispose();
  }

  /// 조건을 못 갖춘 기능은 실행하지 않고 이유만 보여준다.
  bool _guard(AiCoachFeature feature) {
    final reason = _readiness.blockedReason(feature);
    if (reason == null) return true;
    setState(() {
      _result = null;
      _error = reason;
      _recommendationError = null;
    });
    return false;
  }

  /// 공고와 무관하게 문장 자체의 맞춤법·문법·표현을 다듬는다.
  Future<void> _reviewResume() async {
    if (!_guard(AiCoachFeature.resumeAnalysis)) return;
    if (widget.hasUnsavedChanges && !await _saveBeforeReview()) return;
    if (!mounted) return;
    final cohort = ref.read(effectiveCohortIdProvider);
    final user = ref.read(firebaseAuthProvider).currentUser;
    if (cohort == null || (user == null && !DemoConfig.enabled)) {
      setState(() => _error = '첨삭에는 실제 Firebase 로그인이 필요합니다.');
      return;
    }
    final ResumeReviewApiClient client = DemoConfig.enabled
        ? DemoResumeReviewApiClient(draft: widget.draftContent)
        : ResumeReviewApiClient(token: () => user!.getIdToken());
    final reviewKey = ValueKey('general-review-${widget.resumeId}');
    try {
      await ReviewDock.show<void>(
        context,
        key: reviewKey,
        child: JobResumeReviewDialog(
          key: reviewKey,
          client: client,
          cohortId: cohort,
          aiOps: DemoConfig.enabled ? null : ref.read(aiOpsServiceProvider),
          resumeId: widget.resumeId,
          draft: widget.draftContent,
          generalReview: true,
          onChanged: (content) {
            // 창을 내려두고 편집 화면을 떠났으면 알릴 곳이 없다. 저장은 서버가 이미 했다.
            if (!mounted) return;
            widget.onResumeChanged?.call(content);
            setState(() => _result = null);
          },
        ),
      );
    } catch (error) {
      if (mounted) setState(() => _error = '이력서 첨삭을 시작하지 못했습니다: $error');
    } finally {
      client.close();
    }
  }

  void _openChat() {
    setState(() {
      _chatMode = true;
      _error = null;
    });
  }

  /// 챗봇에서 "내 이력서로 맞는 공고"를 물으면 **바로 추천을 돌려 대화창에 답한다.**
  ///
  /// 서버 챗봇은 이력서를 받지 않는다. 하지만 앱은 들고 있으므로 앱이 돌리면 된다.
  /// 버튼을 한 번 더 누르게 하면 "골라 드릴게요"라는 말만 오가고 답이 안 나온다.
  ///
  /// 결과는 `_result`에도 넣는다. 근거 전체(이력서 문장 ↔ 공고 문장)는 코치 화면이
  /// 보여주므로, 대화에서 "자세한 근거 보기"로 그쪽으로 넘어갈 수 있어야 한다.
  Future<void> _recommendInChat([String scope = '전체']) async {
    final blocked = _readiness.blockedReason(AiCoachFeature.jobRecommendation);
    if (blocked != null) {
      // 이력서가 덜 찼을 때만 이렇게 답한다. 이때는 "채워 주세요"가 사실이다.
      setState(() => _messages.add(_ChatMessage.bot(blocked)));
      return;
    }

    final requestedContent = widget.draftContent;
    final missing = _emptyScopeReason(scope, requestedContent);
    if (missing != null) {
      setState(() => _messages.add(_ChatMessage.bot(missing)));
      return;
    }

    setState(() {
      _chatBusy = true;
      _chatBusyLabels = [
        switch (scope) {
          '프로젝트' => '프로젝트 경험을 읽는 중…',
          '기술스택' => '기술스택을 읽는 중…',
          '자기소개서' => '자기소개서를 읽는 중…',
          '경력' => '경력을 읽는 중…',
          _ => '이력서를 읽는 중…',
        },
        '맞는 공고를 고르는 중…',
        '적합도를 비교하는 중…',
      ];
    });
    try {
      final result = await ref
          .read(aiJobCoachRepositoryProvider)
          .analyzeAndMatch(
            draftContent: requestedContent,
            preferences: _preferences,
            // 읽을 글만 좁힌다. 검증과 조건은 이력서 원본 그대로다.
            focus: scope == '전체' ? null : _scopedResume(scope),
          );
      if (!mounted) return;
      setState(() {
        _result = result;
        final hint = _readiness.weakEvidenceHint;
        _messages.add(
          _ChatMessage.bot(
            _recommendSummary(result.recommendations, scope) +
                (hint == null ? '' : '\n\n$hint'),
            mode: '추천',
            recommendations: result.recommendations.take(3).toList(),
          ),
        );
      });
    } on JobRecommendApiException catch (error) {
      if (mounted)
        setState(() => _messages.add(_ChatMessage.bot(error.message)));
    } catch (error) {
      if (mounted) {
        setState(
          () => _messages.add(_ChatMessage.bot('공고를 고르지 못했습니다: $error')),
        );
      }
    } finally {
      if (mounted) {
        setState(() {
          _chatBusy = false;
          _chatBusyLabels = const [];
        });
      }
    }
  }

  /// 서버가 **읽을 글**만 남긴 이력서. 조건 판정에는 쓰지 않는다.
  ///
  /// 이걸 원본 대신 넘기면 필수 항목 검증에 걸린다. 실제로 그랬다 — 이력서가 멀쩡한데
  /// "핵심역량·기술스택·자기소개서를 작성해 주세요"로 막혔다. 학력·연차·전공·자격증은
  /// `analyzeAndMatch`가 원본에서 따로 뽑으므로 여기서 지워도 조건은 그대로다.
  ResumeContent _scopedResume(String scope) {
    final content = widget.draftContent;
    const emptyCore = ResumeCoreCompetencies();
    const emptyIntro = ResumeSelfIntroduction();
    return switch (scope) {
      // 물어본 그대로 그 부분만 남긴다. 경력 기술까지 섞으면 "프로젝트 경험만"이 아니다.
      '프로젝트' => content.copyWith(
        experience: const [],
        techStack: const [],
        awards: const [],
        trainingExperience: const [],
        otherActivities: const [],
        coreCompetencies: emptyCore,
        selfIntroduction: emptyIntro,
      ),
      '기술스택' => content.copyWith(
        experience: const [],
        projects: const [],
        awards: const [],
        trainingExperience: const [],
        otherActivities: const [],
        coreCompetencies: emptyCore,
        selfIntroduction: emptyIntro,
      ),
      // 자기소개서에는 핵심역량을 함께 남긴다. 둘 다 "내가 어떤 사람인가"를 쓰는
      // 칸이고, 자기소개서만으로는 글이 너무 짧아 검색이 흐려진다.
      '자기소개서' => content.copyWith(
        experience: const [],
        projects: const [],
        techStack: const [],
        awards: const [],
        trainingExperience: const [],
        otherActivities: const [],
      ),
      '경력' => content.copyWith(
        projects: const [],
        techStack: const [],
        awards: const [],
        trainingExperience: const [],
        otherActivities: const [],
        coreCompetencies: emptyCore,
        selfIntroduction: emptyIntro,
      ),
      _ => content,
    };
  }

  /// 좁힌 곳이 비어 있으면 추천이 근거 없이 돈다. 먼저 알린다.
  static String? _emptyScopeReason(String scope, ResumeContent content) {
    if (scope == '프로젝트' && content.projects.isEmpty) {
      return '이력서에 프로젝트가 아직 없어요. 하나 적어 주시면 그걸 기준으로 찾아드릴게요.';
    }
    if (scope == '기술스택' && content.techStack.isEmpty) {
      return '이력서에 기술스택이 아직 없어요. 쓸 줄 아는 기술을 넣어 주시면 그걸 기준으로 찾아드릴게요.';
    }
    if (scope == '자기소개서' &&
        !content.selfIntroduction.isFilled &&
        !content.coreCompetencies.isFilled) {
      return '이력서에 자기소개서가 아직 없어요. 한 항목이라도 적어 주시면 그걸 기준으로 찾아드릴게요.';
    }
    if (scope == '경력' && content.experience.where((e) => e.isFilled).isEmpty) {
      return '이력서에 경력이 아직 없어요. 신입이시라면 "내 프로젝트 경험만 보고 추천해줘"라고 해보세요.';
    }
    return null;
  }

  /// 몇 건을 골랐고 그중 몇 건이 잘 맞는지. 등급은 서버가 매긴 그대로 센다.
  static String _recommendSummary(List<JobRecommendation> found, String scope) {
    final source = switch (scope) {
      '프로젝트' => '프로젝트 경험',
      '기술스택' => '기술스택',
      '자기소개서' => '자기소개서',
      '경력' => '경력',
      _ => '이력서',
    };
    if (found.isEmpty) {
      return '$source을 읽었지만 조건에 맞는 공고를 찾지 못했어요.\n'
          '희망 지역이나 고용형태를 넓혀 보시겠어요?';
    }
    return '$source을 읽고 ${found.length}건을 골랐어요.';
  }

  /// 공고 하나를 놓고 묻기 시작한다. 그만둘 때까지 모든 말이 이 공고로 간다.
  void _askAbout(JobChatJob job) {
    setState(() {
      _askingAbout = job;
      _messages.add(
        _ChatMessage.bot(
          '"${job.title}" 공고에 대해 물어보세요. 공고에 적힌 것만 근거로 답해드려요.',
          mode: '공고',
          suggestions: const [
            '자격요건이 뭐야?',
            '신입도 지원할 수 있어?',
            '어떤 일을 하는 자리야?',
          ],
        ),
      );
    });
  }

  /// 채용에 대해 묻고 답을 받는다. 서버가 조건 해석·검색·집계를 모두 한다.
  ///
  /// 앱에 박힌 공고 파일을 쓰지 않으므로 밤마다 모은 새 공고가 바로 나온다.
  Future<void> _sendChatMessage([String? preset]) async {
    final text = (preset ?? _chatController.text).trim();
    if (text.isEmpty || _chatBusy) return;

    final client = ref.read(jobRecommendApiClientProvider);
    setState(() {
      _messages.add(_ChatMessage.user(text));
      _chatController.clear();
      _chatBusy = true;
      _chatBusyLabels = _askingAbout != null
          ? const ['공고 내용을 살펴보는 중…', '답을 정리하는 중…']
          // 공고 검색만이 아니라 준비·자소서 같은 질문도 온다. 어느 쪽이든 맞는 말로.
          : const ['질문을 살펴보는 중…', '필요한 정보를 찾는 중…', '답을 정리하는 중…'];
    });

    if (client == null) {
      setState(() {
        _chatBusy = false;
        _messages.add(
          const _ChatMessage.bot('공고 검색 서버 주소가 비어 있어 찾을 수 없습니다.'),
        );
      });
      return;
    }

    try {
      final result = await client.chat(
        message: text,
        filters: _chatFilters,
        jobId: _askingAbout?.jobId,
        // 카드를 눌렀거나, 직전에 목록을 보여 줬으면 함께 보낸다(shouldSendResume).
        resumeText:
            shouldSendResume(
              askingAboutJob: _askingAbout != null,
              hasShownJobs: _lastShownJobIds.isNotEmpty,
            )
            ? buildResumeText(widget.draftContent)
            : null,
        // "2번 자세히 봐줘"에 답하려면 서버가 직전에 무엇을 보여 줬는지 알아야 한다.
        // 서버는 대화를 저장하지 않으므로 앱이 되돌려 준다.
        lastJobIds: _lastShownJobIds,
        // "두 공고의 자격요건만"은 번호가 없다. 방금 이야기한 공고가 무엇인지
        // 알려 줘야 답할 수 있다. 번호가 가리킬 목록과는 다른 값이다.
        lastAnswerJobIds: _lastAnswerJobIds,
        // "이거 말고"를 거듭해도 앞에서 본 공고가 다시 나오지 않게 본 것을 모두 보낸다.
        seenJobIds: _seenJobIds,
      );
      if (!mounted) return;
      setState(() {
        _seenJobIds = nextSeenJobIds(
          mode: result.mode,
          jobsInAnswer: [for (final job in result.jobs) job.jobId],
          previous: _seenJobIds,
          sameConditions: sameChatConditions(
            _chatFilters?.toJson(),
            result.filters.toJson(),
          ),
        );
        _chatFilters = result.filters;
        _lastShownJobIds = nextShownJobIds(
          mode: result.mode,
          jobsInAnswer: [for (final job in result.jobs) job.jobId],
          previous: _lastShownJobIds,
        );
        // 이쪽은 답에 공고가 들어 있으면 무엇이든 갈아 끼운다. 방금 이야기한 대상이
        // 곧 그 공고들이다. 공고가 없는 답은 이야기한 대상도 없으니 그대로 둔다.
        if (result.jobs.isNotEmpty) {
          _lastAnswerJobIds = [for (final job in result.jobs) job.jobId];
        }
        _messages.add(
          _ChatMessage.bot(
            result.reply,
            jobs: result.jobs,
            suggestions: result.suggestions,
            mode: result.mode,
          ),
        );
      });
      // 이력서로 골라 달라는 말이었다. 말만 하고 끝내지 않고 바로 돌린다.
      if (result.mode == '추천') {
        await _recommendInChat(result.resumeScope);
      }
    } on JobRecommendApiException catch (error) {
      if (!mounted) return;
      setState(() => _messages.add(_ChatMessage.bot(error.message)));
    } catch (error) {
      if (!mounted) return;
      setState(() => _messages.add(_ChatMessage.bot('공고를 찾지 못했습니다: $error')));
    } finally {
      if (mounted) setState(() => _chatBusy = false);
    }
  }

  Future<void> _run() async {
    if (_loading || _linkedJobLoading || !_guard(AiCoachFeature.jobRecommendation)) return;
    final requestedContent = widget.draftContent;
    bool resumeUnchanged() => sameResumeContent(
      widget.draftContent,
      requestedContent.toMap(),
    );
    // 무엇이 나왔고 얼마나 걸렸는지 남긴다. 원문은 안 보내고 메타만 보낸다.
    // 기수를 모르면(로그인 전) 남길 곳이 없으므로 건너뛴다. 로그가 실패해도
    // 추천은 막지 않는다 — `recordCoachLog`가 실패 시 null을 돌려준다.
    // 데모 모드는 예시 결과라 남기지 않는다.
    final cohort = DemoConfig.enabled
        ? null
        : ref.read(effectiveCohortIdProvider);
    final ops = ref.read(aiOpsServiceProvider);
    final watch = Stopwatch()..start();
    setState(() {
      _loading = true;
      _recommendationCompleted = false;
      _recommendationError = null;
      _result = null;
      _error = null;
      _stage = null;
      _stageResults.clear();
    });
    try {
      final result = await ref
          .read(aiJobCoachRepositoryProvider)
          .analyzeAndMatch(
            draftContent: requestedContent,
            preferences: _preferences,
            onProgress: (stage, detail) {
              if (!mounted) return;
              setState(() {
                if (detail == null) {
                  _stage = stage;
                } else {
                  _stageResults[stage] = detail;
                }
              });
            },
          );
      if (cohort != null) {
        _recommendLogId = await ops.recordCoachLog(
          type: AiOpsTypes.jobRecommend,
          cohortId: cohort,
          watch: watch,
          success: true,
          promptVersion: result.promptVersion,
          model: result.model,
          generatedCount: result.recommendations.length,
          meta: {
            'jobCount': result.recommendations.length,
            'topK': result.recommendations.length,
            'reranked': result.reranked,
            'resumeLength': buildResumeText(requestedContent).length,
          },
        );
        _recommendPromptVersion = result.promptVersion.isEmpty
            ? AiOpsPromptVersions.jobRecommend
            : result.promptVersion;
      }
      if (!mounted) return;
      if (resumeUnchanged()) {
        setState(() => _recommendationCompleted = true);
        if (!MediaQuery.disableAnimationsOf(context)) {
          await Future<void>.delayed(
            JobRecommendationLoading.completionDuration,
          );
        }
      }
      if (!mounted) return;
      // The draft can change during the completion animation as well.
      setState(() {
        if (resumeUnchanged()) {
          _result = result;
        } else {
          _error = '추천 중 이력서가 변경됐습니다. 저장 후 다시 추천해 주세요.';
        }
      });
    } on JobRecommendApiException catch (error) {
      if (cohort != null) {
        await ops.recordCoachLog(
          type: AiOpsTypes.jobRecommend,
          cohortId: cohort,
          watch: watch,
          success: false,
          error: error.message,
        );
      }
      if (mounted) setState(() => _recommendationError = error.message);
    } catch (error) {
      if (cohort != null) {
        await ops.recordCoachLog(
          type: AiOpsTypes.jobRecommend,
          cohortId: cohort,
          watch: watch,
          success: false,
          error: error,
        );
      }
      if (mounted) setState(() => _recommendationError = '분석 실패: $error');
    } finally {
      if (mounted) {
        setState(() {
          _loading = false;
          _recommendationCompleted = false;
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final panel = Material(
      color: widget.isSidebar
          ? AppColors.surfaceVariant.withValues(alpha: 0.45)
          : AppColors.surface,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          if (_chatMode)
            _Header(
              onToggleChat: () => setState(() => _chatMode = false),
              userName: widget.draftContent.basicInfo.name,
            ),
          if (_chatMode)
            Expanded(
              child: _ChatView(
                onOpenDetail: () => setState(() => _chatMode = false),
                askingAbout: _askingAbout,
                onStopAsking: () => setState(() => _askingAbout = null),
                onAskAbout: _askAbout,
                messages: _messages,
                controller: _chatController,
                onSend: _sendChatMessage,
                onSuggestion: _sendChatMessage,
                busy: _chatBusy,
                busyLabels: _chatBusyLabels,
              ),
            )
          else
            Expanded(
              child: CustomScrollView(
                slivers: [
                  SliverPadding(
                    padding: EdgeInsets.all(AppSpace.s(14)),
                    sliver: SliverList.list(
                      children: [
                        SizedBox(height: AppSpace.s(10)),
                        _CurrentResumeCard(
                          title: widget.resumeTitle,
                          content: widget.draftContent,
                          readiness: _readiness,
                          analyzing: _loading,
                        ),
                        SizedBox(height: AppSpace.s(18)),
                        Text(
                          '빠른 실행',
                          style: TextStyle(
                            fontSize: 11,
                            fontWeight: FontWeight.w600,
                            color: AppColors.textSecondary,
                          ),
                        ),
                        SizedBox(height: AppSpace.s(10)),
                        Row(
                          children: [
                            Expanded(
                              child: _ActionButton(
                                icon: Icons.edit_outlined,
                                iconColor: Color(0xFFFF6B5E),
                                label: '이력서 첨삭',
                                loading: false,
                                // 첨삭할 내용이 하나라도 있으면 실행할 수 있다.
                                enabled: _readiness.canAnalyzeResume,
                                disabledTooltip: _readiness.blockedReason(
                                  AiCoachFeature.resumeAnalysis,
                                ),
                                onPressed: _reviewResume,
                              ),
                            ),
                            SizedBox(width: AppSpace.s(8)),
                            Expanded(
                              child: _ActionButton(
                                icon: Icons.star_rounded,
                                iconColor: Color(0xFFF4C430),
                                label: _hasLinkedJob ? '맞춤 공고 보기' : '맞춤 공고 추천',
                                loading: _loading || _linkedJobLoading,
                                // 필수 항목이 하나라도 비면 추천하지 않는다.
                                enabled:
                                    _hasLinkedJob ||
                                    _readiness.canRecommendJobs,
                                disabledTooltip: _hasLinkedJob
                                    ? null
                                    : _readiness.blockedReason(
                                        AiCoachFeature.jobRecommendation,
                                      ),
                                onPressed: _hasLinkedJob
                                    ? _showLinkedJob
                                    : _run,
                              ),
                            ),
                            SizedBox(width: AppSpace.s(8)),
                            Expanded(
                              // 검색창이 아니라 코치와의 대화가 열린다.
                              child: _ActionButton(
                                art: const RobotHeadIcon(
                                  size: 34,
                                  inverted: true,
                                ),
                                label: '코치에게 묻기',
                                loading: false,
                                // 공고 검색은 이력서 상태와 무관하다.
                                enabled: true,
                                disabledTooltip: null,
                                onPressed: _openChat,
                              ),
                            ),
                          ],
                        ),
                        if (_error != null) ...[
                          SizedBox(height: AppSpace.s(14)),
                          _ErrorCard(message: _error!),
                        ],
                        if (_linkedJobLoading) ...[
                          SizedBox(height: AppSpace.s(18)),
                          const _LinkedJobLoadingLine(),
                        ],
                        if (_result == null &&
                            !_loading &&
                            !_linkedJobLoading &&
                            _error == null &&
                            _recommendationError == null) ...[
                          SizedBox(height: AppSpace.s(26)),
                          const _EmptyState(),
                        ],
                        if (_result case final result?) ...[
                          SizedBox(height: AppSpace.s(18)),
                          // 기술 근거·이력서 피드백·학습 추천 섹션은 팀원의 첨삭 모듈(S32-17)이 맡기로 해 제거했다.
                          _RecommendationSection(
                            title: _hasLinkedJob ? '맞춤 공고' : '맞춤 공고 Ranking',
                            result: result,
                            reviewButtonLabel: _hasLinkedJob ? '재첨삭' : null,
                            onReview: widget.onResumeChanged == null
                                ? null
                                : _reviewJob,
                          ),
                          SizedBox(height: AppSpace.s(20)),
                        ],
                      ],
                    ),
                  ),
                  if (_loading || _recommendationError != null)
                    SliverFillRemaining(
                      hasScrollBody: false,
                      child: Padding(
                        padding: EdgeInsets.fromLTRB(
                          AppSpace.s(14),
                          AppSpace.s(12),
                          AppSpace.s(14),
                          AppSpace.s(24),
                        ),
                        child: Align(
                          alignment: Alignment.bottomCenter,
                          child: JobRecommendationLoading(
                            current: _stage,
                            results: _stageResults,
                            completed: _recommendationCompleted,
                            errorMessage: _recommendationError,
                            onRetry: _run,
                          ),
                        ),
                      ),
                    ),
                ],
              ),
            ),
        ],
      ),
    );

    if (widget.isSidebar) return panel;
    // 높이는 편집 화면이 정한다. 좁은 화면에서는 손잡이로 끌어 조절하므로 여기서
    // 상한을 박으면 아무리 끌어도 그 위로 못 커진다.
    return SizedBox(
      height: double.infinity,
      child: DecoratedBox(
        decoration: BoxDecoration(
          border: Border(top: BorderSide(color: AppColors.border)),
        ),
        child: panel,
      ),
    );
  }
}

class _Header extends StatelessWidget {
  const _Header({
    required this.onToggleChat,
    required this.userName,
  });

  final VoidCallback onToggleChat;
  final String userName;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: EdgeInsets.fromLTRB(
        AppSpace.s(14),
        AppSpace.s(10),
        AppSpace.s(8),
        AppSpace.s(10),
      ),
      decoration: BoxDecoration(
        color: AppColors.surface,
        border: Border(bottom: BorderSide(color: AppColors.border)),
      ),
      child: Row(
        children: [
          InkWell(
            onTap: onToggleChat,
            borderRadius: BorderRadius.circular(12),
            child: Container(
              width: 40,
              height: AppSpace.row(40),
              decoration: BoxDecoration(
                color: const Color(0xFF171717),
                borderRadius: BorderRadius.circular(12),
              ),
              child: Icon(
                Icons.arrow_back_rounded,
                size: 20,
                color: Colors.white,
              ),
            ),
          ),
          SizedBox(width: AppSpace.s(10)),
          const RobotHeadIcon(size: 40, inverted: true),
          SizedBox(width: AppSpace.s(8)),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text(
                  '커리어 코치',
                  style: TextStyle(fontWeight: FontWeight.w700, fontSize: 14),
                ),
                Text(
                  userName.trim().isEmpty
                      ? '나의 취업 코치'
                      : '${userName.trim()} 님의 코치',
                  style: TextStyle(
                    fontSize: 11,
                    color: AppColors.textSecondary,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _ActionButton extends StatelessWidget {
  const _ActionButton({
    this.icon,
    this.iconColor,
    this.art,
    required this.label,
    required this.loading,
    required this.enabled,
    required this.disabledTooltip,
    required this.onPressed,
  }) : assert(icon != null || art != null);

  final IconData? icon;
  final Color? iconColor;

  /// 아이콘 글꼴 대신 그림을 쓸 때. 코치에게 묻기의 로봇 머리.
  final Widget? art;
  final String label;
  final bool loading;
  final bool enabled;

  /// 왜 지금 누를 수 없는지. 비활성일 때만 쓴다.
  final String? disabledTooltip;
  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    final button = OutlinedButton(
      onPressed: (loading || !enabled) ? null : onPressed,
      style: OutlinedButton.styleFrom(
        minimumSize: const Size.fromHeight(98),
        padding: EdgeInsets.symmetric(
          horizontal: AppSpace.s(6),
          vertical: AppSpace.s(15),
        ),
        foregroundColor: AppColors.textPrimary,
        side: BorderSide(color: AppColors.border),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          // 그림 칸 높이를 셋이 같게 둔다. 로봇 머리가 아이콘보다 커서, 칸을
          // 맞추지 않으면 버튼마다 글자 줄 높이가 달라진다.
          SizedBox(
            height: 34,
            child: Center(
              child: loading
                  ? const SizedBox(
                      width: 23,
                      height: 23,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : art ??
                        Icon(icon, size: 26, color: enabled ? iconColor : null),
            ),
          ),
          SizedBox(height: AppSpace.s(9)),
          Text(
            label,
            textAlign: TextAlign.center,
            style: const TextStyle(fontSize: 11, fontWeight: FontWeight.w600),
          ),
        ],
      ),
    );
    if (enabled || disabledTooltip == null) return button;
    // 비활성 버튼은 툴팁을 받지 못하므로 감싸서 이유를 보여준다.
    return Tooltip(
      message: disabledTooltip!,
      child: button,
    );
  }
}

class _EmptyState extends StatelessWidget {
  const _EmptyState();

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        Icon(Icons.hub_outlined, size: 42, color: AppColors.textHint),
        SizedBox(height: AppSpace.s(12)),
        Text(
          '이력서와 채용공고를 연결해볼까요?',
          style: TextStyle(fontWeight: FontWeight.w600, fontSize: 14),
        ),
        SizedBox(height: AppSpace.s(6)),
        Text(
          '분석 버튼을 누르면 명시 조건, 추천 순위,\nSkill Gap을 한 번에 확인합니다.',
          textAlign: TextAlign.center,
          style: TextStyle(
            fontSize: 12,
            height: 1.5,
            color: AppColors.textSecondary,
          ),
        ),
      ],
    );
  }
}

class _RecommendationSection extends StatelessWidget {
  const _RecommendationSection({
    required this.result,
    required this.title,
    this.reviewButtonLabel,
    this.onReview,
  });

  final AiJobCoachResult result;
  final String title;
  final String? reviewButtonLabel;
  final ValueChanged<JobRecommendation>? onReview;

  @override
  Widget build(BuildContext context) {
    return _Section(
      title: title,
      subtitle: result.notice,
      child: Column(
        children: [
          if (result.searchQuery.isNotEmpty) ...[
            _ServerQueryNote(
              searchQuery: result.searchQuery,
              profileSummary: result.profileSummary,
            ),
            SizedBox(height: AppSpace.s(8)),
          ],
          if (result.fromServer && result.recommendations.isEmpty)
            Text(
              '조건에 맞는 공고를 찾지 못했습니다. 희망 지역·고용형태를 넓히거나 이력서에 기술과 프로젝트를 더 적어 보세요.',
              style: TextStyle(
                fontSize: 11,
                color: AppColors.textSecondary,
                height: 1.4,
              ),
            ),
          for (var index = 0; index < result.recommendations.length; index++)
            Padding(
              padding: EdgeInsets.only(bottom: AppSpace.s(8)),
              child: _RecommendationCard(
                index: index + 1,
                item: result.recommendations[index],
                reviewButtonLabel: reviewButtonLabel,
                onReview: onReview,
              ),
            ),
        ],
      ),
    );
  }
}

class _RecommendationCard extends StatefulWidget {
  const _RecommendationCard({
    required this.index,
    required this.item,
    this.reviewButtonLabel,
    this.onReview,
  });

  final int index;
  final JobRecommendation item;
  final String? reviewButtonLabel;
  final ValueChanged<JobRecommendation>? onReview;

  @override
  State<_RecommendationCard> createState() => _RecommendationCardState();
}

class _RecommendationCardState extends State<_RecommendationCard> {
  bool _expanded = false;

  JobRecommendation get item => widget.item;

  Future<void> _open() async {
    final uri = Uri.tryParse(item.sourceUrl);
    if (uri != null && (uri.scheme == 'http' || uri.scheme == 'https')) {
      await launchUrl(uri, mode: LaunchMode.externalApplication);
    }
  }

  /// 접힌 상태에서 이 공고가 어떤 자리인지 한 줄로 보이게 한다.
  ///
  /// 근거 건수·확인할 요건 건수·조건 통과 여부는 뺐다. 펼치면 근거와 우려가 그대로
  /// 나오므로 숫자로 미리 말할 이유가 없고, "조건 통과"는 걸러진 것만 보여주는 목록에서
  /// 늘 참이라 정보가 되지 않는다. 지원할지 정할 때 먼저 보는 것은 근무지·고용형태·경력이다.
  String _summary() {
    if (item.isFromServer) {
      return [
        if (item.region.isNotEmpty) item.region,
        ?item.employmentType,
        item.careerLabel,
      ].join(' · ');
    }
    String bucket(String label, List<String> matched, List<String> unmatched) =>
        '$label ${matched.length}/${matched.length + unmatched.length}';
    final hasBuckets =
        item.matchedRequired.isNotEmpty ||
        item.unmatchedRequired.isNotEmpty ||
        item.matchedPreferred.isNotEmpty ||
        item.unmatchedPreferred.isNotEmpty ||
        item.matchedTags.isNotEmpty ||
        item.unmatchedTags.isNotEmpty;
    final detail = item.scoreDetail;
    final parts = <String>[
      if (hasBuckets) ...[
        if (item.matchedRequired.isNotEmpty ||
            item.unmatchedRequired.isNotEmpty)
          bucket('필수', item.matchedRequired, item.unmatchedRequired),
        if (item.matchedPreferred.isNotEmpty ||
            item.unmatchedPreferred.isNotEmpty)
          bucket('우대', item.matchedPreferred, item.unmatchedPreferred),
        if (item.matchedTags.isNotEmpty || item.unmatchedTags.isNotEmpty)
          bucket('태그', item.matchedTags, item.unmatchedTags),
      ] else if (detail != null && detail.skillsTotal > 0)
        '요구 기술 ${item.matchedSkills.length}/${detail.skillsTotal} 일치',
      if (item.projectSkills.isNotEmpty)
        '프로젝트 근거 ${item.projectSkills.length}건',
      if (item.roleTerms.isNotEmpty) '직무 키워드 ${item.roleTerms.length}개',
      if (item.region.isNotEmpty) item.region,
      ?item.employmentType,
      item.hardFilterStatus == 'PASS' ? '조건 통과' : '조건 확인 필요',
      if (item.embeddingRank case final rank?) '임베딩 유사도 $rank위',
    ];
    return parts.join(' · ');
  }

  Widget _reviewButton() {
    final unavailable = item.bodyIsImage;
    return Tooltip(
      message: unavailable
          ? '상세 공고가 이미지뿐이라 원문 근거 첨삭을 할 수 없습니다.'
          : '선택 공고와 이력서를 비교해 첨삭합니다.',
      child: FilledButton.icon(
        onPressed: unavailable ? null : () => widget.onReview!(item),
        style: FilledButton.styleFrom(
          foregroundColor: Colors.white,
          minimumSize: const Size(0, 32),
          padding: EdgeInsets.symmetric(
            horizontal: AppSpace.s(10),
            vertical: AppSpace.s(7),
          ),
          visualDensity: VisualDensity.compact,
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(8),
          ),
        ),
        icon: const Icon(Icons.auto_fix_high, size: 14),
        label: Text(
          unavailable ? '원문 확인 불가' : (widget.reviewButtonLabel ?? '공고 맞춤 첨삭'),
          style: const TextStyle(fontSize: 11, fontWeight: FontWeight.w600),
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final hasLink = item.sourceUrl.startsWith('http');
    return Container(
      padding: EdgeInsets.all(AppSpace.s(11)),
      decoration: BoxDecoration(
        color: AppColors.surface,
        border: Border.all(color: AppColors.border),
        borderRadius: BorderRadius.circular(10),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              CircleAvatar(
                radius: 13,
                backgroundColor: AppColors.primaryLight,
                child: Text(
                  '${widget.index}',
                  style: const TextStyle(fontSize: 11),
                ),
              ),
              SizedBox(width: AppSpace.s(9)),
              Expanded(
                child: InkWell(
                  onTap: hasLink ? _open : null,
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        item.title,
                        style: const TextStyle(
                          fontSize: 12,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                      SizedBox(height: AppSpace.s(3)),
                      Text(
                        item.source.isEmpty
                            ? item.company
                            : '${item.company} · ${item.source}',
                        style: TextStyle(
                          fontSize: 10,
                          color: AppColors.textSecondary,
                        ),
                      ),
                      if (item.bodyIsImage) ...[
                        SizedBox(height: AppSpace.s(4)),
                        Container(
                          padding: EdgeInsets.symmetric(
                            horizontal: AppSpace.s(6),
                            vertical: AppSpace.s(2),
                          ),
                          decoration: BoxDecoration(
                            color: AppColors.warning.withValues(alpha: 0.12),
                            borderRadius: BorderRadius.circular(4),
                          ),
                          child: Text(
                            '상세 이미지 공고 · 기술 태그로만 비교',
                            style: TextStyle(
                              fontSize: 9.5,
                              color: AppColors.warning,
                              fontWeight: FontWeight.w600,
                            ),
                          ),
                        ),
                      ],
                    ],
                  ),
                ),
              ),
              SizedBox(width: AppSpace.s(8)),
              Column(
                crossAxisAlignment: CrossAxisAlignment.end,
                children: [
                  // 서버 추천은 점수가 아니라 적합도(높음/보통/낮음)만 준다.
                  if (!item.isFromServer)
                    Text(
                      '${item.score.toStringAsFixed(1)}점',
                      style: const TextStyle(
                        fontSize: 13,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                  // 서버 적합도는 사람 정답으로 검증된 적이 없다. 순서에만 쓰고
                  // 화면에는 내지 않는다. 근거 문장이 그 자리를 대신한다.
                  if (!item.isFromServer)
                    Text(
                      item.grade,
                      style: TextStyle(
                        fontSize: 10,
                        color: item.grade == '높음'
                            ? AppColors.success
                            : AppColors.textSecondary,
                      ),
                    ),
                  if (hasLink)
                    IconButton(
                      onPressed: _open,
                      tooltip: '공고 열기',
                      visualDensity: VisualDensity.compact,
                      padding: EdgeInsets.zero,
                      constraints: const BoxConstraints(
                        minWidth: 24,
                        minHeight: 24,
                      ),
                      icon: Icon(
                        Icons.open_in_new,
                        size: 13,
                        color: AppColors.textHint,
                      ),
                    ),
                ],
              ),
            ],
          ),
          SizedBox(height: AppSpace.s(6)),
          Text(
            _summary(),
            style: TextStyle(
              fontSize: 10.5,
              color: AppColors.info,
              height: 1.4,
            ),
          ),
          // 마감은 조건 표 안쪽이 아니라 여기 있어야 한다. 지원할지 정할 때
          // 근무지·고용형태 다음으로 보는 것이 언제까지냐인데, 표는 펼쳐야 보인다.
          if (item.deadline case final deadline?)
            Text(
              '~ ${_deadlineDate(deadline)}',
              style: TextStyle(
                fontSize: 10.5,
                color: AppColors.textSecondary,
                height: 1.4,
              ),
            ),
          if (item.unknownConditions.isNotEmpty) ...[
            SizedBox(height: AppSpace.s(3)),
            Text(
              '확인 필요: ${item.unknownConditions.join(', ')}',
              style: TextStyle(fontSize: 10, color: AppColors.warning),
            ),
          ],
          if (_expanded && item.isFromServer && widget.onReview != null) ...[
            SizedBox(height: AppSpace.s(2)),
            Align(
              alignment: Alignment.centerRight,
              child: _reviewButton(),
            ),
          ],
          SizedBox(height: AppSpace.s(4)),
          if (_expanded) ...[
            SizedBox(height: AppSpace.s(6)),
            _RecommendationRationale(item: item),
          ],
          SizedBox(height: AppSpace.s(4)),
          Row(
            children: [
              Expanded(
                child: InkWell(
                  onTap: () => setState(() => _expanded = !_expanded),
                  child: Padding(
                    padding: EdgeInsets.symmetric(vertical: AppSpace.s(4)),
                    child: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Text(
                          _expanded ? '근거 접기' : '추천 근거 보기',
                          style: const TextStyle(
                            fontSize: 10.5,
                            fontWeight: FontWeight.w600,
                            color: Color(0xFF7C3AED),
                          ),
                        ),
                        Icon(
                          _expanded ? Icons.expand_less : Icons.expand_more,
                          size: 14,
                          color: const Color(0xFF7C3AED),
                        ),
                      ],
                    ),
                  ),
                ),
              ),
              if (!_expanded && item.isFromServer && widget.onReview != null)
                _reviewButton(),
            ],
          ),
        ],
      ),
    );
  }
}

/// 추천 근거 상세. 점수가 어떻게 구성됐고 어떤 문장·기술·조건이 근거였는지 보여준다.
class _RecommendationRationale extends StatelessWidget {
  const _RecommendationRationale({required this.item});

  final JobRecommendation item;

  /// 하드 필터 문구에서 해당 조건의 결과를 찾는다. (통과 여부, 문구)
  (bool?, String?) _condition(List<String> keywords) {
    for (final text in item.passedConditions) {
      if (keywords.any(text.contains)) return (true, text);
    }
    for (final text in item.unknownConditions) {
      if (keywords.any(text.contains)) return (null, text);
    }
    return (null, null);
  }

  @override
  Widget build(BuildContext context) {
    final region = _condition(const ['근무지역', '전국 근무', '희망지역']);
    final employment = _condition(const ['고용형태']);
    final career = _condition(const ['경력']);
    final education = _condition(const ['학력']);
    final major = _condition(const ['전공']);
    final certification = _condition(const ['자격증']);
    final military = _condition(const ['병역']);
    final hasBuckets = [
      item.matchedRequired,
      item.unmatchedRequired,
      item.matchedPreferred,
      item.unmatchedPreferred,
      item.matchedTags,
      item.unmatchedTags,
    ].any((list) => list.isNotEmpty);

    return Container(
      padding: EdgeInsets.all(AppSpace.s(10)),
      decoration: BoxDecoration(
        color: AppColors.surfaceVariant.withValues(alpha: 0.7),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _AnalysisLabel('공고 조건', AppColors.textSecondary),
          _ConditionRow(
            label: '근무지역',
            value: item.region.isEmpty ? '미기재' : item.region,
            ok: region.$1,
            note: region.$2,
          ),
          _ConditionRow(
            label: '고용형태',
            value: item.employmentType ?? '미기재',
            ok: employment.$1,
            note: employment.$2,
          ),
          _ConditionRow(
            label: '경력',
            value: item.careerLabel,
            ok: career.$1,
            note: career.$2,
          ),
          _ConditionRow(
            label: '학력',
            value: item.education.isEmpty ? '미기재' : item.education,
            ok: education.$1,
            note: education.$2,
          ),
          if (item.requiredMajors.isNotEmpty)
            _ConditionRow(
              label: '전공',
              value: item.requiredMajors.join(', '),
              ok: major.$1,
              note: major.$2,
            ),
          if (item.requiredCertifications.isNotEmpty)
            _ConditionRow(
              label: '자격증',
              value: item.requiredCertifications.join(', '),
              ok: certification.$1,
              note: certification.$2,
            ),
          if (item.militaryRequired)
            _ConditionRow(
              label: '병역',
              value: '병역필 또는 면제',
              ok: military.$1,
              note: military.$2,
            ),
          SizedBox(height: AppSpace.s(8)),
          if (item.reasons.isNotEmpty) ...[
            _AnalysisLabel('추천 근거 — 이력서 문장 ↔ 공고 문장', AppColors.success),
            for (final reason in item.reasons) _ReasonTile(reason: reason),
            SizedBox(height: AppSpace.s(6)),
          ],
          if (item.concerns.isNotEmpty) ...[
            _AnalysisLabel(
              '공고 자격요건 중 이력서에서 확인되지 않는 것',
              AppColors.warning,
            ),
            for (final concern in item.concerns)
              Padding(
                padding: EdgeInsets.only(bottom: AppSpace.s(2)),
                child: Text(
                  '• $concern',
                  style: const TextStyle(fontSize: 10.5, height: 1.4),
                ),
              ),
            Text(
              '경험이 없다는 판단이 아닙니다. 경험이 있다면 이력서에 적어 주세요.',
              style: TextStyle(
                fontSize: 10,
                color: AppColors.textSecondary,
                height: 1.4,
              ),
            ),
            SizedBox(height: AppSpace.s(8)),
          ],
          if (hasBuckets) ...[
            _AnalysisLabel('기술 근거', AppColors.textSecondary),
            _SkillBucketRow(
              label: '필수 기술',
              matched: item.matchedRequired,
              unmatched: item.unmatchedRequired,
            ),
            _SkillBucketRow(
              label: '우대 기술',
              matched: item.matchedPreferred,
              unmatched: item.unmatchedPreferred,
            ),
            _SkillBucketRow(
              label: '기업 등록 태그',
              matched: item.matchedTags,
              unmatched: item.unmatchedTags,
            ),
          ] else if (item.matchedSkills.isNotEmpty) ...[
            _AnalysisLabel('일치한 기술', AppColors.success),
            _ChipRow(items: item.matchedSkills, color: AppColors.success),
          ],
          if (item.unmatchedSkills.isNotEmpty) ...[
            SizedBox(height: AppSpace.s(3)),
            Text(
              '회색 기술은 이력서에 적혀 있지 않다는 뜻이며, 경험이 없다고 판단한 것은 아닙니다. '
              '경험이 있다면 기술스택이나 프로젝트에 적어 주세요.',
              style: TextStyle(
                fontSize: 10,
                color: AppColors.textSecondary,
                height: 1.4,
              ),
            ),
          ],
          if (item.bodyIsImage) ...[
            SizedBox(height: AppSpace.s(8)),
            Text(
              '이 공고는 상세 내용이 이미지로만 올라와 있어 필수·우대 요건을 텍스트로 확인하지 못했습니다. '
              '기업이 등록 때 고른 기술 태그와 조건만으로 비교했으니 공고 원문을 직접 확인해 주세요.',
              style: TextStyle(
                fontSize: 10,
                color: AppColors.textSecondary,
                height: 1.4,
              ),
            ),
          ],
          if (item.embeddingRank case final rank?) ...[
            SizedBox(height: AppSpace.s(8)),
            Text(
              '자기소개서·프로젝트 문장과 공고 내용의 임베딩 유사도 $rank위로 순위에 반영됨',
              style: TextStyle(
                fontSize: 10,
                color: AppColors.textSecondary,
                height: 1.4,
              ),
            ),
          ],
        ],
      ),
    );
  }
}

/// 공고 조건 한 줄: 값과 희망 조건 대비 결과.
class _ConditionRow extends StatelessWidget {
  const _ConditionRow({
    required this.label,
    required this.value,
    required this.ok,
    required this.note,
  });

  final String label;
  final String value;

  /// true 통과, null 확인 필요(희망 조건 미입력 등), false 불일치.
  final bool? ok;
  final String? note;

  @override
  Widget build(BuildContext context) {
    final color = switch (ok) {
      true => AppColors.success,
      false => AppColors.error,
      null => AppColors.textHint,
    };
    final icon = switch (ok) {
      true => Icons.check_circle_outline,
      false => Icons.cancel_outlined,
      null => Icons.help_outline,
    };
    return Padding(
      padding: EdgeInsets.only(bottom: AppSpace.s(3)),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(
            width: 50,
            child: Text(
              label,
              style: TextStyle(
                fontSize: 10.5,
                color: AppColors.textSecondary,
              ),
            ),
          ),
          Expanded(
            child: Text(
              value,
              style: const TextStyle(
                fontSize: 10.5,
                fontWeight: FontWeight.w600,
              ),
            ),
          ),
          if (note != null) ...[
            Icon(icon, size: 12, color: color),
            SizedBox(width: AppSpace.s(3)),
            Flexible(
              child: Text(
                note!,
                style: TextStyle(fontSize: 10, color: color),
                overflow: TextOverflow.ellipsis,
              ),
            ),
          ],
        ],
      ),
    );
  }
}

/// 출처별 기술 근거 한 줄: 일치는 초록, 근거 없음은 회색으로 나란히 둔다.
class _SkillBucketRow extends StatelessWidget {
  const _SkillBucketRow({
    required this.label,
    required this.matched,
    required this.unmatched,
  });

  final String label;
  final List<String> matched;
  final List<String> unmatched;

  @override
  Widget build(BuildContext context) {
    final total = matched.length + unmatched.length;
    return Padding(
      padding: EdgeInsets.only(bottom: AppSpace.s(6)),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            total == 0
                ? '$label · 공고에 없음'
                : '$label ${matched.length}/$total 일치',
            style: const TextStyle(fontSize: 10.5, fontWeight: FontWeight.w600),
          ),
          if (total > 0) ...[
            SizedBox(height: AppSpace.s(3)),
            Wrap(
              spacing: 4,
              runSpacing: 4,
              children: [
                for (final text in matched)
                  _SkillChip(text: text, color: AppColors.success),
                for (final text in unmatched)
                  _SkillChip(text: text, color: AppColors.textHint),
              ],
            ),
          ],
        ],
      ),
    );
  }
}

class _SkillChip extends StatelessWidget {
  const _SkillChip({required this.text, required this.color});

  final String text;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: EdgeInsets.symmetric(
        horizontal: AppSpace.s(7),
        vertical: AppSpace.s(3),
      ),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(6),
      ),
      child: Text(
        text,
        style: TextStyle(
          fontSize: 10,
          color: color,
          fontWeight: FontWeight.w600,
        ),
      ),
    );
  }
}

class _ChipRow extends StatelessWidget {
  const _ChipRow({required this.items, required this.color});

  final List<String> items;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Wrap(
      spacing: 4,
      runSpacing: 4,
      children: [
        for (final text in items)
          Container(
            padding: EdgeInsets.symmetric(
              horizontal: AppSpace.s(7),
              vertical: AppSpace.s(3),
            ),
            decoration: BoxDecoration(
              color: color.withValues(alpha: 0.1),
              borderRadius: BorderRadius.circular(6),
            ),
            child: Text(
              text,
              style: TextStyle(
                fontSize: 10,
                color: color,
                fontWeight: FontWeight.w600,
              ),
            ),
          ),
      ],
    );
  }
}

class _Section extends StatelessWidget {
  const _Section({
    required this.title,
    required this.subtitle,
    required this.child,
  });

  final String title;
  final String subtitle;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          title,
          style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w700),
        ),
        if (subtitle.isNotEmpty) ...[
          SizedBox(height: AppSpace.s(3)),
          Text(
            subtitle,
            style: TextStyle(
              fontSize: 10,
              height: 1.35,
              color: AppColors.textSecondary,
            ),
          ),
        ],
        SizedBox(height: AppSpace.s(9)),
        child,
      ],
    );
  }
}

/// 맞춤 이력서에 연결된 공고를 읽어 오는 동안의 한 줄 안내.
class _LinkedJobLoadingLine extends StatelessWidget {
  const _LinkedJobLoadingLine();

  @override
  Widget build(BuildContext context) {
    return Row(
      key: const ValueKey('linked-job-loading'),
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        SizedBox(
          width: 14,
          height: 14,
          child: CircularProgressIndicator(
            strokeWidth: 2,
            color: AppColors.primary,
          ),
        ),
        SizedBox(width: AppSpace.s(8)),
        Text(
          '이 이력서와 연결된 공고를 불러오는 중이에요',
          style: TextStyle(fontSize: 12, color: AppColors.textSecondary),
        ),
      ],
    );
  }
}

class _ErrorCard extends StatelessWidget {
  const _ErrorCard({required this.message});

  final String message;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: EdgeInsets.all(AppSpace.s(10)),
      decoration: BoxDecoration(
        color: AppColors.error.withValues(alpha: 0.06),
        border: Border.all(color: AppColors.error.withValues(alpha: 0.25)),
        borderRadius: BorderRadius.circular(9),
      ),
      child: Row(
        children: [
          Icon(Icons.error_outline, size: 17, color: AppColors.error),
          SizedBox(width: AppSpace.s(7)),
          Expanded(child: Text(message, style: const TextStyle(fontSize: 11))),
        ],
      ),
    );
  }
}

/// Figma 시안의 "현재 분석 중인 이력서" 카드.
class _CurrentResumeCard extends StatelessWidget {
  const _CurrentResumeCard({
    required this.title,
    required this.content,
    required this.readiness,
    required this.analyzing,
  });

  final ResumeContent content;
  final String title;
  final ResumeReadiness readiness;
  final bool analyzing;

  @override
  Widget build(BuildContext context) {
    final ready = readiness.canRecommendJobs;
    final skillCount = content.techStack.where((item) => item.isFilled).length;
    final projectCount = content.projects.where((item) => item.isFilled).length;

    return Container(
      width: double.infinity,
      padding: EdgeInsets.all(AppSpace.s(20)),
      decoration: BoxDecoration(
        color: AppColors.tint(const Color(0xFFF7F6F4)),
        borderRadius: BorderRadius.circular(20),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      '현재 분석 중인 이력서',
                      style: TextStyle(
                        fontSize: 11,
                        color: AppColors.textSecondary,
                      ),
                    ),
                    SizedBox(height: AppSpace.s(5)),
                    Text(
                      title.trim().isEmpty ? '현재 작성 중인 이력서' : title.trim(),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(
                        fontSize: 15,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                  ],
                ),
              ),
              SizedBox(width: AppSpace.s(10)),
              Container(
                padding: EdgeInsets.symmetric(
                  horizontal: AppSpace.s(10),
                  vertical: AppSpace.s(5),
                ),
                decoration: BoxDecoration(
                  color: analyzing
                      ? AppColors.primaryLight
                      : ready
                      ? AppColors.tint(const Color(0xFFF0FDF4))
                      : AppColors.tint(const Color(0xFFFFF7ED)),
                  borderRadius: BorderRadius.circular(99),
                ),
                child: Text(
                  analyzing
                      ? '분석 중'
                      : ready
                      ? '준비 완료'
                      : '작성 필요',
                  style: TextStyle(
                    fontSize: 10,
                    fontWeight: FontWeight.w700,
                    color: analyzing
                        ? AppColors.primary
                        : ready
                        ? const Color(0xFF16A34A)
                        : const Color(0xFFEA580C),
                  ),
                ),
              ),
            ],
          ),
          SizedBox(height: AppSpace.s(16)),
          Text(
            '기술 $skillCount개  ·  프로젝트 $projectCount개',
            style: TextStyle(
              fontSize: 11,
              color: AppColors.textSecondary,
            ),
          ),
        ],
      ),
    );
  }
}

class _AnalysisLabel extends StatelessWidget {
  const _AnalysisLabel(this.text, this.color);

  final String text;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.only(bottom: AppSpace.s(4)),
      child: Text(
        text,
        style: TextStyle(
          fontSize: 11,
          fontWeight: FontWeight.w700,
          color: color,
        ),
      ),
    );
  }
}

/// 챗봇으로 채용공고를 찾는 화면.
class _ChatView extends StatefulWidget {
  const _ChatView({
    required this.messages,
    required this.controller,
    required this.onSend,
    required this.onSuggestion,
    required this.busy,
    required this.askingAbout,
    required this.onStopAsking,
    required this.onAskAbout,
    required this.onOpenDetail,
    this.busyLabels = const [],
  });

  final List<_ChatMessage> messages;
  final TextEditingController controller;
  final VoidCallback onSend;
  final ValueChanged<String> onSuggestion;

  /// 서버 응답을 기다리는 중. 그동안 같은 질문을 다시 보내지 못하게 한다.
  final bool busy;

  /// 공고 하나를 놓고 묻는 중이면 그 공고. 무엇에 대해 묻는 중인지 늘 보여야 한다.
  final JobChatJob? askingAbout;
  final VoidCallback onStopAsking;
  final ValueChanged<JobChatJob> onAskAbout;

  /// 근거 전체를 보러 코치 화면으로 넘어간다.
  final VoidCallback onOpenDetail;

  /// 무엇을 기다리는 중인지. 차례대로 넘어간다. 비어 있으면 기본 문구를 쓴다.
  final List<String> busyLabels;

  @override
  State<_ChatView> createState() => _ChatViewState();
}

class _ChatViewState extends State<_ChatView> {
  final ScrollController _scroll = ScrollController();

  @override
  void dispose() {
    _scroll.dispose();
    super.dispose();
  }

  @override
  void didUpdateWidget(covariant _ChatView oldWidget) {
    super.didUpdateWidget(oldWidget);
    // 답이 왔는데 화면은 그대로면 사용자가 직접 내려야 한다. 말이 길수록 어디까지
    // 왔는지도 모른다. 새 말이 붙을 때마다 아래로 따라간다.
    if (widget.messages.length != oldWidget.messages.length ||
        (widget.busy && !oldWidget.busy)) {
      _scrollToBottom();
    }
  }

  /// 프레임이 그려진 뒤에 내린다. 지금 재면 새 말풍선의 높이가 아직 없다.
  void _scrollToBottom() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!_scroll.hasClients) return;
      _scroll.animateTo(
        _scroll.position.maxScrollExtent,
        duration: const Duration(milliseconds: 250),
        curve: Curves.easeOut,
      );
    });
  }

  @override
  Widget build(BuildContext context) {
    final messages = widget.messages;
    final busy = widget.busy;
    final onAskAbout = widget.onAskAbout;
    final onOpenDetail = widget.onOpenDetail;
    final onSuggestion = widget.onSuggestion;
    final busyLabels = widget.busyLabels;
    final askingAbout = widget.askingAbout;
    final onStopAsking = widget.onStopAsking;
    final controller = widget.controller;
    final onSend = widget.onSend;
    return Column(
      children: [
        Expanded(
          child: ListView.builder(
            controller: _scroll,
            padding: EdgeInsets.all(AppSpace.s(14)),
            // 기다리는 동안에는 대화 끝에 코치가 입력 중인 말풍선을 하나 더 둔다.
            itemCount: messages.length + (busy ? 1 : 0),
            itemBuilder: (context, index) => index == messages.length
                ? _CoachTyping(
                    labels: busyLabels.isEmpty
                        ? const ['답을 찾는 중…']
                        : busyLabels,
                  )
                : _ChatBubble(
                    message: messages[index],
                    onAskAbout: busy ? null : onAskAbout,
                    // 넘어가기는 마지막 답에서만. 지나간 답의 버튼을 누르면 그때 물어본
                    // 것이 아니라 지금 이력서로 돌아 혼란스럽다.
                    onOpenDetail: busy ? null : onOpenDetail,
                    // 제안은 마지막 답에서만 누를 수 있다. 지나간 답의 제안을 누르면 그때가
                    // 아니라 지금 조건에 붙어 엉뚱한 결과가 나온다.
                    onSuggestion: index == messages.length - 1 && !busy
                        ? onSuggestion
                        : null,
                  ),
          ),
        ),
        // 무엇에 대해 묻는 중인지. 이게 없으면 짧은 말이 어디로 가는지 알 수 없다.
        if (askingAbout case final job?)
          Container(
            padding: EdgeInsets.fromLTRB(
              AppSpace.s(12),
              AppSpace.s(8),
              AppSpace.s(6),
              AppSpace.s(8),
            ),
            color: AppColors.primaryLight.withValues(alpha: 0.4),
            child: Row(
              children: [
                Icon(
                  Icons.help_outline,
                  size: 14,
                  color: AppColors.primary,
                ),
                SizedBox(width: AppSpace.s(6)),
                Expanded(
                  child: Text(
                    '"${job.title}"에 대해 묻는 중',
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                      fontSize: 11,
                      color: AppColors.primary,
                    ),
                  ),
                ),
                IconButton(
                  tooltip: '그만 묻기',
                  onPressed: onStopAsking,
                  icon: const Icon(Icons.close, size: 14),
                  visualDensity: VisualDensity.compact,
                ),
              ],
            ),
          ),
        Container(
          padding: EdgeInsets.fromLTRB(
            AppSpace.s(12),
            AppSpace.s(8),
            AppSpace.s(12),
            AppSpace.s(12),
          ),
          decoration: BoxDecoration(
            border: Border(top: BorderSide(color: AppColors.border)),
          ),
          child: Row(
            children: [
              Expanded(
                child: TextField(
                  controller: controller,
                  style: const TextStyle(fontSize: 12),
                  decoration: InputDecoration(
                    hintText: askingAbout == null
                        ? '공고를 찾거나, 채용에 대해 물어보세요'
                        : '이 공고에 대해 물어보세요',
                    hintStyle: const TextStyle(fontSize: 12),
                    isDense: true,
                    contentPadding: EdgeInsets.symmetric(
                      horizontal: AppSpace.s(12),
                      vertical: AppSpace.s(10),
                    ),
                  ),
                  onSubmitted: busy ? null : (_) => onSend(),
                ),
              ),
              SizedBox(width: AppSpace.s(6)),
              IconButton(
                tooltip: '보내기',
                onPressed: busy ? null : onSend,
                icon: const Icon(Icons.send, size: 18),
              ),
            ],
          ),
        ),
      ],
    );
  }
}

class _ChatBubble extends StatelessWidget {
  const _ChatBubble({
    required this.message,
    this.onSuggestion,
    this.onAskAbout,
    this.onOpenDetail,
  });

  final _ChatMessage message;
  final ValueChanged<String>? onSuggestion;
  final ValueChanged<JobChatJob>? onAskAbout;
  final VoidCallback? onOpenDetail;

  @override
  Widget build(BuildContext context) {
    final bubble = Container(
      margin: EdgeInsets.only(bottom: AppSpace.s(10)),
      padding: EdgeInsets.fromLTRB(
        AppSpace.s(12),
        AppSpace.s(10),
        AppSpace.s(12),
        AppSpace.s(12),
      ),
      constraints: const BoxConstraints(maxWidth: 300),
      // 답이 길면 말풍선이 배경에 묻혀 글자만 흩어져 보였다. 배경을 옅게라도
      // 깔고 테두리를 둘러야 "여기까지가 한 답"이라는 게 보인다.
      decoration: BoxDecoration(
        color: message.isUser
            ? AppColors.primaryLight
            : AppColors.surfaceVariant,
        borderRadius: BorderRadius.circular(10),
        border: message.isUser ? null : Border.all(color: AppColors.border),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _ChatText(message.text),
          // 이력서를 읽고 고른 공고. 적합도와 근거가 붙는다.
          for (final job in message.recommendations) ...[
            SizedBox(height: AppSpace.s(8)),
            _ChatRecommendCard(job: job),
          ],
          if (message.recommendations.isNotEmpty && onOpenDetail != null) ...[
            SizedBox(height: AppSpace.s(8)),
            InkWell(
              onTap: onOpenDetail,
              borderRadius: BorderRadius.circular(4),
              child: Padding(
                padding: EdgeInsets.symmetric(vertical: AppSpace.s(2)),
                child: Text(
                  '근거 전체 보기 →',
                  style: TextStyle(
                    fontSize: 11,
                    fontWeight: FontWeight.w600,
                    color: Color(0xFF7C3AED),
                  ),
                ),
              ),
            ),
          ],
          // 질문에 답한 경우 목록은 찾아 준 결과가 아니라 **답의 근거**다.
          // 그렇게 적어 두지 않으면 "이게 추천인가?"로 읽힌다.
          if (message.mode == '질문' && message.jobs.isNotEmpty) ...[
            SizedBox(height: AppSpace.s(8)),
            Text(
              '이 숫자를 센 공고들이에요',
              style: TextStyle(fontSize: 10.5, color: AppColors.textHint),
            ),
          ],
          for (final job in message.jobs) ...[
            SizedBox(height: AppSpace.s(8)),
            _ChatJobCard(
              job: job,
              onAsk: onAskAbout == null ? null : () => onAskAbout!(job),
            ),
          ],
          if (message.suggestions.isNotEmpty && onSuggestion != null) ...[
            SizedBox(height: AppSpace.s(8)),
            // 제안은 문장이라 한 줄에 안 들어간다. Chip은 높이가 한 줄로 고정되어
            // 폭을 좁혀 줘도 글자가 잘렸다. 줄이 늘어나는 만큼 키가 크는 버튼으로
            // 바꾼다. 나란히 놓을 것도 아니어서 한 줄에 하나씩 세로로 쌓는다.
            for (final suggestion in message.suggestions) ...[
              SizedBox(height: AppSpace.s(6)),
              _SuggestionButton(
                text: suggestion,
                onTap: () => onSuggestion!(suggestion),
              ),
            ],
          ],
        ],
      ),
    );

    if (message.isUser) {
      return Align(alignment: Alignment.centerRight, child: bubble);
    }
    // 코치의 답 옆에는 학생 챗봇처럼 머리를 둔다. 누가 말하는지 보이게.
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const SizedBox.square(
          dimension: 40,
          child: Center(child: RobotHeadIcon(size: 36, inverted: true)),
        ),
        SizedBox(width: AppSpace.s(7)),
        Flexible(child: bubble),
      ],
    );
  }
}

/// 코치가 답을 쓰는 중. 학생 챗봇과 같은 물결 점을 코치 말풍선 안에 둔다.
///
/// 예전에는 입력창 위에 작은 원형 표시만 돌아, 대화와 떨어져서 누가 무엇을
/// 하는 중인지 잘 보이지 않았다. 답이 올 자리에서 기다리게 한다.
class _CoachTyping extends StatefulWidget {
  const _CoachTyping({required this.labels});

  /// 차례대로 보여 줄 말. 마지막 말에서 멈춘다.
  final List<String> labels;

  /// 다음 말로 넘어가는 간격. 추천이 11초쯤 걸려 세 단계가 고르게 지나간다.
  static const step = Duration(milliseconds: 3200);

  @override
  State<_CoachTyping> createState() => _CoachTypingState();
}

class _CoachTypingState extends State<_CoachTyping>
    with SingleTickerProviderStateMixin {
  late final _wave = AnimationController(
    vsync: this,
    duration: const Duration(milliseconds: 900),
  );
  Timer? _next;
  var _index = 0;

  @override
  void initState() {
    super.initState();
    _schedule();
  }

  @override
  void didUpdateWidget(_CoachTyping oldWidget) {
    super.didUpdateWidget(oldWidget);
    // 질문 답을 받은 뒤 이어서 추천을 돌리면 같은 자리에 새 말 묶음이 온다.
    if (widget.labels.join('|') != oldWidget.labels.join('|')) {
      _index = 0;
      _schedule();
    }
  }

  void _schedule() {
    _next?.cancel();
    if (_index >= widget.labels.length - 1) return;
    _next = Timer(_CoachTyping.step, () {
      if (!mounted) return;
      setState(() => _index++);
      _schedule();
    });
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    // 움직임 줄이기를 켠 사람에게는 점을 멈춰 둔다.
    if (MediaQuery.disableAnimationsOf(context)) {
      _wave.stop();
    } else if (!_wave.isAnimating) {
      _wave.repeat();
    }
  }

  @override
  void dispose() {
    _next?.cancel();
    _wave.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const SizedBox.square(
          dimension: 40,
          child: Center(child: RobotHeadIcon(size: 36, inverted: true)),
        ),
        SizedBox(width: AppSpace.s(7)),
        Flexible(
          child: Container(
            margin: EdgeInsets.only(bottom: AppSpace.s(10)),
            padding: EdgeInsets.symmetric(
              horizontal: AppSpace.s(12),
              vertical: AppSpace.s(11),
            ),
            decoration: BoxDecoration(
              color: AppColors.surfaceVariant,
              borderRadius: BorderRadius.circular(10),
              border: Border.all(color: AppColors.border),
            ),
            child: Semantics(
              liveRegion: true,
              label: '커리어 코치 응답 대기 중',
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  AnimatedBuilder(
                    animation: _wave,
                    builder: (context, _) => Row(
                      mainAxisSize: MainAxisSize.min,
                      children: List.generate(3, (i) {
                        final wave = math.sin(
                          _wave.value * math.pi * 2 - i * 0.8,
                        );
                        return Transform.translate(
                          offset: Offset(0, -3 * wave),
                          child: Container(
                            width: 6,
                            height: 6,
                            margin: const EdgeInsets.symmetric(horizontal: 2.5),
                            decoration: BoxDecoration(
                              color: AppColors.primary,
                              shape: BoxShape.circle,
                            ),
                          ),
                        );
                      }),
                    ),
                  ),
                  SizedBox(width: AppSpace.s(10)),
                  Flexible(
                    child: AnimatedSwitcher(
                      duration: const Duration(milliseconds: 220),
                      child: Text(
                        widget.labels[math.min(
                          _index,
                          widget.labels.length - 1,
                        )],
                        key: ValueKey(_index),
                        style: TextStyle(
                          fontSize: 11,
                          color: AppColors.textSecondary,
                        ),
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
      ],
    );
  }
}

/// 눌러 보낼 수 있는 제안 한 줄. 문장이 길면 줄을 바꾸고 키가 커진다.
class _SuggestionButton extends StatelessWidget {
  const _SuggestionButton({required this.text, required this.onTap});

  final String text;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(8),
      child: Container(
        width: double.infinity,
        padding: EdgeInsets.symmetric(
          horizontal: AppSpace.s(10),
          vertical: AppSpace.s(7),
        ),
        decoration: BoxDecoration(
          color: AppColors.primaryLight.withValues(alpha: 0.55),
          borderRadius: BorderRadius.circular(8),
          border: Border.all(color: AppColors.border),
        ),
        child: Text(
          text,
          style: TextStyle(
            fontSize: 11,
            height: 1.35,
            color: AppColors.primary,
          ),
        ),
      ),
    );
  }
}

/// 답을 서식대로 그린다. 굵게와 항목 줄만 읽는다(`chat_text.dart`).
class _ChatText extends StatelessWidget {
  const _ChatText(this.text);

  final String text;

  @override
  Widget build(BuildContext context) {
    final blocks = parseChatText(text);
    if (blocks.isEmpty) return const SizedBox.shrink();
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        for (var i = 0; i < blocks.length; i++) ...[
          if (i > 0) SizedBox(height: AppSpace.s(6)),
          if (blocks[i].bullet)
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Padding(
                  padding: EdgeInsets.only(right: AppSpace.s(6)),
                  child: Text('•', style: TextStyle(fontSize: 12, height: 1.5)),
                ),
                Expanded(child: _line(blocks[i])),
              ],
            )
          else
            _line(blocks[i]),
        ],
      ],
    );
  }

  Widget _line(ChatBlock block) => Text.rich(
    TextSpan(
      children: [
        for (final span in block.spans)
          TextSpan(
            text: span.text,
            style: span.bold
                ? const TextStyle(fontWeight: FontWeight.w700)
                : null,
          ),
      ],
    ),
    style: const TextStyle(fontSize: 12, height: 1.5),
  );
}

/// 이력서를 읽고 고른 공고 한 건. 조건 검색 카드와 달리 **왜 맞는지**를 함께 보여준다.
class _ChatRecommendCard extends StatelessWidget {
  const _ChatRecommendCard({required this.job});

  final JobRecommendation job;

  Future<void> _open() async {
    final uri = Uri.tryParse(job.sourceUrl);
    if (uri != null && (uri.scheme == 'http' || uri.scheme == 'https')) {
      await launchUrl(uri, mode: LaunchMode.externalApplication);
    }
  }

  @override
  Widget build(BuildContext context) {
    final hasLink = job.sourceUrl.startsWith('http');
    // 근거 한 줄. 주장(claim)만 보여주고, 인용 원문은 코치 화면에 있다.
    final reason = job.reasons.isNotEmpty
        ? job.reasons.first.claim
        : job.evidence.join(' · ');
    return InkWell(
      onTap: hasLink ? _open : null,
      borderRadius: BorderRadius.circular(8),
      child: Container(
        padding: EdgeInsets.all(AppSpace.s(9)),
        decoration: BoxDecoration(
          color: AppColors.surface,
          border: Border.all(color: AppColors.border),
          borderRadius: BorderRadius.circular(8),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              job.company,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(
                fontSize: 10.5,
                color: AppColors.textSecondary,
              ),
            ),
            SizedBox(height: AppSpace.s(3)),
            Text(
              job.title,
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
              style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w600),
            ),
            if (job.region.isNotEmpty || job.careerText.isNotEmpty) ...[
              SizedBox(height: AppSpace.s(2)),
              Text(
                [
                  job.region,
                  job.careerText,
                ].where((v) => v.isNotEmpty).join(' · '),
                style: TextStyle(fontSize: 10, color: AppColors.textHint),
              ),
            ],
            // 왜 맞는지 한 줄. 전체 근거는 코치 화면에 있다.
            if (reason.isNotEmpty) ...[
              SizedBox(height: AppSpace.s(5)),
              Text(
                reason,
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
                style: TextStyle(
                  fontSize: 10.5,
                  height: 1.4,
                  color: AppColors.textSecondary,
                ),
              ),
            ],
            if (hasLink) ...[
              SizedBox(height: AppSpace.s(5)),
              const Text(
                '공고 보기 →',
                style: TextStyle(
                  fontSize: 10.5,
                  fontWeight: FontWeight.w600,
                  color: Color(0xFF7C3AED),
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }
}

class _ChatJobCard extends StatelessWidget {
  const _ChatJobCard({required this.job, this.onAsk});

  final JobChatJob job;

  /// 이 공고를 놓고 물어보기. 목록에서 바로 이어 물을 수 있어야 한다.
  final VoidCallback? onAsk;

  Future<void> _open() async {
    final uri = Uri.tryParse(job.sourceUrl);
    if (uri != null && (uri.scheme == 'http' || uri.scheme == 'https')) {
      await launchUrl(uri, mode: LaunchMode.externalApplication);
    }
  }

  @override
  Widget build(BuildContext context) {
    final skills = job.techStack;
    final hasLink = job.sourceUrl.startsWith('http');
    return InkWell(
      onTap: hasLink ? _open : null,
      borderRadius: BorderRadius.circular(8),
      child: Container(
        padding: EdgeInsets.all(AppSpace.s(9)),
        decoration: BoxDecoration(
          color: AppColors.surface,
          border: Border.all(color: AppColors.border),
          borderRadius: BorderRadius.circular(8),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              job.title,
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
              style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w600),
            ),
            SizedBox(height: AppSpace.s(3)),
            Text(
              '${job.company} · ${job.region} · ${job.career}',
              style: TextStyle(
                fontSize: 10.5,
                color: AppColors.textSecondary,
              ),
            ),
            if (job.deadline case final deadline?)
              Text(
                '마감 ${_deadlineDate(deadline)}',
                style: TextStyle(fontSize: 10, color: AppColors.textHint),
              ),
            if (skills.isNotEmpty) ...[
              SizedBox(height: AppSpace.s(5)),
              Text(
                skills.take(5).join(' · '),
                style: TextStyle(
                  fontSize: 10.5,
                  color: AppColors.primary,
                ),
              ),
            ],
            SizedBox(height: AppSpace.s(5)),
            Row(
              children: [
                if (hasLink)
                  const Text(
                    '공고 보기 →',
                    style: TextStyle(
                      fontSize: 10.5,
                      fontWeight: FontWeight.w600,
                      color: Color(0xFF7C3AED),
                    ),
                  ),
                const Spacer(),
                if (onAsk != null)
                  InkWell(
                    onTap: onAsk,
                    borderRadius: BorderRadius.circular(4),
                    child: Padding(
                      padding: EdgeInsets.symmetric(
                        horizontal: AppSpace.s(4),
                        vertical: AppSpace.s(2),
                      ),
                      child: Text(
                        '이 공고 물어보기',
                        style: TextStyle(
                          fontSize: 10.5,
                          fontWeight: FontWeight.w600,
                          color: AppColors.primary,
                        ),
                      ),
                    ),
                  ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

/// 서버가 이력서에서 만든 검색 질의문. 어떤 기준으로 찾았는지 사용자가 볼 수 있게 한다.
class _ServerQueryNote extends StatelessWidget {
  const _ServerQueryNote({
    required this.searchQuery,
    required this.profileSummary,
  });

  final String searchQuery;
  final String profileSummary;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: EdgeInsets.all(AppSpace.s(9)),
      decoration: BoxDecoration(
        color: AppColors.primaryLight.withValues(alpha: 0.35),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            '이력서에서 뽑은 검색 기준',
            style: TextStyle(
              fontSize: 10,
              fontWeight: FontWeight.w700,
              color: AppColors.textSecondary,
            ),
          ),
          SizedBox(height: AppSpace.s(3)),
          Text(
            searchQuery,
            style: const TextStyle(fontSize: 10.5, height: 1.4),
          ),
          if (profileSummary.isNotEmpty) ...[
            SizedBox(height: AppSpace.s(3)),
            Text(
              profileSummary,
              style: TextStyle(
                fontSize: 10,
                color: AppColors.textSecondary,
                height: 1.4,
              ),
            ),
          ],
        ],
      ),
    );
  }
}

/// 추천 근거 하나. 주장 한 줄과 그 근거인 이력서·공고 원문 인용.
class _ReasonTile extends StatelessWidget {
  const _ReasonTile({required this.reason});

  final RecommendReason reason;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.only(bottom: AppSpace.s(6)),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            reason.claim,
            style: const TextStyle(
              fontSize: 10.5,
              fontWeight: FontWeight.w600,
              height: 1.35,
            ),
          ),
          if (reason.resumeQuote.isNotEmpty)
            _QuoteLine(
              label: '이력서',
              text: reason.resumeQuote,
              color: AppColors.success,
            ),
          if (reason.jobQuote.isNotEmpty)
            _QuoteLine(
              label: '공고',
              text: reason.jobQuote,
              color: AppColors.info,
            ),
        ],
      ),
    );
  }
}

class _QuoteLine extends StatelessWidget {
  const _QuoteLine({
    required this.label,
    required this.text,
    required this.color,
  });

  final String label;
  final String text;
  final Color color;

  @override
  Widget build(BuildContext context) {
    // 공고 원문 인용은 HTML/문단 경계에서 줄바꿈을 포함할 수 있다. 근거 값 자체는
    // 보존하고, 카드에서는 라벨 뒤에 자연스럽게 이어지도록 표시만 한 줄로 정리한다.
    final displayText = text.replaceAll(RegExp(r'\s+'), ' ').trim();
    if (displayText.isEmpty) return const SizedBox.shrink();

    return Padding(
      padding: EdgeInsets.only(top: AppSpace.s(2), left: AppSpace.s(4)),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(
            width: 34,
            child: Text(
              label,
              style: TextStyle(
                fontSize: 9.5,
                color: color,
                fontWeight: FontWeight.w600,
              ),
            ),
          ),
          Expanded(
            child: Text(
              '“$displayText”',
              style: TextStyle(
                fontSize: 10,
                color: AppColors.textSecondary,
                height: 1.35,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

/// 마감은 날짜까지만 보여준다. 서버는 `2026-10-08T23:59:59+09:00` 처럼 시각과
/// 시간대를 붙여 주는데, 마감은 그 날 하루가 통째로 남았느냐의 문제라 뒤쪽은
/// 읽는 사람에게 쓸모가 없다. 시간대를 옮기지 않고 앞 열 글자만 쓴다 —
/// 한국 공고의 마감일은 한국 날짜 그대로 보여야 한다.
String _deadlineDate(String value) {
  final date = RegExp(r'^\d{4}-\d{2}-\d{2}').stringMatch(value);
  return date ?? value;
}
