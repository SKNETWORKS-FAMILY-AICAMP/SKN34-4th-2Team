import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/routing/route_paths.dart';
import '../../../core/theme/app_colors.dart';
import '../../../shared/providers/side_rail_theme_provider.dart';
import '../../../shared/widgets/app_side_rail.dart';
import '../../../shared/widgets/profile_nav_chip.dart';
import '../../auth/providers/auth_providers.dart';
import '../../onboarding/domain/onboarding_target_registry.dart';
import '../../onboarding/instructor/instructor_onboarding_keys.dart';
import '../../onboarding/presentation/instructor_onboarding_host.dart';
import '../../onboarding/presentation/onboarding_controller.dart';
import '../../shell/widgets/app_shell_header.dart';
import '../../../core/theme/shell_chrome.dart';
import '../../../core/theme/app_space.dart';

class _NavItem {
  const _NavItem(this.icon, this.label, this.path, this.targetId);
  final IconData icon;
  final String label;
  final String path;
  final String targetId;
}

const _kInstructorNavItems = [
  _NavItem(
    Icons.fact_check_outlined,
    '자리 확인',
    RoutePaths.instructor,
    InstructorOnboardingTargets.navAttendance,
  ),
  _NavItem(
    Icons.description_rounded,
    '이력서관리',
    RoutePaths.instructorResumes,
    InstructorOnboardingTargets.navResumes,
  ),
  _NavItem(
    Icons.forum_rounded,
    '게시물관리',
    RoutePaths.instructorBoard,
    InstructorOnboardingTargets.navBoard,
  ),
  _NavItem(
    Icons.quiz_outlined,
    '성취도평가',
    RoutePaths.instructorAssessments,
    InstructorOnboardingTargets.navAssessments,
  ),
  _NavItem(
    Icons.table_chart_outlined,
    '커리큘럼',
    RoutePaths.instructorCurriculum,
    InstructorOnboardingTargets.navCurriculum,
  ),
  _NavItem(
    Icons.person_rounded,
    '마이페이지',
    RoutePaths.instructorMyPage,
    InstructorOnboardingTargets.navMyPage,
  ),
];

bool _isNavSelected(String location, String path) {
  if (path == RoutePaths.instructor) {
    return location == path;
  }
  return location == path || location.startsWith(path);
}

/// 강사 Shell — 와이드: 좌측 레일 / 좁음: 상단 탭
class InstructorShellScreen extends ConsumerWidget {
  const InstructorShellScreen({super.key, required this.child});

  final Widget child;

  static const _railBreakpoint = 900.0;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final location = GoRouterState.of(context).matchedLocation;
    final currentUser = ref.watch(currentUserProvider);
    final user = currentUser.value;
    final wide = MediaQuery.sizeOf(context).width >= _railBreakpoint;
    final tourActive = ref.watch(onboardingTourProvider)?.active == true;
    final railDark = ref.watch(sideRailDarkModeProvider);
    final railPalette = ref.watch(sideRailDarkPaletteProvider);

    final railItems = [
      for (final item in _kInstructorNavItems)
        AppSideRailItem(
          icon: item.icon,
          label: item.label,
          path: item.path,
          itemKey: wide ? OnboardingTargetRegistry.keyOf(item.targetId) : null,
        ),
      const AppSideRailItem(
        icon: Icons.settings_outlined,
        label: '설정',
        path: RoutePaths.instructorSettings,
      ),
    ];

    void navigate(String path) {
      if (tourActive) return;
      context.go(path);
    }

    return InstructorOnboardingHost(
      child: Scaffold(
        backgroundColor: AppColors.background,
        appBar: AppBar(
          automaticallyImplyLeading: false,
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
          title: AppShellHeader(homePath: RoutePaths.instructor, overRail: wide),
          actions: [
            if (user != null)
              Center(
                child: Padding(
                  padding: EdgeInsets.only(right: AppSpace.s(8)),
                  child: ProfileNavChip(
                    user: user,
                    style: ProfileNavChipStyle.appBar,
                    onTap: tourActive
                        ? () {}
                        : () => context.go(RoutePaths.instructorMyPage),
                  ),
                ),
              ),
            if (!wide)
              IconButton(
                tooltip: '로그아웃',
                onPressed: tourActive
                    ? null
                    : () => ref.read(authRepositoryProvider).signOut(),
                icon: const Icon(Icons.logout, size: 20),
              ),
            SizedBox(width: AppSpace.s(4)),
          ],
        ),
        body: Row(
          children: [
            if (wide)
              AppSideRail(
                items: railItems,
                location: location,
                isSelected: _isNavSelected,
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
                            : 'I',
                        onTap: tourActive
                            ? () {}
                            : () => context.go(RoutePaths.instructorMyPage),
                      ),
              ),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  if (!wide)
                    _InstructorTopNav(
                      currentLocation: location,
                      tourActive: tourActive,
                    ),
                  Expanded(child: child),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _InstructorTopNav extends StatelessWidget {
  const _InstructorTopNav({
    required this.currentLocation,
    required this.tourActive,
  });

  final String currentLocation;
  final bool tourActive;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: AppColors.surface,
      child: DecoratedBox(
        decoration: BoxDecoration(
          border: Border(bottom: BorderSide(color: AppColors.border)),
        ),
        child: LayoutBuilder(
          builder: (context, constraints) {
            final compact = constraints.maxWidth < 720;
            return SingleChildScrollView(
              scrollDirection: Axis.horizontal,
              padding: EdgeInsets.symmetric(
                horizontal: compact ? AppSpace.s(8) : AppSpace.s(16),
                vertical: AppSpace.s(8),
              ),
              child: Row(
                children: [
                  for (final item in _kInstructorNavItems) ...[
                    if (item != _kInstructorNavItems.first)
                      SizedBox(width: compact ? 4 : 6),
                    KeyedSubtree(
                      key: OnboardingTargetRegistry.keyOf(item.targetId),
                      child: _NavChip(
                        icon: item.icon,
                        label: item.label,
                        selected: _isNavSelected(currentLocation, item.path),
                        compact: compact,
                        onTap: tourActive ? () {} : () => context.go(item.path),
                      ),
                    ),
                  ],
                ],
              ),
            );
          },
        ),
      ),
    );
  }
}

class _NavChip extends StatelessWidget {
  const _NavChip({
    required this.icon,
    required this.label,
    required this.selected,
    required this.compact,
    required this.onTap,
  });

  final IconData icon;
  final String label;
  final bool selected;
  final bool compact;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final fg = selected ? Colors.white : AppColors.textPrimary;
    final bg = selected ? AppColors.primary : AppColors.surfaceVariant;

    return Material(
      color: bg,
      borderRadius: BorderRadius.circular(12),
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(12),
        child: Padding(
          padding: EdgeInsets.symmetric(
            horizontal: compact ? AppSpace.s(12) : AppSpace.s(14),
            vertical: compact ? AppSpace.s(8) : AppSpace.s(10),
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(icon, size: compact ? 16 : 18, color: fg),
              SizedBox(width: compact ? 6 : 8),
              Text(
                label,
                style: TextStyle(
                  fontSize: compact ? 13 : 14,
                  fontWeight: selected ? FontWeight.w700 : FontWeight.w600,
                  color: fg,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
