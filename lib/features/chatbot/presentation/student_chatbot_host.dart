import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter_markdown_plus/flutter_markdown_plus.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/theme/app_colors.dart';
import '../../../shared/constants/ai_ops_types.dart';
import '../../../shared/demo/demo_accounts.dart';
import '../../../shared/models/user_model.dart';
import '../../../shared/providers/firebase_providers.dart';
import '../../../shared/services/ai_ops_service.dart';
import '../data/demo_student_chatbot_api_client.dart';
import '../data/student_chatbot_api_client.dart';
import 'robot_head_icon.dart';
import '../../../core/theme/app_space.dart';

class StudentChatbotHost extends ConsumerStatefulWidget {
  const StudentChatbotHost({
    super.key,
    required this.user,
    required this.child,
    this.apiClient,
  });

  final UserModel user;
  final Widget child;
  final StudentChatbotApiClient? apiClient;

  @override
  ConsumerState<StudentChatbotHost> createState() => _StudentChatbotHostState();
}

class _StudentChatbotHostState extends ConsumerState<StudentChatbotHost> {
  /// 로봇에 마우스를 올렸을 때 나오는 인사말.
  static const _greeting = '안녕하세요! 궁금한 점이 있으신가요? 저를 눌러 주세요!';

  static const Map<String, String> _faqAnswers = {
    '출결 기준': '''**출결 기준**

- **출석**: 정규수업 8시간을 모두 수강한 경우
- **결석**: 정규수업의 50%인 4시간 미만을 수강한 경우
- **지각·조퇴·외출**: 4시간 이상 8시간 미만을 수강한 경우
- 단위기간 내 지각·조퇴·외출 합계 3회는 결석 1일로 처리돼요.
- 단위기간 출석률 50% 미만 또는 전체 훈련기간 출석률 80% 미만이면 제적 대상이에요.''',
    '공가 사용 방법': '''**공가 사용 방법**

1. 공가 사용 당일 출결이슈 구글폼으로 일정을 공유해 주세요.
2. 다음 출석일 16:50에 라운지에서 증빙서류를 제출해 주세요.
3. 출석입력대장에 서명해 주세요.

훈련·시험, 면접, 예비군, 병가, 휴가 등이 증빙 제출 시 공가로 인정될 수 있어요.''',
    '캠퍼스 운영 시간': '''캠퍼스 운영 시간은 **오전 8:30부터 오후 9:50까지**예요.

공식 오픈 시간은 오전 8:30이며, 일찍 출근한 직원이 있는 경우 더 일찍 열릴 수 있어요.''',
    '훈련장려금': '''훈련장려금은 **단위기간 출석률 80% 이상**이 지급 기준이에요.

단위기간 종료 후 공가 등 출석 증빙이 반영되면 비용 신청이 진행돼요. 실업급여 등 다른 지원금 수급이나 취업 상태에 따라 지급 대상에서 제외될 수 있어요.''',
    '프로젝트 레퍼런스':
        '''이전 기수의 단위·최종 프로젝트에서 **주제, 기획 설명, 활용 데이터·기술, GitHub 주소**를 찾아볼 수 있어요.

원하는 기수·차수·개수를 함께 적어 주세요. 예: “25기 3차 프로젝트 주제 5개와 핵심 기술을 알려줘”''',

    '질문 가이드': '''**질문할 수 있는 내용**

- LMS 정책·FAQ, 출결·공가, 훈련장려금, 교육 일정
- 캠퍼스 운영 공지와 이전 기수 프로젝트 레퍼런스

**질문하는 방법**

질문의 대상과 조건을 함께 적어 주세요. 기수·차수·단위기간·날짜·원하는 개수를 넣으면 더 정확하게 안내할 수 있어요.

- 공지: “34기 라운지 취식 가능 여부를 알려줘”
- 출결: “3단위기간 출석률 85%면 훈련장려금을 받을 수 있어?”
- 프로젝트: “25기 3차 프로젝트 주제 5개와 핵심 기술을 알려줘”
- 최종 프로젝트: “34기 최종 프로젝트 레퍼런스 3개를 비교해줘”

검색 근거가 없는 내용이나 LMS와 관련 없는 질문에는 답변하기 어려워요.''',
  };

  static const Map<String, Map<String, String>> _faqFollowUps = {
    '출결 기준': {
      '지각·조퇴·외출은 어떻게 처리돼?':
          '''정규수업 8시간 중 **4시간 이상 8시간 미만**을 수강하면 지각·조퇴·외출로 처리돼요.

단위기간 안에서 지각·조퇴·외출을 합쳐 **3회가 되면 결석 1일**로 환산돼요.''',
      '출석률이 낮으면 어떻게 돼?':
          '''단위기간 출석률이 **50% 미만**이거나 전체 훈련기간 출석률이 **80% 미만**이면 제적 대상이 될 수 있어요.

실제 처리는 출결 증빙 반영 여부를 포함해 담당자에게 확인해 주세요.''',
    },
    '공가 사용 방법': {
      '공가는 어떤 순서로 신청해?':
          '''공가 당일 출결이슈 구글폼으로 일정을 공유하고, 다음 출석일 **16:50**에 라운지에서 증빙서류를 제출한 뒤 출석입력대장에 서명해 주세요.''',
      '어떤 사유가 공가로 인정돼?': '''훈련·시험, 면접, 예비군, 병가, 휴가 등이 증빙서류 제출 시 공가로 인정될 수 있어요.

사유별 인정 범위와 필요한 서류는 다를 수 있으므로 제출 전에 담당자에게 확인해 주세요.''',
    },
    '캠퍼스 운영 시간': {
      '캠퍼스는 몇 시부터 이용할 수 있어?': '''캠퍼스 운영 시간은 **오전 8:30부터 오후 9:50까지**예요.

공식 오픈 시간은 오전 8:30이며, 직원 출근 상황에 따라 조금 일찍 열릴 수 있어요.''',
      '캠퍼스 흡연 공간은 어디야?':
          '''흡연은 캠퍼스 내부가 아니라 **건물 외부 1층 또는 18층 옥상 흡연 공간**을 이용해 주세요.''',
    },
    '훈련장려금': {
      '훈련장려금의 출석률 기준은 뭐야?': '''훈련장려금은 해당 단위기간의 출석률이 **80% 이상**이어야 지급 기준을 충족해요.

공가 등 출석 증빙이 모두 반영된 뒤 최종 출석률을 확인해 주세요.''',
      '출석률이 80%면 무조건 지급돼?': '''출석률 80% 이상은 기본 기준이지만 **지급 확정을 의미하지는 않아요**.

실업급여·다른 지원금 수급 여부와 취업 상태 등에 따라 지급 대상에서 제외될 수 있어요.''',
    },
    '프로젝트 레퍼런스': {
      '프로젝트를 정확히 검색하려면 어떻게 물어봐?': '''**기수·프로젝트 차수·원하는 개수**를 함께 적어 주세요.

예: “25기 3차 프로젝트 주제 10개와 사용 기술을 알려줘”''',
      '최종 프로젝트는 어떻게 질문해?': '''“34기 **최종 프로젝트** 주제 5개와 GitHub 주소를 알려줘”처럼 질문해 주세요.

‘최종 프로젝트’ 또는 ‘final project’라고 입력하면 최종 프로젝트 기준으로 검색해요.''',
    },
  };

  late StudentChatbotApiClient _api;
  late bool _ownsApi;
  late String _threadId;
  final _messages = <_ChatMessage>[];
  final _questionController = TextEditingController();
  final _searchController = TextEditingController();
  final _scrollController = ScrollController();
  Map<String, String> _faqChoices = _faqAnswers;
  bool _open = false;
  bool _hoveringLauncher = false;
  int _robotBounce = 0;
  bool _searching = false;
  bool _initializing = false;
  bool _ready = false;
  bool _answering = false;
  double? _panelWidth;
  double? _panelHeight;
  String? _error;

  @override
  void initState() {
    super.initState();
    _threadId = _newThreadId();
    _ownsApi = widget.apiClient == null;
    _api =
        widget.apiClient ??
        (DemoConfig.enabled
            ? DemoStudentChatbotApiClient()
            : StudentChatbotApiClient(
                token: () async =>
                    await ref.read(firebaseAuthProvider).currentUser?.getIdToken(),
              ));
    if (widget.user.isStudent) _initialize();
  }

  @override
  void didUpdateWidget(covariant StudentChatbotHost oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.user.uid != widget.user.uid && widget.user.isStudent) {
      _newChat();
    }
  }

  @override
  void dispose() {
    if (_ownsApi) _api.close();
    _questionController.dispose();
    _searchController.dispose();
    _scrollController.dispose();
    super.dispose();
  }

  String _newThreadId() => DateTime.now().microsecondsSinceEpoch.toString();

  Future<void> _initialize() async {
    setState(() {
      _initializing = true;
      _ready = false;
      _error = null;
    });
    try {
      await _api.initialize(_threadId);
      if (!mounted) return;
      setState(() {
        _ready = true;
        _faqChoices = _faqAnswers;
        _messages
          ..clear()
          ..add(
            const _ChatMessage(
              text: '안녕하세요! LMS 정책, 공지, 출결과 이전 기수 프로젝트를 도와드릴게요.',
              fromUser: false,
            ),
          );
      });
    } catch (error) {
      if (mounted) {
        setState(
          () => _error = error.toString().replaceFirst('FormatException: ', ''),
        );
      }
    } finally {
      if (mounted) setState(() => _initializing = false);
    }
  }

  Future<void> _newChat() async {
    if (_answering) return;
    _threadId = _newThreadId();
    _searchController.clear();
    _searching = false;
    await _initialize();
  }

  void _showFaq(String label, String answer) {
    if (!_ready || _answering) return;
    final followUps = _faqFollowUps[label];
    setState(() {
      _messages
        ..add(
          _ChatMessage(
            text: label.endsWith('?') ? label : '$label을 알려주세요.',
            fromUser: true,
          ),
        )
        ..add(_ChatMessage(text: answer, fromUser: false));
      if (label == '질문 가이드') {
        _faqChoices = _faqAnswers;
      } else if (followUps != null) {
        _faqChoices = {
          '질문 가이드': _faqAnswers['질문 가이드']!,
          ...followUps,
        };
      }
    });
    _scrollToBottom();
  }

  Future<void> _send([String? preset]) async {
    final question = (preset ?? _questionController.text).trim();
    if (question.isEmpty || !_ready || _answering) return;
    _questionController.clear();
    setState(() {
      _faqChoices = _faqAnswers;
      _answering = true;
      _error = null;
      _messages
        ..add(_ChatMessage(text: question, fromUser: true))
        ..add(const _ChatMessage(text: '', fromUser: false));
    });
    _scrollToBottom();

    try {
      await for (final chunk in _api.ask(
        threadId: _threadId,
        question: question,
      )) {
        if (!mounted) return;
        setState(() {
          final current = _messages.last;
          _messages[_messages.length - 1] = current.copyWith(
            text: current.text + chunk,
          );
        });
        _scrollToBottom();
      }
      if (mounted && _messages.last.text.isEmpty) {
        setState(
          () => _messages[_messages.length - 1] = const _ChatMessage(
            text: '답변을 생성하지 못했습니다. 다시 시도해 주세요.',
            fromUser: false,
          ),
        );
      } else if (mounted) {
        final ops = _api.lastOps;
        if (ops != null && ops.logId.isNotEmpty) {
          setState(() {
            final current = _messages.last;
            _messages[_messages.length - 1] = current.copyWith(
              logId: ops.logId,
              promptVersion: ops.promptVersion,
            );
          });
        }
      }
    } catch (error) {
      if (!mounted) return;
      setState(
        () => _messages[_messages.length - 1] = _ChatMessage(
          text: error.toString().replaceFirst('FormatException: ', ''),
          fromUser: false,
          isError: true,
        ),
      );
    } finally {
      if (mounted) setState(() => _answering = false);
      _scrollToBottom();
    }
  }

  Future<void> _onFeedback(int index, String outcome) async {
    if (DemoConfig.enabled || index < 0 || index >= _messages.length) return;
    final message = _messages[index];
    final logId = message.logId;
    if (logId == null || logId.isEmpty || message.feedbackOutcome != null) {
      return;
    }
    setState(() {
      _messages[index] = message.copyWith(feedbackOutcome: outcome);
    });
    await ref.read(aiOpsServiceProvider).recordOutcome(
      cohortId: widget.user.cohortId,
      logId: logId,
      outcome: outcome,
      promptVersion: message.promptVersion,
      type: AiOpsTypes.studentChatbot,
    );
  }

  void _scrollToBottom() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_scrollController.hasClients) {
        _scrollController.animateTo(
          _scrollController.position.maxScrollExtent,
          duration: const Duration(milliseconds: 180),
          curve: Curves.easeOut,
        );
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    if (!widget.user.isStudent) return widget.child;
    return LayoutBuilder(
      builder: (context, constraints) {
        final compact = constraints.maxWidth < 600;
        const launcherSize = 112.0;
        const launcherBottom = 4.0;
        const panelBottom = launcherBottom + launcherSize + 8;
        final maxWidth = compact
            ? constraints.maxWidth - 24
            : constraints.maxWidth / 2;
        final minWidth = math.min(320.0, maxWidth);
        final defaultWidth = compact ? maxWidth : math.min(390.0, maxWidth);
        final maxHeight = math.max(
          0.0,
          constraints.maxHeight - panelBottom - 16,
        );
        final minHeight = math.min(420.0, maxHeight);
        final width = (_panelWidth ?? defaultWidth)
            .clamp(minWidth, maxWidth)
            .toDouble();
        final height = (_panelHeight ?? math.min(640.0, maxHeight))
            .clamp(minHeight, maxHeight)
            .toDouble();
        return Stack(
          clipBehavior: Clip.none,
          children: [
            Positioned.fill(child: widget.child),
            if (_open)
              Positioned(
                right: compact ? 12 : 20,
                bottom: panelBottom,
                child: _ChatPanel(
                  width: width,
                  height: height,
                  messages: _filteredMessages,
                  searchQuery: _searching ? _searchController.text.trim() : '',
                  questionController: _questionController,
                  searchController: _searchController,
                  scrollController: _scrollController,
                  faqAnswers: _faqChoices,
                  searching: _searching,
                  initializing: _initializing,
                  answering: _answering,
                  ready: _ready,
                  error: _error,
                  onClose: () => setState(() => _open = false),
                  onToggleSearch: () => setState(() {
                    _searching = !_searching;
                    if (!_searching) _searchController.clear();
                  }),
                  onSearchChanged: (_) => setState(() {}),
                  onNewChat: _newChat,
                  onRetry: _initialize,
                  onSend: _send,
                  onFaq: _showFaq,
                  onFeedback: DemoConfig.enabled ? null : _onFeedback,
                  onResize: (size) => setState(() {
                    _panelWidth = size.width
                        .clamp(minWidth, maxWidth)
                        .toDouble();
                    _panelHeight = size.height
                        .clamp(minHeight, maxHeight)
                        .toDouble();
                  }),
                ),
              ),
            Positioned(
              key: const ValueKey('student-chatbot-greeting'),
              right: (compact ? 6 : 8) + launcherSize - 14,
              bottom: launcherBottom + 38,
              child: _LauncherGreeting(
                visible: _hoveringLauncher && !_open,
                text: _greeting,
              ),
            ),
            Positioned(
              key: const ValueKey('student-chatbot-launcher'),
              right: compact ? 6 : 8,
              bottom: launcherBottom,
              child: MouseRegion(
                onEnter: (_) => setState(() => _hoveringLauncher = true),
                onExit: (_) => setState(() => _hoveringLauncher = false),
                child: SizedBox.square(
                  dimension: launcherSize,
                  // 툴팁을 떼고 이름만 붙인다. 툴팁이 말풍선과 같이 뜨면 같은
                  // 자리에서 같은 말을 두 번 하는 꼴이고, 한쪽 상태에만 달면
                  // FloatingActionButton이 툴팁을 끼우고 빼면서 그 아래 로봇까지
                  // 새로 만든다 — 누를 때마다 하던 늘어남 동작이 끊긴다.
                  // 화면 낭독기에는 label이 버튼에 합쳐져 그대로 읽힌다.
                  child: MergeSemantics(
                    child: Semantics(
                      label: _open ? '챗봇 닫기' : '학생 챗봇 열기',
                      // 누르는 동안 칠해지는 강조색은 버튼 설정에 없어 테마로 끈다.
                      child: Theme(
                        data: Theme.of(
                          context,
                        ).copyWith(highlightColor: Colors.transparent),
                        child: FloatingActionButton(
                          heroTag: 'student-chatbot',
                          tooltip: null,
                          backgroundColor: Colors.transparent,
                          elevation: 0,
                          hoverElevation: 0,
                          focusElevation: 0,
                          highlightElevation: 0,
                          disabledElevation: 0,
                          splashColor: Colors.transparent,
                          // 마우스를 올리거나 누르면 로봇 둘레에 사각형이 칠해졌다. 호버는 말풍선이 알려 준다.
                          // 키보드 포커스 표시는 남긴다.
                          hoverColor: Colors.transparent,
                          onPressed: () => setState(() {
                            _robotBounce++;
                            _open = !_open;
                          }),
                          child: RobotHeadIcon(size: 104, bounce: _robotBounce),
                        ),
                      ),
                    ),
                  ),
                ),
              ),
            ),
          ],
        );
      },
    );
  }

  List<_ChatMessage> get _filteredMessages {
    final query = _searchController.text.trim().toLowerCase();
    if (!_searching || query.isEmpty) return _messages;
    return _messages
        .where((message) => message.text.toLowerCase().contains(query))
        .toList();
  }
}

class _ChatPanel extends StatelessWidget {
  const _ChatPanel({
    required this.width,
    required this.height,
    required this.messages,
    required this.searchQuery,
    required this.questionController,
    required this.searchController,
    required this.scrollController,
    required this.faqAnswers,
    required this.searching,
    required this.initializing,
    required this.answering,
    required this.ready,
    required this.error,
    required this.onClose,
    required this.onToggleSearch,
    required this.onSearchChanged,
    required this.onNewChat,
    required this.onRetry,
    required this.onSend,
    required this.onFaq,
    this.onFeedback,
    required this.onResize,
  });

  final double width;
  final double height;
  final List<_ChatMessage> messages;
  final String searchQuery;
  final TextEditingController questionController;
  final TextEditingController searchController;
  final ScrollController scrollController;
  final Map<String, String> faqAnswers;
  final bool searching;
  final bool initializing;
  final bool answering;
  final bool ready;
  final String? error;
  final VoidCallback onClose;
  final VoidCallback onToggleSearch;
  final ValueChanged<String> onSearchChanged;
  final VoidCallback onNewChat;
  final VoidCallback onRetry;
  final ValueChanged<String?> onSend;
  final void Function(String label, String answer) onFaq;
  final void Function(int index, String outcome)? onFeedback;
  final ValueChanged<Size> onResize;

  void _resizeToPointer(
    BuildContext context,
    DragUpdateDetails details, {
    required bool horizontal,
    required bool vertical,
  }) {
    final panel = context.findRenderObject();
    if (panel is! RenderBox) return;

    final bottomRight = panel.localToGlobal(
      Offset(panel.size.width, panel.size.height),
    );
    onResize(
      Size(
        horizontal ? bottomRight.dx - details.globalPosition.dx : width,
        vertical ? bottomRight.dy - details.globalPosition.dy : height,
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Material(
      key: const Key('student-chatbot-panel'),
      elevation: 18,
      borderRadius: BorderRadius.circular(18),
      clipBehavior: Clip.antiAlias,
      color: AppColors.surface,
      child: SizedBox(
        width: width,
        height: height,
        child: Stack(
          children: [
            Positioned.fill(
              child: Column(
                children: [
                  _header(context),
                  if (searching)
                    Padding(
                      padding: EdgeInsets.fromLTRB(AppSpace.s(12), AppSpace.s(10), AppSpace.s(12), AppSpace.s(0)),
                      child: TextField(
                        controller: searchController,
                        autofocus: true,
                        onChanged: onSearchChanged,
                        decoration: const InputDecoration(
                          isDense: true,
                          prefixIcon: Icon(Icons.search_rounded, size: 20),
                          hintText: '현재 채팅 기록 검색',
                        ),
                      ),
                    ),
                  Expanded(child: _body()),
                  _input(),
                  Padding(
                    padding: EdgeInsets.only(bottom: AppSpace.s(9)),
                    child: Text(
                      '챗봇은 실수할 수 있습니다',
                      style: TextStyle(
                        fontSize: 10,
                        color: AppColors.textSecondary,
                      ),
                    ),
                  ),
                ],
              ),
            ),
            Positioned(
              left: 0,
              top: 16,
              bottom: 0,
              width: 6,
              child: _resizeSurface(
                key: const Key('chatbot-resize-left'),
                cursor: SystemMouseCursors.resizeLeftRight,
                onPanUpdate: (details) => _resizeToPointer(
                  context,
                  details,
                  horizontal: true,
                  vertical: false,
                ),
              ),
            ),
            Positioned(
              left: 16,
              top: 0,
              right: 0,
              height: 6,
              child: _resizeSurface(
                key: const Key('chatbot-resize-top'),
                cursor: SystemMouseCursors.resizeUpDown,
                onPanUpdate: (details) => _resizeToPointer(
                  context,
                  details,
                  horizontal: false,
                  vertical: true,
                ),
              ),
            ),
            Positioned(
              left: 0,
              top: 0,
              width: 16,
              height: 16,
              child: _resizeSurface(
                key: const Key('chatbot-resize-corner'),
                cursor: SystemMouseCursors.resizeUpLeftDownRight,
                onPanUpdate: (details) => _resizeToPointer(
                  context,
                  details,
                  horizontal: true,
                  vertical: true,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _header(BuildContext context) => Container(
    height: AppSpace.row(58),
    padding: EdgeInsets.symmetric(horizontal: AppSpace.s(14)),
    color: Theme.of(context).colorScheme.primary,
    child: Row(
      children: [
        const SizedBox.square(
          dimension: 44,
          child: Center(child: RobotHeadIcon(size: 44)),
        ),
        SizedBox(width: AppSpace.s(9)),
        Expanded(
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                'PLAYDATA 챗봇',
                style: TextStyle(
                  color: Colors.white,
                  fontWeight: FontWeight.w700,
                ),
              ),
              Text(
                '● 온라인',
                style: TextStyle(color: Colors.white70, fontSize: 10),
              ),
            ],
          ),
        ),
        _headerButton(Icons.search_rounded, '기록 검색', onToggleSearch),
        _headerButton(Icons.add_rounded, '새 채팅', onNewChat),
        _headerButton(Icons.close_rounded, '닫기', onClose),
      ],
    ),
  );

  Widget _headerButton(IconData icon, String tooltip, VoidCallback onPressed) =>
      IconButton(
        tooltip: tooltip,
        onPressed: onPressed,
        visualDensity: VisualDensity.compact,
        icon: Icon(icon, size: 20, color: Colors.white),
      );

  Widget _resizeSurface({
    required Key key,
    required MouseCursor cursor,
    required GestureDragUpdateCallback onPanUpdate,
  }) => MouseRegion(
    key: key,
    cursor: cursor,
    child: GestureDetector(
      behavior: HitTestBehavior.opaque,
      onPanUpdate: onPanUpdate,
    ),
  );

  Widget _body() {
    if (initializing) {
      return const _ChatLoading(
        initialLabel: '학생 정보를 불러오는 중입니다...',
        centered: true,
      );
    }
    if (error != null && !ready) {
      return Center(
        child: Padding(
          padding: EdgeInsets.all(AppSpace.s(24)),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(
                Icons.error_outline_rounded,
                color: AppColors.error,
                size: 32,
              ),
              SizedBox(height: AppSpace.s(10)),
              Text(error!, textAlign: TextAlign.center),
              SizedBox(height: AppSpace.s(12)),
              OutlinedButton.icon(
                onPressed: onRetry,
                icon: const Icon(Icons.refresh),
                label: const Text('다시 시도'),
              ),
            ],
          ),
        ),
      );
    }
    return Column(
      children: [
        Expanded(
          child: messages.isEmpty
              ? Center(
                  child: Text(
                    '검색 결과가 없습니다.',
                    style: TextStyle(color: AppColors.textSecondary),
                  ),
                )
              : ListView.separated(
                  controller: scrollController,
                  padding: EdgeInsets.all(AppSpace.s(12)),
                  itemCount: messages.length,
                  separatorBuilder: (_, _) => SizedBox(height: AppSpace.s(10)),
                  itemBuilder: (context, index) {
                    final message = messages[index];
                    if (answering &&
                        index == messages.length - 1 &&
                        !message.fromUser &&
                        message.text.isEmpty) {
                      return const _ChatLoading(
                        initialLabel: '챗봇이 정보를 검색 중입니다...',
                        nextLabel: '챗봇이 답변을 생성하는 중입니다...',
                      );
                    }
                    final showFaq =
                        !searching &&
                        !answering &&
                        faqAnswers.isNotEmpty &&
                        index == messages.length - 1 &&
                        !message.fromUser &&
                        !message.isError &&
                        message.text.isNotEmpty;
                    return Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        _MessageBubble(
                          message: message,
                          highlight: searchQuery,
                        ),
                        if (!message.fromUser &&
                            !message.isError &&
                            !answering &&
                            message.logId != null &&
                            message.logId!.isNotEmpty)
                          _FeedbackRow(
                            outcome: message.feedbackOutcome,
                            onHelpful: onFeedback == null
                                ? null
                                : () => onFeedback!(
                                    index,
                                    AiOpsOutcomes.helpful,
                                  ),
                            onNotHelpful: onFeedback == null
                                ? null
                                : () => onFeedback!(
                                    index,
                                    AiOpsOutcomes.notHelpful,
                                  ),
                          ),
                        if (showFaq) _faqButtons(),
                      ],
                    );
                  },
                ),
        ),
      ],
    );
  }

  Widget _faqButtons() => Padding(
    padding: EdgeInsets.only(left: AppSpace.s(35), top: AppSpace.s(8)),
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          '자주 묻는 질문',
          style: TextStyle(
            color: AppColors.textSecondary,
            fontSize: 11,
            fontWeight: FontWeight.w700,
          ),
        ),
        SizedBox(height: AppSpace.s(5)),
        Wrap(
          spacing: 5,
          runSpacing: 5,
          children: faqAnswers.entries
              .map(
                (entry) => ActionChip(
                  avatar: const Icon(Icons.help_outline_rounded, size: 16),
                  label: Text(
                    entry.key,
                    style: const TextStyle(fontSize: 11),
                  ),
                  onPressed: () => onFaq(entry.key, entry.value),
                ),
              )
              .toList(),
        ),
      ],
    ),
  );

  Widget _input() => Padding(
    padding: EdgeInsets.fromLTRB(AppSpace.s(10), AppSpace.s(8), AppSpace.s(10), AppSpace.s(6)),
    child: TextField(
      controller: questionController,
      enabled: ready && !answering,
      textInputAction: TextInputAction.send,
      onSubmitted: (_) => onSend(null),
      decoration: InputDecoration(
        isDense: true,
        hintText: '메시지를 입력하세요',
        suffixIcon: IconButton(
          tooltip: '질문 보내기',
          onPressed: ready && !answering ? () => onSend(null) : null,
          icon: const Icon(Icons.send_rounded),
        ),
      ),
    ),
  );
}

class _ChatLoading extends StatefulWidget {
  const _ChatLoading({
    required this.initialLabel,
    this.nextLabel,
    this.centered = false,
  });

  final String initialLabel;
  final String? nextLabel;
  final bool centered;

  @override
  State<_ChatLoading> createState() => _ChatLoadingState();
}

class _ChatLoadingState extends State<_ChatLoading>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller;
  Timer? _labelTimer;
  var _showNextLabel = false;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 900),
    )..repeat();
    if (widget.nextLabel != null) {
      _labelTimer = Timer(const Duration(milliseconds: 1600), () {
        if (mounted) setState(() => _showNextLabel = true);
      });
    }
  }

  @override
  void dispose() {
    _labelTimer?.cancel();
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final content = Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        Semantics(
          label: '챗봇 응답 대기 중',
          child: AnimatedBuilder(
            animation: _controller,
            builder: (context, _) => Row(
              key: const Key('chatbot-loading-dots'),
              mainAxisSize: MainAxisSize.min,
              children: List.generate(3, (index) {
                final wave = math.sin(
                  (_controller.value * math.pi * 2) - (index * 0.8),
                );
                return Transform.translate(
                  offset: Offset(0, -4 * wave),
                  child: Container(
                    width: 7,
                    height: 7,
                    margin: EdgeInsets.symmetric(horizontal: AppSpace.s(3)),
                    decoration: BoxDecoration(
                      color: AppColors.primary,
                      shape: BoxShape.circle,
                    ),
                  ),
                );
              }),
            ),
          ),
        ),
        SizedBox(height: AppSpace.s(12)),
        AnimatedSwitcher(
          duration: const Duration(milliseconds: 220),
          child: Text(
            _showNextLabel ? widget.nextLabel! : widget.initialLabel,
            key: ValueKey(_showNextLabel),
            style: TextStyle(
              fontSize: 11,
              color: AppColors.textSecondary,
            ),
          ),
        ),
      ],
    );
    return widget.centered
        ? Center(child: content)
        : Align(alignment: Alignment.centerLeft, child: content);
  }
}

/// 로봇에 마우스를 올리면 옆에서 말을 거는 말풍선.
///
/// 툴팁 대신 쓴다. 툴팁은 "학생 챗봇 열기"처럼 기능 이름만 말하지만, 이 자리에서
/// 필요한 것은 말을 걸어도 된다는 신호다. 손가락으로 쓰는 화면에는 마우스가 없어
/// 뜨지 않는다 — 거기서는 로봇을 누르는 것 말고 할 일이 없어 잃는 것이 없다.
class _LauncherGreeting extends StatelessWidget {
  const _LauncherGreeting({required this.visible, required this.text});

  final bool visible;
  final String text;

  @override
  Widget build(BuildContext context) {
    final duration = MediaQuery.disableAnimationsOf(context)
        ? Duration.zero
        : const Duration(milliseconds: 170);
    // 말풍선은 늘 그 자리에 있고 투명도만 바뀐다. 마우스를 뗐을 때 툭 끊기지 않고
    // 잦아든다. 포인터는 받지 않는다 — 받으면 말풍선 위에서 마우스가 로봇을
    // 벗어난 것이 되어, 떴다 사라졌다 깜빡인다.
    return IgnorePointer(
      child: AnimatedSlide(
        offset: visible ? Offset.zero : const Offset(0.05, 0),
        duration: duration,
        curve: Curves.easeOut,
        child: AnimatedOpacity(
          opacity: visible ? 1 : 0,
          duration: duration,
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: 208),
                child: Container(
                  padding: EdgeInsets.symmetric(
                    horizontal: AppSpace.s(14),
                    vertical: AppSpace.s(10),
                  ),
                  decoration: BoxDecoration(
                    color: AppColors.surface,
                    borderRadius: BorderRadius.circular(14),
                    border: Border.all(color: AppColors.border),
                    boxShadow: const [
                      BoxShadow(
                        color: Color(0x1F0B2A6F),
                        blurRadius: 14,
                        offset: Offset(0, 4),
                      ),
                    ],
                  ),
                  child: Text(
                    text,
                    style: TextStyle(
                      fontSize: 13,
                      height: 1.35,
                      color: AppColors.textPrimary,
                    ),
                  ),
                ),
              ),
              CustomPaint(
                size: const Size(9, 14),
                painter: const _GreetingTailPainter(),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// 말풍선에서 로봇 쪽으로 뻗는 꼬리.
class _GreetingTailPainter extends CustomPainter {
  const _GreetingTailPainter();

  @override
  void paint(Canvas canvas, Size size) {
    final path = Path()
      ..moveTo(0, 1)
      ..lineTo(size.width, size.height / 2)
      ..lineTo(0, size.height - 1);
    canvas.drawPath(path, Paint()..color = AppColors.surface);
    // 몸통과 같은 테두리를 두 빗변에만 긋는다. 밑변을 그으면 몸통과 꼬리 사이에
    // 선이 하나 생겨 붙어 있지 않은 것처럼 보인다.
    canvas.drawPath(
      path,
      Paint()
        ..color = AppColors.border
        ..style = PaintingStyle.stroke
        ..strokeWidth = 1,
    );
  }

  @override
  bool shouldRepaint(_GreetingTailPainter oldDelegate) => false;
}

class _MessageBubble extends StatelessWidget {
  const _MessageBubble({required this.message, required this.highlight});
  final _ChatMessage message;
  final String highlight;

  @override
  Widget build(BuildContext context) => Row(
    mainAxisAlignment: message.fromUser
        ? MainAxisAlignment.end
        : MainAxisAlignment.start,
    crossAxisAlignment: CrossAxisAlignment.start,
    children: [
      if (!message.fromUser) ...[
        const SizedBox.square(
          dimension: 40,
          child: Center(child: RobotHeadIcon(size: 36)),
        ),
        SizedBox(width: AppSpace.s(7)),
      ],
      Flexible(
        child: Container(
          padding: EdgeInsets.symmetric(horizontal: AppSpace.s(12), vertical: AppSpace.s(9)),
          decoration: BoxDecoration(
            color: message.fromUser
                ? AppColors.primary
                : message.isError
                ? AppColors.error.withValues(alpha: 0.1)
                : AppColors.background,
            borderRadius: BorderRadius.circular(13),
          ),
          child: message.fromUser || message.isError
              ? _HighlightedText(
                  text: message.text,
                  query: highlight,
                  style: TextStyle(
                    color: message.fromUser
                        ? Colors.white
                        : AppColors.textPrimary,
                    fontSize: 13,
                    height: 1.4,
                  ),
                )
              : highlight.isNotEmpty
              ? _HighlightedMarkdown(text: message.text, query: highlight)
              : MarkdownBody(
                  data: message.text,
                  selectable: true,
                  softLineBreak: true,
                  styleSheet: MarkdownStyleSheet(
                    p: TextStyle(
                      color: AppColors.textPrimary,
                      fontSize: 13,
                      height: 1.4,
                    ),
                    listBullet: TextStyle(
                      color: AppColors.textPrimary,
                      fontSize: 13,
                    ),
                    strong: TextStyle(
                      color: AppColors.textPrimary,
                      fontWeight: FontWeight.w800,
                    ),
                    code: TextStyle(
                      color: AppColors.textPrimary,
                      backgroundColor: AppColors.surfaceVariant,
                      fontSize: 12,
                    ),
                  ),
                ),
        ),
      ),
    ],
  );
}

class _FeedbackRow extends StatelessWidget {
  const _FeedbackRow({
    required this.outcome,
    required this.onHelpful,
    required this.onNotHelpful,
  });

  final String? outcome;
  final VoidCallback? onHelpful;
  final VoidCallback? onNotHelpful;

  @override
  Widget build(BuildContext context) {
    final recorded = outcome != null && outcome!.isNotEmpty;
    return Padding(
      padding: EdgeInsets.only(left: AppSpace.s(47), top: AppSpace.s(4)),
      child: recorded
          ? Text(
              outcome == AiOpsOutcomes.helpful ? '도움됨으로 기록됨' : '안 됨으로 기록됨',
              style: TextStyle(
                fontSize: 11,
                color: AppColors.textSecondary,
              ),
            )
          : Wrap(
              spacing: 4,
              children: [
                TextButton(
                  onPressed: onHelpful,
                  style: TextButton.styleFrom(
                    visualDensity: VisualDensity.compact,
                    padding: EdgeInsets.symmetric(horizontal: AppSpace.s(8)),
                    minimumSize: const Size(0, 28),
                    tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                  ),
                  child: const Text('도움됨', style: TextStyle(fontSize: 12)),
                ),
                TextButton(
                  onPressed: onNotHelpful,
                  style: TextButton.styleFrom(
                    visualDensity: VisualDensity.compact,
                    padding: EdgeInsets.symmetric(horizontal: AppSpace.s(8)),
                    minimumSize: const Size(0, 28),
                    tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                  ),
                  child: const Text('안됨', style: TextStyle(fontSize: 12)),
                ),
              ],
            ),
    );
  }
}

class _HighlightedMarkdown extends StatelessWidget {
  const _HighlightedMarkdown({required this.text, required this.query});

  final String text;
  final String query;

  @override
  Widget build(BuildContext context) {
    final baseStyle = DefaultTextStyle.of(context).style.copyWith(
      color: AppColors.textPrimary,
      fontSize: 13,
      height: 1.4,
    );
    final spans = <InlineSpan>[];
    final bold = RegExp(r'\*\*(.*?)\*\*', dotAll: true);
    var cursor = 0;
    for (final match in bold.allMatches(text)) {
      spans.addAll(
        _highlightSpans(text.substring(cursor, match.start), query, baseStyle),
      );
      spans.addAll(
        _highlightSpans(
          match.group(1)!,
          query,
          baseStyle.copyWith(fontWeight: FontWeight.w800),
        ),
      );
      cursor = match.end;
    }
    spans.addAll(_highlightSpans(text.substring(cursor), query, baseStyle));
    return Text.rich(
      key: const Key('chat-search-highlight'),
      TextSpan(children: spans),
    );
  }
}

class _HighlightedText extends StatelessWidget {
  const _HighlightedText({
    required this.text,
    required this.query,
    required this.style,
  });

  final String text;
  final String query;
  final TextStyle style;

  @override
  Widget build(BuildContext context) => Text.rich(
    key: const Key('chat-search-highlight'),
    TextSpan(children: _highlightSpans(text, query, style)),
  );
}

List<InlineSpan> _highlightSpans(String text, String query, TextStyle style) {
  if (query.isEmpty) return [TextSpan(text: text, style: style)];
  final matches = RegExp(
    RegExp.escape(query),
    caseSensitive: false,
  ).allMatches(text);
  if (matches.isEmpty) return [TextSpan(text: text, style: style)];

  final spans = <InlineSpan>[];
  var cursor = 0;
  for (final match in matches) {
    if (match.start > cursor) {
      spans.add(
        TextSpan(text: text.substring(cursor, match.start), style: style),
      );
    }
    spans.add(
      TextSpan(
        text: text.substring(match.start, match.end),
        style: style.copyWith(
          backgroundColor: AppColors.warning.withValues(alpha: 0.32),
          fontWeight: FontWeight.w700,
        ),
      ),
    );
    cursor = match.end;
  }
  if (cursor < text.length) {
    spans.add(TextSpan(text: text.substring(cursor), style: style));
  }
  return spans;
}

class _ChatMessage {
  const _ChatMessage({
    required this.text,
    required this.fromUser,
    this.isError = false,
    this.logId,
    this.promptVersion,
    this.feedbackOutcome,
  });
  final String text;
  final bool fromUser;
  final bool isError;
  final String? logId;
  final String? promptVersion;
  final String? feedbackOutcome;

  _ChatMessage copyWith({
    String? text,
    String? logId,
    String? promptVersion,
    String? feedbackOutcome,
  }) =>
      _ChatMessage(
        text: text ?? this.text,
        fromUser: fromUser,
        isError: isError,
        logId: logId ?? this.logId,
        promptVersion: promptVersion ?? this.promptVersion,
        feedbackOutcome: feedbackOutcome ?? this.feedbackOutcome,
      );
}
