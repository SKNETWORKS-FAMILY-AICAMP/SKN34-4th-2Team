import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/routing/route_paths.dart';
import '../../../core/theme/app_colors.dart';
import '../../../core/utils/date_utils.dart';
import '../../../core/widgets/app_dropdown.dart';
import '../../../core/widgets/loading_widgets.dart';
import '../../../shared/models/alert_popup_model.dart';
import '../../../shared/models/notice_model.dart';
import '../../../shared/models/scheduled_notice_model.dart';
import '../../../shared/providers/cohort_providers.dart';
import '../../../shared/providers/lms_providers.dart';
import '../../hub/presentation/widgets/board_ui.dart';
import '../../hub/presentation/widgets/notice_list_widgets.dart';
import '../../onboarding/admin/admin_onboarding_keys.dart';
import '../../onboarding/domain/onboarding_target_registry.dart';
import '../../../core/theme/app_space.dart';

/// 관리자 — 게시판 관리 (공지 + 예약 공지)
class AdminBoardScreen extends ConsumerStatefulWidget {
  const AdminBoardScreen({super.key});

  @override
  ConsumerState<AdminBoardScreen> createState() => _AdminBoardScreenState();
}

class _AdminBoardScreenState extends ConsumerState<AdminBoardScreen>
    with SingleTickerProviderStateMixin {
  late final TabController _tabController;

  @override
  void initState() {
    super.initState();
    _tabController = TabController(length: 3, vsync: this)
      ..addListener(() => setState(() {}));
  }

  @override
  void dispose() {
    _tabController.dispose();
    super.dispose();
  }

  String get _createLabel => switch (_tabController.index) {
    0 => '공지 작성',
    1 => '예약 등록',
    _ => '알림 팝업',
  };

  void _onCreate() {
    switch (_tabController.index) {
      case 0:
        context.push(RoutePaths.adminBoardNoticeCreate);
      case 1:
        context.push(RoutePaths.adminBoardScheduledCreate);
      default:
        context.push(RoutePaths.adminBoardAlertPopupCreate);
    }
  }

  @override
  Widget build(BuildContext context) {
    return ColoredBox(
      color: BoardUi.listBackground,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          BoardPageHeader(
            title: '게시판 관리',
            subtitle: '공지 · 예약 게시 · 로그인 알림 팝업을 관리합니다.',
            action: KeyedSubtree(
              key: OnboardingTargetRegistry.keyOf(
                AdminOnboardingTargets.boardCreate,
              ),
              child: FilledButton.icon(
                onPressed: _onCreate,
                style: BoardUi.primaryButtonStyle(),
                icon: const Icon(Icons.add, size: 18),
                label: Text(_createLabel),
              ),
            ),
          ),
          BoardTabBar(
            controller: _tabController,
            tabs: const ['공지 관리', '예약 공지', '알림 팝업'],
          ),
          Expanded(
            child: TabBarView(
              controller: _tabController,
              children: const [
                _NoticeManageTab(),
                _ScheduledNoticeTab(),
                _AlertPopupTab(),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _NoticeManageTab extends ConsumerWidget {
  const _NoticeManageTab();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final notices = ref.watch(noticesStreamProvider);

    return RefreshIndicator(
      onRefresh: () async => ref.invalidate(noticesStreamProvider),
      child: notices.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => ErrorView(message: e.toString()),
        data: (list) {
          if (list.isEmpty) {
            return ListView(
              physics: const AlwaysScrollableScrollPhysics(),
              children: [
                SizedBox(height: AppSpace.s(48)),
                EmptyView(
                  message: '등록된 공지가 없습니다.',
                  icon: Icons.campaign_outlined,
                ),
              ],
            );
          }

          return ListView.builder(
            physics: const AlwaysScrollableScrollPhysics(),
            padding: EdgeInsets.all(AppSpace.s(20)),
            itemCount: list.length,
            itemBuilder: (_, i) {
              final notice = list[i];
              return NoticeCard(
                notice: notice,
                onTap: () => NoticeDetailSheet.show(context, notice),
                trailing: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    IconButton(
                      visualDensity: VisualDensity.compact,
                      tooltip: notice.isFavorite ? '즐겨찾기 해제' : '즐겨찾기',
                      onPressed: () => _toggleFavorite(ref, notice),
                      icon: Icon(
                        notice.isFavorite
                            ? Icons.star_rounded
                            : Icons.star_outline_rounded,
                        color: notice.isFavorite
                            ? BoardUi.favorite
                            : AppColors.textHint,
                        size: 22,
                      ),
                    ),
                    AppIconMenu<String>(
                      icon: const Icon(Icons.more_vert),
                      iconSize: 20,
                      color: AppColors.textHint,
                      onSelected: (value) async {
                        if (value == 'edit') {
                          context.push(
                            RoutePaths.adminBoardNoticeEditPath(notice.id),
                          );
                        } else if (value == 'delete') {
                          await _confirmDelete(context, ref, notice);
                        }
                      },
                      items: const [
                        AppMenuAction(value: 'edit', label: '수정'),
                        AppMenuAction(
                          value: 'delete',
                          label: '삭제',
                          danger: true,
                        ),
                      ],
                    ),
                  ],
                ),
              );
            },
          );
        },
      ),
    );
  }

  Future<void> _toggleFavorite(WidgetRef ref, NoticeModel notice) async {
    final cohortId = ref.read(effectiveCohortIdProvider);
    if (cohortId == null) return;
    await ref
        .read(lmsRepositoryProvider)
        .toggleNoticeFavorite(
          cohortId: cohortId,
          noticeId: notice.id,
          isFavorite: !notice.isFavorite,
        );
  }

  Future<void> _confirmDelete(
    BuildContext context,
    WidgetRef ref,
    NoticeModel notice,
  ) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('공지 삭제'),
        content: Text('「${notice.title}」 공지를 삭제할까요?'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('취소'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(ctx, true),
            style: FilledButton.styleFrom(backgroundColor: AppColors.error),
            child: const Text('삭제'),
          ),
        ],
      ),
    );
    if (ok != true) return;

    final cohortId = ref.read(effectiveCohortIdProvider);
    if (cohortId == null) return;
    await ref.read(lmsRepositoryProvider).deleteNotice(cohortId, notice.id);
  }
}

class _ScheduledNoticeTab extends ConsumerStatefulWidget {
  const _ScheduledNoticeTab();

  @override
  ConsumerState<_ScheduledNoticeTab> createState() =>
      _ScheduledNoticeTabState();
}

class _ScheduledNoticeTabState extends ConsumerState<_ScheduledNoticeTab> {
  final _selectedIds = <String>{};
  var _runningNow = false;

  void _toggleSelection(String id, bool selected) {
    setState(() {
      if (selected) {
        _selectedIds.add(id);
      } else {
        _selectedIds.remove(id);
      }
    });
  }

  void _toggleSelectAllActive(List<ScheduledNoticeModel> list) {
    final activeIds = list.where((n) => n.isActive).map((n) => n.id).toSet();
    setState(() {
      if (activeIds.every(_selectedIds.contains)) {
        _selectedIds.removeAll(activeIds);
      } else {
        _selectedIds.addAll(activeIds);
      }
    });
  }

  Future<void> _publishSelected(List<ScheduledNoticeModel> list) async {
    final cohortId = ref.read(effectiveCohortIdProvider);
    if (cohortId == null) return;

    final activeSelected = _selectedIds
        .where((id) => list.any((n) => n.id == id && n.isActive))
        .toList();
    if (activeSelected.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('활성 예약 공지를 선택해 주세요.')),
      );
      return;
    }

    setState(() => _runningNow = true);
    try {
      final count = await ref
          .read(scheduledNoticeAdminServiceProvider)
          .publishSelected(cohortId: cohortId, scheduledIds: activeSelected);
      ref.invalidate(noticesStreamProvider);
      ref.invalidate(scheduledNoticesProvider);
      if (mounted) {
        setState(() => _selectedIds.clear());
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(
              count > 0 ? '$count건의 예약 공지가 게시되었습니다.' : '게시된 예약 공지가 없습니다.',
            ),
          ),
        );
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('실행 실패: $e')),
        );
      }
    } finally {
      if (mounted) setState(() => _runningNow = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final scheduled = ref.watch(scheduledNoticesProvider);

    return RefreshIndicator(
      onRefresh: () async => ref.invalidate(scheduledNoticesProvider),
      child: scheduled.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => ErrorView(message: e.toString()),
        data: (list) {
          final activeCount = list.where((n) => n.isActive).length;
          final allActiveSelected =
              activeCount > 0 &&
              list
                  .where((n) => n.isActive)
                  .every((n) => _selectedIds.contains(n.id));

          if (list.isEmpty) {
            return ListView(
              physics: const AlwaysScrollableScrollPhysics(),
              padding: EdgeInsets.all(AppSpace.s(20)),
              children: [
                SizedBox(height: AppSpace.s(48)),
                EmptyView(
                  message: '등록된 예약 공지가 없습니다.',
                  icon: Icons.schedule_outlined,
                ),
              ],
            );
          }

          return ListView(
            physics: const AlwaysScrollableScrollPhysics(),
            padding: EdgeInsets.fromLTRB(AppSpace.s(20), AppSpace.s(16), AppSpace.s(20), AppSpace.s(28)),
            children: [
              Row(
                children: [
                  if (activeCount > 0)
                    TextButton.icon(
                      onPressed: () => _toggleSelectAllActive(list),
                      icon: Icon(
                        allActiveSelected
                            ? Icons.check_box_rounded
                            : Icons.check_box_outline_blank_rounded,
                        size: 18,
                      ),
                      label: Text(
                        allActiveSelected ? '선택 해제' : '활성 전체 선택',
                        style: const TextStyle(fontSize: 13),
                      ),
                    ),
                  const Spacer(),
                  FilledButton.icon(
                    onPressed: _runningNow || _selectedIds.isEmpty
                        ? null
                        : () => _publishSelected(list),
                    style: BoardUi.primaryButtonStyle(),
                    icon: _runningNow
                        ? SizedBox(
                            width: 14,
                            height: 14,
                            child: CircularProgressIndicator(
                              strokeWidth: 2,
                              color: Colors.white,
                            ),
                          )
                        : const Icon(Icons.play_arrow_rounded, size: 18),
                    label: Text(
                      _selectedIds.isEmpty
                          ? '지금 게시 실행'
                          : '지금 게시 실행 (${_selectedIds.length})',
                    ),
                  ),
                ],
              ),
              SizedBox(height: AppSpace.s(12)),
              Container(
                decoration: BoxDecoration(
                  color: AppColors.surface,
                  borderRadius: BorderRadius.circular(12),
                  border: Border.all(color: AppColors.border),
                ),
                clipBehavior: Clip.antiAlias,
                child: Column(
                  children: [
                    for (var i = 0; i < list.length; i++) ...[
                      if (i > 0) const Divider(height: 1, thickness: 1),
                      _ScheduledRow(
                        item: list[i],
                        selected: _selectedIds.contains(list[i].id),
                        onSelected: list[i].isActive
                            ? (v) => _toggleSelection(list[i].id, v)
                            : null,
                        onInactive: () => _toggleSelection(list[i].id, false),
                      ),
                    ],
                  ],
                ),
              ),
            ],
          );
        },
      ),
    );
  }
}

class _ScheduledRow extends ConsumerWidget {
  const _ScheduledRow({
    required this.item,
    required this.selected,
    this.onSelected,
    this.onInactive,
  });

  final ScheduledNoticeModel item;
  final bool selected;
  final ValueChanged<bool>? onSelected;
  final VoidCallback? onInactive;

  String get _metaLine {
    final parts = <String>[item.repeatLabel];
    if (item.nextPublishAt != null) {
      parts.add('다음 ${AppDateUtils.formatDateTime(item.nextPublishAt!)}');
    }
    parts.add(item.isActive ? '활성' : '비활성');
    return parts.join(' · ');
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return SizedBox(
      height: AppSpace.row(48),
      child: Row(
        children: [
          SizedBox(
            width: 44,
            child: Checkbox(
              value: selected,
              onChanged: onSelected == null
                  ? null
                  : (v) => onSelected!(v ?? false),
              materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
              visualDensity: VisualDensity.compact,
            ),
          ),
          Expanded(
            child: InkWell(
              onTap: onSelected == null ? null : () => onSelected!(!selected),
              child: Row(
                children: [
                  if (item.isFavorite) ...[
                    const Icon(
                      Icons.star_rounded,
                      size: 16,
                      color: BoardUi.favorite,
                    ),
                    SizedBox(width: AppSpace.s(4)),
                  ],
                  Expanded(
                    child: Text(
                      item.title,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(
                        fontSize: 14,
                        fontWeight: FontWeight.w600,
                        color: item.isActive
                            ? AppColors.textPrimary
                            : AppColors.textHint,
                      ),
                    ),
                  ),
                  SizedBox(width: AppSpace.s(8)),
                  Flexible(
                    child: Text(
                      _metaLine,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      textAlign: TextAlign.right,
                      style: TextStyle(
                        fontSize: 11,
                        color: AppColors.textHint,
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ),
          Transform.scale(
            scale: 0.85,
            child: Switch(
              value: item.isActive,
              onChanged: (v) => _toggleActive(ref, v),
              materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
            ),
          ),
          AppIconMenu<String>(
            icon: const Icon(Icons.more_vert),
            iconSize: 18,
            color: AppColors.textHint,
            padding: EdgeInsets.zero,
            onSelected: (action) {
              if (action == 'edit') {
                context.push(RoutePaths.adminBoardScheduledEditPath(item.id));
              } else if (action == 'delete') {
                _confirmDelete(context, ref);
              }
            },
            items: const [
              AppMenuAction(value: 'edit', label: '수정'),
              AppMenuAction(value: 'delete', label: '삭제', danger: true),
            ],
          ),
        ],
      ),
    );
  }

  Future<void> _toggleActive(WidgetRef ref, bool isActive) async {
    final cohortId = ref.read(effectiveCohortIdProvider);
    if (cohortId == null) return;
    await ref
        .read(lmsRepositoryProvider)
        .toggleScheduledNoticeActive(
          cohortId: cohortId,
          scheduledId: item.id,
          isActive: isActive,
        );
    if (!isActive) onInactive?.call();
  }

  Future<void> _confirmDelete(BuildContext context, WidgetRef ref) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('예약 삭제'),
        content: Text('「${item.title}」 예약을 삭제할까요?'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('취소'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(ctx, true),
            style: FilledButton.styleFrom(backgroundColor: AppColors.error),
            child: const Text('삭제'),
          ),
        ],
      ),
    );
    if (ok != true) return;

    final cohortId = ref.read(effectiveCohortIdProvider);
    if (cohortId == null) return;
    await ref
        .read(lmsRepositoryProvider)
        .deleteScheduledNotice(cohortId, item.id);
  }
}

class _AlertPopupTab extends ConsumerWidget {
  const _AlertPopupTab();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final popups = ref.watch(alertPopupsAdminProvider);

    return RefreshIndicator(
      onRefresh: () async => ref.invalidate(alertPopupsAdminProvider),
      child: popups.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => ErrorView(message: e.toString()),
        data: (list) {
          if (list.isEmpty) {
            return ListView(
              physics: const AlwaysScrollableScrollPhysics(),
              children: [
                SizedBox(height: AppSpace.s(48)),
                EmptyView(
                  message: '등록된 알림 팝업이 없습니다.',
                  icon: Icons.notifications_none_outlined,
                  actionLabel: '알림 팝업 등록',
                  onAction: () =>
                      context.push(RoutePaths.adminBoardAlertPopupCreate),
                ),
              ],
            );
          }

          return ListView.separated(
            physics: const AlwaysScrollableScrollPhysics(),
            padding: EdgeInsets.all(AppSpace.s(20)),
            itemCount: list.length,
            separatorBuilder: (_, _) => SizedBox(height: AppSpace.s(10)),
            itemBuilder: (_, i) {
              return _AlertPopupCard(item: list[i]);
            },
          );
        },
      ),
    );
  }
}

class _AlertPopupCard extends ConsumerWidget {
  const _AlertPopupCard({required this.item});

  final AlertPopupModel item;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return Material(
      color: AppColors.surface,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(12),
        side: BorderSide(color: AppColors.border),
      ),
      child: Padding(
        padding: EdgeInsets.fromLTRB(AppSpace.s(14), AppSpace.s(12), AppSpace.s(8), AppSpace.s(12)),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Expanded(
                        child: Text(
                          item.title,
                          style: const TextStyle(
                            fontWeight: FontWeight.w700,
                            fontSize: 15,
                          ),
                        ),
                      ),
                      Container(
                        padding: EdgeInsets.symmetric(
                          horizontal: AppSpace.s(8),
                          vertical: AppSpace.s(3),
                        ),
                        decoration: BoxDecoration(
                          color: item.isActive
                              ? BoardUi.activeBadgeBg
                              : AppColors.surfaceVariant,
                          borderRadius: BorderRadius.circular(6),
                        ),
                        child: Text(
                          item.isActive ? '활성' : '비활성',
                          style: TextStyle(
                            fontSize: 11,
                            fontWeight: FontWeight.w600,
                            color: item.isActive
                                ? BoardUi.activeBadgeText
                                : AppColors.textSecondary,
                          ),
                        ),
                      ),
                    ],
                  ),
                  SizedBox(height: AppSpace.s(6)),
                  Text(
                    item.content,
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                      fontSize: 13,
                      color: AppColors.textSecondary,
                      height: 1.35,
                    ),
                  ),
                  SizedBox(height: AppSpace.s(6)),
                  Text(
                    '순서 ${item.sortOrder} · ${item.timeWindowLabel}'
                    '${item.linkUrl != null && item.linkUrl!.isNotEmpty ? ' · 링크' : ''}',
                    style: TextStyle(
                      fontSize: 11,
                      color: AppColors.textHint,
                    ),
                  ),
                ],
              ),
            ),
            Switch(
              value: item.isActive,
              onChanged: (v) => _toggleActive(ref, v),
            ),
            AppIconMenu<String>(
              onSelected: (value) async {
                if (value == 'edit') {
                  context.push(
                    RoutePaths.adminBoardAlertPopupEditPath(item.id),
                  );
                } else if (value == 'delete') {
                  await _confirmDelete(context, ref);
                }
              },
              items: const [
                AppMenuAction(value: 'edit', label: '수정'),
                AppMenuAction(value: 'delete', label: '삭제', danger: true),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Future<void> _toggleActive(WidgetRef ref, bool isActive) async {
    final cohortId = ref.read(effectiveCohortIdProvider);
    if (cohortId == null) return;
    await ref
        .read(lmsRepositoryProvider)
        .toggleAlertPopupActive(
          cohortId: cohortId,
          popupId: item.id,
          isActive: isActive,
        );
  }

  Future<void> _confirmDelete(BuildContext context, WidgetRef ref) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('알림 팝업 삭제'),
        content: Text('「${item.title}」 알림을 삭제할까요?'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('취소'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(ctx, true),
            style: FilledButton.styleFrom(backgroundColor: AppColors.error),
            child: const Text('삭제'),
          ),
        ],
      ),
    );
    if (ok != true) return;
    final cohortId = ref.read(effectiveCohortIdProvider);
    if (cohortId == null) return;
    await ref.read(lmsRepositoryProvider).deleteAlertPopup(cohortId, item.id);
  }
}
