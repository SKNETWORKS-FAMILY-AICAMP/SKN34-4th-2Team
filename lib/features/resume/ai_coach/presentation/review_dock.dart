import 'dart:async';

import 'package:flutter/material.dart';

import '../../../../core/theme/app_colors.dart';
import '../../../../core/theme/app_space.dart';

/// 첨삭 창을 앱 맨 위 층에 띄우고, 기다리는 동안 오른쪽 아래 막대로 내려둔다.
///
/// 첨삭 한 번이 40~70초 걸린다(2026-09-14 Firestore 기록 33~71초). 대화 상자
/// (`showDialog`)로 띄우면 그동안 앱 전체가 막히고, 닫으면 진행 중인 결과를 잃는다.
/// 그래서 창을 경로(route)가 아니라 [ReviewDockHost] 층에 올린다. 화면을 옮겨도
/// 창 위젯이 살아 있어 요청과 대화가 그대로 남는다.
///
/// 층은 앱 Navigator **위**에 있다. 이력서 수정 화면은 사이드바 틀 밖의 경로라,
/// 틀 안에 두면 화면을 옮길 때 창이 같이 사라진다. 대신 창 안에 따로 Navigator를
/// 둔다. 창 안에서 여는 확인 대화 상자("첨삭을 완료할까요?")가 앱 Navigator에 뜨면
/// 이 층 아래에 깔리기 때문이다.
///
/// 층이 없는 곳(위젯 시험 등)에서는 예전처럼 대화 상자로 띄운다.
abstract final class ReviewDock {
  static Future<T?> show<T>(
    BuildContext context, {
    required Key key,
    required Widget child,
  }) {
    final host = context.findAncestorStateOfType<ReviewDockHostState>();
    if (host == null) {
      return showDialog<T>(
        context: context,
        barrierDismissible: false,
        builder: (_) => child,
      );
    }
    return host._show(key, child).then((value) => value as T?);
  }
}

/// 창이 막대에 알리는 지금 상태.
@immutable
class ReviewDockStatus {
  const ReviewDockStatus({
    this.title = '이력서 첨삭',
    this.subtitle = '',
    this.busy = false,
    this.stageLabel,
    this.stageIndex,
    this.stageCount,
    this.failed = false,
  });

  final String title;
  final String subtitle;
  final bool busy;

  /// 지금 하는 일. "부족한 근거 선별", "답변을 검토하고 있어요".
  final String? stageLabel;

  /// 단계가 있는 첫 첨삭만 채운다. 막대의 진행 칸을 그린다.
  final int? stageIndex;
  final int? stageCount;

  /// 방금 끝난 일이 실패했는가.
  final bool failed;
}

/// 층 안의 창이 자기를 내려두고, 닫고, 상태를 알릴 때 쓴다.
class ReviewDockScope extends InheritedWidget {
  const ReviewDockScope._(
    this._host, {
    required this.minimized,
    required super.child,
  });

  final ReviewDockHostState _host;
  final bool minimized;

  /// 빌드 중에 부른다. 내려두기 여부가 바뀌면 다시 그린다.
  static ReviewDockScope? watch(BuildContext context) =>
      context.dependOnInheritedWidgetOfExactType<ReviewDockScope>();

  /// 누름 처리·비동기 흐름에서 부른다.
  static ReviewDockScope? read(BuildContext context) =>
      context.getInheritedWidgetOfExactType<ReviewDockScope>();

  void minimize() => _host._setMinimized(true);

  void close([Object? result]) => _host._close(result);

  void report(ReviewDockStatus status) => _host._report(status);

  @override
  bool updateShouldNotify(ReviewDockScope oldWidget) =>
      minimized != oldWidget.minimized;
}

class ReviewDockHost extends StatefulWidget {
  const ReviewDockHost({super.key, required this.child});

  final Widget child;

  @override
  State<ReviewDockHost> createState() => ReviewDockHostState();
}

class ReviewDockHostState extends State<ReviewDockHost> {
  Key? _key;
  Widget? _panel;
  Completer<Object?>? _completer;
  bool _minimized = false;
  ReviewDockStatus _status = const ReviewDockStatus();
  DateTime? _busySince;
  Duration _lastElapsed = Duration.zero;

  /// 내려둔 동안 끝났다. 막대를 초록으로 바꾸고 "열기"를 보인다.
  bool _finishedWhileMinimized = false;
  Timer? _clock;

  @override
  void dispose() {
    _clock?.cancel();
    // 로그아웃·테마 변경으로 앱을 새로 그리면 층도 사라진다. 기다리는 쪽을 풀어 준다.
    final completer = _completer;
    if (completer != null && !completer.isCompleted) completer.complete(null);
    super.dispose();
  }

  Future<Object?> _show(Key key, Widget child) {
    if (_panel != null) {
      setState(() => _minimized = false);
      if (_key != key) {
        _notice('진행 중인 첨삭 창이 있어요. 그 창을 닫은 뒤에 새로 열 수 있어요.');
      }
      return Future.value();
    }
    final completer = Completer<Object?>();
    setState(() {
      _key = key;
      _panel = child;
      _completer = completer;
      _minimized = false;
      _finishedWhileMinimized = false;
      _status = const ReviewDockStatus();
      _busySince = null;
      _lastElapsed = Duration.zero;
    });
    return completer.future;
  }

  void _close(Object? result) {
    final completer = _completer;
    _clock?.cancel();
    setState(() {
      _key = null;
      _panel = null;
      _completer = null;
      _minimized = false;
      _finishedWhileMinimized = false;
    });
    if (completer != null && !completer.isCompleted) completer.complete(result);
  }

  void _setMinimized(bool value) {
    if (_panel == null || _minimized == value) return;
    setState(() {
      _minimized = value;
      if (!value) _finishedWhileMinimized = false;
    });
    _syncClock();
  }

  void _report(ReviewDockStatus status) {
    if (!mounted || _panel == null) return;
    final wasBusy = _status.busy;
    setState(() {
      if (status.busy && !wasBusy) {
        _busySince = DateTime.now();
        _finishedWhileMinimized = false;
      }
      if (!status.busy && wasBusy) {
        final since = _busySince;
        if (since != null) _lastElapsed = DateTime.now().difference(since);
        _busySince = null;
        if (_minimized) _finishedWhileMinimized = true;
      }
      _status = status;
    });
    _syncClock();
    // 끝났을 때 스낵바를 따로 띄우지 않는다. 내려둔 막대가 이미 같은 자리에서 "완료 · 결과를 확인해
    // 주세요 · 열기"를 보여 주는데, 기본 스낵바(검정)가 그 위에 겹쳐 두 겹으로 보였다.
  }

  /// 내려둔 막대의 경과 시간을 1초마다 새로 그린다. 창이 펼쳐져 있으면 멈춘다.
  void _syncClock() {
    final run = _minimized && _status.busy;
    if (run && _clock == null) {
      _clock = Timer.periodic(const Duration(seconds: 1), (_) {
        if (mounted) setState(() {});
      });
    } else if (!run) {
      _clock?.cancel();
      _clock = null;
    }
  }

  void _notice(String text) {
    final messenger = ScaffoldMessenger.maybeOf(context);
    if (messenger == null) return;
    messenger
      ..hideCurrentSnackBar()
      ..showSnackBar(
        SnackBar(
          content: Text(text),
          persist: false,
          duration: const Duration(seconds: 4),
        ),
      );
  }

  @override
  Widget build(BuildContext context) {
    final panel = _panel;
    return Stack(
      fit: StackFit.expand,
      children: [
        widget.child,
        if (panel != null) ...[
          // 키가 없으면 가림막이 빠질 때 뒤 칸이 앞으로 당겨지면서 창을 새로 만든다.
          // 그러면 진행 중인 첨삭과 대화가 사라진다.
          if (!_minimized)
            const ModalBarrier(
              key: ValueKey('review-dock-barrier'),
              color: Colors.black54,
              dismissible: false,
            ),
          Offstage(
            key: const ValueKey('review-dock-panel'),
            offstage: _minimized,
            child: TickerMode(
              enabled: !_minimized,
              child: ReviewDockScope._(
                this,
                minimized: _minimized,
                // 앱 Navigator의 HeroController를 나눠 쓰면 안 된다(Flutter가 막는다).
                child: HeroControllerScope.none(
                  child: Navigator(
                    key: ValueKey(_key),
                    onGenerateRoute: (_) => PageRouteBuilder<void>(
                      opaque: false,
                      pageBuilder: (_, _, _) => panel,
                    ),
                  ),
                ),
              ),
            ),
          ),
          if (_minimized)
            _ReviewDockBar(
              status: _status,
              finished: _finishedWhileMinimized,
              elapsed: _busySince == null
                  ? _lastElapsed
                  : DateTime.now().difference(_busySince!),
              onOpen: () => _setMinimized(false),
            ),
        ],
      ],
    );
  }
}

/// 내려둔 첨삭 창. 오른쪽 아래, 학생 챗봇 로봇(112px) 왼쪽에 놓는다.
/// 폭이 좁으면 로봇 위로 올린다.
class _ReviewDockBar extends StatelessWidget {
  const _ReviewDockBar({
    required this.status,
    required this.finished,
    required this.elapsed,
    required this.onOpen,
  });

  final ReviewDockStatus status;
  final bool finished;
  final Duration elapsed;
  final VoidCallback onOpen;

  static String _clock(Duration d) =>
      '${d.inMinutes}:${(d.inSeconds % 60).toString().padLeft(2, '0')}';

  @override
  Widget build(BuildContext context) {
    final compact = MediaQuery.sizeOf(context).width < 600;
    final failed = finished && status.failed;
    final accent = failed
        ? AppColors.error
        : finished
        ? AppColors.success
        : AppColors.primary;
    final title = failed
        ? '${status.title} 중 문제가 생겼어요'
        : finished
        ? '${status.title} 완료'
        : status.busy
        ? '${status.title} 중'
        : status.title;
    final detail = failed
        ? '창을 열어 다시 시도해 주세요'
        : finished
        ? '결과를 확인해 주세요'
        : status.busy
        ? [
            if (status.stageIndex != null && status.stageCount != null)
              '${status.stageIndex! + 1}/${status.stageCount}',
            status.stageLabel ?? '진행 중',
          ].join(' · ')
        : (status.subtitle.isEmpty ? '창을 내려두었어요' : status.subtitle);
    // 단계를 모르는 기다림(답변 검토 등)만 계속 흐르는 막대로 그린다.
    final progress = finished
        ? 1.0
        : !status.busy
        ? 0.0
        : status.stageIndex != null && (status.stageCount ?? 0) > 0
        ? (status.stageIndex! + 0.5) / status.stageCount!
        : null;

    final bar = Material(
      color: AppColors.surface,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(14),
        side: BorderSide(
          color: finished ? accent : AppColors.border,
          width: finished ? 1.5 : 1,
        ),
      ),
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: onOpen,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Padding(
              padding: EdgeInsets.fromLTRB(
                AppSpace.s(12),
                AppSpace.s(10),
                AppSpace.s(6),
                AppSpace.s(8),
              ),
              child: Row(
                children: [
                  Container(
                    width: 32,
                    height: 32,
                    decoration: BoxDecoration(
                      color: finished ? accent : AppColors.primaryLight,
                      borderRadius: BorderRadius.circular(10),
                    ),
                    alignment: Alignment.center,
                    child: finished
                        ? Icon(
                            failed ? Icons.priority_high : Icons.check,
                            size: 18,
                            color: Colors.white,
                          )
                        : status.busy
                        ? SizedBox.square(
                            dimension: 16,
                            child: CircularProgressIndicator(
                              strokeWidth: 2.2,
                              color: AppColors.primary,
                            ),
                          )
                        : Icon(
                            Icons.auto_awesome,
                            size: 18,
                            color: AppColors.primary,
                          ),
                  ),
                  SizedBox(width: AppSpace.s(10)),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Row(
                          children: [
                            Flexible(
                              child: Text(
                                title,
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis,
                                style: TextStyle(
                                  fontSize: 13,
                                  fontWeight: FontWeight.w700,
                                  color: AppColors.textPrimary,
                                ),
                              ),
                            ),
                            if (status.busy || finished) ...[
                              SizedBox(width: AppSpace.s(6)),
                              Text(
                                _clock(elapsed),
                                style: TextStyle(
                                  fontSize: 11.5,
                                  color: AppColors.textSecondary,
                                  fontFeatures: const [
                                    FontFeature.tabularFigures(),
                                  ],
                                ),
                              ),
                            ],
                          ],
                        ),
                        SizedBox(height: AppSpace.s(2)),
                        Text(
                          detail,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: TextStyle(
                            fontSize: 11.5,
                            color: AppColors.textSecondary,
                          ),
                        ),
                      ],
                    ),
                  ),
                  SizedBox(width: AppSpace.s(4)),
                  finished
                      ? FilledButton(
                          onPressed: onOpen,
                          style: FilledButton.styleFrom(
                            backgroundColor: accent,
                            minimumSize: const Size(0, 34),
                            padding: EdgeInsets.symmetric(
                              horizontal: AppSpace.s(14),
                            ),
                          ),
                          child: const Text('열기'),
                        )
                      : TextButton(
                          onPressed: onOpen,
                          child: const Text('펼치기'),
                        ),
                ],
              ),
            ),
            SizedBox(
              height: 4,
              child: LinearProgressIndicator(
                value: progress,
                color: accent,
                backgroundColor: AppColors.surfaceVariant,
              ),
            ),
          ],
        ),
      ),
    );

    // 넓은 화면은 가운데 아래에 둔다. Align은 카드 밖을 누르면 뒤 화면으로 넘겨 좌우 빈 곳을 막지 않는다.
    return Positioned(
      right: 12,
      left: 12,
      bottom: compact ? 124 : 18,
      child: SafeArea(
        child: Align(
          alignment: Alignment.bottomCenter,
          child: Semantics(
            container: true,
            liveRegion: true,
            label: '$title, $detail',
            child: Container(
              width: compact ? null : 340,
              decoration: BoxDecoration(
                borderRadius: BorderRadius.circular(14),
                boxShadow: [
                  BoxShadow(
                    color: Colors.black.withValues(alpha: 0.14),
                    blurRadius: 24,
                    offset: const Offset(0, 8),
                  ),
                ],
              ),
              child: bar,
            ),
          ),
        ),
      ),
    );
  }
}
