import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../../../core/constants/app_constants.dart';
import '../../../core/routing/route_paths.dart';
import '../../../core/theme/app_colors.dart';
import '../../../core/widgets/loading_widgets.dart';
import '../../../shared/models/resume_content.dart';
import '../../../shared/models/resume_model.dart';
import '../../../shared/providers/cohort_providers.dart';
import '../../../shared/providers/lms_providers.dart';
import '../../auth/providers/auth_providers.dart';
import '../data/basic_info_prefill.dart';
import '../ai_coach/presentation/ai_job_coach_panel.dart';
import '../services/resume_pdf_exporter.dart';
import 'widgets/feedback_bell.dart';
import 'widgets/resume_edit_feedback_panel.dart';
import 'widgets/section_feedback_thread.dart';
import 'widgets/resume_section_nav.dart';
import 'widgets/tech_stack_editor.dart';
import '../../../core/theme/app_space.dart';

enum _ResumeViewMode { edit, doc }

/// 이력서 작성/편집/미리보기 페이지
class ResumeEditScreen extends ConsumerStatefulWidget {
  const ResumeEditScreen({
    super.key,
    required this.resumeId,
    this.initialSection,
    this.cohortId,
    this.openFeedback = false,
  });

  final String resumeId;
  final String? initialSection;
  final String? cohortId;

  /// 목록의 「읽으러 가기」로 들어왔나. 그러면 종을 펼친 채로 연다.
  final bool openFeedback;

  @override
  ConsumerState<ResumeEditScreen> createState() => _ResumeEditScreenState();
}

class _ResumeEditScreenState extends ConsumerState<ResumeEditScreen> {
  _ResumeViewMode _viewMode = _ResumeViewMode.edit;
  bool _isSaving = false;
  bool _dirty = false;
  bool _showAiCoach = false;
  bool _coachVisibilityInitialized = false;

  static const _coachVisibilityPreference = 'resume_ai_coach_open';

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (_coachVisibilityInitialized) return;
    _coachVisibilityInitialized = true;
    final wide = MediaQuery.sizeOf(context).width >= 1000;
    // 넓은 편집 화면에서는 코치를 기본으로 열고, 좁은 화면에서는 본문을 먼저 보인다.
    _showAiCoach = wide;
    if (wide) unawaited(_restoreCoachVisibility());
  }

  Future<void> _restoreCoachVisibility() async {
    final preferences = await SharedPreferences.getInstance();
    final saved = preferences.getBool(_coachVisibilityPreference);
    if (!mounted || saved == null) return;
    setState(() => _showAiCoach = saved);
  }

  void _setCoachVisible(bool visible) {
    if (_showAiCoach == visible) return;
    setState(() => _showAiCoach = visible);
    unawaited(_saveCoachVisibility(visible));
  }

  Future<void> _saveCoachVisibility(bool visible) async {
    final preferences = await SharedPreferences.getInstance();
    await preferences.setBool(_coachVisibilityPreference, visible);
  }

  /// 화면에 들어왔을 때 이미 있던 피드백의 id. 이 뒤에 온 것만 배너로 알린다.
  /// 들어올 때마다 알리면 잔소리가 된다.
  ///
  /// 건수만 적어 두면 **내가 단 답글까지** 새 피드백으로 세어져, 답글을 쓰는 족족
  /// "새 피드백 1건이 도착했습니다"가 떴다. 답글도 같은 곳에 쌓이기 때문이다.
  /// id를 적어 두고 글쓴이를 보면 내 것과 남의 것을 가릴 수 있다.
  Set<String>? _feedbackIdsOnOpen;

  /// 배너를 닫았나. 닫아도 배지는 그대로다 — 읽은 것이 아니기 때문이다.
  bool _bannerDismissed = false;

  /// 댓글을 펼쳐 둔 항목. 종에서 넘어오면 그 항목이 여기 들어간다.
  final Set<String> _openThreads = <String>{};

  /// 오른쪽 패널 너비. 왼쪽 가장자리를 끌어 바꾼다.
  /// 최소값은 첨삭 브랜치 쪽을 따른다 — 패널이 280이면 첨삭 대화가 접힌다.
  static const double _panelMinWidth = 360;
  static const double _panelDefaultWidth = 420;
  static const double _reviewPanelMinWidth = 500;
  static const double _reviewPanelDefaultWidth = 560;

  /// 이력서 본문에 남겨 둘 최소 폭. 이보다 좁아지면 입력칸이 읽기 어려워진다.
  static const double _minResumeWidth = 560;

  /// 좁은 화면에서 아래에 붙는 코치 패널. 넓은 화면의 좌우 조절과 같은 방식으로
  /// 위아래로 끌어 높이를 바꾼다.
  static const double _panelMinHeight = 200;
  static const double _panelDefaultHeight = 430;
  static const double _minResumeHeight = 200;

  /// 손잡이가 차지하는 폭. 보이는 선은 1px이지만 잡히는 폭은 이만큼이다.
  static const double _handleWidth = 28;

  /// 너비만 따로 들고 있는다. `setState`로 두면 끌 때마다 이력서 화면 전체를
  /// 다시 그린다 — 입력칸 수십 개짜리 화면을 초당 60번 다시 만들어 눈에 띄게 버벅인다.
  /// 알림값으로 두면 아래의 `ValueListenableBuilder` 안쪽만 다시 그린다.
  final ValueNotifier<double> _panelWidth = ValueNotifier<double>(
    _panelDefaultWidth,
  );

  /// 좁은 화면에서의 패널 높이. 너비와 같은 이유로 알림값이다.
  final ValueNotifier<double> _panelHeight = ValueNotifier<double>(
    _panelDefaultHeight,
  );

  /// 끌기를 시작한 순간의 너비·높이. 커서까지의 거리를 여기서 뺀다.
  double? _dragStartWidth;
  double? _dragStartHeight;

  /// 타이핑이 멎은 뒤 파생 표시를 따라잡게 하는 타이머.
  Timer? _derivedRefresh;

  /// 마지막으로 그린 파생 값의 지문. [_derivedSignature] 참고.
  String? _lastDerived;

  /// 닫혀 있는 동안 다시 만들지 않으려고 들고 있는 AI 코치 위젯.
  Widget? _coachPanel;

  /// AI 코치가 트리의 어느 자리에 있든 같은 것으로 알아보게 하는 열쇠.
  ///
  /// 창을 좁히면 좌우 배치가 상하 배치로 바뀌면서 패널이 `Row` 밑에서 `Column` 밑으로
  /// 옮겨 간다. 열쇠가 없으면 Flutter가 다른 위젯으로 보고 상태를 새로 만들어, 받아 둔
  /// 맞춤 공고와 대화가 사라진다. 전역 열쇠는 한 프레임 안에서 자리를 옮겨도 상태를
  /// 그대로 들고 간다.
  final GlobalKey _coachKey = GlobalKey();

  String _title = '';
  ResumeContent _content = ResumeContent.empty();
  bool _initialized = false;
  bool _pendingInitialScroll = false;
  bool _profilePrefillTried = false;
  bool _reviewPanelWidthInitialized = false;
  bool _programmaticSectionScroll = false;
  bool _sectionSyncScheduled = false;

  late final ScrollController _scrollController;
  late final Map<String, GlobalKey> _sectionKeys;
  String? _selectedSection;

  /// 이 이력서를 검토하는 사람인가(강사·관리자). 관리자만 보던 것을 넓혔다 —
  /// 강사는 관리자가 아니라 학생용 화면을 받았고, 남의 이력서에 저장을
  /// 시도해 'permission-denied' 가 났다.
  bool _isReviewer = false;
  ResumeModel? _resume;

  @override
  void initState() {
    super.initState();
    _scrollController = ScrollController();
    _scrollController.addListener(_syncReviewerSectionFromScroll);
    _sectionKeys = {
      for (final k in AppConstants.resumeSections) k: GlobalKey(),
    };
    _selectedSection = widget.initialSection;
    _pendingInitialScroll = widget.initialSection != null;
    if (widget.cohortId != null) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        selectCohort(ref, widget.cohortId!);
      });
    }
  }

  @override
  void dispose() {
    _derivedRefresh?.cancel();
    _scrollController.removeListener(_syncReviewerSectionFromScroll);
    _scrollController.dispose();
    _panelWidth.dispose();
    _panelHeight.dispose();
    super.dispose();
  }

  void _initFromResume(ResumeModel resume) {
    if (_initialized) return;
    _title = resume.title;
    _content = resume.content;
    _initialized = true;
    // 검토자는 읽는 사람이라 문서 모드로 연다. 승인된 이력서라도 본인은 편집 모드다.
    // 학생은 피드백을 요청한 뒤에도 같은 화면(오른쪽 AI 코치, 항목 밑 댓글)을 쓴다. 한때 피드백 요청
    // 상태면 학생에게도 검토자용 오른쪽 패널을 띄웠는데, 학생 화면은 댓글형을 유지하기로 했다(2026-09-15).
    if (ref.read(canReviewResumesProvider)) {
      _viewMode = _ResumeViewMode.doc;
    }
    if (_pendingInitialScroll && widget.initialSection != null) {
      _pendingInitialScroll = false;
      WidgetsBinding.instance.addPostFrameCallback((_) {
        _scrollToSection(widget.initialSection!);
      });
    }
    // 화면을 열었다고 읽은 것이 아니다. 예전에는 여기서 전부 읽음으로 넘겼는데,
    // 그러면 배지가 사라진 뒤에야 무슨 말이 있었는지 찾게 된다. 이제는 전문을 연
    // 항목만 읽음이 된다(FeedbackBell).
    //
    // 열어 둔 사이에 새로 도착한 것만 배너로 알린다. 기준이 되는 목록은 스트림이
    // 도착한 뒤에야 알 수 있으므로 배너를 그릴 때 한 번만 적어 둔다.
  }

  /// 승인된 뒤에도 학생은 고칠 수 있다. 승인은 "더는 손대지 말라"가 아니라
  /// "여기까지 봤다"는 표시다. 회사마다 이력서를 손보는 것이 정상이다.
  bool _isReadOnly({required bool isReviewer, required ResumeModel resume}) =>
      isReviewer || _viewMode == _ResumeViewMode.doc;

  /// 마이페이지 프로필로 기본정보의 빈 칸을 채운다. 학생 본인이 편집할 수 있는
  /// 이력서에서만 동작하고, 이미 적힌 값은 건드리지 않는다.
  ///
  /// [announce]가 true면 채운 항목을 스낵바로 알린다(첫 로드). 프로필 스트림이
  /// 아직 안 왔으면 조용히 건너뛰고, 기본정보 섹션의 버튼으로 다시 시도할 수 있다.
  bool _prefillBasicInfoFromProfile(
    ResumeModel resume, {
    required bool announce,
  }) {
    if (ref.read(canReviewResumesProvider)) return false;
    final user = ref.read(currentUserProvider).value;
    if (user == null) return false;
    final result = prefillBasicInfoFromProfile(_content.basicInfo, user);
    if (!result.changed) return false;
    _content = _content.copyWith(basicInfo: result.info);
    _dirty = true;
    if (announce) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (!mounted) return;
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(
              '마이페이지 정보로 ${result.filledLabels.join(', ')}을(를) 채웠습니다. 저장하면 반영됩니다.',
            ),
          ),
        );
      });
    }
    return true;
  }

  /// 이력서 내용을 갈아 끼운다. **글자 수정에는 화면을 다시 만들지 않는다.**
  ///
  /// 입력칸은 저마다 컨트롤러를 들고 있어서, 화면을 다시 만들지 않아도 글자는 그대로
  /// 보인다. 그런데 예전에는 키 입력마다 `setState`를 불러 입력칸 수십 개와 항목마다
  /// 붙은 댓글 실을 통째로 다시 만들었다. 글자가 손가락을 못 따라온 이유다.
  ///
  /// 곧바로 다시 만들어야 하는 경우는 둘뿐이다.
  ///
  /// - **줄이 늘거나 줄었을 때.** 프로젝트를 하나 더하면 그 자리가 바로 보여야 한다.
  /// - **처음으로 고쳐졌을 때.** 저장 버튼과 나가기 확인이 그때 깨어난다.
  ///
  /// 나머지(작성 현황 개수 같은 파생 표시)는 타이핑이 멎은 뒤 한 번에 따라잡는다.
  void _updateContent(ResumeContent next) {
    final structural = _rowCountsChanged(_content, next);
    _content = next;
    _markDirty();
    if (structural) {
      _derivedRefresh?.cancel();
      _lastDerived = _derivedSignature();
      setState(() {});
    } else {
      _scheduleDerivedRefresh();
    }
  }

  /// 줄 수가 달라졌나. 글자만 고친 것과 항목을 더하고 지운 것을 가른다.
  static bool _rowCountsChanged(ResumeContent a, ResumeContent b) =>
      a.experience.length != b.experience.length ||
      a.education.length != b.education.length ||
      a.techStack.length != b.techStack.length ||
      a.certifications.length != b.certifications.length ||
      a.awards.length != b.awards.length ||
      a.trainingExperience.length != b.trainingExperience.length ||
      a.otherActivities.length != b.otherActivities.length ||
      a.projects.length != b.projects.length;

  /// 타이핑이 멎으면 한 번 다시 그린다. 작성 현황 개수처럼 즉시가 아니어도 되는 것들.
  ///
  /// 다만 **보이는 것이 그대로면 그리지 않는다.** 이미 채워진 항목에 글자를 더하는
  /// 동안에는 작성 현황도 제목도 바뀌지 않는다. 그때마다 화면을 다시 만들면 타이핑을
  /// 잠깐 멈출 때마다 한 번씩 끊긴다.
  ///
  /// 코치가 열려 있으면 건너뛰지 않는다. 코치는 지금 이력서를 들고 있어야 추천을
  /// 누른 순간 최신 글로 보낸다.
  void _scheduleDerivedRefresh() {
    _derivedRefresh?.cancel();
    _derivedRefresh = Timer(const Duration(milliseconds: 400), () {
      if (!mounted) return;
      final next = _derivedSignature();
      if (!_showAiCoach && next == _lastDerived) return;
      _lastDerived = next;
      setState(() {});
    });
  }

  /// 화면에 보이는 파생 값의 지문. 이게 그대로면 다시 그려도 달라질 것이 없다.
  String _derivedSignature() {
    final sections = _content.computeSections();
    final filled = sections.values.where((done) => done).length;
    return '$filled|${_title.trim()}';
  }

  void _markDirty() {
    final resume = _resume;
    if (resume == null ||
        _isReadOnly(isReviewer: _isReviewer, resume: resume)) {
      return;
    }
    // 이미 고쳐진 상태면 다시 그릴 이유가 없다. 처음 한 번만 화면이 바뀐다.
    if (_dirty) return;
    setState(() => _dirty = true);
  }

  Future<bool> _confirmLeave() async {
    if (!_dirty) return true;
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('저장하지 않은 변경'),
        content: const Text('저장하지 않은 내용이 있습니다. 나가시겠습니까?'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('계속 작성'),
          ),
          ElevatedButton(
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('나가기'),
          ),
        ],
      ),
    );
    return ok ?? false;
  }

  Future<void> _goBack() async {
    if (!await _confirmLeave() || !mounted) return;
    context.go(RoutePaths.resume);
  }

  /// 화면을 열어 둔 사이에 도착한 피드백만 알린다. 저절로 사라지지 않는다 —
  /// 글을 쓰는 중에 몇 초 만에 사라지면 못 보고 지나친다.
  Widget _feedbackBanner(ResumeModel resume) {
    final all = ref.watch(resumeFeedbackProvider(resume.id)).asData?.value;
    // 스트림이 아직이면 기준을 잡을 수 없다. 여기서 빈 목록을 기준으로 삼으면
    // 곧 도착할 예전 피드백이 전부 "새로 왔다"가 된다.
    if (all == null) return const SizedBox.shrink();
    _feedbackIdsOnOpen ??= {for (final f in all) f.id};

    // 내가 단 답글은 나에게 온 피드백이 아니다.
    final arrived = all
        .where(
          (f) => !_feedbackIdsOnOpen!.contains(f.id) && !f.isReplyOn(resume),
        )
        .length;
    if (arrived <= 0 || _bannerDismissed) return const SizedBox.shrink();
    return Container(
      width: double.infinity,
      padding: EdgeInsets.fromLTRB(
        AppSpace.s(16),
        AppSpace.s(9),
        AppSpace.s(8),
        AppSpace.s(9),
      ),
      decoration: BoxDecoration(
        color: AppColors.primaryLight,
        border: Border(
          bottom: BorderSide(color: AppColors.tint(const Color(0xFFC9DBFF))),
        ),
      ),
      child: Row(
        children: [
          Icon(Icons.notifications, size: 16, color: AppColors.primary),
          SizedBox(width: AppSpace.s(8)),
          Expanded(
            child: Text(
              '새 피드백 $arrived건이 도착했습니다. 종을 눌러 확인하세요.',
              style: TextStyle(
                fontSize: 12.5,
                color: AppColors.primaryDark,
              ),
            ),
          ),
          IconButton(
            tooltip: '배너 닫기',
            visualDensity: VisualDensity.compact,
            iconSize: 18,
            onPressed: () => setState(() => _bannerDismissed = true),
            icon: Icon(Icons.close, color: AppColors.textSecondary),
          ),
        ],
      ),
    );
  }

  void _syncReviewerSectionFromScroll() {
    if (!_isReviewer ||
        _programmaticSectionScroll ||
        !_scrollController.hasClients ||
        _sectionSyncScheduled) {
      return;
    }
    _sectionSyncScheduled = true;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _sectionSyncScheduled = false;
      if (!mounted || !_isReviewer || _programmaticSectionScroll) {
        return;
      }

      const probeY = 180.0;
      String? visibleSection;
      var visibleTop = double.negativeInfinity;
      String? nearestSection;
      var nearestDistance = double.infinity;
      for (final key in AppConstants.resumeSections) {
        final renderObject = _sectionKeys[key]?.currentContext
            ?.findRenderObject();
        if (renderObject is! RenderBox || !renderObject.attached) continue;
        final top = renderObject.localToGlobal(Offset.zero).dy;
        final distance = (top - probeY).abs();
        if (distance < nearestDistance) {
          nearestDistance = distance;
          nearestSection = key;
        }
        if (top <= probeY && top > visibleTop) {
          visibleTop = top;
          visibleSection = key;
        }
      }
      final next = visibleSection ?? nearestSection;
      if (next != null && next != _selectedSection) {
        setState(() => _selectedSection = next);
      }
    });
  }

  Future<void> _scrollToSection(String key) async {
    setState(() => _selectedSection = key);
    final ctx = _sectionKeys[key]?.currentContext;
    if (ctx != null) {
      _programmaticSectionScroll = true;
      try {
        await Scrollable.ensureVisible(
          ctx,
          duration: const Duration(milliseconds: 300),
          curve: Curves.easeInOut,
          alignment: 0.08,
        );
      } finally {
        _programmaticSectionScroll = false;
      }
    }
  }

  /// 항목 하나. 학생에게는 아래에 그 항목의 댓글을 붙인다. 검토자는 오른쪽 패널에서 쓴다.
  /// 여기 한 곳만 고치면 모든 항목에 붙는다.
  Widget _section(String key, Widget child, ResumeModel resume) => KeyedSubtree(
    key: _sectionKeys[key],
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        child,
        if (!_isReviewer)
          SectionFeedbackThread(
            resume: resume,
            sectionKey: key,
            expanded: _openThreads.contains(key),
            onToggle: () => setState(() {
              _openThreads.contains(key)
                  ? _openThreads.remove(key)
                  : _openThreads.add(key);
            }),
          ),
      ],
    ),
  );

  /// 부르는 곳마다 resume 을 적지 않도록 한 번 묶어 둔다.
  Widget Function(String, Widget) _sectionOf(ResumeModel resume) =>
      (key, child) => _section(key, child, resume);

  /// 종에서 넘어왔다. 그 항목으로 굴러가 댓글을 펼친다.
  void _openThread(String key) {
    setState(() => _openThreads.add(key));
    _scrollToSection(key);
  }

  Future<void> _save({
    required ResumeModel resume,
    String? status,
    bool incrementRevision = true,
  }) async {
    final isReviewer = ref.read(canReviewResumesProvider);
    if (_isReadOnly(isReviewer: isReviewer, resume: resume) && status == null) {
      return;
    }
    setState(() => _isSaving = true);
    try {
      final cohortId = ref.read(effectiveCohortIdProvider)!;
      await ref
          .read(lmsRepositoryProvider)
          .updateResume(
            cohortId: cohortId,
            resumeId: widget.resumeId,
            title: _title.trim().isEmpty ? '새 이력서' : _title.trim(),
            content: _content,
            status: status,
            incrementRevision: incrementRevision && status == null,
          );
      _dirty = false;
      if (mounted && status == null) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('저장되었습니다.')),
        );
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('저장 실패: $e')),
        );
      }
    } finally {
      if (mounted) setState(() => _isSaving = false);
    }
  }

  /// 학생이 피드백을 요청한다. 이때부터 강사·관리자에게 이력서가 보인다.
  Future<void> _submitRequest(ResumeModel resume) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('피드백 요청'),
        content: const Text(
          '강사·관리자에게 피드백을 요청합니다. 요청해야 이력서가 전달되고, 요청한 뒤에도 계속 수정할 수 있습니다.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('취소'),
          ),
          ElevatedButton(
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('피드백 요청'),
          ),
        ],
      ),
    );
    if (ok != true || !mounted) return;
    await _save(resume: resume, status: 'submitted', incrementRevision: false);
    if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('피드백을 요청했습니다.')),
      );
    }
  }

  Future<void> _approve(ResumeModel resume) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('이력서 승인'),
        content: const Text('이 이력서를 승인합니다. 학생은 승인 뒤에도 계속 수정할 수 있습니다.'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('취소'),
          ),
          ElevatedButton(
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('승인'),
          ),
        ],
      ),
    );
    if (ok != true || !mounted) return;
    setState(() => _isSaving = true);
    try {
      await ref
          .read(lmsRepositoryProvider)
          .approveResume(
            cohortId: ref.read(effectiveCohortIdProvider)!,
            resumeId: widget.resumeId,
          );
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('승인되었습니다.')),
        );
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('승인 실패: $e')),
        );
      }
    } finally {
      if (mounted) setState(() => _isSaving = false);
    }
  }

  Future<void> _exportPdf(ResumeModel resume) async {
    try {
      final model = resume.copyWith(
        title: _title.trim().isEmpty ? '새 이력서' : _title.trim(),
        content: _content,
      );
      await ResumePdfExporter.showPrintPreview(model);
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('PDF 내보내기 실패: $e')),
        );
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final isReviewer = ref.watch(canReviewResumesProvider);
    final resumeAsync = ref.watch(resumeDetailProvider(widget.resumeId));

    return resumeAsync.when(
      loading: () =>
          const Scaffold(body: Center(child: CircularProgressIndicator())),
      error: (e, _) => Scaffold(body: ErrorView(message: e.toString())),
      data: (resume) {
        if (resume == null) {
          return Scaffold(
            appBar: AppBar(title: const Text('이력서')),
            body: const Center(child: Text('이력서를 찾을 수 없습니다.')),
          );
        }
        _initFromResume(resume);
        // 첫 로드 때 프로필 스트림이 아직 안 왔으면 도착한 뒤 한 번만 자동으로 채운다.
        if (!_profilePrefillTried &&
            ref.watch(currentUserProvider).value != null) {
          _profilePrefillTried = true;
          _prefillBasicInfoFromProfile(resume, announce: true);
        }
        _isReviewer = isReviewer;
        _resume = resume;
        if (isReviewer && !_reviewPanelWidthInitialized) {
          _reviewPanelWidthInitialized = true;
          WidgetsBinding.instance.addPostFrameCallback((_) {
            if (mounted && _panelWidth.value == _panelDefaultWidth) {
              _panelWidth.value = _reviewPanelDefaultWidth;
            }
          });
        }
        final readOnly = _isReadOnly(isReviewer: isReviewer, resume: resume);
        final liveSections = _content.computeSections();
        final completed = liveSections.values.where((v) => v).length;

        return PopScope(
          canPop: !_dirty,
          onPopInvokedWithResult: (didPop, result) async {
            if (didPop) return;
            if (await _confirmLeave() && context.mounted) {
              context.go(RoutePaths.resume);
            }
          },
          // 본문이 오른쪽 패널을 옆에 둘 만큼 넓은지는 여기서 한 번만 잰다. 창 전체
          // 폭(MediaQuery)은 사이드 레일까지 포함해 본문보다 넓어, 그것으로 재면
          // 본문은 좁게 배치됐는데 앱바의 열기 단추는 숨는 구간이 생긴다. 좁은
          // 배치에서 코치를 닫으면 이 단추 말고는 다시 열 길이 없다.
          child: LayoutBuilder(
            builder: (context, outer) {
              final wide = outer.maxWidth >= (isReviewer ? 1120 : 1000);
              return Scaffold(
                appBar: AppBar(
                  // 검토자는 남의 이력서를 연다. 지금 누구 것을 보고 있는지 머리말에
                  // 적어 둔다. 학생 자신은 굳이 알 필요가 없어 비워 둔다.
                  title: isReviewer
                      ? Text(
                          resume.displayTitle(asReviewer: true),
                          style: const TextStyle(fontSize: 15),
                        )
                      : const SizedBox.shrink(),
                  leading: TextButton.icon(
                    onPressed: _goBack,
                    icon: const Icon(Icons.arrow_back, size: 18),
                    label: const Text('목록으로'),
                  ),
                  leadingWidth: 110,
                  actions: [
                    if (!wide)
                      IconButton(
                        tooltip: _showAiCoach
                            ? (isReviewer ? '피드백 접기' : 'AI 코치 접기')
                            : (isReviewer ? '피드백 열기' : 'AI 코치 열기'),
                        onPressed: () => _setCoachVisible(!_showAiCoach),
                        icon: Icon(
                          _showAiCoach
                              ? Icons.keyboard_arrow_down
                              : (isReviewer
                                    ? Icons.chat_bubble_outline
                                    : Icons.smart_toy_outlined),
                        ),
                      ),
                    // 종. 누르면 아래로 말풍선이 내려온다. 오른쪽 패널을 쓰지 않으므로
                    // 이력서 너비를 뺏지 않고, AI 코치와 자리를 다투지도 않는다.
                    if (!isReviewer)
                      FeedbackBell(
                        resume: resume,
                        onGoToSection: _openThread,
                        openOnStart: widget.openFeedback,
                      ),
                    SizedBox(width: AppSpace.s(8)),
                    // 승인된 이력서도 학생이 편집·문서 보기를 오갈 수 있다. 승인은
                    // "여기까지 봤다"는 표시일 뿐 잠금이 아니다.
                    _ModeToggle(
                      isEdit: _viewMode == _ResumeViewMode.edit,
                      onEdit: () =>
                          setState(() => _viewMode = _ResumeViewMode.edit),
                      onDoc: () =>
                          setState(() => _viewMode = _ResumeViewMode.doc),
                    ),
                    if (_viewMode == _ResumeViewMode.doc) ...[
                      SizedBox(width: AppSpace.s(8)),
                      IconButton(
                        tooltip: 'PDF 내보내기',
                        onPressed: () => _exportPdf(resume),
                        icon: const Icon(Icons.picture_as_pdf_outlined),
                      ),
                    ],
                    if (!isReviewer &&
                        resume.canStudentEdit &&
                        _viewMode == _ResumeViewMode.edit) ...[
                      SizedBox(width: AppSpace.s(8)),
                      OutlinedButton(
                        onPressed: _isSaving
                            ? null
                            : () => _save(resume: resume),
                        child: const Text('저장'),
                      ),
                      if (!resume.isSubmitted) ...[
                        SizedBox(width: AppSpace.s(8)),
                        FilledButton.icon(
                          onPressed: _isSaving
                              ? null
                              : () => _submitRequest(resume),
                          icon: const Icon(Icons.send, size: 16),
                          label: const Text('피드백 요청'),
                        ),
                      ],
                      SizedBox(width: AppSpace.s(8)),
                    ],
                    if (isReviewer &&
                        resume.isSubmitted &&
                        !resume.isApproved) ...[
                      FilledButton.icon(
                        onPressed: _isSaving ? null : () => _approve(resume),
                        icon: const Icon(Icons.check_circle_outline, size: 16),
                        label: const Text('승인'),
                      ),
                      SizedBox(width: AppSpace.s(8)),
                    ],
                    if (_isSaving)
                      Padding(
                        padding: EdgeInsets.only(right: AppSpace.s(12)),
                        child: SizedBox(
                          width: 18,
                          height: 18,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        ),
                      ),
                  ],
                ),
                body: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    ResumeProgressHeader(
                      completed: completed,
                      total: AppConstants.resumeSections.length,
                      revisionCount: resume.revisionCount,
                      statusLabel: resume.statusLabel,
                    ),
                    if (!isReviewer) _feedbackBanner(resume),
                    if (resume.isSubmitted && !resume.isApproved && !isReviewer)
                      Container(
                        width: double.infinity,
                        padding: EdgeInsets.symmetric(
                          horizontal: AppSpace.s(16),
                          vertical: AppSpace.s(8),
                        ),
                        color: AppColors.primaryLight,
                        child: Text(
                          '피드백 요청됨 — 계속 수정할 수 있습니다.',
                          style: TextStyle(
                            fontSize: 12,
                            color: AppColors.textSecondary,
                          ),
                        ),
                      ),
                    // 학생에게 하는 안내다. 강사·관리자는 위 진행 줄의 "승인 완료"로 충분하다.
                    if (resume.isApproved && !isReviewer)
                      Container(
                        width: double.infinity,
                        padding: EdgeInsets.symmetric(
                          horizontal: AppSpace.s(16),
                          vertical: AppSpace.s(8),
                        ),
                        color: AppColors.success.withValues(alpha: 0.12),
                        child: Text(
                          '승인 완료 — 계속 수정할 수 있습니다.',
                          style: TextStyle(
                            fontSize: 12,
                            color: AppColors.success,
                          ),
                        ),
                      ),
                    if (!isReviewer)
                      ResumeSectionNav(
                        sections: AppConstants.resumeSections,
                        completedSections: liveSections,
                        selectedKey: _selectedSection,
                        onSelected: _scrollToSection,
                      ),
                    Expanded(
                      child: LayoutBuilder(
                        builder: (context, constraints) {
                          final resumeScroll = SingleChildScrollView(
                            controller: _scrollController,
                            padding: EdgeInsets.all(AppSpace.s(16)),
                            child: Center(
                              child: ConstrainedBox(
                                constraints: BoxConstraints(
                                  maxWidth: wide ? double.infinity : 720,
                                ),
                                child: Column(
                                  crossAxisAlignment:
                                      CrossAxisAlignment.stretch,
                                  children: [
                                    _TitleSection(
                                      title: _title,
                                      readOnly: readOnly,
                                      onChanged: (v) {
                                        // 제목도 입력칸이 스스로 보여 준다. 화면 위쪽의
                                        // 이력서 이름만 잠시 뒤 따라잡으면 된다.
                                        _title = v;
                                        _markDirty();
                                        _scheduleDerivedRefresh();
                                      },
                                    ),
                                    SizedBox(height: AppSpace.s(24)),
                                    _sectionOf(resume)(
                                      'basicInfo',
                                      _BasicInfoSection(
                                        info: _content.basicInfo,
                                        readOnly: readOnly,
                                        onChanged: (info) {
                                          _updateContent(
                                            _content.copyWith(basicInfo: info),
                                          );
                                          _markDirty();
                                        },
                                        onPrefill: readOnly
                                            ? null
                                            : () {
                                                final changed =
                                                    _prefillBasicInfoFromProfile(
                                                      resume,
                                                      announce: false,
                                                    );
                                                setState(() {});
                                                ScaffoldMessenger.of(
                                                  context,
                                                ).showSnackBar(
                                                  SnackBar(
                                                    content: Text(
                                                      changed
                                                          ? '마이페이지 정보로 빈 칸을 채웠습니다.'
                                                          : '채울 빈 칸이 없거나 마이페이지에 정보가 없습니다.',
                                                    ),
                                                  ),
                                                );
                                              },
                                      ),
                                    ),
                                    SizedBox(height: AppSpace.s(24)),
                                    _sectionOf(resume)(
                                      'coreCompetencies',
                                      _CoreCompetenciesSection(
                                        data: _content.coreCompetencies,
                                        readOnly: readOnly,
                                        onChanged: (d) {
                                          _updateContent(
                                            _content.copyWith(
                                              coreCompetencies: d,
                                            ),
                                          );
                                          _markDirty();
                                        },
                                      ),
                                    ),
                                    SizedBox(height: AppSpace.s(24)),
                                    _sectionOf(resume)(
                                      'experience',
                                      _ExperienceSection(
                                        items: _content.experience,
                                        readOnly: readOnly,
                                        onChanged: (items) {
                                          _updateContent(
                                            _content.copyWith(
                                              experience: items,
                                            ),
                                          );
                                          _markDirty();
                                        },
                                      ),
                                    ),
                                    SizedBox(height: AppSpace.s(24)),
                                    _sectionOf(resume)(
                                      'education',
                                      _EducationSection(
                                        items: _content.education,
                                        readOnly: readOnly,
                                        onChanged: (items) {
                                          _updateContent(
                                            _content.copyWith(education: items),
                                          );
                                          _markDirty();
                                        },
                                      ),
                                    ),
                                    SizedBox(height: AppSpace.s(24)),
                                    _sectionOf(resume)(
                                      'techStack',
                                      _TechStackSection(
                                        items: _content.techStack,
                                        readOnly: readOnly,
                                        onChanged: (items) {
                                          _updateContent(
                                            _content.copyWith(techStack: items),
                                          );
                                          _markDirty();
                                        },
                                      ),
                                    ),
                                    SizedBox(height: AppSpace.s(24)),
                                    _sectionOf(resume)(
                                      'certifications',
                                      _CertificationsSection(
                                        items: _content.certifications,
                                        readOnly: readOnly,
                                        onChanged: (items) {
                                          _updateContent(
                                            _content.copyWith(
                                              certifications: items,
                                            ),
                                          );
                                          _markDirty();
                                        },
                                      ),
                                    ),
                                    SizedBox(height: AppSpace.s(24)),
                                    _sectionOf(resume)(
                                      'awards',
                                      _AwardsSection(
                                        items: _content.awards,
                                        readOnly: readOnly,
                                        onChanged: (items) {
                                          _updateContent(
                                            _content.copyWith(awards: items),
                                          );
                                          _markDirty();
                                        },
                                      ),
                                    ),
                                    SizedBox(height: AppSpace.s(24)),
                                    _sectionOf(resume)(
                                      'trainingExperience',
                                      _TrainingSection(
                                        items: _content.trainingExperience,
                                        readOnly: readOnly,
                                        onChanged: (items) {
                                          _updateContent(
                                            _content.copyWith(
                                              trainingExperience: items,
                                            ),
                                          );
                                          _markDirty();
                                        },
                                      ),
                                    ),
                                    SizedBox(height: AppSpace.s(24)),
                                    _sectionOf(resume)(
                                      'otherActivities',
                                      _ActivitiesSection(
                                        items: _content.otherActivities,
                                        readOnly: readOnly,
                                        onChanged: (items) {
                                          _updateContent(
                                            _content.copyWith(
                                              otherActivities: items,
                                            ),
                                          );
                                          _markDirty();
                                        },
                                      ),
                                    ),
                                    SizedBox(height: AppSpace.s(24)),
                                    _sectionOf(resume)(
                                      'projects',
                                      _ProjectsSection(
                                        items: _content.projects,
                                        readOnly: readOnly,
                                        onChanged: (items) {
                                          _updateContent(
                                            _content.copyWith(projects: items),
                                          );
                                          _markDirty();
                                        },
                                      ),
                                    ),
                                    SizedBox(height: AppSpace.s(24)),
                                    _sectionOf(resume)(
                                      'selfIntroduction',
                                      _SelfIntroSection(
                                        data: _content.selfIntroduction,
                                        readOnly: readOnly,
                                        onChanged: (d) {
                                          _updateContent(
                                            _content.copyWith(
                                              selfIntroduction: d,
                                            ),
                                          );
                                          _markDirty();
                                        },
                                      ),
                                    ),
                                    SizedBox(height: AppSpace.s(32)),
                                  ],
                                ),
                              ),
                            ),
                          );

                          // 두 패널을 갈아끼우지 않고 **숨기기만** 한다. 트리에서 빼면 AI
                          // 코치의 대화와 좁혀 둔 검색 조건이 함께 사라져, 접었다 펴는 것만으로
                          // 처음부터 다시 말해야 한다. 대화를 어디에도 저장하지 않는 것은
                          // 그대로다 — 화면을 떠나면 사라진다.
                          //
                          // `Offstage`는 자식을 배치·그리지 않을 뿐 상태는 남긴다. AI 코치는
                          // initState도 네트워크 호출도 없어 숨어 있는 동안 아무 일도 하지 않는다.
                          //
                          // 반대로 피드백 패널은 **보일 때만** 만든다. 이쪽은 Firestore 스트림을
                          // 구독하므로 숨은 채로 남겨 두면 AI 코치를 보는 내내 없던 구독이
                          // 열려 있게 된다. 이 패널은 남길 상태도 없다.
                          //
                          // `passthrough`로 지금과 같은 제약을 그대로 넘긴다(넓은 화면에서는
                          // 높이를 채우고, 좁은 화면에서는 내용만큼만 차지한다).
                          // 닫혀 있는 동안에는 **직전에 만든 위젯을 그대로 넘긴다.**
                          // `Offstage`는 배치·그리기만 건너뛸 뿐 자식을 만들기는 한다.
                          // 그래서 숨어 있어도 키 입력마다 코치 화면이 다시 만들어졌다.
                          // 같은 위젯 객체를 넘기면 Flutter가 그 아래를 통째로 건너뛴다.
                          final usesFeedbackPanel = isReviewer;
                          if (!usesFeedbackPanel &&
                              (_showAiCoach || _coachPanel == null)) {
                            _coachPanel = AiJobCoachPanel(
                              key: _coachKey,
                              resumeId: widget.resumeId,
                              resumeTitle: _title,
                              baseResumeId: resume.baseResumeId,
                              sourceTailoredResumeId:
                                  resume.sourceTailoredResumeId,
                              linkedJobId: resume.linkedJobId,
                              draftContent: _content,
                              hasUnsavedChanges: _dirty || _isSaving,
                              onSaveRequested: isReviewer
                                  ? null
                                  : () async {
                                      await _save(resume: resume);
                                      return !_dirty;
                                    },
                              onResumeChanged: isReviewer
                                  ? null
                                  : (content) => setState(() {
                                      _content = content;
                                      _dirty = false;
                                    }),
                              isSidebar: wide,
                              onClose: () => _setCoachVisible(false),
                            );
                          }
                          final rightPanel = usesFeedbackPanel
                              ? ResumeEditFeedbackPanel(
                                  key: ValueKey('review-feedback-${resume.id}'),
                                  resume: resume,
                                  isAdmin: isReviewer,
                                  isVisible: _showAiCoach,
                                  selectedSectionKey: _selectedSection,
                                  completedSections: liveSections,
                                  isSidebar: true,
                                  showSectionSidebar: wide,
                                  onSectionChanged: _scrollToSection,
                                )
                              : Stack(
                                  fit: StackFit.passthrough,
                                  children: [
                                    Offstage(
                                      offstage: !_showAiCoach,
                                      child: _coachPanel,
                                    ),
                                  ],
                                );

                          // 작성 중인 학생은 AI 코치, 피드백 요청 상태의 학생과 검토자는
                          // 같은 댓글 패널을 오른쪽에서 사용한다.
                          final hasRightPanel = _showAiCoach;

                          // 닫아도 트리에서 빼지 않는다. 빼면 상태가 버려져 받아 둔
                          // 맞춤 공고가 사라지고, 다시 열면 빈 화면이 나온다. `Offstage`가
                          // 이미 안쪽에 있어 닫힌 동안에는 자리를 차지하지 않는다.
                          if (!wide) {
                            // 이력서 본문을 최소 200px 남기고, 패널도 200px을 지킨다.
                            final panelMaxHeight =
                                (constraints.maxHeight -
                                        _minResumeHeight -
                                        _handleWidth)
                                    .clamp(_panelMinHeight, 900)
                                    .toDouble();
                            return Column(
                              children: [
                                Expanded(child: resumeScroll),
                                // 닫혀 있으면 손잡이도 패널도 자리를 차지하지 않는다.
                                // 넓은 화면과 같은 이유로 트리에서 빼지는 않는다.
                                Offstage(
                                  offstage: !hasRightPanel,
                                  child: _PanelResizeHandle(
                                    axis: Axis.horizontal,
                                    onStart: () =>
                                        _dragStartHeight = _panelHeight.value,
                                    onUpdate: (dy) {
                                      // 위로 끌면(거리가 음수) 높아진다.
                                      _panelHeight.value =
                                          ((_dragStartHeight ??
                                                      _panelHeight.value) -
                                                  dy)
                                              .clamp(
                                                _panelMinHeight,
                                                panelMaxHeight,
                                              );
                                    },
                                    onReset: () => _panelHeight.value =
                                        _panelDefaultHeight,
                                  ),
                                ),
                                ValueListenableBuilder<double>(
                                  valueListenable: _panelHeight,
                                  child: rightPanel,
                                  builder: (context, raw, panel) => SizedBox(
                                    height: hasRightPanel
                                        ? raw.clamp(
                                            _panelMinHeight,
                                            panelMaxHeight,
                                          )
                                        : 0,
                                    child: panel,
                                  ),
                                ),
                              ],
                            );
                          }

                          // 이력서 본문을 최소 560px 남기고, 오른쪽 패널은 최소 360px을 지킨다.
                          // 화면 크기가 달라져도 조절해 둔 폭을 안전한 범위 안에서만 쓴다.
                          final panelMinWidth = usesFeedbackPanel
                              ? _reviewPanelMinWidth
                              : _panelMinWidth;
                          final panelMaxWidth =
                              (constraints.maxWidth -
                                      _minResumeWidth -
                                      _handleWidth)
                                  .clamp(panelMinWidth, 900)
                                  .toDouble();

                          return Row(
                            crossAxisAlignment: CrossAxisAlignment.stretch,
                            children: [
                              Expanded(child: resumeScroll),
                              // 닫혀 있어도 같은 자리·같은 깊이로 남는다. 트리에서 빼거나
                              // 감싸는 위젯 수를 바꾸면 패널 상태가 버려져 받아 둔 맞춤
                              // 공고가 사라진다. 닫을 때는 폭을 0으로 만들 뿐이다.
                              ValueListenableBuilder<double>(
                                valueListenable: _panelWidth,
                                // 패널 자체는 여기 그대로 넘어와 다시 만들어지지 않는다.
                                child: rightPanel,
                                builder: (context, raw, panel) {
                                  final width = raw.clamp(
                                    panelMinWidth,
                                    panelMaxWidth,
                                  );
                                  return Row(
                                    mainAxisSize: MainAxisSize.min,
                                    crossAxisAlignment:
                                        CrossAxisAlignment.stretch,
                                    children: [
                                      if (hasRightPanel)
                                        _PanelResizeHandle(
                                          onStart: () =>
                                              _dragStartWidth = width,
                                          onUpdate: (dx) {
                                            // 왼쪽으로 끌면(거리가 음수) 넓어진다.
                                            _panelWidth.value =
                                                ((_dragStartWidth ?? width) -
                                                        dx)
                                                    .clamp(
                                                      panelMinWidth,
                                                      panelMaxWidth,
                                                    );
                                          },
                                          onReset: () => _panelWidth.value =
                                              usesFeedbackPanel
                                              ? _reviewPanelDefaultWidth
                                              : _panelDefaultWidth,
                                          onToggle: () =>
                                              _setCoachVisible(false),
                                        )
                                      else
                                        _CoachEdgeToggle(
                                          expanded: false,
                                          onPressed: () =>
                                              _setCoachVisible(true),
                                        ),
                                      SizedBox(
                                        width: hasRightPanel ? width : 0,
                                        child: DecoratedBox(
                                          decoration: BoxDecoration(
                                            border: Border(
                                              left: BorderSide(
                                                color: hasRightPanel
                                                    ? AppColors.border
                                                    : Colors.transparent,
                                              ),
                                            ),
                                          ),
                                          child: panel,
                                        ),
                                      ),
                                    ],
                                  );
                                },
                              ),
                            ],
                          );
                        },
                      ),
                    ),
                  ],
                ),
              );
            },
          ),
        );
      },
    );
  }
}

// ── 공통 위젯 ──

/// 오른쪽 패널의 너비를 바꾸는 손잡이. 패널 왼쪽 가장자리에 세워 둔다.
///
/// 보이는 선은 1픽셀이지만 잡히는 폭은 12픽셀이다. 1픽셀짜리는 마우스로 집기 어렵다.
/// 두 번 누르면 처음 너비로 돌아온다.
///
/// 포인터 이벤트를 직접 받는다(`Listener`). `GestureDetector`의 드래그는 웹에서
/// "이건 드래그다"라고 판정한 뒤에야 알려 주어, 처음 몇 픽셀이 씹히고 손잡이가
/// 커서보다 뒤처진다. 첨삭 브랜치에서 같은 문제를 만나 이 방식으로 옮겼다.
///
/// 매 신호의 변화량을 더하지 않고 **누른 지점에서 커서까지의 거리**를 넘긴다.
/// 한 프레임에 신호가 여러 번 오면 변화량 방식은 마지막 것만 남아 손실이 생긴다.
class _PanelResizeHandle extends StatefulWidget {
  const _PanelResizeHandle({
    required this.onStart,
    required this.onUpdate,
    required this.onReset,
    this.onToggle,
    this.axis = Axis.vertical,
  });

  /// 손잡이가 놓인 방향. [Axis.vertical]은 세로 막대라 좌우로 끈다(넓은 화면),
  /// [Axis.horizontal]은 가로 막대라 위아래로 끈다(좁은 화면).
  final Axis axis;

  final VoidCallback onStart;
  final ValueChanged<double> onUpdate;
  final VoidCallback onReset;
  final VoidCallback? onToggle;

  @override
  State<_PanelResizeHandle> createState() => _PanelResizeHandleState();
}

class _PanelResizeHandleState extends State<_PanelResizeHandle> {
  bool _dragging = false;
  double _start = 0;

  bool get _isVertical => widget.axis == Axis.vertical;

  /// 끄는 방향의 좌표만 본다. 세로 막대는 x, 가로 막대는 y다.
  double _along(Offset position) => _isVertical ? position.dx : position.dy;

  void _stop() {
    if (_dragging) setState(() => _dragging = false);
  }

  @override
  Widget build(BuildContext context) {
    const thickness = _ResumeEditScreenState._handleWidth;
    return MouseRegion(
      cursor: _isVertical
          ? SystemMouseCursors.resizeColumn
          : SystemMouseCursors.resizeRow,
      child: SizedBox(
        width: _isVertical ? thickness : double.infinity,
        height: _isVertical ? null : thickness,
        child: Stack(
          clipBehavior: Clip.none,
          alignment: Alignment.center,
          children: [
            Positioned.fill(
              child: GestureDetector(
                onDoubleTap: widget.onReset,
                child: Listener(
                  behavior: HitTestBehavior.translucent,
                  onPointerDown: (event) {
                    _start = _along(event.position);
                    widget.onStart();
                    setState(() => _dragging = true);
                  },
                  onPointerMove: (event) {
                    if (!_dragging) return;
                    widget.onUpdate(_along(event.position) - _start);
                  },
                  onPointerUp: (_) => _stop(),
                  onPointerCancel: (_) => _stop(),
                  child: Center(
                    child: AnimatedContainer(
                      duration: const Duration(milliseconds: 120),
                      width: _isVertical ? 1 : double.infinity,
                      height: _isVertical ? double.infinity : 1,
                      color: AppColors.border,
                    ),
                  ),
                ),
              ),
            ),
            if (_isVertical && widget.onToggle != null)
              _CoachEdgeToggle(
                expanded: true,
                onPressed: widget.onToggle!,
              ),
          ],
        ),
      ),
    );
  }
}

class _CoachEdgeToggle extends StatefulWidget {
  const _CoachEdgeToggle({required this.expanded, required this.onPressed});

  final bool expanded;
  final VoidCallback onPressed;

  @override
  State<_CoachEdgeToggle> createState() => _CoachEdgeToggleState();
}

class _CoachEdgeToggleState extends State<_CoachEdgeToggle> {
  bool _hovered = false;

  @override
  Widget build(BuildContext context) => MouseRegion(
    cursor: SystemMouseCursors.click,
    onEnter: (_) => setState(() => _hovered = true),
    onExit: (_) => setState(() => _hovered = false),
    child: AnimatedOpacity(
      opacity: 1,
      duration: const Duration(milliseconds: 120),
      child: Material(
        color: AppColors.surface,
        elevation: _hovered ? 4 : 1,
        shape: RoundedRectangleBorder(
          side: BorderSide(
            color: _hovered ? const Color(0xFF171717) : AppColors.border,
          ),
          borderRadius: BorderRadius.circular(9),
        ),
        child: InkWell(
          onTap: widget.onPressed,
          borderRadius: BorderRadius.circular(9),
          child: SizedBox(
            width: 28,
            height: AppSpace.row(56),
            child: Icon(
              widget.expanded
                  ? Icons.chevron_right_rounded
                  : Icons.chevron_left_rounded,
              size: 22,
              color: const Color(0xFF171717),
            ),
          ),
        ),
      ),
    ),
  );
}

class _ModeToggle extends StatelessWidget {
  const _ModeToggle({
    required this.isEdit,
    required this.onEdit,
    required this.onDoc,
  });

  final bool isEdit;
  final VoidCallback onEdit;
  final VoidCallback onDoc;

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        border: Border.all(color: AppColors.border),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          _ToggleChip(label: 'Doc', selected: !isEdit, onTap: onDoc),
          _ToggleChip(label: 'Edit', selected: isEdit, onTap: onEdit),
        ],
      ),
    );
  }
}

class _ToggleChip extends StatelessWidget {
  const _ToggleChip({
    required this.label,
    required this.selected,
    required this.onTap,
  });

  final String label;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onTap,
      child: Container(
        padding: EdgeInsets.symmetric(
          horizontal: AppSpace.s(14),
          vertical: AppSpace.s(8),
        ),
        decoration: BoxDecoration(
          color: selected ? AppColors.primaryLight : Colors.transparent,
          borderRadius: BorderRadius.circular(7),
        ),
        child: Text(
          label,
          style: TextStyle(
            fontWeight: selected ? FontWeight.w600 : FontWeight.normal,
            color: selected ? AppColors.textPrimary : AppColors.textSecondary,
          ),
        ),
      ),
    );
  }
}

class _FlatSection extends StatelessWidget {
  const _FlatSection({required this.title, required this.child});
  final String title;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          title,
          style: const TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
        ),
        SizedBox(height: AppSpace.s(8)),
        Divider(height: 1, color: AppColors.border),
        SizedBox(height: AppSpace.s(16)),
        child,
      ],
    );
  }
}

class _Field extends StatefulWidget {
  const _Field({
    required this.label,
    this.hint,
    required this.value,
    required this.readOnly,
    required this.onChanged,
    this.maxLines = 1,
    this.minLines,
    this.scrollPhysics,
    this.keyboardType,
    this.boxed = false,
  });

  final String label;
  final String? hint;
  final String value;
  final bool readOnly;
  final ValueChanged<String> onChanged;

  /// null이면 입력한 내용만큼 높이가 늘어나며 내부 스크롤을 만들지 않는다.
  final int? maxLines;
  final int? minLines;
  final ScrollPhysics? scrollPhysics;
  final TextInputType? keyboardType;
  final bool boxed;

  @override
  State<_Field> createState() => _FieldState();
}

class _FieldState extends State<_Field> {
  late TextEditingController _controller;

  @override
  void initState() {
    super.initState();
    _controller = TextEditingController(text: widget.value);
  }

  @override
  void didUpdateWidget(_Field oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.value != _controller.text) {
      _controller.text = widget.value;
    }
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final isMultiline = widget.maxLines == null || widget.maxLines! > 1;
    final minLines = widget.minLines ?? 1;
    if (widget.readOnly) {
      final empty = widget.value.trim().isEmpty;
      return Padding(
        padding: EdgeInsets.only(bottom: AppSpace.s(8)),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            if (widget.label.isNotEmpty)
              Text(
                widget.label,
                style: TextStyle(
                  fontSize: 12,
                  color: AppColors.textSecondary,
                ),
              ),
            if (widget.label.isNotEmpty) SizedBox(height: AppSpace.s(2)),
            Text(
              empty ? '미작성' : widget.value,
              style: TextStyle(
                color: empty ? AppColors.textHint : AppColors.textPrimary,
                height: isMultiline ? 1.5 : null,
              ),
            ),
          ],
        ),
      );
    }

    if (widget.boxed) {
      return Padding(
        padding: EdgeInsets.only(bottom: AppSpace.s(8)),
        child: TextField(
          controller: _controller,
          decoration: InputDecoration(
            labelText: widget.label.isEmpty ? null : widget.label,
            hintText: widget.hint,
            alignLabelWithHint: isMultiline,
          ),
          maxLines: widget.maxLines,
          minLines: minLines,
          scrollPhysics: widget.scrollPhysics,
          textAlignVertical: isMultiline ? TextAlignVertical.top : null,
          keyboardType: widget.keyboardType,
          onChanged: widget.onChanged,
        ),
      );
    }

    return Padding(
      padding: EdgeInsets.only(bottom: AppSpace.s(8)),
      child: TextField(
        controller: _controller,
        decoration: InputDecoration(
          labelText: widget.label.isEmpty ? null : widget.label,
          hintText: widget.hint,
          border: InputBorder.none,
          enabledBorder: InputBorder.none,
          focusedBorder: UnderlineInputBorder(
            borderSide: BorderSide(color: AppColors.border),
          ),
          filled: false,
          contentPadding: EdgeInsets.symmetric(vertical: AppSpace.s(8)),
        ),
        maxLines: widget.maxLines,
        minLines: minLines,
        scrollPhysics: widget.scrollPhysics,
        textAlignVertical: isMultiline ? TextAlignVertical.top : null,
        keyboardType: widget.keyboardType,
        onChanged: widget.onChanged,
      ),
    );
  }
}

class _AddButton extends StatelessWidget {
  const _AddButton({required this.label, required this.onPressed});
  final String label;
  final VoidCallback? onPressed;

  @override
  Widget build(BuildContext context) {
    return TextButton.icon(
      onPressed: onPressed,
      style: TextButton.styleFrom(
        foregroundColor: AppColors.textSecondary,
        alignment: Alignment.centerLeft,
      ),
      icon: const Icon(Icons.add, size: 18),
      label: Text(label),
    );
  }
}

class _ItemCard extends StatelessWidget {
  const _ItemCard({
    required this.index,
    required this.readOnly,
    required this.onDelete,
    required this.child,
  });

  final int index;
  final bool readOnly;
  final VoidCallback onDelete;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: EdgeInsets.only(bottom: AppSpace.s(12)),
      padding: EdgeInsets.all(AppSpace.s(12)),
      decoration: BoxDecoration(
        border: Border.all(color: AppColors.border),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Text(
                '항목 ${index + 1}',
                style: const TextStyle(fontWeight: FontWeight.w600),
              ),
              const Spacer(),
              if (!readOnly)
                IconButton(
                  icon: const Icon(Icons.delete_outline, size: 20),
                  onPressed: onDelete,
                ),
            ],
          ),
          child,
        ],
      ),
    );
  }
}

Future<void> _pickDate(
  BuildContext context,
  String current,
  ValueChanged<String> onPicked,
) async {
  final initial = DateTime.tryParse(current) ?? DateTime(2000);
  final picked = await showDatePicker(
    context: context,
    initialDate: initial,
    firstDate: DateTime(1970),
    lastDate: DateTime(2100),
  );
  if (picked != null) {
    onPicked(
      '${picked.year}-${picked.month.toString().padLeft(2, '0')}-${picked.day.toString().padLeft(2, '0')}',
    );
  }
}

// ── 섹션 위젯 ──

class _TitleSection extends StatefulWidget {
  const _TitleSection({
    required this.title,
    required this.readOnly,
    required this.onChanged,
  });

  final String title;
  final bool readOnly;
  final ValueChanged<String> onChanged;

  @override
  State<_TitleSection> createState() => _TitleSectionState();
}

class _TitleSectionState extends State<_TitleSection> {
  late TextEditingController _controller;

  @override
  void initState() {
    super.initState();
    _controller = TextEditingController(text: widget.title);
  }

  @override
  void didUpdateWidget(_TitleSection oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.title != _controller.text) {
      _controller.text = widget.title;
    }
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.end,
      children: [
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text(
                '이력서 제목',
                style: TextStyle(fontWeight: FontWeight.w600),
              ),
              SizedBox(height: AppSpace.s(8)),
              if (widget.readOnly)
                Text(
                  widget.title.isEmpty ? '새 이력서' : widget.title,
                  style: const TextStyle(fontSize: 18),
                )
              else
                TextField(
                  controller: _controller,
                  decoration: const InputDecoration(
                    hintText: '새 이력서',
                    border: InputBorder.none,
                  ),
                  maxLength: 100,
                  buildCounter:
                      (
                        _, {
                        required currentLength,
                        required isFocused,
                        maxLength,
                      }) => null,
                  onChanged: widget.onChanged,
                ),
            ],
          ),
        ),
        if (!widget.readOnly)
          Text(
            '${widget.title.length}/100',
            style: TextStyle(
              fontSize: 12,
              color: AppColors.textSecondary,
            ),
          ),
      ],
    );
  }
}

class _BasicInfoSection extends StatelessWidget {
  const _BasicInfoSection({
    required this.info,
    required this.readOnly,
    required this.onChanged,
    this.onPrefill,
  });

  final ResumeBasicInfo info;
  final bool readOnly;
  final ValueChanged<ResumeBasicInfo> onChanged;

  /// 마이페이지 정보로 빈 칸을 채우는 동작. 읽기 전용이면 null.
  final VoidCallback? onPrefill;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        if (readOnly)
          Text(
            info.name.isEmpty ? '이름 없음' : info.name,
            style: const TextStyle(fontSize: 20, fontWeight: FontWeight.bold),
          )
        else
          _NameField(
            value: info.name,
            onChanged: (v) => onChanged(info.copyWith(name: v)),
          ),
        if (onPrefill != null) ...[
          SizedBox(height: AppSpace.s(4)),
          TextButton.icon(
            onPressed: onPrefill,
            style: TextButton.styleFrom(
              foregroundColor: AppColors.textSecondary,
              padding: EdgeInsets.zero,
              visualDensity: VisualDensity.compact,
            ),
            icon: const Icon(Icons.person_outline, size: 16),
            label: const Text(
              '마이페이지 정보로 빈 칸 채우기',
              style: TextStyle(fontSize: 12),
            ),
          ),
        ],
        SizedBox(height: AppSpace.s(12)),
        Wrap(
          spacing: 24,
          runSpacing: 8,
          children: [
            _IconField(
              icon: Icons.phone_outlined,
              label: '연락처',
              value: info.phone,
              readOnly: readOnly,
              keyboardType: TextInputType.phone,
              onChanged: (v) => onChanged(info.copyWith(phone: v)),
            ),
            _IconField(
              icon: Icons.email_outlined,
              label: '이메일',
              value: info.email,
              readOnly: readOnly,
              keyboardType: TextInputType.emailAddress,
              onChanged: (v) => onChanged(info.copyWith(email: v)),
            ),
            _IconField(
              icon: Icons.calendar_today_outlined,
              label: '생년월일',
              value: info.birthDate,
              readOnly: readOnly,
              onTap: readOnly
                  ? null
                  : () => _pickDate(
                      context,
                      info.birthDate,
                      (v) => onChanged(info.copyWith(birthDate: v)),
                    ),
              onChanged: (v) => onChanged(info.copyWith(birthDate: v)),
            ),
            _IconField(
              icon: Icons.code,
              label: 'Github URL',
              value: info.githubUrl,
              readOnly: readOnly,
              keyboardType: TextInputType.url,
              onChanged: (v) => onChanged(info.copyWith(githubUrl: v)),
            ),
            _IconField(
              icon: Icons.language,
              label: 'Blog URL',
              value: info.blogUrl,
              readOnly: readOnly,
              keyboardType: TextInputType.url,
              onChanged: (v) => onChanged(info.copyWith(blogUrl: v)),
            ),
          ],
        ),
      ],
    );
  }
}

class _NameField extends StatefulWidget {
  const _NameField({required this.value, required this.onChanged});
  final String value;
  final ValueChanged<String> onChanged;

  @override
  State<_NameField> createState() => _NameFieldState();
}

class _NameFieldState extends State<_NameField> {
  late TextEditingController _controller;

  @override
  void initState() {
    super.initState();
    _controller = TextEditingController(text: widget.value);
  }

  @override
  void didUpdateWidget(_NameField oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.value != _controller.text) {
      _controller.text = widget.value;
    }
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return TextField(
      controller: _controller,
      decoration: InputDecoration(
        hintText: '이름을 입력하세요',
        hintStyle: TextStyle(
          fontSize: 20,
          fontWeight: FontWeight.bold,
          color: AppColors.textHint,
        ),
        border: InputBorder.none,
        enabledBorder: InputBorder.none,
        focusedBorder: InputBorder.none,
        filled: false,
        isDense: true,
        contentPadding: EdgeInsets.symmetric(vertical: AppSpace.s(4)),
      ),
      style: const TextStyle(fontSize: 20, fontWeight: FontWeight.bold),
      onChanged: widget.onChanged,
    );
  }
}

class _IconField extends StatefulWidget {
  const _IconField({
    required this.icon,
    required this.label,
    required this.value,
    required this.readOnly,
    required this.onChanged,
    this.keyboardType,
    this.onTap,
  });

  final IconData icon;
  final String label;
  final String value;
  final bool readOnly;
  final ValueChanged<String> onChanged;
  final TextInputType? keyboardType;
  final VoidCallback? onTap;

  @override
  State<_IconField> createState() => _IconFieldState();
}

class _IconFieldState extends State<_IconField> {
  late TextEditingController _controller;

  @override
  void initState() {
    super.initState();
    _controller = TextEditingController(text: widget.value);
  }

  @override
  void didUpdateWidget(_IconField oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.value != _controller.text) {
      _controller.text = widget.value;
    }
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final textField = TextField(
      controller: _controller,
      decoration: InputDecoration(
        labelText: widget.label,
        hintText: widget.onTap != null ? '날짜 선택' : null,
        isDense: true,
      ),
      readOnly: widget.onTap != null,
      showCursor: widget.onTap == null,
      keyboardType: widget.keyboardType,
      onTap: widget.onTap,
      onChanged: widget.onChanged,
      style: const TextStyle(fontSize: 13),
    );

    return SizedBox(
      width: 200,
      child: Row(
        children: [
          Icon(widget.icon, size: 18, color: AppColors.textSecondary),
          SizedBox(width: AppSpace.s(8)),
          Expanded(
            child: widget.readOnly
                ? Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        widget.label,
                        style: TextStyle(
                          fontSize: 11,
                          color: AppColors.textHint,
                        ),
                      ),
                      Text(
                        widget.value.isEmpty ? '미작성' : widget.value,
                        style: TextStyle(
                          fontSize: 13,
                          color: widget.value.isEmpty
                              ? AppColors.textHint
                              : AppColors.textPrimary,
                        ),
                      ),
                    ],
                  )
                : textField,
          ),
        ],
      ),
    );
  }
}

class _CoreCompetenciesSection extends StatelessWidget {
  const _CoreCompetenciesSection({
    required this.data,
    required this.readOnly,
    required this.onChanged,
  });

  final ResumeCoreCompetencies data;
  final bool readOnly;
  final ValueChanged<ResumeCoreCompetencies> onChanged;

  @override
  Widget build(BuildContext context) {
    return _FlatSection(
      title: AppConstants.resumeSectionLabels['coreCompetencies']!,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            '채용 담당자들이 가장 먼저 읽게 되는 글입니다.',
            style: TextStyle(fontSize: 13, color: AppColors.textSecondary),
          ),
          Text(
            '경력을 기반으로 나의 역량과 강점을 소개해 주세요.',
            style: TextStyle(fontSize: 13, color: AppColors.textSecondary),
          ),
          Text(
            '5줄 이내로 간결하게 작성하는 것을 권장합니다.',
            style: TextStyle(fontSize: 13, color: AppColors.textHint),
          ),
          SizedBox(height: AppSpace.s(12)),
          _Field(
            label: '',
            hint: '역량과 강점을 입력하세요',
            value: data.text,
            readOnly: readOnly,
            maxLines: 5,
            boxed: true,
            onChanged: (v) => onChanged(data.copyWith(text: v)),
          ),
        ],
      ),
    );
  }
}

class _ExperienceSection extends StatelessWidget {
  const _ExperienceSection({
    required this.items,
    required this.readOnly,
    required this.onChanged,
  });

  final List<ResumeExperienceItem> items;
  final bool readOnly;
  final ValueChanged<List<ResumeExperienceItem>> onChanged;

  void _update(int i, ResumeExperienceItem item) {
    final list = [...items];
    list[i] = item;
    onChanged(list);
  }

  @override
  Widget build(BuildContext context) {
    return _FlatSection(
      title: AppConstants.resumeSectionLabels['experience']!,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          ...items.asMap().entries.map((e) {
            final i = e.key;
            final item = e.value;
            return _ItemCard(
              index: i,
              readOnly: readOnly,
              onDelete: () =>
                  onChanged(items.where((x) => x.id != item.id).toList()),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  _Field(
                    label: '회사명',
                    value: item.company,
                    readOnly: readOnly,
                    onChanged: (v) => _update(i, item.copyWith(company: v)),
                  ),
                  _Field(
                    label: '직무',
                    value: item.role,
                    readOnly: readOnly,
                    onChanged: (v) => _update(i, item.copyWith(role: v)),
                  ),
                  _Field(
                    label: '시작일',
                    value: item.startDate,
                    readOnly: readOnly,
                    onChanged: (v) => _update(i, item.copyWith(startDate: v)),
                  ),
                  _Field(
                    label: '종료일',
                    value: item.endDate,
                    readOnly: readOnly,
                    onChanged: (v) => _update(i, item.copyWith(endDate: v)),
                  ),
                  if (!readOnly)
                    CheckboxListTile(
                      contentPadding: EdgeInsets.zero,
                      value: item.isCurrent,
                      title: const Text('재직 중'),
                      onChanged: (v) =>
                          _update(i, item.copyWith(isCurrent: v ?? false)),
                    ),
                  _Field(
                    label: '업무 설명',
                    value: item.description,
                    readOnly: readOnly,
                    maxLines: 3,
                    onChanged: (v) => _update(i, item.copyWith(description: v)),
                  ),
                ],
              ),
            );
          }),
          if (!readOnly)
            _AddButton(
              label: '항목 추가',
              onPressed: () =>
                  onChanged([...items, ResumeExperienceItem.empty()]),
            ),
        ],
      ),
    );
  }
}

class _EducationSection extends StatelessWidget {
  const _EducationSection({
    required this.items,
    required this.readOnly,
    required this.onChanged,
  });

  final List<ResumeEducationItem> items;
  final bool readOnly;
  final ValueChanged<List<ResumeEducationItem>> onChanged;

  void _update(int i, ResumeEducationItem item) {
    final list = [...items];
    list[i] = item;
    onChanged(list);
  }

  @override
  Widget build(BuildContext context) {
    return _FlatSection(
      title: AppConstants.resumeSectionLabels['education']!,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          ...items.asMap().entries.map((e) {
            final i = e.key;
            final item = e.value;
            return _ItemCard(
              index: i,
              readOnly: readOnly,
              onDelete: () =>
                  onChanged(items.where((x) => x.id != item.id).toList()),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  _Field(
                    label: '학교명',
                    value: item.school,
                    readOnly: readOnly,
                    onChanged: (v) => _update(i, item.copyWith(school: v)),
                  ),
                  _Field(
                    label: '전공',
                    value: item.major,
                    readOnly: readOnly,
                    onChanged: (v) => _update(i, item.copyWith(major: v)),
                  ),
                  _Field(
                    label: '시작일',
                    value: item.startDate,
                    readOnly: readOnly,
                    onChanged: (v) => _update(i, item.copyWith(startDate: v)),
                  ),
                  _Field(
                    label: '종료일',
                    value: item.endDate,
                    readOnly: readOnly,
                    onChanged: (v) => _update(i, item.copyWith(endDate: v)),
                  ),
                  _Field(
                    label: '상태 (졸업/재학/수료)',
                    value: item.status,
                    readOnly: readOnly,
                    onChanged: (v) => _update(i, item.copyWith(status: v)),
                  ),
                ],
              ),
            );
          }),
          if (!readOnly)
            _AddButton(
              label: '항목 추가',
              onPressed: () =>
                  onChanged([...items, ResumeEducationItem.empty()]),
            ),
        ],
      ),
    );
  }
}

class _TechStackSection extends StatelessWidget {
  const _TechStackSection({
    required this.items,
    required this.readOnly,
    required this.onChanged,
  });

  final List<ResumeTechStackItem> items;
  final bool readOnly;
  final ValueChanged<List<ResumeTechStackItem>> onChanged;

  @override
  Widget build(BuildContext context) {
    // 기술은 태그로 고르고 숙련도는 설명이 달린 단계로 정한다.
    // 자유 입력 카드 방식은 표기가 제각각이라 공고 키워드 매칭에 잘 안 잡혔다.
    return _FlatSection(
      title: AppConstants.resumeSectionLabels['techStack']!,
      child: TechStackEditor(
        items: items,
        readOnly: readOnly,
        onChanged: onChanged,
      ),
    );
  }
}

class _CertificationsSection extends StatelessWidget {
  const _CertificationsSection({
    required this.items,
    required this.readOnly,
    required this.onChanged,
  });

  final List<ResumeCertificationItem> items;
  final bool readOnly;
  final ValueChanged<List<ResumeCertificationItem>> onChanged;

  void _update(int i, ResumeCertificationItem item) {
    final list = [...items];
    list[i] = item;
    onChanged(list);
  }

  @override
  Widget build(BuildContext context) {
    return _FlatSection(
      title: AppConstants.resumeSectionLabels['certifications']!,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          ...items.asMap().entries.map((e) {
            final i = e.key;
            final item = e.value;
            return _ItemCard(
              index: i,
              readOnly: readOnly,
              onDelete: () =>
                  onChanged(items.where((x) => x.id != item.id).toList()),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  _Field(
                    label: '자격명',
                    value: item.name,
                    readOnly: readOnly,
                    onChanged: (v) => _update(i, item.copyWith(name: v)),
                  ),
                  _Field(
                    label: '발급기관',
                    value: item.issuer,
                    readOnly: readOnly,
                    onChanged: (v) => _update(i, item.copyWith(issuer: v)),
                  ),
                  _Field(
                    label: '취득일',
                    value: item.acquiredDate,
                    readOnly: readOnly,
                    onChanged: (v) =>
                        _update(i, item.copyWith(acquiredDate: v)),
                  ),
                ],
              ),
            );
          }),
          if (!readOnly)
            _AddButton(
              label: '항목 추가',
              onPressed: () =>
                  onChanged([...items, ResumeCertificationItem.empty()]),
            ),
        ],
      ),
    );
  }
}

class _AwardsSection extends StatelessWidget {
  const _AwardsSection({
    required this.items,
    required this.readOnly,
    required this.onChanged,
  });

  final List<ResumeAwardItem> items;
  final bool readOnly;
  final ValueChanged<List<ResumeAwardItem>> onChanged;

  void _update(int i, ResumeAwardItem item) {
    final list = [...items];
    list[i] = item;
    onChanged(list);
  }

  @override
  Widget build(BuildContext context) {
    return _FlatSection(
      title: AppConstants.resumeSectionLabels['awards']!,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          ...items.asMap().entries.map((e) {
            final i = e.key;
            final item = e.value;
            return _ItemCard(
              index: i,
              readOnly: readOnly,
              onDelete: () =>
                  onChanged(items.where((x) => x.id != item.id).toList()),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  _Field(
                    label: '수상명',
                    value: item.name,
                    readOnly: readOnly,
                    onChanged: (v) => _update(i, item.copyWith(name: v)),
                  ),
                  _Field(
                    label: '기관',
                    value: item.organization,
                    readOnly: readOnly,
                    onChanged: (v) =>
                        _update(i, item.copyWith(organization: v)),
                  ),
                  _Field(
                    label: '날짜',
                    value: item.date,
                    readOnly: readOnly,
                    onChanged: (v) => _update(i, item.copyWith(date: v)),
                  ),
                  _Field(
                    label: '설명',
                    value: item.description,
                    readOnly: readOnly,
                    maxLines: 2,
                    onChanged: (v) => _update(i, item.copyWith(description: v)),
                  ),
                ],
              ),
            );
          }),
          if (!readOnly)
            _AddButton(
              label: '항목 추가',
              onPressed: () => onChanged([...items, ResumeAwardItem.empty()]),
            ),
        ],
      ),
    );
  }
}

class _TrainingSection extends StatelessWidget {
  const _TrainingSection({
    required this.items,
    required this.readOnly,
    required this.onChanged,
  });

  final List<ResumeTrainingItem> items;
  final bool readOnly;
  final ValueChanged<List<ResumeTrainingItem>> onChanged;

  void _update(int i, ResumeTrainingItem item) {
    final list = [...items];
    list[i] = item;
    onChanged(list);
  }

  @override
  Widget build(BuildContext context) {
    return _FlatSection(
      title: AppConstants.resumeSectionLabels['trainingExperience']!,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          ...items.asMap().entries.map((e) {
            final i = e.key;
            final item = e.value;
            return _ItemCard(
              index: i,
              readOnly: readOnly,
              onDelete: () =>
                  onChanged(items.where((x) => x.id != item.id).toList()),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  _Field(
                    label: '과정명',
                    value: item.course,
                    readOnly: readOnly,
                    onChanged: (v) => _update(i, item.copyWith(course: v)),
                  ),
                  _Field(
                    label: '기관',
                    value: item.organization,
                    readOnly: readOnly,
                    onChanged: (v) =>
                        _update(i, item.copyWith(organization: v)),
                  ),
                  _Field(
                    label: '시작일',
                    value: item.startDate,
                    readOnly: readOnly,
                    onChanged: (v) => _update(i, item.copyWith(startDate: v)),
                  ),
                  _Field(
                    label: '종료일',
                    value: item.endDate,
                    readOnly: readOnly,
                    onChanged: (v) => _update(i, item.copyWith(endDate: v)),
                  ),
                  _Field(
                    label: '설명',
                    value: item.description,
                    readOnly: readOnly,
                    maxLines: 2,
                    onChanged: (v) => _update(i, item.copyWith(description: v)),
                  ),
                ],
              ),
            );
          }),
          if (!readOnly)
            _AddButton(
              label: '항목 추가',
              onPressed: () =>
                  onChanged([...items, ResumeTrainingItem.empty()]),
            ),
        ],
      ),
    );
  }
}

class _ActivitiesSection extends StatelessWidget {
  const _ActivitiesSection({
    required this.items,
    required this.readOnly,
    required this.onChanged,
  });

  final List<ResumeActivityItem> items;
  final bool readOnly;
  final ValueChanged<List<ResumeActivityItem>> onChanged;

  void _update(int i, ResumeActivityItem item) {
    final list = [...items];
    list[i] = item;
    onChanged(list);
  }

  @override
  Widget build(BuildContext context) {
    return _FlatSection(
      title: AppConstants.resumeSectionLabels['otherActivities']!,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          ...items.asMap().entries.map((e) {
            final i = e.key;
            final item = e.value;
            return _ItemCard(
              index: i,
              readOnly: readOnly,
              onDelete: () =>
                  onChanged(items.where((x) => x.id != item.id).toList()),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  _Field(
                    label: '활동명',
                    value: item.name,
                    readOnly: readOnly,
                    onChanged: (v) => _update(i, item.copyWith(name: v)),
                  ),
                  _Field(
                    label: '시작일',
                    value: item.startDate,
                    readOnly: readOnly,
                    onChanged: (v) => _update(i, item.copyWith(startDate: v)),
                  ),
                  _Field(
                    label: '종료일',
                    value: item.endDate,
                    readOnly: readOnly,
                    onChanged: (v) => _update(i, item.copyWith(endDate: v)),
                  ),
                  _Field(
                    label: '설명',
                    value: item.description,
                    readOnly: readOnly,
                    maxLines: 2,
                    onChanged: (v) => _update(i, item.copyWith(description: v)),
                  ),
                ],
              ),
            );
          }),
          if (!readOnly)
            _AddButton(
              label: '항목 추가',
              onPressed: () =>
                  onChanged([...items, ResumeActivityItem.empty()]),
            ),
        ],
      ),
    );
  }
}

class _ProjectsSection extends StatelessWidget {
  const _ProjectsSection({
    required this.items,
    required this.readOnly,
    required this.onChanged,
  });

  final List<ResumeProjectItem> items;
  final bool readOnly;
  final ValueChanged<List<ResumeProjectItem>> onChanged;

  void _update(int i, ResumeProjectItem item) {
    final list = [...items];
    list[i] = item;
    onChanged(list);
  }

  @override
  Widget build(BuildContext context) {
    return _FlatSection(
      title: AppConstants.resumeSectionLabels['projects']!,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          ...items.asMap().entries.map((e) {
            final i = e.key;
            final item = e.value;
            return _ItemCard(
              index: i,
              readOnly: readOnly,
              onDelete: () =>
                  onChanged(items.where((x) => x.id != item.id).toList()),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  _Field(
                    label: '프로젝트명',
                    value: item.name,
                    readOnly: readOnly,
                    onChanged: (v) => _update(i, item.copyWith(name: v)),
                  ),
                  _Field(
                    label: '시작일',
                    value: item.startDate,
                    readOnly: readOnly,
                    onChanged: (v) => _update(i, item.copyWith(startDate: v)),
                  ),
                  _Field(
                    label: '종료일',
                    value: item.endDate,
                    readOnly: readOnly,
                    onChanged: (v) => _update(i, item.copyWith(endDate: v)),
                  ),
                  _Field(
                    label: '역할',
                    value: item.role,
                    readOnly: readOnly,
                    onChanged: (v) => _update(i, item.copyWith(role: v)),
                  ),
                  _Field(
                    label: '기술스택',
                    value: item.techStack,
                    readOnly: readOnly,
                    onChanged: (v) => _update(i, item.copyWith(techStack: v)),
                  ),
                  _Field(
                    label: '설명',
                    value: item.description,
                    readOnly: readOnly,
                    // 프로젝트 설명은 긴 문장을 쓰는 자리라 내부 스크롤 대신
                    // 내용 높이만큼 늘어나도록 한다.
                    minLines: 3,
                    maxLines: null,
                    scrollPhysics: const NeverScrollableScrollPhysics(),
                    onChanged: (v) => _update(i, item.copyWith(description: v)),
                  ),
                  _Field(
                    label: 'URL (선택)',
                    value: item.url,
                    readOnly: readOnly,
                    keyboardType: TextInputType.url,
                    onChanged: (v) => _update(i, item.copyWith(url: v)),
                  ),
                ],
              ),
            );
          }),
          if (!readOnly)
            _AddButton(
              label: '프로젝트 추가',
              onPressed: () => onChanged([...items, ResumeProjectItem.empty()]),
            ),
        ],
      ),
    );
  }
}

class _SelfIntroSection extends StatelessWidget {
  const _SelfIntroSection({
    required this.data,
    required this.readOnly,
    required this.onChanged,
  });

  final ResumeSelfIntroduction data;
  final bool readOnly;
  final ValueChanged<ResumeSelfIntroduction> onChanged;

  @override
  Widget build(BuildContext context) {
    return _FlatSection(
      title: AppConstants.resumeSectionLabels['selfIntroduction']!,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: ResumeSelfIntroLabels.keys.map((key) {
          final section = data.sectionByKey(key);
          final label = ResumeSelfIntroLabels.labels[key]!;
          return Padding(
            padding: EdgeInsets.only(bottom: AppSpace.s(16)),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  label,
                  style: const TextStyle(fontWeight: FontWeight.w600),
                ),
                SizedBox(height: AppSpace.s(8)),
                _Field(
                  label: '부제목',
                  hint: '부제목을 작성하세요',
                  value: section.subtitle,
                  readOnly: readOnly,
                  onChanged: (v) => onChanged(
                    data.copyWithSection(key, section.copyWith(subtitle: v)),
                  ),
                ),
                _Field(
                  label: '상세 내용',
                  hint: '상세 내용을 작성해주세요.',
                  value: section.body,
                  readOnly: readOnly,
                  maxLines: 5,
                  onChanged: (v) => onChanged(
                    data.copyWithSection(key, section.copyWith(body: v)),
                  ),
                ),
                const Divider(),
              ],
            ),
          );
        }).toList(),
      ),
    );
  }
}
