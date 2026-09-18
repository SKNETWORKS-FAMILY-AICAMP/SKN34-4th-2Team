import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../../core/theme/app_colors.dart';
import '../../../shared/models/alert_popup_model.dart';
import '../../../shared/models/user_model.dart';
import '../../../shared/providers/alert_popup_providers.dart';
import '../../../shared/providers/lms_providers.dart';
import '../../../shared/services/alert_popup_dismiss_store.dart';
import '../../auth/providers/auth_providers.dart';
import '../../../core/theme/app_space.dart';

/// 학생 셸 — 활성 알림을 화면 위 오버레이로 표시
class AlertPopupHost extends ConsumerStatefulWidget {
  const AlertPopupHost({super.key, required this.child});

  final Widget child;

  @override
  ConsumerState<AlertPopupHost> createState() => _AlertPopupHostState();
}

class _AlertPopupHostState extends ConsumerState<AlertPopupHost> {
  Timer? _pollTimer;
  var _saving = false;

  @override
  void initState() {
    super.initState();
    _pollTimer = Timer.periodic(const Duration(seconds: 30), (_) {
      if (mounted) setState(() {});
    });
  }

  @override
  void dispose() {
    _pollTimer?.cancel();
    super.dispose();
  }

  AlertPopupModel? _firstVisible({
    required List<AlertPopupModel> popups,
    required Set<String> sessionClosed,
    required Set<String> dismissedToday,
  }) {
    final now = DateTime.now();
    for (final popup in popups) {
      if (sessionClosed.contains(popup.id)) continue;
      if (dismissedToday.contains(popup.id)) continue;
      if (!popup.isVisibleAt(now)) continue;
      return popup;
    }
    return null;
  }

  Future<void> _dismissToday(UserModel user, AlertPopupModel popup) async {
    if (_saving) return;
    final dateKey = alertPopupTodayKey();

    ref.read(alertPopupSessionClosedProvider.notifier).close(popup.id);
    ref.read(alertPopupLocalDismissedProvider.notifier).dismiss(
          popup.id,
          dateKey,
        );

    _saving = true;
    try {
      await AlertPopupDismissStore.dismissToday(
        uid: user.uid,
        popupId: popup.id,
        dateKey: dateKey,
      );
      await ref.read(lmsRepositoryProvider).dismissAlertPopupToday(
            uid: user.uid,
            popupId: popup.id,
            dateKey: dateKey,
          );
    } catch (_) {
      // 로컬 기록은 이미 남아 당일에는 다시 뜨지 않는다.
    } finally {
      if (mounted) _saving = false;
    }
  }

  @override
  Widget build(BuildContext context) {
    final user = ref.watch(currentUserProvider).value;
    final popups =
        ref.watch(activeAlertPopupsProvider).value ?? const <AlertPopupModel>[];
    final sessionClosed = ref.watch(alertPopupSessionClosedProvider);
    final localDismissed = ref.watch(alertPopupLocalDismissedProvider);
    final remoteDismissed =
        ref.watch(alertPopupRemoteDismissedProvider).value ?? const {};
    final dismissedToday = alertPopupIdsDismissedToday(
      local: localDismissed,
      remote: remoteDismissed,
      dateKey: alertPopupTodayKey(),
    );

    final isStudentView =
        user != null && !user.isAdmin && !user.isInstructor;
    final popup = isStudentView
        ? _firstVisible(
            popups: popups,
            sessionClosed: sessionClosed,
            dismissedToday: dismissedToday,
          )
        : null;

    return Stack(
      fit: StackFit.expand,
      children: [
        widget.child,
        if (popup != null && user != null)
          Positioned.fill(
            child: _AlertPopupOverlay(
              popup: popup,
              onClose: () {
                ref
                    .read(alertPopupSessionClosedProvider.notifier)
                    .close(popup.id);
              },
              onDismissToday: () => _dismissToday(user, popup),
            ),
          ),
      ],
    );
  }
}

class _AlertPopupOverlay extends StatelessWidget {
  const _AlertPopupOverlay({
    required this.popup,
    required this.onClose,
    required this.onDismissToday,
  });

  final AlertPopupModel popup;
  final VoidCallback onClose;
  final Future<void> Function() onDismissToday;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: const Color(0x99000000),
      child: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: EdgeInsets.all(AppSpace.s(24)),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 420),
              child: AlertDialog(
                insetPadding: EdgeInsets.zero,
                title: Row(
                  children: [
                    const Icon(Icons.notifications_active_outlined, size: 22),
                    SizedBox(width: AppSpace.s(8)),
                    Expanded(
                      child: Text(
                        popup.title,
                        style: const TextStyle(fontSize: 17),
                      ),
                    ),
                  ],
                ),
                content: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Text(
                      popup.content,
                      style: const TextStyle(fontSize: 14, height: 1.45),
                    ),
                    if (popup.hasTimeWindow) ...[
                      SizedBox(height: AppSpace.s(10)),
                      Text(
                        '표시 시간 ${popup.timeWindowLabel}',
                        style: TextStyle(
                          fontSize: 12,
                          color: AppColors.textSecondary,
                        ),
                      ),
                    ],
                    if (popup.linkUrl != null && popup.linkUrl!.isNotEmpty) ...[
                      SizedBox(height: AppSpace.s(14)),
                      Align(
                        alignment: Alignment.centerLeft,
                        child: TextButton.icon(
                          onPressed: () => launchUrl(
                            Uri.parse(popup.linkUrl!),
                            mode: LaunchMode.externalApplication,
                          ),
                          icon: const Icon(Icons.open_in_new, size: 16),
                          label: const Text('링크 열기'),
                        ),
                      ),
                    ],
                  ],
                ),
                actions: [
                  TextButton(
                    onPressed: onClose,
                    child: const Text('닫기'),
                  ),
                  FilledButton(
                    onPressed: () => onDismissToday(),
                    child: const Text('오늘 다시 보지 않기'),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
