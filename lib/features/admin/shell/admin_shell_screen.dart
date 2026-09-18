import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/routing/route_paths.dart';
import '../../../core/theme/app_colors.dart';
import '../../../shared/models/user_model.dart';
import '../../../shared/providers/side_rail_theme_provider.dart';
import '../../../shared/widgets/app_side_rail.dart';
import '../../../shared/widgets/profile_nav_chip.dart';
import '../../auth/providers/auth_providers.dart';
import '../../onboarding/admin/admin_onboarding_host.dart';
import '../../onboarding/admin/admin_onboarding_keys.dart';
import '../../onboarding/domain/onboarding_target_registry.dart';
import '../../onboarding/presentation/onboarding_controller.dart';
import '../../shell/widgets/app_shell_header.dart';
import '../../../core/theme/shell_chrome.dart';
import '../../../core/theme/app_space.dart';

String? _adminTargetIdForPath(String path) => switch (path) {
  RoutePaths.admin => AdminOnboardingTargets.navDashboard,
  RoutePaths.adminCohorts => AdminOnboardingTargets.navCohorts,
  RoutePaths.adminStudents => AdminOnboardingTargets.navStudents,
  RoutePaths.adminInstructors => AdminOnboardingTargets.navInstructors,
  RoutePaths.adminAttendance => AdminOnboardingTargets.navAttendance,
  RoutePaths.adminSeatPresence => AdminOnboardingTargets.navSeatPresence,
  RoutePaths.adminSeating => AdminOnboardingTargets.navSeating,
  RoutePaths.adminAssessments => AdminOnboardingTargets.navAssessments,
  RoutePaths.adminRecords => AdminOnboardingTargets.navRecords,
  RoutePaths.adminResumes => AdminOnboardingTargets.navResumes,
  RoutePaths.adminFormTasks => AdminOnboardingTargets.navFormTasks,
  RoutePaths.adminStudyRoom => AdminOnboardingTargets.navStudyRoom,
  RoutePaths.adminBoard => AdminOnboardingTargets.navBoard,
  RoutePaths.adminMileage => AdminOnboardingTargets.navMileage,
  RoutePaths.adminAiQuality => AdminOnboardingTargets.navAiQuality,
  _ => null,
};

List<AppSideRailSection> _adminSections({required bool expandAll}) {
  Key? keyFor(String path) {
    final id = _adminTargetIdForPath(path);
    return id == null ? null : OnboardingTargetRegistry.keyOf(id);
  }

  return [
    AppSideRailSection(
      id: 'home',
      initiallyExpanded: true,
      items: [
        AppSideRailItem(
          icon: Icons.dashboard_rounded,
          label: '대시보드',
          path: RoutePaths.admin,
          itemKey: keyFor(RoutePaths.admin),
        ),
      ],
    ),
    AppSideRailSection(
      id: 'people',
      title: '운영 · 인원',
      initiallyExpanded: expandAll,
      items: [
        AppSideRailItem(
          icon: Icons.calendar_month_rounded,
          label: '기수 관리',
          path: RoutePaths.adminCohorts,
          itemKey: keyFor(RoutePaths.adminCohorts),
        ),
        AppSideRailItem(
          icon: Icons.groups_rounded,
          label: '학생 관리',
          path: RoutePaths.adminStudents,
          itemKey: keyFor(RoutePaths.adminStudents),
        ),
        AppSideRailItem(
          icon: Icons.badge_outlined,
          label: '강사 관리',
          path: RoutePaths.adminInstructors,
          itemKey: keyFor(RoutePaths.adminInstructors),
        ),
      ],
    ),
    AppSideRailSection(
      id: 'attendance',
      title: '출결 · 공간',
      initiallyExpanded: expandAll,
      items: [
        AppSideRailItem(
          icon: Icons.fact_check_outlined,
          label: '출석 관리',
          path: RoutePaths.adminAttendance,
          itemKey: keyFor(RoutePaths.adminAttendance),
        ),
        AppSideRailItem(
          icon: Icons.event_available_outlined,
          label: '자리 확인',
          path: RoutePaths.adminSeatPresence,
          itemKey: keyFor(RoutePaths.adminSeatPresence),
        ),
        AppSideRailItem(
          icon: Icons.event_seat_rounded,
          label: '좌석 배치',
          path: RoutePaths.adminSeating,
          itemKey: keyFor(RoutePaths.adminSeating),
        ),
      ],
    ),
    AppSideRailSection(
      id: 'learning',
      title: '학습 · 평가',
      initiallyExpanded: expandAll,
      items: [
        AppSideRailItem(
          icon: Icons.quiz_outlined,
          label: '성취도 평가',
          path: RoutePaths.adminAssessments,
          itemKey: keyFor(RoutePaths.adminAssessments),
        ),
        AppSideRailItem(
          icon: Icons.history_rounded,
          label: '기록실',
          path: RoutePaths.adminRecords,
          itemKey: keyFor(RoutePaths.adminRecords),
        ),
        AppSideRailItem(
          icon: Icons.description_rounded,
          label: '이력서',
          path: RoutePaths.adminResumes,
          itemKey: keyFor(RoutePaths.adminResumes),
        ),
        AppSideRailItem(
          icon: Icons.ballot_outlined,
          label: '설문 · 제출',
          path: RoutePaths.adminFormTasks,
          itemKey: keyFor(RoutePaths.adminFormTasks),
        ),
        AppSideRailItem(
          icon: Icons.menu_book_rounded,
          label: '학습실',
          path: RoutePaths.adminStudyRoom,
          itemKey: keyFor(RoutePaths.adminStudyRoom),
        ),
      ],
    ),
    AppSideRailSection(
      id: 'engage',
      title: '소통 · 리워드',
      initiallyExpanded: expandAll,
      items: [
        AppSideRailItem(
          icon: Icons.forum_rounded,
          label: '게시판',
          path: RoutePaths.adminBoard,
          itemKey: keyFor(RoutePaths.adminBoard),
        ),
        AppSideRailItem(
          icon: Icons.card_giftcard_rounded,
          label: '마일리지',
          path: RoutePaths.adminMileage,
          itemKey: keyFor(RoutePaths.adminMileage),
        ),
      ],
    ),
    AppSideRailSection(
      id: 'system',
      title: '시스템',
      initiallyExpanded: expandAll,
      items: [
        AppSideRailItem(
          icon: Icons.analytics_outlined,
          label: 'LLMOps',
          path: RoutePaths.adminAiQuality,
          itemKey: keyFor(RoutePaths.adminAiQuality),
        ),
        const AppSideRailItem(
          icon: Icons.settings_outlined,
          label: '설정',
          path: RoutePaths.adminSettings,
        ),
      ],
    ),
  ];
}

bool _isAdminNavSelected(String location, String path) {
  if (path == RoutePaths.admin) return location == path;
  return location == path || location.startsWith(path);
}

/// 관리자 Shell — 와이드: 좌측 레일 / 좁음: Drawer
class AdminShellScreen extends ConsumerWidget {
  const AdminShellScreen({super.key, required this.child});

  final Widget child;

  static const _railBreakpoint = 900.0;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final location = GoRouterState.of(context).matchedLocation;
    final currentUser = ref.watch(currentUserProvider);
    final user = currentUser.value;
    final wide = MediaQuery.sizeOf(context).width >= _railBreakpoint;
    final tourActive =
        ref.watch(onboardingTourProvider)?.active == true &&
        ref.watch(onboardingTourProvider)?.tourId == 'admin';
    final railDark = ref.watch(sideRailDarkModeProvider);
    final railPalette = ref.watch(sideRailDarkPaletteProvider);

    final sections = _adminSections(expandAll: tourActive || !wide);

    void navigate(String path) {
      if (tourActive) return;
      context.go(path);
    }

    return AdminOnboardingHost(
      child: Scaffold(
        backgroundColor: AppColors.background,
        appBar: AppBar(
          backgroundColor: ShellChrome.appBarBackground(railDark, railPalette),
          foregroundColor: ShellChrome.appBarForeground(railDark),
          surfaceTintColor: Colors.transparent,
          elevation: 0,
          scrolledUnderElevation: 0,
          iconTheme: IconThemeData(
            color: ShellChrome.appBarForeground(railDark),
          ),
          flexibleSpace: wide
              ? ShellChrome.railCorner(
                  railDark: railDark,
                  palette: railPalette,
                )
              : null,
          title: AppShellHeader(homePath: RoutePaths.admin, overRail: wide),
          automaticallyImplyLeading: !wide,
          actions: [
            if (user != null)
              Center(
                child: Padding(
                  padding: EdgeInsets.only(right: AppSpace.s(12)),
                  child: ProfileNavChip(
                    user: user,
                    style: ProfileNavChipStyle.appBar,
                    onTap: tourActive
                        ? () {}
                        : () => context.go(RoutePaths.adminMyPage),
                  ),
                ),
              ),
          ],
        ),
        drawer: wide
            ? null
            : _AdminDrawer(
                user: user,
                currentLocation: location,
                tourActive: tourActive,
                sections: sections,
              ),
        body: Row(
          children: [
            if (wide)
              AppSideRail(
                key: ValueKey('admin_rail_tour_$tourActive'),
                sections: sections,
                location: location,
                isSelected: _isAdminNavSelected,
                onNavigate: navigate,
                onLogout: tourActive
                    ? null
                    : () => ref.read(authRepositoryProvider).signOut(),
                profile: user == null
                    ? null
                    : SideRailProfileTile(
                        label: user.displayName.isNotEmpty
                            ? user.displayName
                            : '마이페이지',
                        initial: user.displayName.isNotEmpty
                            ? user.displayName[0]
                            : 'A',
                        onTap: tourActive
                            ? () {}
                            : () => context.go(RoutePaths.adminMyPage),
                      ),
              ),
            Expanded(child: child),
          ],
        ),
      ),
    );
  }
}

class _AdminDrawer extends ConsumerStatefulWidget {
  const _AdminDrawer({
    required this.currentLocation,
    required this.tourActive,
    required this.sections,
    this.user,
  });

  final UserModel? user;
  final String currentLocation;
  final bool tourActive;
  final List<AppSideRailSection> sections;

  @override
  ConsumerState<_AdminDrawer> createState() => _AdminDrawerState();
}

class _AdminDrawerState extends ConsumerState<_AdminDrawer> {
  late Set<String> _expanded;

  @override
  void initState() {
    super.initState();
    _expanded = {
      for (final s in widget.sections)
        if (!s.isGroup ||
            s.initiallyExpanded ||
            s.items.any(
              (i) => _isAdminNavSelected(widget.currentLocation, i.path),
            ))
          s.id,
    };
  }

  @override
  void didUpdateWidget(covariant _AdminDrawer oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.tourActive && !oldWidget.tourActive) {
      setState(() {
        _expanded = {for (final s in widget.sections) s.id};
      });
    }
  }

  void _toggle(String id) {
    setState(() {
      if (_expanded.contains(id)) {
        _expanded = {..._expanded}..remove(id);
      } else {
        _expanded = {..._expanded, id};
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    return Drawer(
      child: Column(
        children: [
          SafeArea(
            bottom: false,
            child: Container(
              width: double.infinity,
              padding: EdgeInsets.fromLTRB(AppSpace.s(16), AppSpace.s(12), AppSpace.s(16), AppSpace.s(16)),
              decoration: BoxDecoration(
                color: AppColors.surface,
                border: Border(bottom: BorderSide(color: AppColors.border)),
              ),
              child: widget.user != null
                  ? Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        Align(
                          alignment: Alignment.centerLeft,
                          child: Container(
                            padding: EdgeInsets.symmetric(
                              horizontal: AppSpace.s(8),
                              vertical: AppSpace.s(3),
                            ),
                            decoration: BoxDecoration(
                              color: AppColors.primaryLight,
                              borderRadius: BorderRadius.circular(20),
                            ),
                            child: Text(
                              '관리자',
                              style: TextStyle(
                                fontSize: 11,
                                fontWeight: FontWeight.w700,
                                color: AppColors.primary,
                              ),
                            ),
                          ),
                        ),
                        SizedBox(height: AppSpace.s(10)),
                        ProfileNavChip(
                          user: widget.user!,
                          style: ProfileNavChipStyle.drawer,
                          onTap: () {
                            if (widget.tourActive) return;
                            Navigator.pop(context);
                            context.go(RoutePaths.adminMyPage);
                          },
                        ),
                      ],
                    )
                  : const SizedBox.shrink(),
            ),
          ),
          Expanded(
            child: ListView(
              padding: EdgeInsets.symmetric(horizontal: AppSpace.s(8), vertical: AppSpace.s(8)),
              children: [
                for (final section in widget.sections) ...[
                  if (section.isGroup)
                    ListTile(
                      dense: true,
                      visualDensity: VisualDensity.compact,
                      title: Text(
                        section.title!,
                        style: TextStyle(
                          fontSize: 12,
                          fontWeight: FontWeight.w700,
                          color:
                              section.items.any(
                                (i) => _isAdminNavSelected(
                                  widget.currentLocation,
                                  i.path,
                                ),
                              )
                              ? AppColors.primary
                              : AppColors.textSecondary,
                        ),
                      ),
                      trailing: Icon(
                        _expanded.contains(section.id)
                            ? Icons.keyboard_arrow_up_rounded
                            : Icons.keyboard_arrow_down_rounded,
                        size: 18,
                        color: AppColors.textSecondary,
                      ),
                      onTap: () => _toggle(section.id),
                    ),
                  if (!section.isGroup || _expanded.contains(section.id))
                    for (final item in section.items)
                      Builder(
                        builder: (context) {
                          final selected = _isAdminNavSelected(
                            widget.currentLocation,
                            item.path,
                          );
                          return KeyedSubtree(
                            key: item.itemKey,
                            child: ListTile(
                              leading: Icon(
                                item.icon,
                                color: selected
                                    ? AppColors.primary
                                    : AppColors.textSecondary,
                              ),
                              title: Text(
                                item.label,
                                style: TextStyle(
                                  fontWeight: selected
                                      ? FontWeight.w600
                                      : FontWeight.normal,
                                  color: selected
                                      ? AppColors.primary
                                      : AppColors.textPrimary,
                                ),
                              ),
                              selected: selected,
                              selectedTileColor: AppColors.primaryLight,
                              shape: RoundedRectangleBorder(
                                borderRadius: BorderRadius.circular(10),
                              ),
                              onTap: () {
                                if (widget.tourActive) return;
                                Navigator.pop(context);
                                context.go(item.path);
                              },
                            ),
                          );
                        },
                      ),
                ],
              ],
            ),
          ),
          const Divider(height: 1),
          ListTile(
            leading: Icon(Icons.logout, color: AppColors.error),
            title: Text(
              '로그아웃',
              style: TextStyle(color: AppColors.error),
            ),
            onTap: widget.tourActive
                ? null
                : () async {
                    Navigator.pop(context);
                    await ref.read(authRepositoryProvider).signOut();
                  },
          ),
        ],
      ),
    );
  }
}
